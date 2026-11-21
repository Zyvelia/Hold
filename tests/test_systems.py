import os
import struct
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from pokemongb.page import PokemonGBPage
from pokemongb.systems import BY_ID, bios_dir, cores_dir, locate, module_dir, open_core, pack_state, unpack_state


def tiny_nes() -> bytes:
    prg = bytearray(16384)
    prg[0:3] = bytes([0x4C, 0x00, 0x80])
    prg[0x3FFC:0x3FFE] = bytes([0x00, 0x80])
    return b"NES\x1a" + bytes([1, 1, 0, 0]) + bytes(8) + bytes(prg) + bytes(8192)


def tiny_snes() -> bytes:
    rom = bytearray(32768)
    rom[0:3] = bytes([0x4C, 0x00, 0x80])
    rom[0x7FC0:0x7FD5] = b"TINY SNES".ljust(21, b" ")
    rom[0x7FD5] = 0x20
    rom[0x7FD7] = 0x05
    rom[0x7FFC:0x7FFE] = bytes([0x00, 0x80])
    return bytes(rom)


def tiny_md() -> bytes:
    rom = bytearray(0x220)
    rom[4:8] = (0x200).to_bytes(4, "big")
    rom[0x100:0x110] = b"SEGA GENESIS    "
    rom[0x110:0x120] = b"(C)TINY 2026.OCT"
    rom[0x120:0x150] = b"TINY MD".ljust(48, b" ")
    rom[0x180:0x18E] = b"GM 00000000-00"
    rom[0x200:0x202] = bytes([0x60, 0xFE])
    return bytes(rom)


def tiny_ps1() -> bytes:
    exe = bytearray(0x2000)
    exe[0:8] = b"PS-X EXE"
    exe[0x10:0x14] = (0x80010000).to_bytes(4, "little")
    exe[0x18:0x1C] = (0x80010000).to_bytes(4, "little")
    exe[0x1C:0x20] = (0x800).to_bytes(4, "little")
    exe[0x30:0x34] = (0x801FFF00).to_bytes(4, "little")
    exe[0x800:0x808] = bytes([0xFF, 0xFF, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00])
    return bytes(exe)


def tiny_psp() -> bytes:
    elf = bytearray(0x80)
    elf[0:4] = b"\x7fELF"
    elf[4:8] = bytes([1, 1, 1, 0])
    struct.pack_into("<HHI", elf, 16, 2, 8, 1)
    struct.pack_into("<III", elf, 24, 0x08900000, 52, 0)
    struct.pack_into("<HHHHHH", elf, 40, 0, 52, 32, 1, 0, 0)
    struct.pack_into("<IIIIIIII", elf, 52, 1, 0x60, 0x08900000, 0x08900000, 8, 8, 5, 0x1000)
    elf[0x60:0x68] = bytes([0xFF, 0xFF, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00])
    return bytes(elf)


def tiny_dol() -> bytes:
    code = bytes.fromhex("48000000") + b"\x00" * 28
    blob = bytearray(0x100 + len(code))
    struct.pack_into(">I", blob, 0x00, 0x100)
    struct.pack_into(">I", blob, 0x48, 0x80003100)
    struct.pack_into(">I", blob, 0x90, len(code))
    struct.pack_into(">I", blob, 0xE0, 0x80003100)
    blob[0x100:] = code
    return bytes(blob)


def tiny_pce() -> bytes:
    rom = bytearray(8192)
    rom[0:3] = bytes([0x4C, 0x00, 0xE0])
    rom[-2:] = bytes([0x00, 0xE0])
    return bytes(rom)


class LocateTests(unittest.TestCase):
    def test_bios_folder_follows_this_module(self):
        from pokemongb.systems import place_bios

        root = cores_dir() / "system"
        self.assertEqual(module_dir(), cores_dir().parent)
        self.assertEqual(bios_dir("scph5501.bin", 512 * 1024), root)
        self.assertEqual(
            bios_dir("SCPH-90001_BIOS_V18_USA_230.BIN", 4 * 1024 * 1024),
            root / "pcsx2" / "bios",
        )
        self.assertEqual(bios_dir("neogeo.zip", 10), root / "fbneo")
        self.assertEqual(bios_dir("mcpx_1.0.bin", 10), root / "xemu")
        self.assertEqual(bios_dir("keys.txt", 8), root / "Cemu")
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder) / "zz-test-bios.bin"
            src.write_bytes(b"bios")
            dest = place_bios(src)
            try:
                self.assertEqual(dest, root / "zz-test-bios.bin")
                self.assertEqual(dest.read_bytes(), b"bios")
                self.assertTrue(str(dest).startswith(str(module_dir())))
            finally:
                dest.unlink(missing_ok=True)

    def test_suffixes_and_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            nes = root / "demo.nes"
            nes.write_bytes(tiny_nes())
            path, system = locate(nes, root / "cache")
            self.assertEqual(system.id, "nes")
            self.assertEqual(path, nes)
            gb = root / "red.gb"
            gb.write_bytes(b"\x00" * 32)
            self.assertIsNone(locate(gb, root / "cache"))
            zipped = root / "cart.zip"
            with zipfile.ZipFile(zipped, "w") as zf:
                zf.writestr("demo.nes", tiny_nes())
            extracted, system = locate(zipped, root / "cache")
            self.assertEqual(system.id, "nes")
            self.assertTrue(extracted.is_file())
            handheld = root / "both.zip"
            with zipfile.ZipFile(handheld, "w") as zf:
                zf.writestr("red.gb", b"\x00" * 0x8000)
                zf.writestr("demo.nes", tiny_nes())
            self.assertIsNone(locate(handheld, root / "cache"))
            psp = root / "game.elf"
            psp.write_bytes(tiny_psp())
            _, system = locate(psp, root / "cache")
            self.assertEqual(system.id, "psp")
            iso = root / "disc.iso"
            blob = bytearray(0x8010)
            blob[0x8001:0x8006] = b"CD001"
            iso.write_bytes(blob)
            _, system = locate(iso, root / "cache")
            self.assertEqual(system.id, "psp")
            ps2 = root / "ps2.iso"
            disc = bytearray(0x8030)
            disc[0x8001:0x8006] = b"CD001"
            disc[0x8008:0x8008 + 12] = b"PLAYSTATION "
            ps2.write_bytes(disc)
            _, system = locate(ps2, root / "cache")
            self.assertEqual(system.id, "ps2")
            ee = bytearray(tiny_psp())
            struct.pack_into("<I", ee, 36, 0x00920000)
            elf = root / "ee.elf"
            elf.write_bytes(ee)
            _, system = locate(elf, root / "cache")
            self.assertEqual(system.id, "ps2")
            sheet = root / "game.ciso"
            sheet.write_bytes(b"\0" * 32)
            _, system = locate(sheet, root / "cache")
            self.assertEqual(system.id, "ps2")
            cabinet = root / "sf.zip"
            with zipfile.ZipFile(cabinet, "w") as zf:
                zf.writestr("pgm.bin", b"\x00" * 32)
                zf.writestr("tiles.rom", b"\x00" * 32)
            _, system = locate(cabinet, root / "cache")
            self.assertEqual(system.id, "arcade")
            xbox = root / "game.xiso"
            xbox.write_bytes(b"\x00" * 32)
            _, system = locate(xbox, root / "cache")
            self.assertEqual(system.id, "xbox")
            xex = root / "default.xex"
            xex.write_bytes(b"\x00" * 32)
            _, system = locate(xex, root / "cache")
            self.assertEqual(system.id, "x360")
            wud = root / "game.wud"
            wud.write_bytes(b"\x00" * 32)
            _, system = locate(wud, root / "cache")
            self.assertEqual(system.id, "wiiu")
            disc = root / "game.iso"
            blob = bytearray(0x10000 + 21)
            blob[0x10000:0x10015] = b"MICROSOFT*XBOX*MEDIA"
            disc.write_bytes(blob)
            _, system = locate(disc, root / "cache")
            self.assertEqual(system.id, "xbox")
            cube = root / "cube.iso"
            cube.write_bytes(b"\x00" * 0x1C + bytes.fromhex("C2339F3D"))
            _, system = locate(cube, root / "cache")
            self.assertEqual(system.id, "gc")
            for name, system_id in (
                ("game.a26", "a2600"),
                ("game.a52", "a5200"),
                ("game.a78", "a7800"),
                ("game.lnx", "lynx"),
                ("game.j64", "jaguar"),
                ("game.vec", "vectrex"),
                ("game.chf", "channelf"),
                ("game.ws", "ws"),
                ("game.ngp", "ngp"),
                ("game.vb", "vb"),
                ("game.sv", "sv"),
                ("game.32x", "s32x"),
            ):
                rom = root / name
                rom.write_bytes(b"\x00" * 32)
                _, system = locate(rom, root / "cache")
                self.assertEqual(system.id, system_id)

    def test_state_wrapper_rejects_another_game(self):
        blob = pack_state("nes", "nes_AAAA", b"state")
        self.assertEqual(unpack_state(blob, "nes", "nes_AAAA"), b"state")
        with self.assertRaises(ValueError):
            unpack_state(blob, "snes", "nes_AAAA")


class CoreBootTests(unittest.TestCase):
    def _boot(self, system_id: str, name: str, rom: bytes, size: tuple[int, int]) -> None:
        system = BY_ID[system_id]
        dll = cores_dir() / system.dll
        if not dll.is_file():
            self.skipTest(f"{system.dll} is not installed")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / name
            path.write_bytes(rom)
            core = open_core(system, Path(folder))
            try:
                core.load(path, full_path_only=system.full_path)
                started = time.perf_counter()
                for _ in range(30):
                    core.run()
                elapsed = time.perf_counter() - started
                self.assertEqual(core.frame_size, size)
                self.assertGreater(30 / elapsed, 30)
                raw = core.serialize()
                core.unserialize(unpack_state(pack_state(system.id, "k", raw), system.id, "k"))
                core.run()
                self.assertEqual(core.frame_size, size)
            finally:
                core.close()

    def test_nes(self):
        self._boot("nes", "tiny.nes", tiny_nes(), (256, 224))

    def test_snes(self):
        self._boot("snes", "tiny.sfc", tiny_snes(), (256, 224))

    def test_mega_drive(self):
        self._boot("md", "tiny.md", tiny_md(), (256, 192))

    def test_pc_engine(self):
        self._boot("pce", "tiny.pce", tiny_pce(), (256, 240))

    def test_psp(self):
        system = BY_ID["psp"]
        if not (cores_dir() / system.dll).is_file():
            self.skipTest("ppsspp core is not installed")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tiny.elf"
            path.write_bytes(tiny_psp())
            core = open_core(system, Path(folder))
            try:
                core.load(path, full_path_only=True)
                started = time.perf_counter()
                for _ in range(30):
                    core.run()
                elapsed = time.perf_counter() - started
                self.assertEqual(core.frame_size[0], 480)
                self.assertIn(core.frame_size[1], (270, 272))
                self.assertGreater(30 / elapsed, 20)
            finally:
                core.close()

    def test_gamecube_context(self):
        system = BY_ID["gc"]
        if not (cores_dir() / system.dll).is_file():
            self.skipTest("dolphin core is not installed")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tiny.dol"
            path.write_bytes(tiny_dol())
            core = open_core(system, Path(folder))
            try:
                core.load(path, full_path_only=True)
                core.run()
                self.assertTrue(core._hw_requested)
                self.assertEqual(core.frame_size, (640, 528))
            finally:
                core.close()

    def test_remaining_cartridges(self):
        cases = (
            ("a2600", "tiny.a26", 8192, (160, 210)),
            ("a5200", "tiny.a52", 8192, (320, 224)),
            ("a7800", "tiny.a78", 8192, (320, 223)),
            ("lynx", "tiny.lnx", 8192, (160, 102)),
            ("jaguar", "tiny.j64", 8192, (326, 240)),
            ("vectrex", "tiny.vec", 8192, (330, 410)),
            ("channelf", "tiny.chf", 8192, (306, 192)),
            ("ws", "tiny.ws", 65536, (224, 144)),
            ("ngp", "tiny.ngp", 8192, (160, 152)),
            ("vb", "tiny.vb", 8192, (384, 224)),
            ("sv", "tiny.sv", 32768, (160, 160)),
            ("s32x", "tiny.32x", 8192, (320, 224)),
        )
        for system_id, name, size, frame in cases:
            with self.subTest(system=system_id):
                system = BY_ID[system_id]
                if not (cores_dir() / system.dll).is_file():
                    self.skipTest(f"{system.dll} is not installed")
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / name
                    path.write_bytes(b"\x00" * size)
                    core = open_core(system, Path(folder))
                    try:
                        core.load(path, full_path_only=system.full_path)
                        for _ in range(8):
                            core.run()
                        self.assertEqual(core.frame_size, frame)
                        self.assertIsNotNone(core.frame)
                    finally:
                        core.close()

    def test_playstation(self):
        system = BY_ID["ps1"]
        if not (cores_dir() / system.dll).is_file():
            self.skipTest("pcsx core is not installed")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tiny.exe"
            path.write_bytes(tiny_ps1())
            core = open_core(system, Path(folder))
            try:
                core.load(path, full_path_only=True)
                started = time.perf_counter()
                for _ in range(30):
                    core.run()
                elapsed = time.perf_counter() - started
                self.assertIsNotNone(core.frame)
                width, height = core.frame_size
                self.assertIn(width, (256, 320, 368, 640))
                self.assertIn(height, (240, 480))
                self.assertGreater(30 / elapsed, 20)
            finally:
                core.close()


class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_atari_reaches_the_screen(self):
        if not (cores_dir() / "stella2014_libretro.dll").is_file():
            self.skipTest("stella core is not installed")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tiny.a26"
            path.write_bytes(b"\x00" * 4096)
            page = PokemonGBPage()
            try:
                page.load_path(str(path))
                page._tick()
                pixmap = page.screen.pixmap()
                self.assertIsNotNone(pixmap)
                self.assertEqual(pixmap.width(), 320)
                self.assertEqual(pixmap.height(), 420)
                self.assertIn("Atari 2600", page.status.text())
            finally:
                page.shutdown()

    def test_nes_reaches_the_screen(self):
        if not (cores_dir() / "fceumm_libretro.dll").is_file():
            self.skipTest("fceumm core is not installed")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tiny.nes"
            path.write_bytes(tiny_nes())
            page = PokemonGBPage()
            try:
                page.load_path(str(path))
                page._tick()
                pixmap = page.screen.pixmap()
                self.assertIsNotNone(pixmap)
                self.assertEqual(pixmap.width(), 512)
                self.assertEqual(pixmap.height(), 448)
                self.assertIn("NES", page.status.text())
                page.save_state()
                state = page._state_path()
                self.assertTrue(state.is_file())
                page.load_state()
                state.unlink()
                state.with_name(state.name + ".png").unlink(missing_ok=True)
            finally:
                page.shutdown()

    def test_playstation_reaches_the_screen(self):
        if not (cores_dir() / "pcsx_rearmed_libretro.dll").is_file():
            self.skipTest("pcsx core is not installed")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tiny.exe"
            path.write_bytes(tiny_ps1())
            page = PokemonGBPage()
            try:
                page.load_path(str(path))
                page._tick()
                pixmap = page.screen.pixmap()
                self.assertIsNotNone(pixmap)
                self.assertGreater(pixmap.width(), 0)
                self.assertIn("PlayStation", page.status.text())
            finally:
                page.shutdown()

    def test_gamecube_reaches_the_window(self):
        if not (cores_dir() / "dolphin_libretro.dll").is_file():
            self.skipTest("dolphin core is not installed")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tiny.dol"
            path.write_bytes(tiny_dol())
            page = PokemonGBPage()
            try:
                page.load_path(str(path))
                self.assertEqual(page.kind, "gc")
                self.assertIn("GameCube", page.status.text())
                page._tick()
            finally:
                page.shutdown()
