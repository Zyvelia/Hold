"""Standalone window so the emulator can be tested before it becomes a module."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow

from pokemongb.page import PokemonGBPage


def rom_from_args(argv: list[str]) -> str | None:
    """A ROM path typed after the program name opens when the window starts."""
    if len(argv) > 1 and Path(argv[1]).is_file():
        return argv[1]
    return None


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Emulator")
    window = QMainWindow()
    window.setWindowTitle("Emulator")
    page = PokemonGBPage()
    window.setCentralWidget(page)
    window.resize(920, 1220)
    page.apply_window(window)
    rom = rom_from_args(sys.argv)
    if rom:
        page.load_path(rom)
    window.show()
    page.setFocus()
    app.aboutToQuit.connect(page.shutdown)
    sys.exit(app.exec())
