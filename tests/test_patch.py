import os
import tempfile
import unittest
import zlib
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from pokemongb.cheats import parse_cheat_file, read_cheat_entries, write_cheat_file
from pokemongb.library import Library
from pokemongb.page import PokemonGBPage
from pokemongb.patch import apply_bps, apply_ips, apply_patch
from pokemongb.shelf import GameSettings


def _bps_number(value: int) -> bytes:
    out = bytearray()
    while True:
        piece = value & 0x7F
        value >>= 7
        if value == 0:
            out.append(0x80 | piece)
            break
        out.append(piece)
        value -= 1
    return bytes(out)


def _bps(source: bytes, target: bytes) -> bytes:
    # Copy the shared prefix from the ROM, then write the rest from the patch.
    shared = 0
    while shared < len(source) and shared < len(target) and source[shared] == target[shared]:
        shared += 1
    body = b"BPS1" + _bps_number(len(source)) + _bps_number(len(target)) + _bps_number(0)
    if shared:
        body += _bps_number((shared - 1) << 2)
    rest = target[shared:]
    if rest:
        body += _bps_number(((len(rest) - 1) << 2) | 1) + rest
    body += (zlib.crc32(source) & 0xFFFFFFFF).to_bytes(4, "little")
    body += (zlib.crc32(target) & 0xFFFFFFFF).to_bytes(4, "little")
    body += (zlib.crc32(body) & 0xFFFFFFFF).to_bytes(4, "little")
    return body


class PatchTests(unittest.TestCase):
    def test_ips_writes_a_byte_and_a_run(self):
        rom = b"\x11" * 8
        patch = b"PATCH" + (2).to_bytes(3, "big") + (1).to_bytes(2, "big") + b"\x5A" + b"EOF"
        self.assertEqual(apply_ips(rom, patch)[2], 0x5A)
        run = b"PATCH" + (0).to_bytes(3, "big") + (0).to_bytes(2, "big") + (4).to_bytes(2, "big") + b"\x22" + b"EOF"
        self.assertEqual(apply_patch(rom, run)[:4], b"\x22" * 4)

    def test_bps_rewrites_the_tail_and_rejects_another_rom(self):
        source = b"ABCDEFGH"
        target = b"ABCDWXYZ"
        patch = _bps(source, target)
        self.assertEqual(apply_bps(source, patch), target)
        with self.assertRaises(ValueError):
            apply_bps(b"ABCDEFGX", patch)


class CheatFileTests(unittest.TestCase):
    def test_cht_and_plain_list(self):
        cht = 'cheats = 2\ncheat0_desc = "Lives"\ncheat0_code = "015500C0"\ncheat0_enable = true\ncheat1_desc = "Off"\ncheat1_code = "015501C1"\ncheat1_enable = false\n'
        rows = parse_cheat_file(cht)
        self.assertEqual(rows[0], ("Lives", "015500C0", True))
        self.assertFalse(rows[1][2])
        text = "Lives: 015500C0\nC000:55\n"
        plain = parse_cheat_file(text)
        self.assertEqual(plain[0][0], "Lives")
        self.assertEqual(plain[0][1], "015500C0")
        self.assertEqual(plain[1][1], "C000:55")

    def test_written_file_is_what_gets_read_back(self):
        text = write_cheat_file([("Lives", "015500C0", True, "gameshark")])
        self.assertEqual(read_cheat_entries(text), [("Lives", "015500C0", True, "gameshark")])


class PatchUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_import_and_patch_reach_the_game(self):
        with tempfile.TemporaryDirectory() as folder:
            os.environ["POKEMONGB_SETTINGS"] = str(Path(folder) / "settings.json")
            os.environ["POKEMONGB_LIBRARY"] = folder
            os.environ["POKEMONGB_CONTROLS"] = str(Path(folder) / "controls.json")
            try:
                root = Path(folder)
                rom = bytearray(0x8000)
                rom[0x100] = 0x18
                rom[0x101] = 0xFE
                rom[0x134:0x13F] = b"PATCHTEST"
                path = root / "patch.gb"
                path.write_bytes(rom)
                page = PokemonGBPage()
                page.library.remember(path, "PATCHTEST", "Game Boy", "gb")
                game = page.library.games[0]
                dialog = GameSettings(page.library, game, page)
                added = dialog.import_text('cheat0_desc = "Lives"\ncheat0_code = "015500C0"\ncheat0_enable = true\ncheats = 1\n')
                self.assertEqual(added, 1)
                self.assertEqual(page.library.games[0].cheats[0].name, "Lives")
                ips = root / "fix.ips"
                ips.write_bytes(b"PATCH" + (0x200).to_bytes(3, "big") + (1).to_bytes(2, "big") + b"\x42" + b"EOF")
                page.library.set_patch(game.id, ips)
                self.assertEqual(page.library.games[0].patch_name, "fix.ips")
                page.load_path(str(path))
                self.assertEqual(page.gb.mmu.read(0x200), 0x42)
                page.library.add_cheat(page.library.by_path(path).id, "015500C1", "Other", "auto")
                cheat_path = page.library.cheat_path(page.library.by_path(path))
                self.assertTrue(cheat_path.is_file())
                cheat_path.write_text(write_cheat_file([("Lives", "015500C0", True, "gameshark")]), encoding="utf-8")
                page._apply_cheats()
                page.gb.run_frame()
                self.assertEqual(page.gb.mmu.read(0xC000), 0x55)
                page.shutdown()
            finally:
                os.environ.pop("POKEMONGB_SETTINGS", None)
                os.environ.pop("POKEMONGB_LIBRARY", None)
                os.environ.pop("POKEMONGB_CONTROLS", None)
