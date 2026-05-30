from __future__ import annotations

from collections.abc import Awaitable, Callable
import html
import logging
from typing import TypeVar

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from .config import AppConfig, RootConfig
from .filesystem import FilesystemResolver

logger = logging.getLogger(__name__)

HandlerCallback = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]
_CallbackT = TypeVar("_CallbackT", bound=HandlerCallback)


def build_application(config: AppConfig) -> Application:
    if not config.telegram.bot_token:
        raise ValueError(f"Missing bot token environment variable: {config.telegram.bot_token_env}")

    application = ApplicationBuilder().token(config.telegram.bot_token).build()
    application.bot_data["app_config"] = config
    application.bot_data["filesystem_resolver"] = FilesystemResolver(config.filesystem.roots)

    application.add_handler(CommandHandler("start", _guarded(config, start_command)))
    application.add_handler(CommandHandler("roots", _guarded(config, roots_command)))
    application.add_handler(CommandHandler("help", _guarded(config, help_command)))
    application.add_handler(CommandHandler("cancel", _guarded(config, cancel_command)))
    application.add_error_handler(error_handler)
    return application


def run_bot(config: AppConfig) -> None:
    application = build_application(config)
    logger.info("Starting Telegram polling for %s", config.name)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = _config_from_context(context)
    message = (
        f"<b>{html.escape(config.name)}</b>\n\n"
        "Private laptop file bot is ready.\n\n"
        f"{format_roots_message(config.filesystem.roots)}\n\n"
        "Use /roots to show these folders again, /help for commands, or /cancel to clear pending actions."
    )
    await _reply_text(update, message)


async def roots_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = _config_from_context(context)
    await _reply_text(update, format_roots_message(config.filesystem.roots))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply_text(update, format_help_message())


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply_text(update, "No pending action to cancel.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.error:
        logger.error(
            "Unhandled Telegram bot error",
            exc_info=(type(context.error), context.error, context.error.__traceback__),
        )
    else:
        logger.error("Unhandled Telegram bot error")
    if isinstance(update, Update):
        await _safe_reply(update, "Something went wrong. Try the command again.")


def format_roots_message(roots: tuple[RootConfig, ...]) -> str:
    lines = ["<b>Configured root folders</b>"]
    for root in roots:
        display_name = html.escape(root.display_name)
        path = html.escape(str(root.path))
        lines.append(f"- <b>{display_name}</b>: <code>{path}</code>")
    return "\n".join(lines)


def format_help_message() -> str:
    return "\n".join(
        [
            "<b>Commands</b>",
            "/start - Show bot status and configured root folders.",
            "/roots - Show configured root folders.",
            "/help - Show available commands.",
            "/cancel - Cancel the current pending action.",
        ]
    )


def is_authorized_user_id(user_id: int | None, owner_user_ids: tuple[int, ...]) -> bool:
    return user_id is not None and user_id in owner_user_ids


def _guarded(config: AppConfig, callback: _CallbackT) -> _CallbackT:
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not is_authorized_user_id(user.id if user else None, config.telegram.owner_user_ids):
            logger.warning("Rejected unauthorized Telegram user id=%s", user.id if user else None)
            await _safe_reply(update, "Access denied. This bot is private.")
            return

        try:
            await callback(update, context)
        except Exception:
            logger.exception("Command handler failed")
            await _safe_reply(update, "Something went wrong. Try the command again.")

    return wrapped  # type: ignore[return-value]


def _config_from_context(context: ContextTypes.DEFAULT_TYPE) -> AppConfig:
    config = context.application.bot_data.get("app_config")
    if not isinstance(config, AppConfig):
        raise RuntimeError("App config is missing from Telegram application state")
    return config


async def _reply_text(update: Update, text: str) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


async def _safe_reply(update: Update, text: str) -> None:
    try:
        await _reply_text(update, text)
    except Exception:
        logger.exception("Failed to send Telegram error response")
