import os
import struct
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from pokemongb.cart import gba_save_key, open_rom
from pokemongb.gba import core_path, open_core, pack_state, unpack_state
from pokemongb.page import PokemonGBPage


def tiny_gba() -> bytes:
    """Mode 3 homebrew: one red pixel, then a tight loop."""
    rom = bytearray(0x200)
    struct.pack_into("<I", rom, 0x00, 0xEA00002E)
    rom[0xA0:0xAC] = b"TINYHOMEBREW"
    rom[0xAC:0xB0] = b"T001"
    rom[0xB2] = 0x96
    checksum = 0
    for index in range(0xA0, 0xBD):
        checksum = (checksum - rom[index]) & 0xFF
    rom[0xBD] = (checksum - 0x19) & 0xFF
    words = {
        0xC0: 0xE59F0018,
        0xC4: 0xE3A01003,
        0xC8: 0xE3811B01,
        0xCC: 0xE1C010B0,
        0xD0: 0xE59F2010,
        0xD4: 0xE3A0301F,
        0xD8: 0xE1C230B0,
        0xDC: 0xEAFFFFFE,
        0xE0: 0x04000000,
        0xE8: 0x06000000,
    }
    for address, word in words.items():
        struct.pack_into("<I", rom, address, word)
    return bytes(rom)


class CartKindTests(unittest.TestCase):
    def test_zip_gba_is_advance(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "game.zip"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("ruby.gba", b"\x00" * 0x200)
            data, kind = open_rom(path)
        self.assertEqual(kind, "gba")
        self.assertEqual(len(data), 0x200)

    def test_zip_gb_stays_game_boy(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "game.zip"
            rom = b"\x00" * 0x8000
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("red.gba", b"\x00" * 0x200)
                zf.writestr("red.gb", rom)
            data, kind = open_rom(path)
        self.assertEqual(kind, "gb")
        self.assertEqual(data, rom)


@unittest.skipUnless(core_path().is_file(), "mGBA core is not installed")
class GbaCoreTests(unittest.TestCase):
    def test_homebrew_frame_and_save_state(self):
        with tempfile.TemporaryDirectory() as folder:
            rom_path = Path(folder) / "tiny.gba"
            rom_path.write_bytes(tiny_gba())
            core = open_core(Path(folder))
            try:
                core.load(rom_path, save_name="tiny")
                for _ in range(30):
                    core.run()
                self.assertIsNotNone(core.frame)
                raw, width, height = core.frame
                self.assertEqual((width, height), (240, 160))
                self.assertGreaterEqual(len(raw), width * height * 4)
                red = raw[2]
                self.assertGreater(
                    red,
                    200,
                    f"pixel format {core.pixel_format}, rate {core.sample_rate}, "
                    f"unknown env {sorted(core._unknown_env)}",
                )
                started = time.perf_counter()
                frames = 180
                for _ in range(frames):
                    core.run()
                elapsed = time.perf_counter() - started
                print(f"gba frames/sec: {frames / elapsed:.1f}")
                self.assertGreater(frames / elapsed, 30)
                first = core.serialize()
                self.assertGreater(len(first), 1000)
                for _ in range(20):
                    core.run()
                self.assertNotEqual(core.serialize(), first)
                core.unserialize(first)
                self.assertEqual(core.serialize(), first)
                packed = pack_state(gba_save_key(tiny_gba()), first)
                self.assertEqual(unpack_state(packed, gba_save_key(tiny_gba())), first)
                with self.assertRaises(ValueError):
                    unpack_state(packed, "other")
            finally:
                core.close()


class GbaPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @unittest.skipUnless(core_path().is_file(), "mGBA core is not installed")
    def test_gba_reaches_the_screen(self):
        page = PokemonGBPage()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tiny.gba"
            path.write_bytes(tiny_gba())
            page.load_path(str(path))
            self.assertEqual(page.kind, "gba", page.status.text())
            for _ in range(10):
                page._tick()
            pixmap = page.screen.pixmap()
            self.assertIsNotNone(pixmap)
            self.assertFalse(pixmap.isNull())
            self.assertEqual(pixmap.width(), 720)
            self.assertEqual(pixmap.height(), 480)
            page.save_state()
            state = page._state_path()
            self.assertTrue(state.is_file())
            page.load_state()
            page.shutdown()
            state.unlink(missing_ok=True)
            state.with_name(state.name + ".png").unlink(missing_ok=True)
            state.with_name("TINYHOMEBREW_T001.srm").unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
