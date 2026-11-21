import array
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox

from pokemongb.library import Library
from pokemongb.local_link import LocalLinkDialog, battery_paths
from pokemongb.page import PokemonGBPage, _p2_action
from pokemongb.picture import gb_picture
from pokemongb.shelf import GameSettings
from pokemongb.system import GameBoy, LocalLink


def program(title: str, control: int, first_byte: int, color: bool = False) -> bytes:
    rom = bytearray(0x8000)
    rom[0x100:0x103] = bytes.fromhex("c3 50 01")
    rom[0x134:0x134 + len(title)] = title.encode()
    rom[0x143] = 0x80 if color else 0
    rom[0x147:0x14A] = bytes((3, 0, 2))
    code = bytearray.fromhex("21 00 c0 06 10 16")
    code.append(first_byte)
    loop = len(code)
    code.extend(bytes((0x7A, 0xE0, 0x01, 0x3E, control, 0xE0, 0x02)))
    code.extend(bytes.fromhex("f0 02 e6 80 20 fa f0 01 22 14 05 20"))
    code.append((loop - len(code) - 1) & 0xFF)
    code.extend(bytes.fromhex("18 fe"))
    rom[0x150:0x150 + len(code)] = code
    return bytes(rom)


class LocalCableTests(unittest.TestCase):
    def test_link_exchanges_multiple_bytes_both_directions(self):
        for color, control in ((False, 0x81), (True, 0x83)):
            with self.subTest(color=color):
                first, second = GameBoy(), GameBoy()
                first.load(program("FIRST", control, 0x30, color))
                second.load(program("SECOND", 0x80, 0x70, color))
                cable = LocalLink(first, second)
                cable.run_frame()
                self.assertEqual(cable.transfers, 16)
                self.assertEqual(first.mmu.mem[0xC000:0xC010], bytes(range(0x70, 0x80)))
                self.assertEqual(second.mmu.mem[0xC000:0xC010], bytes(range(0x30, 0x40)))
                self.assertEqual(first.mmu.iff & second.mmu.iff & 8, 8)


class LocalFeatureUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        save_dir = patch("pokemongb.page._saves_dir", return_value=self.folder)
        save_dir.start()
        self.addCleanup(save_dir.stop)
        self.page = PokemonGBPage()
        self.addCleanup(self.page.close)
        self.page.library = Library(self.folder / "library")

    def test_scan_recurses_without_launching_and_deduplicates(self):
        nested = self.folder / "roms" / "deep"
        nested.mkdir(parents=True)
        (nested / "game.gb").write_bytes(program("SCAN", 0x81, 0))
        (nested / "broken.gbc").write_bytes(b"bad")
        (nested / "ignore.txt").write_text("ignore")
        with zipfile.ZipFile(nested / "packed.zip", "w") as archive:
            archive.writestr("inside.gb", program("PACKED", 0x81, 0))
        self.assertEqual(self.page._scan_rom_folder(nested.parent), (2, 1))
        self.assertEqual(self.page._scan_rom_folder(nested.parent), (0, 1))
        self.assertIsNone(self.page.gb)
        self.assertFalse(self.page.clock.isActive())
        self.assertEqual({g.title for g in self.page.library.games}, {"SCAN", "PACKED"})
        self.assertTrue(all(g.launches == 0 for g in self.page.library.games))

    def test_palette_menu_saves_per_game_and_leaves_cgb_alone(self):
        rom = program("COLOR TEST", 0x81, 0)
        path = self.folder / "gray.gb"
        path.write_bytes(rom)
        game = self.page.library.remember(path, "Gray", "Game Boy", "gb")
        another = self.page.library.remember(self.folder / "green.gb", "Green", "Game Boy", "gb")
        settings = GameSettings(self.page.library, game)
        combo = settings.findChild(QComboBox, "GameBoyPalette")
        combo.setCurrentIndex(combo.findData("gray"))
        reloaded = Library(self.page.library.folder)
        self.assertEqual(reloaded.get(game.id).gb_palette, "gray")
        self.assertEqual(reloaded.get(another.id).gb_palette, "green")
        gb = GameBoy()
        gb.load(rom)
        with patch.object(self.page, "_start_audio"):
            self.page.load_bytes(rom)
        self.page.clock.stop()
        self.page._game_id = game.id
        self.page._present()
        self.assertEqual(self.page.screen.pixmap().toImage().pixelColor(0, 0).name(), "#ffffff")
        self.page.library.set_gb_palette(game.id, "custom", ["#123456", "#234567", "#345678", "#456789"])
        output = array.array("I")
        output.frombytes(gb_picture(gb.ppu, game.gb_palette, game.gb_colors))
        self.assertEqual(output[0], 0xFF123456)
        gb.load(program("CGB", 0x83, 0, True))
        self.assertEqual(gb_picture(gb.ppu, "gray"), gb.ppu.fb.tobytes())

    def test_same_rom_link_uses_separate_player_two_battery_save(self):
        rom = program("SAME CART", 0x81, 0)
        path = self.folder / "same.gb"
        path.write_bytes(rom)
        dialog = LocalLinkDialog(self.page, self.folder, _p2_action)
        dialog.paths = [path, path]
        with patch.object(self.page, "_start_audio"):
            dialog._connect()
        dialog.timer.stop()
        dialog.save_timer.stop()
        self.assertEqual(dialog.save_paths[0], battery_paths(rom, self.folder))
        self.assertNotEqual(dialog.save_paths[0], dialog.save_paths[1])
        for port, game in enumerate(dialog.cable.games):
            game.mmu.write(0x0000, 0x0A)
            game.mmu.write(0xA000, port + 1)
        dialog._tick()
        self.assertTrue(all(screen.image is not None for screen in dialog.screens))
        dialog.done(0)
        self.assertEqual([s.read_bytes()[0] for s, _ in dialog.save_paths], [1, 2])
