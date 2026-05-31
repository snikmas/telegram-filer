from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import html
import logging
import os
from pathlib import Path
from secrets import token_urlsafe
import time
from typing import Literal
from typing import TypeVar

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import NetworkError, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .audit import AuditLog
from .config import AppConfig, RootConfig
from .filesystem import FileMetadata, FilesystemError, FilesystemResolver
from .messages import (
    format_delete_confirmation_message,
    format_directory_message,
    format_file_detail_message,
    format_help_message,
    format_preview_message,
    format_roots_message,
    format_search_results_message,
    format_size,
    format_unsupported_preview_message,
    is_previewable_file,
)

logger = logging.getLogger(__name__)

HandlerCallback = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]
_CallbackT = TypeVar("_CallbackT", bound=HandlerCallback)
CallbackKind = Literal[
    "preview",
    "download",
    "archive",
    "delete_request",
    "delete_confirm",
    "delete_cancel",
    "back",
    "directory",
    "search_result",
]

CALLBACK_PREFIX = "fs:"
DIRECTORY_PAGE_SIZE = 8
DELETE_CONFIRMATION_TTL = timedelta(minutes=5)
SEARCH_RESULT_LIMIT = 20
MIN_PREFIX_SELECTOR_LENGTH = 3
POLLING_NETWORK_RETRY_INITIAL_SECONDS = 5
POLLING_NETWORK_RETRY_MAX_SECONDS = 60


@dataclass(frozen=True)
class CallbackAction:
    kind: CallbackKind
    root_id: str
    relative_path: str = ""
    page: int = 0
    pending_token: str = ""


@dataclass(frozen=True)
class BrowserSession:
    root_id: str
    relative_path: str = ""
    page: int = 0
    last_entries: tuple[FileMetadata, ...] = ()


@dataclass(frozen=True)
class PendingDeleteAction:
    root_id: str
    relative_path: str
    expires_at: datetime


class CallbackActionStore:
    def __init__(self, max_entries: int = 4096) -> None:
        self._max_entries = max_entries
        self._actions: dict[str, CallbackAction] = {}

    def put(self, action: CallbackAction) -> str:
        while len(self._actions) >= self._max_entries:
            oldest_token = next(iter(self._actions))
            self._actions.pop(oldest_token, None)
        token = token_urlsafe(9)
        self._actions[token] = action
        return f"{CALLBACK_PREFIX}{token}"

    def get(self, callback_data: str | None) -> CallbackAction | None:
        if not callback_data or not callback_data.startswith(CALLBACK_PREFIX):
            return None
        return self._actions.get(callback_data.removeprefix(CALLBACK_PREFIX))


class PendingDeleteStore:
    def __init__(self, ttl: timedelta = DELETE_CONFIRMATION_TTL, max_entries: int = 1024) -> None:
        self._ttl = ttl
        self._max_entries = max_entries
        self._actions: dict[str, PendingDeleteAction] = {}

    def put(self, root_id: str, relative_path: str, *, now: datetime | None = None) -> tuple[str, PendingDeleteAction]:
        self._expire(now=now)
        while len(self._actions) >= self._max_entries:
            oldest_token = next(iter(self._actions))
            self._actions.pop(oldest_token, None)

        current_time = now or datetime.now(timezone.utc)
        action = PendingDeleteAction(root_id=root_id, relative_path=relative_path, expires_at=current_time + self._ttl)
        token = token_urlsafe(12)
        self._actions[token] = action
        return token, action

    def get(self, token: str, *, now: datetime | None = None) -> PendingDeleteAction | None:
        action = self._actions.get(token)
        if action is None:
            return None
        if action.expires_at <= (now or datetime.now(timezone.utc)):
            self._actions.pop(token, None)
            return None
        return action

    def pop(self, token: str, *, now: datetime | None = None) -> PendingDeleteAction | None:
        action = self.get(token, now=now)
        self._actions.pop(token, None)
        return action

    def cancel(self, token: str) -> None:
        self._actions.pop(token, None)

    def _expire(self, *, now: datetime | None = None) -> None:
        current_time = now or datetime.now(timezone.utc)
        expired_tokens = [token for token, action in self._actions.items() if action.expires_at <= current_time]
        for token in expired_tokens:
            self._actions.pop(token, None)


def build_application(config: AppConfig, audit_log: AuditLog | None = None) -> Application:
    if not config.telegram.bot_token:
        raise ValueError(f"Missing bot token environment variable: {config.telegram.bot_token_env}")

    builder = ApplicationBuilder().token(config.telegram.bot_token)
    proxy = _telegram_proxy_from_environment()
    if proxy:
        builder = builder.proxy(proxy).get_updates_proxy(proxy)

    application = builder.build()
    application.bot_data["app_config"] = config
    application.bot_data["filesystem_resolver"] = FilesystemResolver(config.filesystem.roots)
    application.bot_data["callback_action_store"] = CallbackActionStore()
    application.bot_data["pending_delete_store"] = PendingDeleteStore()
    application.bot_data["audit_log"] = audit_log or AuditLog(config.logging.audit_log_path)

    application.add_handler(CommandHandler("start", _guarded(config, start_command)))
    application.add_handler(CommandHandler("roots", _guarded(config, roots_command)))
    application.add_handler(CommandHandler("search", _guarded(config, search_command)))
    application.add_handler(CommandHandler("help", _guarded(config, help_command)))
    application.add_handler(CommandHandler("cancel", _guarded(config, cancel_command)))
    application.add_handler(CallbackQueryHandler(_guarded(config, filesystem_callback)))
    application.add_handler(MessageHandler(filters.COMMAND, _guarded(config, command_alias_message)))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _guarded(config, text_message)))
    application.add_error_handler(error_handler)
    return application


def _telegram_proxy_from_environment() -> str | None:
    for key in (
        "TG_FILER_PROXY",
        "HTTPS_PROXY",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
        "HTTP_PROXY",
        "http_proxy",
    ):
        value = os.environ.get(key)
        if value and value.strip():
            return value.strip()
    return None


def run_bot(config: AppConfig) -> None:
    audit_log = AuditLog(config.logging.audit_log_path)
    audit_log.validate()
    audit_log.record("startup", status="ok", root_count=len(config.filesystem.roots))
    attempt = 0
    while True:
        application = build_application(config, audit_log=audit_log)
        logger.info("Starting Telegram polling for %s", config.name)
        try:
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                bootstrap_retries=3,
                close_loop=False,
            )
            break
        except NetworkError as exc:
            attempt += 1
            delay_seconds = _polling_retry_delay(attempt)
            logger.warning(
                "Telegram polling network error; retrying in %s seconds",
                delay_seconds,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            audit_log.record(
                "polling_network_error",
                status="retrying",
                error_type=type(exc).__name__,
                retry_delay_seconds=delay_seconds,
                attempt=attempt,
            )
            time.sleep(delay_seconds)
    audit_log.record("shutdown", status="ok")


def _polling_retry_delay(attempt: int) -> int:
    return min(
        POLLING_NETWORK_RETRY_MAX_SECONDS,
        POLLING_NETWORK_RETRY_INITIAL_SECONDS * (2 ** max(0, attempt - 1)),
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = _config_from_context(context)
    _clear_browser_session(context)
    message = (
        f"<b>{html.escape(config.name)}</b>\n\n"
        "Private laptop file bot is ready.\n\n"
        f"{format_roots_message(config.filesystem.roots)}\n\n"
        "Use /help for controls."
    )
    await _reply_text(update, message)


async def roots_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = _config_from_context(context)
    _clear_browser_session(context)
    await _reply_text(update, format_roots_message(config.filesystem.roots))


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args).strip()
    await _run_search(update, context, query)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply_text(update, format_help_message())


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending_store = _pending_delete_store_from_context(context)
    for pending_token in _pending_delete_tokens_from_context(context):
        pending_store.cancel(pending_token)
    context.user_data.pop("pending_delete_tokens", None)
    context.user_data.pop("pending_delete_token", None)
    context.user_data.pop("browser_session", None)
    await _reply_text(update, "Pending action canceled. Session cleared. Type /roots to choose a root.")


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.text is None:
        return

    raw_text = message.text.strip()
    await _handle_text(update, context, raw_text)


async def command_alias_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.text is None:
        return

    raw_text = message.text.strip()
    if not raw_text.startswith("/"):
        return

    first_token, separator, rest = raw_text.partition(" ")
    command_name = first_token.split("@", 1)[0]
    await _handle_text(update, context, f"{command_name}{separator}{rest}".strip())


async def _handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_text: str) -> None:
    if not raw_text:
        return

    command = raw_text.casefold()
    session = _session_from_context(context)

    if command == "/help":
        await _reply_text(update, format_help_message())
        return
    if command == "/roots":
        await roots_command(update, context)
        return
    if command == "/search" or command.startswith("/search "):
        _, _, query = raw_text.partition(" ")
        await _run_search(update, context, query.strip())
        return
    if session is None:
        if _is_number_selector(command) or _is_slash_selector(raw_text):
            await _select_root(update, context, raw_text)
            return
        await _reply_text(update, "Commands start with /. Send /start or /roots.")
        return

    if _is_number_selector(command):
        await _open_entry(update, context, session, command)
    elif command == "/":
        await _show_directory(update, context, session.root_id, "")
    elif command == "/..":
        await _show_directory(update, context, session.root_id, _parent_relative_path(session.relative_path))
    elif _is_slash_selector(raw_text):
        await _change_directory(update, context, session, _slash_selector(raw_text))
    else:
        await _reply_text(update, "Commands start with /. Use a list number or /folder-name.")


async def filesystem_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    await query.answer()
    action = _callback_store_from_context(context).get(query.data)
    if action is None:
        await query.edit_message_text(
            "This button expired. Use /start to open a fresh browser.",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return

    if action.kind == "preview":
        await _show_preview(update, context, action.root_id, action.relative_path)
    elif action.kind == "download":
        await _send_file(update, context, action.root_id, action.relative_path)
    elif action.kind == "archive":
        await _send_archive(update, context, action.root_id, action.relative_path)
    elif action.kind == "delete_request":
        await _show_delete_confirmation(update, context, action.root_id, action.relative_path)
    elif action.kind == "delete_confirm":
        await _confirm_delete(update, context, action.pending_token)
    elif action.kind == "delete_cancel":
        await _cancel_delete(update, context, action.pending_token)
    elif action.kind == "back":
        await _show_directory(update, context, action.root_id, action.relative_path, action.page)
    elif action.kind == "directory":
        await _show_directory(update, context, action.root_id, action.relative_path, action.page)
    elif action.kind == "search_result":
        await _show_file_detail(update, context, action.root_id, action.relative_path)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.error:
        logger.error(
            "Unhandled Telegram bot error",
            exc_info=(type(context.error), context.error, context.error.__traceback__),
        )
    else:
        logger.error("Unhandled Telegram bot error")
    if isinstance(update, Update):
        try:
            _audit(
                context,
                update,
                "telegram_error",
                status="error",
                error_type=type(context.error).__name__ if context.error else None,
            )
        except RuntimeError:
            pass
        await _safe_reply(update, "Something went wrong. Try the command again.")


def is_authorized_user_id(user_id: int | None, owner_user_ids: tuple[int, ...]) -> bool:
    return user_id is not None and user_id in owner_user_ids


def _guarded(config: AppConfig, callback: _CallbackT) -> _CallbackT:
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not is_authorized_user_id(user.id if user else None, config.telegram.owner_user_ids):
            logger.warning("Rejected unauthorized Telegram user id=%s", user.id if user else None)
            try:
                _audit(context, update, "unauthorized_access", status="denied")
            except RuntimeError:
                AuditLog(config.logging.audit_log_path).record(
                    "unauthorized_access",
                    status="denied",
                    **_audit_context(update),
                )
            if update.callback_query is not None:
                await update.callback_query.answer("Access denied.", show_alert=True)
            await _safe_reply(update, "Access denied. This bot is private.")
            return

        try:
            await callback(update, context)
        except Exception as exc:
            logger.exception("Command handler failed")
            _audit(context, update, "handler_failure", status="error", error_type=type(exc).__name__)
            await _safe_reply(update, "Something went wrong. Try the command again.")

    return wrapped  # type: ignore[return-value]


def _config_from_context(context: ContextTypes.DEFAULT_TYPE) -> AppConfig:
    config = context.application.bot_data.get("app_config")
    if not isinstance(config, AppConfig):
        raise RuntimeError("App config is missing from Telegram application state")
    return config


def _resolver_from_context(context: ContextTypes.DEFAULT_TYPE) -> FilesystemResolver:
    resolver = context.application.bot_data.get("filesystem_resolver")
    if not isinstance(resolver, FilesystemResolver):
        raise RuntimeError("Filesystem resolver is missing from Telegram application state")
    return resolver


def _callback_store_from_context(context: ContextTypes.DEFAULT_TYPE) -> CallbackActionStore:
    store = context.application.bot_data.get("callback_action_store")
    if not isinstance(store, CallbackActionStore):
        raise RuntimeError("Callback action store is missing from Telegram application state")
    return store


def _pending_delete_store_from_context(context: ContextTypes.DEFAULT_TYPE) -> PendingDeleteStore:
    store = context.application.bot_data.get("pending_delete_store")
    if not isinstance(store, PendingDeleteStore):
        raise RuntimeError("Pending delete store is missing from Telegram application state")
    return store


def _audit_log_from_context(context: ContextTypes.DEFAULT_TYPE) -> AuditLog:
    audit_log = context.application.bot_data.get("audit_log")
    if not isinstance(audit_log, AuditLog):
        raise RuntimeError("Audit log is missing from Telegram application state")
    return audit_log


def _audit_context(update: Update) -> dict[str, object]:
    user = update.effective_user
    chat = update.effective_chat
    return {
        "user_id": user.id if user else None,
        "username": user.username if user else None,
        "chat_id": chat.id if chat else None,
    }


def _audit(context: ContextTypes.DEFAULT_TYPE, update: Update, action: str, **fields: object) -> None:
    _audit_log_from_context(context).record(action, **_audit_context(update), **fields)


def _session_from_context(context: ContextTypes.DEFAULT_TYPE) -> BrowserSession | None:
    session = context.user_data.get("browser_session")
    if isinstance(session, BrowserSession):
        return session
    return None


def _store_session(context: ContextTypes.DEFAULT_TYPE, session: BrowserSession) -> None:
    context.user_data["browser_session"] = session


def _clear_browser_session(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("browser_session", None)


def _pending_delete_tokens_from_context(context: ContextTypes.DEFAULT_TYPE) -> tuple[str, ...]:
    tokens = context.user_data.get("pending_delete_tokens")
    if isinstance(tokens, list):
        return tuple(token for token in tokens if isinstance(token, str))
    legacy_token = context.user_data.get("pending_delete_token")
    if isinstance(legacy_token, str):
        return (legacy_token,)
    return ()


def _remember_pending_delete_token(context: ContextTypes.DEFAULT_TYPE, pending_token: str) -> None:
    tokens = list(_pending_delete_tokens_from_context(context))
    if pending_token not in tokens:
        tokens.append(pending_token)
    context.user_data["pending_delete_tokens"] = tokens
    context.user_data["pending_delete_token"] = pending_token


def _forget_pending_delete_token(context: ContextTypes.DEFAULT_TYPE, pending_token: str) -> None:
    tokens = [token for token in _pending_delete_tokens_from_context(context) if token != pending_token]
    if tokens:
        context.user_data["pending_delete_tokens"] = tokens
        context.user_data["pending_delete_token"] = tokens[-1]
    else:
        context.user_data.pop("pending_delete_tokens", None)
        context.user_data.pop("pending_delete_token", None)


async def _select_root(update: Update, context: ContextTypes.DEFAULT_TYPE, root_selector: str) -> None:
    config = _config_from_context(context)
    root = _root_match(config.filesystem.roots, root_selector)
    if root is None:
        await _reply_text(
            update,
            f"Unknown root: <code>{html.escape(root_selector)}</code>\n\n{format_roots_message(config.filesystem.roots)}",
        )
        return
    await _show_directory(update, context, root.id, "")


async def _show_directory(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    root_id: str,
    relative_path: str,
    page: int = 0,
) -> None:
    config = _config_from_context(context)
    resolver = _resolver_from_context(context)

    try:
        listing = resolver.list_directory(
            root_id,
            relative_path,
            show_hidden_files=config.filesystem.show_hidden_files,
        )
    except FilesystemError as exc:
        _audit(
            context,
            update,
            "browse",
            status="error",
            root_id=root_id,
            relative_path=relative_path,
            error_type=type(exc).__name__,
        )
        await _edit_or_reply(update, f"Cannot open folder: {html.escape(str(exc))}")
        return

    visible_entries, normalized_page, total_pages = _visible_directory_entries(listing.entries, page)
    session = BrowserSession(
        root_id=root_id,
        relative_path=listing.directory.relative_path,
        page=normalized_page,
        last_entries=visible_entries,
    )
    _store_session(context, session)
    text = format_directory_message(
        listing.directory,
        listing.entries,
        visible_entries,
        normalized_page,
        total_pages,
    )
    await _edit_or_reply(
        update,
        text,
        reply_markup=_directory_keyboard(listing.directory, _callback_store_from_context(context), normalized_page, total_pages),
    )
    _audit(
        context,
        update,
        "browse",
        status="ok",
        root_id=listing.directory.root_id,
        relative_path=listing.directory.relative_path,
        page=normalized_page,
        entry_count=len(listing.entries),
    )


async def _change_directory(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: BrowserSession,
    target: str,
) -> None:
    if target in {"", "."}:
        await _show_directory(update, context, session.root_id, session.relative_path)
        return
    if target == "..":
        await _show_directory(update, context, session.root_id, _parent_relative_path(session.relative_path))
        return
    if target == "/":
        await _show_directory(update, context, session.root_id, "")
        return

    try:
        entry = _resolve_current_entry(context, session, target, dirs_only=True)
    except (FilesystemError, ValueError) as exc:
        await _reply_text(update, html.escape(str(exc)))
        return
    await _show_directory(update, context, entry.root_id, entry.relative_path)


async def _open_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: BrowserSession,
    target: str,
) -> None:
    try:
        entry = _resolve_current_entry(context, session, target)
    except (FilesystemError, ValueError) as exc:
        await _reply_text(update, html.escape(str(exc)))
        return

    if entry.kind == "directory":
        await _show_directory(update, context, entry.root_id, entry.relative_path)
        return
    await _show_file_detail(update, context, entry.root_id, entry.relative_path)


async def _show_file_detail(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    root_id: str,
    relative_path: str,
) -> None:
    resolver = _resolver_from_context(context)
    store = _callback_store_from_context(context)
    config = _config_from_context(context)

    try:
        metadata = resolver.metadata(root_id, relative_path)
    except FilesystemError as exc:
        _audit(
            context,
            update,
            "file_detail",
            status="error",
            root_id=root_id,
            relative_path=relative_path,
            error_type=type(exc).__name__,
        )
        await _edit_or_reply(update, f"Cannot open file details: {html.escape(str(exc))}")
        return

    await _edit_or_reply(
        update,
        format_file_detail_message(metadata, config.filesystem.max_upload_bytes),
        reply_markup=_file_detail_keyboard(metadata, store, config.filesystem.max_upload_bytes),
    )
    _audit(
        context,
        update,
        "file_detail",
        status="ok",
        root_id=metadata.root_id,
        relative_path=metadata.relative_path,
        kind=metadata.kind,
    )


async def _run_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
    if not query:
        await _reply_text(update, "Usage: <code>/search &lt;query&gt;</code>")
        return

    config = _config_from_context(context)
    resolver = _resolver_from_context(context)
    store = _callback_store_from_context(context)
    results = resolver.search_files(
        query,
        limit=SEARCH_RESULT_LIMIT,
        show_hidden_files=config.filesystem.show_hidden_files,
    )
    await _reply_text(
        update,
        format_search_results_message(query, results, SEARCH_RESULT_LIMIT),
        reply_markup=_search_results_keyboard(results, store),
    )
    _audit(context, update, "search", status="ok", query=query, result_count=len(results))


async def _show_delete_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    root_id: str,
    relative_path: str,
) -> None:
    resolver = _resolver_from_context(context)
    callback_store = _callback_store_from_context(context)
    pending_store = _pending_delete_store_from_context(context)

    try:
        metadata = resolver.metadata(root_id, relative_path)
    except FilesystemError as exc:
        _audit(
            context,
            update,
            "delete_request",
            status="error",
            root_id=root_id,
            relative_path=relative_path,
            error_type=type(exc).__name__,
        )
        await _edit_or_reply(update, f"Cannot prepare delete: {html.escape(str(exc))}")
        return

    if metadata.kind == "directory":
        _audit(
            context,
            update,
            "delete_request",
            status="blocked",
            root_id=metadata.root_id,
            relative_path=metadata.relative_path,
            reason="directory",
        )
        await _edit_or_reply(update, "Folder deletion is not available in this MVP.")
        return
    if metadata.kind != "file":
        _audit(
            context,
            update,
            "delete_request",
            status="blocked",
            root_id=metadata.root_id,
            relative_path=metadata.relative_path,
            reason=metadata.kind,
        )
        await _edit_or_reply(update, "Only regular files can be deleted.")
        return

    pending_token, pending_action = pending_store.put(metadata.root_id, metadata.relative_path)
    _remember_pending_delete_token(context, pending_token)
    await _edit_or_reply(
        update,
        format_delete_confirmation_message(metadata, pending_action.expires_at),
        reply_markup=_delete_confirmation_keyboard(metadata, pending_token, callback_store),
    )
    _audit(
        context,
        update,
        "delete_request",
        status="ok",
        root_id=metadata.root_id,
        relative_path=metadata.relative_path,
        expires_at=pending_action.expires_at.isoformat(),
    )


async def _confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, pending_token: str) -> None:
    if not pending_token:
        _audit(context, update, "delete_confirm", status="error", error_type="MissingPendingToken")
        await _edit_or_reply(update, "This delete confirmation is invalid. Open the file again.")
        return

    pending_store = _pending_delete_store_from_context(context)
    pending_action = pending_store.pop(pending_token)
    _forget_pending_delete_token(context, pending_token)

    if pending_action is None:
        _audit(context, update, "delete_confirm", status="expired")
        await _edit_or_reply(update, "This delete confirmation expired or was canceled. Open the file again.")
        return

    resolver = _resolver_from_context(context)
    try:
        metadata = resolver.move_file_to_trash(pending_action.root_id, pending_action.relative_path)
    except FilesystemError as exc:
        _audit(
            context,
            update,
            "delete_confirm",
            status="error",
            root_id=pending_action.root_id,
            relative_path=pending_action.relative_path,
            error_type=type(exc).__name__,
        )
        await _edit_or_reply(update, f"Could not move file to trash: {html.escape(str(exc))}")
        return

    store = _callback_store_from_context(context)
    await _edit_or_reply(
        update,
        "Moved to trash:\n" f"<code>{html.escape(metadata.root_id)}:/{html.escape(metadata.relative_path)}</code>",
        reply_markup=_directory_keyboard_after_file(metadata, store),
    )
    _audit(
        context,
        update,
        "delete_confirm",
        status="ok",
        root_id=metadata.root_id,
        relative_path=metadata.relative_path,
    )


async def _cancel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, pending_token: str) -> None:
    if pending_token:
        _pending_delete_store_from_context(context).cancel(pending_token)
        _forget_pending_delete_token(context, pending_token)
    await _edit_or_reply(update, "Delete canceled.")
    _audit(context, update, "delete_cancel", status="ok")


async def _show_preview(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    root_id: str,
    relative_path: str,
) -> None:
    config = _config_from_context(context)
    resolver = _resolver_from_context(context)
    store = _callback_store_from_context(context)

    try:
        metadata = resolver.metadata(root_id, relative_path)
        if not is_previewable_file(metadata.name):
            await _edit_or_reply(
                update,
                format_unsupported_preview_message(metadata),
                reply_markup=_file_detail_keyboard(metadata, store, config.filesystem.max_upload_bytes),
            )
            _audit(
                context,
                update,
                "preview",
                status="blocked",
                root_id=metadata.root_id,
                relative_path=metadata.relative_path,
                reason="unsupported_file_type",
            )
            return
        preview = resolver.read_text_preview(root_id, relative_path, config.filesystem.max_preview_bytes)
    except FilesystemError as exc:
        _audit(
            context,
            update,
            "preview",
            status="error",
            root_id=root_id,
            relative_path=relative_path,
            error_type=type(exc).__name__,
        )
        await _edit_or_reply(update, f"Cannot preview file: {html.escape(str(exc))}")
        return

    await _edit_or_reply(
        update,
        format_preview_message(metadata, preview),
        reply_markup=_file_detail_keyboard(metadata, store, config.filesystem.max_upload_bytes),
    )
    _audit(
        context,
        update,
        "preview",
        status="ok",
        root_id=metadata.root_id,
        relative_path=metadata.relative_path,
        bytes_read=preview.bytes_read,
        truncated=preview.truncated,
    )


async def _send_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    root_id: str,
    relative_path: str,
) -> None:
    config = _config_from_context(context)
    resolver = _resolver_from_context(context)
    store = _callback_store_from_context(context)

    try:
        metadata = resolver.metadata(root_id, relative_path)
        if metadata.kind != "file":
            _audit(
                context,
                update,
                "download",
                status="blocked",
                root_id=metadata.root_id,
                relative_path=metadata.relative_path,
                reason=metadata.kind,
            )
            await _edit_or_reply(update, "Only regular files can be downloaded.")
            return
        if metadata.size_bytes > config.filesystem.max_upload_bytes:
            await _edit_or_reply(
                update,
                format_file_detail_message(metadata, config.filesystem.max_upload_bytes),
                reply_markup=_file_detail_keyboard(metadata, store, config.filesystem.max_upload_bytes),
            )
            _audit(
                context,
                update,
                "download",
                status="blocked",
                root_id=metadata.root_id,
                relative_path=metadata.relative_path,
                reason="oversized",
                size_bytes=metadata.size_bytes,
            )
            return
        resolved = resolver.resolve(root_id, relative_path)
        message = update.effective_message
        if message is None:
            return
        with resolved.path.open("rb") as file:
            await message.reply_document(
                document=file,
                filename=resolved.path.name,
                caption=f"{metadata.name} ({format_size(metadata.size_bytes)})",
            )
        _audit(
            context,
            update,
            "download",
            status="ok",
            root_id=metadata.root_id,
            relative_path=metadata.relative_path,
            size_bytes=metadata.size_bytes,
        )
    except (FilesystemError, OSError) as exc:
        _audit(
            context,
            update,
            "download",
            status="error",
            root_id=root_id,
            relative_path=relative_path,
            error_type=type(exc).__name__,
        )
        await _safe_reply(update, f"Cannot send file: {html.escape(str(exc))}")
    except TelegramError as exc:
        logger.exception("Telegram upload failed")
        _audit(
            context,
            update,
            "download",
            status="error",
            root_id=root_id,
            relative_path=relative_path,
            error_type=type(exc).__name__,
        )
        await _safe_reply(update, "Telegram could not upload this file. Try compressing it or choose another file.")


async def _send_archive(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    root_id: str,
    relative_path: str,
) -> None:
    config = _config_from_context(context)
    resolver = _resolver_from_context(context)

    try:
        metadata = resolver.metadata(root_id, relative_path)
        if metadata.kind != "file":
            _audit(
                context,
                update,
                "archive",
                status="blocked",
                root_id=metadata.root_id,
                relative_path=metadata.relative_path,
                reason=metadata.kind,
            )
            await _edit_or_reply(update, "Only regular files can be archived.")
            return
        archive = resolver.create_zip_archive(root_id, relative_path)
        try:
            if archive.size_bytes > config.filesystem.max_upload_bytes:
                await _safe_reply(
                    update,
                    (
                        "Compressed archive is still too large to upload.\n\n"
                        f"Original: {format_size(metadata.size_bytes)}\n"
                        f"Compressed: {format_size(archive.size_bytes)}\n"
                        f"Limit: {format_size(config.filesystem.max_upload_bytes)}"
                    ),
                )
                _audit(
                    context,
                    update,
                    "archive",
                    status="blocked",
                    root_id=metadata.root_id,
                    relative_path=metadata.relative_path,
                    reason="oversized",
                    size_bytes=archive.size_bytes,
                    original_size_bytes=metadata.size_bytes,
                )
                return
            message = update.effective_message
            if message is None:
                return
            with archive.path.open("rb") as file:
                await message.reply_document(
                    document=file,
                    filename=archive.path.name,
                    caption=(
                        f"{metadata.name}.zip "
                        f"({format_size(archive.size_bytes)}, original {format_size(metadata.size_bytes)})"
                    ),
                )
            _audit(
                context,
                update,
                "archive",
                status="ok",
                root_id=metadata.root_id,
                relative_path=metadata.relative_path,
                size_bytes=archive.size_bytes,
                original_size_bytes=metadata.size_bytes,
            )
        finally:
            archive.cleanup_directory.cleanup()
    except (FilesystemError, OSError) as exc:
        _audit(
            context,
            update,
            "archive",
            status="error",
            root_id=root_id,
            relative_path=relative_path,
            error_type=type(exc).__name__,
        )
        await _safe_reply(update, f"Cannot create archive: {html.escape(str(exc))}")
    except TelegramError as exc:
        logger.exception("Telegram archive upload failed")
        _audit(
            context,
            update,
            "archive",
            status="error",
            root_id=root_id,
            relative_path=relative_path,
            error_type=type(exc).__name__,
        )
        await _safe_reply(update, "Telegram could not upload the archive. It may still be too large.")


async def _reply_text(
    update: Update,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=reply_markup)


async def _edit_or_reply(
    update: Update,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    query = update.callback_query
    if query is not None:
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
        return
    await _reply_text(update, text, reply_markup=reply_markup)


async def _safe_reply(update: Update, text: str) -> None:
    try:
        await _reply_text(update, text)
    except Exception:
        logger.exception("Failed to send Telegram error response")


def _file_detail_keyboard(
    metadata: FileMetadata,
    store: CallbackActionStore,
    max_upload_bytes: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if metadata.kind == "file":
        action_row: list[InlineKeyboardButton] = []
        if is_previewable_file(metadata.name):
            action_row.append(
                InlineKeyboardButton(
                    "Preview",
                    callback_data=store.put(
                        CallbackAction(kind="preview", root_id=metadata.root_id, relative_path=metadata.relative_path)
                    ),
                )
            )
        if metadata.size_bytes <= max_upload_bytes:
            action_row.append(
                InlineKeyboardButton(
                    "Download",
                    callback_data=store.put(
                        CallbackAction(kind="download", root_id=metadata.root_id, relative_path=metadata.relative_path)
                    ),
                )
            )
        else:
            action_row.append(
                InlineKeyboardButton(
                    "Compress",
                    callback_data=store.put(
                        CallbackAction(kind="archive", root_id=metadata.root_id, relative_path=metadata.relative_path)
                    ),
                )
            )
        if action_row:
            rows.append(action_row)
        rows.append(
            [
                InlineKeyboardButton(
                    "Delete",
                    callback_data=store.put(
                        CallbackAction(
                            kind="delete_request",
                            root_id=metadata.root_id,
                            relative_path=metadata.relative_path,
                        )
                    ),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                "Back",
                callback_data=store.put(
                    CallbackAction(
                        kind="back",
                        root_id=metadata.root_id,
                        relative_path=_parent_relative_path(metadata.relative_path),
                    )
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def _delete_confirmation_keyboard(
    metadata: FileMetadata,
    pending_token: str,
    store: CallbackActionStore,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Confirm delete",
                    callback_data=store.put(
                        CallbackAction(
                            kind="delete_confirm",
                            root_id=metadata.root_id,
                            relative_path=metadata.relative_path,
                            pending_token=pending_token,
                        )
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "Cancel",
                    callback_data=store.put(
                        CallbackAction(
                            kind="delete_cancel",
                            root_id=metadata.root_id,
                            relative_path=metadata.relative_path,
                            pending_token=pending_token,
                        )
                    ),
                )
            ],
        ]
    )


def _search_results_keyboard(
    results: tuple[FileMetadata, ...],
    store: CallbackActionStore,
) -> InlineKeyboardMarkup | None:
    if not results:
        return None

    rows: list[list[InlineKeyboardButton]] = []
    for index, metadata in enumerate(results, start=1):
        if (index - 1) % 5 == 0:
            rows.append([])
        rows[-1].append(
            InlineKeyboardButton(
                str(index),
                callback_data=store.put(
                    CallbackAction(
                        kind="search_result",
                        root_id=metadata.root_id,
                        relative_path=metadata.relative_path,
                    )
                ),
            )
        )
    return InlineKeyboardMarkup(rows)


def _directory_keyboard_after_file(metadata: FileMetadata, store: CallbackActionStore) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Back",
                    callback_data=store.put(
                        CallbackAction(
                            kind="directory",
                            root_id=metadata.root_id,
                            relative_path=_parent_relative_path(metadata.relative_path),
                        )
                    ),
                )
            ]
        ]
    )


def _root_match(roots: tuple[RootConfig, ...], selector: str) -> RootConfig | None:
    normalized = _slash_selector(selector).casefold() if _is_slash_selector(selector) else selector.strip().casefold()
    if not normalized:
        return None
    index = _selector_index(normalized)
    if index is not None:
        if 0 <= index < len(roots):
            return roots[index]

    exact_matches = [
        root
        for root in roots
        if root.id.casefold() == normalized or root.display_name.casefold() == normalized
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]

    if len(normalized) < MIN_PREFIX_SELECTOR_LENGTH:
        return None

    prefix_matches = [
        root
        for root in roots
        if root.id.casefold().startswith(normalized) or root.display_name.casefold().startswith(normalized)
    ]
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    return None


def _visible_directory_entries(
    entries: tuple[FileMetadata, ...],
    page: int,
) -> tuple[tuple[FileMetadata, ...], int, int]:
    total_pages = max(1, (len(entries) + DIRECTORY_PAGE_SIZE - 1) // DIRECTORY_PAGE_SIZE)
    normalized_page = max(0, min(page, total_pages - 1))
    start = normalized_page * DIRECTORY_PAGE_SIZE
    return entries[start : start + DIRECTORY_PAGE_SIZE], normalized_page, total_pages


def _resolve_current_entry(
    context: ContextTypes.DEFAULT_TYPE,
    session: BrowserSession,
    target: str,
    *,
    dirs_only: bool = False,
    files_only: bool = False,
) -> FileMetadata:
    target = target.strip()
    if not target:
        raise ValueError("Missing item selector.")

    visible_match = _entry_from_visible_list(session.last_entries, target)
    if visible_match is not None:
        _validate_entry_kind(visible_match, dirs_only=dirs_only, files_only=files_only)
        return visible_match

    config = _config_from_context(context)
    resolver = _resolver_from_context(context)
    listing = resolver.list_directory(
        session.root_id,
        session.relative_path,
        show_hidden_files=config.filesystem.show_hidden_files,
    )
    index = _selector_index(target)
    if index is not None:
        display_index = index + 1
        if 0 <= index < len(listing.entries):
            raise ValueError(f"Item {display_index} is not on this page. Use Next or Prev to change pages.")
        raise ValueError(f"No item {display_index} on this page.")

    matches = _named_entry_matches(listing.entries, target, dirs_only=dirs_only, files_only=files_only)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"No matching item: {target}")
    names = ", ".join(match.name for match in matches[:5])
    raise ValueError(f"Ambiguous item: {target}. Matches: {names}")


def _entry_from_visible_list(entries: tuple[FileMetadata, ...], target: str) -> FileMetadata | None:
    index = _selector_index(target)
    if index is None:
        return None
    if 0 <= index < len(entries):
        return entries[index]
    return None


def _named_entry_matches(
    entries: tuple[FileMetadata, ...],
    target: str,
    *,
    dirs_only: bool,
    files_only: bool,
) -> tuple[FileMetadata, ...]:
    normalized = target.casefold().removesuffix("/")
    candidates = [
        entry
        for entry in entries
        if not ((dirs_only and entry.kind != "directory") or (files_only and entry.kind != "file"))
    ]
    exact = [entry for entry in candidates if entry.name.casefold() == normalized]
    if exact:
        return tuple(exact)
    if len(normalized) < MIN_PREFIX_SELECTOR_LENGTH:
        return ()
    return tuple(entry for entry in candidates if entry.name.casefold().startswith(normalized))


def _validate_entry_kind(entry: FileMetadata, *, dirs_only: bool, files_only: bool) -> None:
    if dirs_only and entry.kind != "directory":
        raise ValueError(f"Not a folder: {entry.name}")
    if files_only and entry.kind != "file":
        raise ValueError(f"Not a file: {entry.name}")


def _is_slash_selector(text: str) -> bool:
    return text.startswith("/") and not text.startswith("//")


def _is_number_selector(text: str) -> bool:
    return _selector_index(text) is not None


def _selector_index(text: str) -> int | None:
    normalized = text.strip().removesuffix(")").strip()
    if not normalized.isdecimal():
        return None
    return int(normalized) - 1


def _slash_selector(text: str) -> str:
    return text.removeprefix("/").strip().removesuffix("/")


def _directory_keyboard(
    directory: FileMetadata,
    store: CallbackActionStore,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    page_row: list[InlineKeyboardButton] = []
    if page > 0:
        page_row.append(
            InlineKeyboardButton(
                "Prev",
                callback_data=store.put(
                    CallbackAction(
                        kind="directory",
                        root_id=directory.root_id,
                        relative_path=directory.relative_path,
                        page=page - 1,
                    )
                ),
            )
        )
    if page + 1 < total_pages:
        page_row.append(
            InlineKeyboardButton(
                "Next",
                callback_data=store.put(
                    CallbackAction(
                        kind="directory",
                        root_id=directory.root_id,
                        relative_path=directory.relative_path,
                        page=page + 1,
                    )
                ),
            )
        )
    if page_row:
        rows.append(page_row)

    if directory.relative_path:
        rows.append(
            [
                InlineKeyboardButton(
                    "Up",
                    callback_data=store.put(
                        CallbackAction(
                            kind="directory",
                            root_id=directory.root_id,
                            relative_path=_parent_relative_path(directory.relative_path),
                        )
                    ),
                ),
                InlineKeyboardButton(
                    "Root",
                    callback_data=store.put(CallbackAction(kind="directory", root_id=directory.root_id)),
                ),
            ]
        )

    if not rows:
        return None
    return InlineKeyboardMarkup(rows)


def _parent_relative_path(relative_path: str) -> str:
    if not relative_path:
        return ""
    parent = Path(relative_path).parent
    if str(parent) == ".":
        return ""
    return parent.as_posix()
