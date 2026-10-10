"""Coloured console output for the evaluation runners, and a plain-text log of
everything they print.

Colour is used when the output is a terminal (or FORCE_COLOR is set) and
NO_COLOR is not. The log file never contains colour codes.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_CODES = {"red": 31, "green": 32, "yellow": 33, "blue": 34, "magenta": 35, "cyan": 36, "grey": 90}

if sys.platform == "win32":
    os.system("")  # switches the Windows console to ANSI escape processing


def _coloured() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return bool(os.environ.get("FORCE_COLOR")) or sys.stdout.isatty()


def paint(text: object, colour: str, bold: bool = False) -> str:
    if not _coloured():
        return str(text)
    return f"\x1b[{'1;' if bold else ''}{_CODES[colour]}m{text}\x1b[0m"


def green(text: object) -> str:
    return paint(text, "green")


def red(text: object) -> str:
    return paint(text, "red")


def yellow(text: object) -> str:
    return paint(text, "yellow")


def cyan(text: object) -> str:
    return paint(text, "cyan")


def grey(text: object) -> str:
    return paint(text, "grey")


def bold(text: object) -> str:
    return f"\x1b[1m{text}\x1b[0m" if _coloured() else str(text)


def verdict(passed: bool, yes: str = "PASS", no: str = "FAIL") -> str:
    return paint(yes, "green", bold=True) if passed else paint(no, "red", bold=True)


def rate(percent: object, good: float = 90.0, fair: float = 75.0) -> str:
    """A percentage coloured by how good it is."""
    if percent == "" or percent is None:
        return "-"
    colour = "green" if float(percent) >= good else "yellow" if float(percent) >= fair else "red"
    return paint(f"{float(percent):.1f}%", colour)


def money(usd: object) -> str:
    return "-" if usd in ("", None) else f"${float(usd):.6f}"


def heading(text: str, width: int = 110) -> None:
    print("\n" + cyan("=" * width))
    print(bold(text))
    print(cyan("=" * width))


class _Tee:
    def __init__(self, stream, log) -> None:
        self._stream, self._log = stream, log

    def write(self, text: str) -> int:
        self._log.write(_ANSI.sub("", text))
        return self._stream.write(text)

    def flush(self) -> None:
        self._stream.flush()
        self._log.flush()

    def isatty(self) -> bool:
        return self._stream.isatty()

    def __getattr__(self, name: str):
        return getattr(self._stream, name)


def log_to(path: Path) -> None:
    """From here on, everything printed also goes to `path`, without colour."""
    log = open(path, "a", encoding="utf-8")
    sys.stdout = _Tee(sys.stdout, log)
    sys.stderr = _Tee(sys.stderr, log)
    print(grey(f"log: {path}"))
