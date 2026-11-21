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

from pokemongb.cart import n3ds_save_key, prepare_3ds
from pokemongb.n3ds import core_path, open_core, pack_state, unpack_state
from pokemongb.page import PokemonGBPage


def tiny_3dsx() -> bytes:
    rom = bytearray(0x40)
    struct.pack_into("<I", rom, 0, 0x58534433)
    struct.pack_into("<HH", rom, 4, 0x20, 0)
    struct.pack_into("<I", rom, 16, 4)
    struct.pack_into("<I", rom, 0x20, 0xEAFFFFFE)
    return bytes(rom)


class CartKindTests(unittest.TestCase):
    def test_3dsx_file_is_routed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "homebrew.3dsx"
            path.write_bytes(tiny_3dsx())
            routed = prepare_3ds(path, Path(folder) / "cache")
            self.assertEqual(routed, path)

    def test_zip_3ds_is_extracted(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "game.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("x.3dsx", tiny_3dsx())
            routed = prepare_3ds(archive, Path(folder) / "cache")
            self.assertIsNotNone(routed)
            self.assertEqual(routed.read_bytes(), tiny_3dsx())

    def test_gb_zip_is_not_3ds(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "game.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("red.gb", b"\x00" * 0x8000)
            self.assertIsNone(prepare_3ds(archive, Path(folder) / "cache"))

    def test_state_wrapper_rejects_another_game(self):
        packed = pack_state("3DS_AABB", b"state-bytes")
        self.assertEqual(unpack_state(packed, "3DS_AABB"), b"state-bytes")
        with self.assertRaises(ValueError):
            unpack_state(packed, "3DS_CCDD")


@unittest.skipUnless(core_path().is_file(), "Azahar core is not installed")
class N3dsCoreTests(unittest.TestCase):
    def test_both_screens_and_save_state(self):
        with tempfile.TemporaryDirectory() as folder:
            rom_path = Path(folder) / "tiny.3dsx"
            rom_path.write_bytes(tiny_3dsx())
            core = open_core(Path(folder))
            try:
                core.load(rom_path, save_name="tiny", full_path_only=True)
                for _ in range(8):
                    core.run()
                self.assertIsNotNone(core.frame)
                _raw, width, height = core.frame
                self.assertEqual((width, height), (400, 480))
                started = time.perf_counter()
                frames = 30
                for _ in range(frames):
                    core.run()
                elapsed = time.perf_counter() - started
                print(f"3ds frames/sec: {frames / elapsed:.1f}")
                self.assertGreater(frames / elapsed, 30)
                first = core.serialize()
                self.assertGreater(len(first), 1000)
                core.unserialize(first)
                core.run()
                self.assertEqual(core.frame[1:], (400, 480))
                self.assertEqual(n3ds_save_key(tiny_3dsx())[:5], "3DSX_")
            finally:
                core.close()


class N3dsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @unittest.skipUnless(core_path().is_file(), "Azahar core is not installed")
    def test_3ds_reaches_the_screen(self):
        page = PokemonGBPage()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tiny.3dsx"
            path.write_bytes(tiny_3dsx())
            page.load_path(str(path))
            self.assertEqual(page.kind, "3ds", page.status.text())
            for _ in range(6):
                page._tick()
            pixmap = page.screen.pixmap()
            self.assertIsNotNone(pixmap)
            self.assertFalse(pixmap.isNull())
            self.assertEqual(pixmap.width(), 800)
            self.assertEqual(pixmap.height(), 960)
            rect = page.screen.contentsRect()
            origin_x = rect.x() + max(0, (rect.width() - pixmap.width()) // 2)
            origin_y = rect.y() + max(0, (rect.height() - pixmap.height()) // 2)
            bottom = QPoint(origin_x + pixmap.width() // 2, origin_y + pixmap.height() * 3 // 4)
            page._move_touch(page.screen.mapTo(page, bottom))
            self.assertTrue(page.n3ds.pointer_pressed)
            self.assertGreater(page.n3ds.pointer_y, 0)
            page.save_state()
            state = page._state_path()
            self.assertTrue(state.is_file())
            page.load_state()
            page.shutdown()
            state.unlink(missing_ok=True)
            state.with_name(state.name + ".png").unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
