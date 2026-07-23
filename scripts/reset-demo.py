#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE = PROJECT_ROOT / "demo-fixtures"
TARGET = PROJECT_ROOT / "demo-data"


def reset_demo() -> Path:
    source = SOURCE.resolve(strict=True)
    target = TARGET.resolve(strict=False)
    if target.parent != PROJECT_ROOT.resolve() or target.name != "demo-data":
        raise RuntimeError(f"Refusing to reset unexpected demo target: {target}")

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return target


if __name__ == "__main__":
    restored = reset_demo()
    print(f"Safe demo files restored at {restored}")
