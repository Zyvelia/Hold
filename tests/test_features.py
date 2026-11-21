import ctypes
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLabel

from pokemongb.cheats import RamSearch
from pokemongb.gamepad import _scale
from pokemongb.library import Library
from pokemongb.libretro import exchange_gba_link, find_gba_io, rumble_motors
from pokemongb.page import PokemonGBPage, screens_side_by_side


def _rom() -> bytes:
    rom = bytearray(0x8000)
    rom[0x100] = 0x18
    rom[0x101] = 0xFE
    rom[0x134:0x13F] = b"FEATURE"
    return bytes(rom)


class FeatureTests(unittest.TestCase):
    def test_ram_search_narrows(self):
        search = RamSearch()
        search.start({1: 5, 2: 5, 3: 9})
        search.narrow("decreased", {1: 4, 2: 5, 3: 1})
        self.assertEqual(set(search.hits), {1, 3})
        search.narrow("equal", {1: 4, 3: 7}, 7)
        self.assertEqual(list(search.hits), [3])

    def test_rumble_and_gba_link_registers(self):
        self.assertEqual(rumble_motors(0, 0, 0, 1000), (1000, 0))
        self.assertEqual(rumble_motors(1000, 0, 1, 50), (1000, 50))
        self.assertEqual(find_gba_io([(0x04000000, 0, 0x400, 0x1000)]), 0x1000)
        self.assertEqual(find_gba_io([(0, 0, 0x1000, 0x1000)]), 0)
        buf = ctypes.create_string_buffer(0x200)
        base = ctypes.addressof(buf)
        ctypes.c_uint16.from_address(base + 0x120).value = 0x1234
        ctypes.c_uint16.from_address(base + 0x128).value = 0x0080
        self.assertEqual(exchange_gba_link(base, 0xABCD), 0x1234)
        self.assertEqual(ctypes.c_uint16.from_address(base + 0x122).value, 0xABCD)
        self.assertEqual(ctypes.c_uint16.from_address(base + 0x128).value & 0x80, 0)
        self.assertEqual(exchange_gba_link(base, 1), -1)

    def test_side_by_side_puts_the_bottom_half_on_the_right(self):
        top = bytes([1, 0, 0, 0, 2, 0, 0, 0])
        bottom = bytes([3, 0, 0, 0, 4, 0, 0, 0])
        frame, width, height = screens_side_by_side(top + bottom, 2, 2)
        self.assertEqual((width, height), (4, 1))
        self.assertEqual(frame, top + bottom)

    def test_speed_step_keyboard_and_library(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            os.environ["POKEMONGB_SETTINGS"] = str(Path(folder) / "settings.json")
            os.environ["POKEMONGB_LIBRARY"] = folder
            os.environ["POKEMONGB_CONTROLS"] = str(Path(folder) / "controls.json")
            try:
                page = PokemonGBPage()
                page.load_bytes(_rom())
                page.clock.stop()
                page._read_pads = lambda: (page._pad, page._pad)
                calls: list[int] = []
                original = page.gb.run_frame

                def wrapped() -> None:
                    calls.append(1)
                    original()

                page.gb.run_frame = wrapped
                page.speed_box.setCurrentText("0.5x")
                page.fast = False
                page._tick()
                page._tick()
                self.assertEqual(len(calls), 1)
                calls.clear()
                page.speed_box.setCurrentText("2x")
                page._tick()
                self.assertEqual(len(calls), 2)

                calls.clear()
                page.speed_box.setCurrentText("1x")
                page.clock.stop()
                page.keyPressEvent(
                    QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Period, Qt.KeyboardModifier.NoModifier)
                )
                page.clock.stop()
                page._tick()
                self.assertEqual(len(calls), 1)
                self.assertTrue(page.paused)
                page._tick()
                self.assertEqual(len(calls), 1)

                page.paused = False
                fake = type("Core", (), {})()
                fake.buttons = [False] * 16
                fake.buttons_p2 = [False] * 16
                fake.analog = [0, 0, 0, 0]
                fake.analog_p2 = [0, 0, 0, 0]
                fake.game_loaded = True
                page.extra["nes"] = fake
                page.kind = "nes"
                page.keyPressEvent(
                    QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_5, Qt.KeyboardModifier.KeypadModifier)
                )
                self.assertTrue(fake.buttons_p2[8])
                page.keyReleaseEvent(
                    QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_5, Qt.KeyboardModifier.KeypadModifier)
                )
                self.assertFalse(fake.buttons_p2[8])
                page.extra.pop("nes", None)
                page.kind = "gb"

                page.show()
                page._toggle_fullscreen()
                self.assertTrue(page.toolbar.isHidden())
                self.assertTrue(page.status.isHidden())
                page._toggle_fullscreen()
                self.assertFalse(page.toolbar.isHidden())
                self.assertFalse(page.status.isHidden())

                first = page.library.remember(Path(folder) / "red.gb", "Red", "Game Boy", "gb")
                page.library.remember(Path(folder) / "blue.gb", "Blue", "Game Boy", "gb")
                page.library.set_favorite(first.id, True)
                again = Library(Path(folder))
                self.assertTrue(again.get(first.id).favorite)
                page.shelf.refresh()
                page.shelf.search.setText("blue")
                self.assertEqual(len(page.shelf.cards), 1)
                self.assertEqual(page.shelf.cards[0].game_id, page.library.by_path(Path(folder) / "blue.gb").id)
                page.shelf.search.clear()
                page.shelf.favorites.setChecked(True)
                app.processEvents()
                self.assertEqual(len(page.shelf.cards), 1)
                self.assertEqual(page.shelf.cards[0].star.text(), "★")
                page.shelf.favorites.setChecked(False)
                page.shelf.search.clear()

                page.gb.mmu.wram[0][0] = 10
                page._game_id = first.id
                page._show_cheat_search()
                dialog = page._cheat_dialog
                dialog._start()
                page.gb.mmu.wram[0][0] = 3
                dialog.op.setCurrentText("Decreased")
                dialog._narrow()
                self.assertEqual(dialog.search.hits, {0xC000: 3})
                page._add_searched_cheat(0xC000, 3)
                dialog.close()
                game = page.library.get(first.id)
                self.assertTrue(any(cheat.code == "C000:03" for cheat in game.cheats))

                empty = page.shelf.findChild(QLabel, "LibraryEmpty")
                self.assertTrue(empty is None or empty.text() == "Open a ROM and it stays here.")
                page.shutdown()
            finally:
                os.environ.pop("POKEMONGB_SETTINGS", None)
                os.environ.pop("POKEMONGB_LIBRARY", None)
                os.environ.pop("POKEMONGB_CONTROLS", None)
        self.assertIsNotNone(app)

    def test_autofire_deadzone_and_play_time(self):
        self.assertEqual(_scale(100, 200), 0)
        self.assertNotEqual(_scale(1000, 200), 0)
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            os.environ["POKEMONGB_SETTINGS"] = str(Path(folder) / "settings.json")
            os.environ["POKEMONGB_LIBRARY"] = folder
            os.environ["POKEMONGB_CONTROLS"] = str(Path(folder) / "controls.json")
            try:
                page = PokemonGBPage()
                page.load_bytes(_rom())
                page.clock.stop()
                page._read_pads = lambda: (page._pad, page._pad)
                page.zone.setValue(40)
                from pokemongb import gamepad

                self.assertEqual(gamepad.deadzone_percent, 40)
                page.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_X, Qt.KeyboardModifier.NoModifier))
                game = page.library.remember(Path(folder) / "red.gb", "Red", "Game Boy", "gb")
                page._game_id = game.id
                page._play_bank = 90
                page._commit_play()
                page.shelf.refresh()
                card = next(item for item in page.shelf.cards if item.game_id == game.id)
                self.assertIn("1m", card.findChild(QLabel, "CartridgeSystem").text())
                again = Library(Path(folder))
                self.assertGreaterEqual(again.get(game.id).played, 90)
                page.shutdown()
            finally:
                os.environ.pop("POKEMONGB_SETTINGS", None)
                os.environ.pop("POKEMONGB_LIBRARY", None)
                os.environ.pop("POKEMONGB_CONTROLS", None)
        self.assertIsNotNone(app)


if __name__ == "__main__":
    unittest.main()
