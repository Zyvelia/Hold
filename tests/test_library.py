import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QLabel

from pokemongb.cheats import describe, detect, gb_effect
from pokemongb.library import Library
from pokemongb.page import _HELP, PokemonGBPage
from pokemongb.shelf import GameSettings
from pokemongb.system import GameBoy


class CheatShapeTests(unittest.TestCase):
    def test_auto_names_the_shape(self):
        self.assertEqual(detect("ABC-DEF"), "genie")
        self.assertEqual(detect("ABCDEF"), "genie")
        self.assertEqual(detect("ABC-DEF-123"), "genie")
        self.assertEqual(detect("APZLGI"), "genie")
        self.assertEqual(detect("015500C0"), "gameshark")
        self.assertEqual(detect("123456-AB"), "codebreaker")
        self.assertEqual(detect("12345678 9ABC"), "codebreaker")
        self.assertEqual(detect("12345678 9ABCDEF0"), "actionreplay")
        self.assertEqual(detect("12345678+9ABCDEF0"), "actionreplay")
        self.assertEqual(detect("C000:55"), "address")
        self.assertEqual(describe("ABCDEF", "gameshark"), "GameShark")
        self.assertEqual(describe("015500C0", "auto"), "GameShark")

    def test_game_boy_patches(self):
        self.assertEqual(gb_effect("ABC-DEF"), ("rom", 0x0CDE, 0xAB, None))
        self.assertEqual(gb_effect("ABC-DEF-123")[3], 0x7E)
        self.assertEqual(gb_effect("015500C0"), ("ram", 0xC000, 0x55, None))
        self.assertEqual(gb_effect("123456-AB"), ("ram", 0x3456, 0xAB, None))
        self.assertEqual(gb_effect("C000:55"), ("ram", 0xC000, 0x55, None))
        self.assertIsNone(gb_effect("015500C0", "genie"))

    def test_gameshark_writes_ram_and_genie_patches_rom(self):
        gb = GameBoy()
        rom = bytearray(0x8000)
        rom[0x100] = 0x18
        rom[0x101] = 0xFE
        gb.load(bytes(rom))
        gb.set_cheats([("015500C0", "auto")])
        gb.run_frame()
        self.assertEqual(gb.mmu.read(0xC000), 0x55)
        gb.mmu.genie[0x150] = (0x42, None)
        self.assertEqual(gb.mmu.read(0x150), 0x42)
        gb.mmu.genie[0x150] = (0x42, 0x11)
        self.assertEqual(gb.mmu.read(0x150), 0x00)


class LibraryUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_opened_game_gets_a_cartridge_menu(self):
        with tempfile.TemporaryDirectory() as folder:
            os.environ["POKEMONGB_LIBRARY"] = folder
            try:
                page = PokemonGBPage()
                self.assertIs(page.stack.currentWidget(), page.shelf)
                self.assertEqual(page.shelf.findChild(QLabel, "LibraryEmpty").text(), "Open a ROM and it stays here.")
                rom = bytearray(0x8000)
                rom[0x100] = 0x18
                rom[0x101] = 0xFE
                rom[0x134:0x13F] = b"LIBRARYTEST"
                path = Path(folder) / "library.gb"
                path.write_bytes(rom)
                page.load_path(str(path))
                self.assertEqual(page.library.games[0].title, "LIBRARYTEST")
                self.assertEqual(page.library.games[0].system, "Game Boy")
                self.assertIs(page.stack.currentWidget(), page.play)
                page._toggle_library()
                self.assertEqual(page.library_btn.text(), "Back")
                self.assertEqual(len(page.shelf.cards), 1)
                self.assertEqual(page.shelf.cards[0].menu.text(), "···")
                played = []
                card = page.shelf.cards[0]
                card.play.connect(played.append)
                card.configure.disconnect()
                card.menu.click()
                self.assertEqual(played, [])

                dialog = GameSettings(page.library, page.library.games[0], page)
                dialog.code_edit.setText("015500C0")
                dialog._refresh_detected()
                self.assertEqual(dialog.detected.text(), "GameShark")
                dialog.kind_combo.setCurrentIndex(dialog.kind_combo.findData("genie"))
                dialog._refresh_detected()
                self.assertEqual(dialog.detected.text(), "Game Genie")
                dialog.kind_combo.setCurrentIndex(0)
                dialog.name_edit.setText("Lives")
                dialog._add()
                cheat = page.library.games[0].cheats[0]
                self.assertEqual(cheat.kind, "auto")
                self.assertEqual(cheat.name, "Lives")
                self.assertTrue(cheat.enabled)

                image = QImage(8, 8, QImage.Format.Format_RGB32)
                image.fill(0xFF3366AA)
                picture = Path(folder) / "cover.png"
                self.assertTrue(image.save(str(picture)))
                saved = page.library.set_image(page.library.games[0].id, picture)
                self.assertIsNotNone(saved)
                page.shelf.refresh()
                pixmap = page.shelf.cards[0].cover.pixmap()
                self.assertIsNotNone(pixmap)
                self.assertFalse(pixmap.isNull())
                self.assertEqual(page.help_btn.text(), "Help")
                self.assertIn("Arrows move", _HELP)
                self.assertIn("scph5501.bin", _HELP)
                self.assertIn("three dots", _HELP)
                blue = bytearray(rom)
                blue[0x134:0x144] = b"\x00" * 16
                blue[0x134:0x13D] = b"SECONDROM"
                second = Path(folder) / "second.gb"
                second.write_bytes(blue)
                page._add_roms([str(path), str(second)])
                titles = {game.title for game in page.library.games}
                self.assertEqual(titles, {"LIBRARYTEST", "SECONDROM"})
                self.assertIs(page.stack.currentWidget(), page.shelf)
                self.assertFalse(page.clock.isActive())
                page.shutdown()
            finally:
                os.environ.pop("POKEMONGB_LIBRARY", None)

    def test_library_roundtrip_keeps_cheats(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            library = Library(root)
            rom = root / "game.gb"
            rom.write_bytes(b"\x00" * 32)
            game = library.remember(rom, "Demo", "Game Boy", "gb")
            library.add_cheat(game.id, "015500C0", "Lives", "auto")
            again = Library(root)
            self.assertEqual(again.games[0].cheats[0].code, "015500C0")
            again.remember(rom, "Demo", "Game Boy", "gb")
            self.assertEqual(len(again.games), 1)
            self.assertEqual(again.games[0].cheats[0].name, "Lives")
