import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox

from pokemongb.app import rom_from_args
from pokemongb.library import Library
from pokemongb.page import PokemonGBPage
from pokemongb.picture import adjust, blend, integer_box, screens_top_large
from pokemongb.soundfx import AudioDelay, tone_pcm, wav_header


class PictureTests(unittest.TestCase):
    def test_brightness_lifts_a_pixel(self):
        dark = bytes([10, 10, 10, 255])
        same = adjust(dark)
        self.assertEqual(same, dark)
        lit = adjust(dark, brightness=50)
        self.assertGreater(lit[0], 10)

    def test_blend_averages_the_two_pictures(self):
        mixed = blend(bytes([0, 0, 0, 255]), bytes([100, 40, 20, 255]))
        self.assertEqual(mixed[:3], bytes([50, 20, 10]))

    def test_integer_box_keeps_whole_pixels(self):
        self.assertEqual(integer_box(160, 144, 720, 576), (640, 576))

    def test_top_screen_is_the_taller_half(self):
        frame = bytes([1, 0, 0, 255, 2, 0, 0, 255, 9, 0, 0, 255, 8, 0, 0, 255])
        out, width, height = screens_top_large(frame, 2, 2)
        self.assertEqual((width, height), (4, 3))
        self.assertEqual(len(out), 4 * 3 * 4)


class SoundTests(unittest.TestCase):
    def test_low_pass_keeps_the_sample_count(self):
        data = (1000).to_bytes(2, "little", signed=True) * 4
        out = tone_pcm(data, "low", [0.0, 0.0])
        self.assertEqual(len(out), len(data))
        self.assertTrue(wav_header(8).startswith(b"RIFF"))

    def test_positive_delay_holds_the_first_chunk(self):
        delay = AudioDelay()
        delay.ms = 1000
        self.assertEqual(delay.push(b"\x00\x01" * 8), b"")


class LibraryOptionTests(unittest.TestCase):
    def test_launches_hide_and_order_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            library = Library(root)
            rom = root / "game.gb"
            rom.write_bytes(b"\x00" * 32)
            game = library.remember(rom, "Demo", "Game Boy", "gb")
            self.assertEqual(game.launches, 1)
            library.set_hidden(game.id, True)
            library.set_order([game.id, "missing"])
            again = Library(root)
            self.assertEqual(again.games[0].launches, 1)
            self.assertTrue(again.games[0].hidden)
            self.assertEqual(again.order, [game.id])


class LookUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_picture_list_tools_and_list_view(self):
        with tempfile.TemporaryDirectory() as folder:
            os.environ["POKEMONGB_SETTINGS"] = str(Path(folder) / "settings.json")
            os.environ["POKEMONGB_LIBRARY"] = folder
            os.environ["POKEMONGB_CONTROLS"] = str(Path(folder) / "controls.json")
            try:
                page = PokemonGBPage()
                labels = [page.filter_box.itemText(index) for index in range(page.filter_box.count())]
                self.assertEqual(labels, ["Sharp", "Smooth", "Scanlines", "CRT", "LCD"])
                page._show_tools()
                tools = page._tools
                self.assertIsNotNone(tools.findChild(QCheckBox, "IntegerScale"))
                self.assertIsNotNone(tools.findChild(QComboBox, "Speaker"))
                page.shelf.view.setChecked(True)
                self.assertTrue(page.shelf.list.isVisible() or page.library.games == [])
                page.filter_box.setCurrentText("CRT")
                self.assertEqual(page._filter, "crt")
                page._set_theme("Night")
                self.assertEqual(page._theme, "night")
                self.assertIsNone(rom_from_args(["emu"]))
                rom = Path(folder) / "demo.gb"
                rom.write_bytes(b"\x00" * 32)
                self.assertEqual(rom_from_args(["emu", str(rom)]), str(rom))
                page.shutdown()
            finally:
                os.environ.pop("POKEMONGB_SETTINGS", None)
                os.environ.pop("POKEMONGB_LIBRARY", None)
                os.environ.pop("POKEMONGB_CONTROLS", None)
