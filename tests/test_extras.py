import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

from pokemongb.controls import Controls
from pokemongb.gamepad import EMPTY, interpret, map_pad, raw_from
from pokemongb.page import PokemonGBPage, SaveStatesMenu


def _rom() -> bytes:
    rom = bytearray(0x8000)
    rom[0x100] = 0x18
    rom[0x101] = 0xFE
    rom[0x134:0x13F] = b"EXTRAS"
    return bytes(rom)


class _Core:
    def __init__(self):
        self.game_loaded = True
        self.buttons = [False] * 16
        self.buttons_p2 = [False] * 16
        self.analog = [0, 0, 0, 0]
        self.analog_p2 = [0, 0, 0, 0]


class ExtraTests(unittest.TestCase):
    def test_pad_button_can_be_rebound(self):
        with tempfile.TemporaryDirectory() as folder:
            controls = Controls(Path(folder) / "controls.json")
            self.assertEqual(controls.pad_label("b"), "Bottom")
            controls.assign_pad("a", "south")
            self.assertEqual(controls.pad_label("a"), "Bottom")
            self.assertEqual(controls.pad_label("b"), "No pad")
            raw = raw_from(0x1000, 0, 0, 0, 0, 0, 0)
            pad = map_pad(raw, controls.pad)
            self.assertIn("a", pad.actions)
            self.assertNotIn("b", pad.actions)

    def test_second_controller_is_player_two(self):
        app = QApplication.instance() or QApplication([])
        page = PokemonGBPage()
        page.load_bytes(_rom())
        page.clock.stop()
        page.kind = "nes"
        page.extra["nes"] = _Core()
        first = interpret(0x1000, 0, 0, 0, 0, 0, 0)
        second = interpret(0x2000, 0, 0, 0, 0, 0, 0)
        page._read_pads = lambda: (first, second)
        page._poll_gamepad()
        core = page.extra["nes"]
        self.assertTrue(core.buttons[0])
        self.assertFalse(core.buttons[8])
        self.assertTrue(core.buttons_p2[8])
        self.assertFalse(core.buttons_p2[0])
        self.assertEqual(page.gb.joypad.buttons & 0x02, 0)
        page.extra.pop("nes")
        page.kind = "gb"
        page.shutdown()
        self.assertIsNotNone(app)

    def test_volume_screenshot_fullscreen_and_slot_picture(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            os.environ["POKEMONGB_SETTINGS"] = str(Path(folder) / "settings.json")
            try:
                page = PokemonGBPage()
                page.load_bytes(_rom())
                page.clock.stop()
                page._read_pads = lambda: (EMPTY, EMPTY)
                self.assertEqual(page.volume.value(), 35)
                page.volume.setValue(10)
                self.assertEqual(page._volume, 10)
                self.assertIn('"volume": 10', Path(os.environ["POKEMONGB_SETTINGS"]).read_text(encoding="utf-8"))
                image = QImage(16, 16, QImage.Format.Format_RGB32)
                image.fill(Qt.GlobalColor.white)
                page.screen.setPixmap(QPixmap.fromImage(image))
                page._screenshot()
                shots = list((_saves(page) / "screenshots").glob("*.png"))
                self.assertEqual(len(shots), 1)
                for shot in shots:
                    shot.unlink()
                page._toggle_fullscreen()
                self.assertTrue(page._fullscreen)
                self.assertEqual(page.full_btn.text(), "Window")
                page._toggle_fullscreen()
                self.assertFalse(page._fullscreen)
                page.save_state()
                self.assertTrue(page._slot_picture(1).is_file())
                menu = SaveStatesMenu(page)
                self.assertFalse(menu._shots[1].pixmap().isNull())
                page._state_path().unlink(missing_ok=True)
                page._slot_picture(1).unlink(missing_ok=True)
                page.shutdown()
            finally:
                os.environ.pop("POKEMONGB_SETTINGS", None)
        self.assertIsNotNone(app)

    def test_each_game_keeps_its_own_keys(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            os.environ["POKEMONGB_CONTROLS"] = str(Path(folder) / "controls.json")
            try:
                page = PokemonGBPage()
                page._default_controls.assign("a", int(Qt.Key.Key_K))
                page._game_id = "gameone"
                page._use_game_controls()
                self.assertEqual(page.controls.keys("a"), [int(Qt.Key.Key_K)])
                page.controls.assign("b", int(Qt.Key.Key_M))
                self.assertEqual(page._default_controls.keys("b"), [int(Qt.Key.Key_Z)])
                page._game_id = ""
                page._use_game_controls()
                self.assertIs(page.controls, page._default_controls)
                page.shutdown()
            finally:
                os.environ.pop("POKEMONGB_CONTROLS", None)
        self.assertIsNotNone(app)


def _saves(page: PokemonGBPage):
    from pokemongb.page import _saves_dir

    return _saves_dir()


if __name__ == "__main__":
    unittest.main()
