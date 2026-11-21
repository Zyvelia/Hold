import os
import struct
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from pokemongb.cart import nds_save_key, open_rom
from pokemongb.nds import core_path, open_core, pack_state, unpack_state
from pokemongb.page import PokemonGBPage, _saves_dir


def _crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def tiny_nds() -> bytes:
    """Header plus a one-instruction ARM9 and ARM7. Both screens come up."""
    rom = bytearray(0x20000)
    rom[0:12] = b"TINYNDSROM\x00"
    rom[0x0C:0x10] = b"T001"
    struct.pack_into("<I", rom, 0x20, 0x200)
    struct.pack_into("<I", rom, 0x24, 0x02000000)
    struct.pack_into("<I", rom, 0x28, 0x02000000)
    struct.pack_into("<I", rom, 0x2C, 0x10)
    struct.pack_into("<I", rom, 0x30, 0x400)
    struct.pack_into("<I", rom, 0x34, 0x037F8000)
    struct.pack_into("<I", rom, 0x38, 0x037F8000)
    struct.pack_into("<I", rom, 0x3C, 0x10)
    struct.pack_into("<I", rom, 0x80, len(rom))
    struct.pack_into("<I", rom, 0x200, 0xEAFFFFFE)
    struct.pack_into("<I", rom, 0x400, 0xEAFFFFFE)
    struct.pack_into("<H", rom, 0x15E, _crc16(rom[:0x15E]))
    return bytes(rom)


class CartKindTests(unittest.TestCase):
    def test_zip_nds_is_ds(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "game.zip"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("diamond.nds", b"\x00" * 0x200)
            data, kind = open_rom(path)
        self.assertEqual(kind, "nds")
        self.assertEqual(len(data), 0x200)

    def test_state_wrapper_rejects_another_game(self):
        packed = pack_state("DIAMOND_ADAE", b"state-bytes")
        self.assertEqual(unpack_state(packed, "DIAMOND_ADAE"), b"state-bytes")
        with self.assertRaises(ValueError):
            unpack_state(packed, "PEARL_APAE")


@unittest.skipUnless(core_path().is_file(), "melonDS core is not installed")
class NdsCoreTests(unittest.TestCase):
    def test_both_screens_and_save_state(self):
        with tempfile.TemporaryDirectory() as folder:
            rom_path = Path(folder) / "tiny.nds"
            rom_path.write_bytes(tiny_nds())
            core = open_core(Path(folder))
            try:
                core.load(rom_path, save_name="tiny", content_name="tiny.nds")
                for _ in range(20):
                    core.run()
                self.assertIsNotNone(core.frame)
                raw, width, height = core.frame
                self.assertEqual((width, height), (256, 384))
                self.assertEqual(len(raw), width * height * 4)
                started = time.perf_counter()
                frames = 120
                for _ in range(frames):
                    core.run()
                elapsed = time.perf_counter() - started
                print(f"nds frames/sec: {frames / elapsed:.1f}")
                self.assertGreater(frames / elapsed, 60)
                first = core.serialize()
                self.assertGreater(len(first), 1000)
                for _ in range(8):
                    core.run()
                self.assertNotEqual(core.serialize(), first)
                core.unserialize(first)
                core.run()
                self.assertEqual(core.frame[1:], (256, 384))
            finally:
                core.close()


class NdsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @unittest.skipUnless(core_path().is_file(), "melonDS core is not installed")
    def test_nds_reaches_the_screen(self):
        page = PokemonGBPage()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tiny.nds"
            path.write_bytes(tiny_nds())
            page.load_path(str(path))
            self.assertEqual(page.kind, "nds", page.status.text())
            for _ in range(8):
                page._tick()
            pixmap = page.screen.pixmap()
            self.assertIsNotNone(pixmap)
            self.assertFalse(pixmap.isNull())
            self.assertEqual(pixmap.width(), 512)
            self.assertEqual(pixmap.height(), 768)
            rect = page.screen.contentsRect()
            origin_x = rect.x() + max(0, (rect.width() - pixmap.width()) // 2)
            origin_y = rect.y() + max(0, (rect.height() - pixmap.height()) // 2)
            bottom = QPoint(origin_x + pixmap.width() // 2, origin_y + pixmap.height() * 3 // 4)
            page._move_touch(page.screen.mapTo(page, bottom))
            self.assertTrue(page.nds.pointer_pressed)
            self.assertGreater(page.nds.pointer_y, 0)
            page.save_state()
            state = page._state_path()
            self.assertTrue(state.is_file())
            page.load_state()
            page.shutdown()
            state.unlink(missing_ok=True)
            state.with_name(state.name + ".png").unlink(missing_ok=True)
            (_saves_dir() / f"{nds_save_key(tiny_nds())}.sav").unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
