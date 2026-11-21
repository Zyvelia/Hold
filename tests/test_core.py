import time
import unittest

from pokemongb.ppu import Z_PACK
from pokemongb.system import GameBoy


def _machine(code: bytes = b"", size: int = 0x8000, header: dict | None = None) -> GameBoy:
    rom = bytearray(size)
    rom[0x150 : 0x150 + len(code)] = code
    for addr, value in (header or {}).items():
        rom[addr] = value
    gb = GameBoy()
    gb.load(bytes(rom))
    gb.cpu.pc = 0x150
    return gb


class CpuTests(unittest.TestCase):
    def test_dmg_and_cgb_boot_registers(self):
        dmg = _machine()
        dmg.cpu.reset(False)
        self.assertEqual(dmg.cpu.a, 0x01)
        self.assertEqual(dmg.cpu.f, 0xB0)
        self.assertEqual(dmg.cpu.pc, 0x0100)

        cgb = _machine(header={0x143: 0xC0})
        self.assertTrue(cgb.cgb)
        self.assertEqual(cgb.cpu.a, 0x11)
        self.assertEqual(cgb.cpu.f, 0x80)

    def test_daa_adds_bcd(self):
        # 0x45 + 0x38 = 0x7D, DAA -> 0x83 (45 + 38 = 83)
        gb = _machine(bytes([0x3E, 0x45, 0xC6, 0x38, 0x27]))
        for _ in range(3):
            gb.cpu.step()
        self.assertEqual(gb.cpu.a, 0x83)
        self.assertEqual(gb.cpu.f & 0x10, 0)

        # 0x50 + 0x50 = 0xA0, DAA -> 0x00 with carry (50 + 50 = 100)
        gb = _machine(bytes([0x3E, 0x50, 0xC6, 0x50, 0x27]))
        for _ in range(3):
            gb.cpu.step()
        self.assertEqual(gb.cpu.a, 0x00)
        self.assertEqual(gb.cpu.f & 0x90, 0x90)

    def test_high_ram_and_absolute_load(self):
        gb = _machine(bytes([0x3E, 0x5A, 0xE0, 0x80, 0xAF, 0xF0, 0x80]))
        for _ in range(4):
            gb.cpu.step()
        self.assertEqual(gb.cpu.a, 0x5A)

        gb = _machine(bytes([0x3E, 0x42, 0xEA, 0x00, 0xC0, 0xAF, 0xFA, 0x00, 0xC0]))
        for _ in range(4):
            gb.cpu.step()
        self.assertEqual(gb.cpu.a, 0x42)

    def test_call_returns_to_the_next_instruction(self):
        code = bytearray(0x20)
        code[0:3] = bytes([0xCD, 0x60, 0x01])
        code[3:5] = bytes([0x3E, 0x11])
        code[5:7] = bytes([0x18, 0xFE])
        code[0x10:0x13] = bytes([0x3E, 0x99, 0xC9])
        gb = _machine(bytes(code))
        for _ in range(8):
            if gb.cpu.pc == 0x155:
                break
            gb.cpu.step()
        self.assertEqual(gb.cpu.pc, 0x155)
        self.assertEqual(gb.cpu.a, 0x11)
        self.assertEqual(gb.cpu.sp, 0xFFFE)

    def test_add_sp_sets_half_carry(self):
        gb = _machine(bytes([0x31, 0x0F, 0x00, 0xE8, 0x01]))
        gb.cpu.step()
        gb.cpu.step()
        self.assertEqual(gb.cpu.sp, 0x0010)
        self.assertEqual(gb.cpu.f, 0x20)

    def test_rlca_clears_zero_and_cb_rlc_sets_it(self):
        gb = _machine(bytes([0xAF, 0x07]))
        gb.cpu.step()
        gb.cpu.step()
        self.assertEqual(gb.cpu.a, 0x00)
        self.assertEqual(gb.cpu.f & 0x80, 0)

        gb = _machine(bytes([0xAF, 0xCB, 0x07]))
        gb.cpu.step()
        gb.cpu.step()
        self.assertEqual(gb.cpu.a, 0x00)
        self.assertEqual(gb.cpu.f & 0x80, 0x80)


class CartridgeTests(unittest.TestCase):
    def test_mbc3_banks_and_ram(self):
        rom = bytearray(0x10000)
        rom[0x147] = 0x13
        rom[0x149] = 0x03
        rom[0x4000] = 0x11
        rom[0x8000] = 0x22
        gb = GameBoy()
        gb.load(bytes(rom))
        self.assertEqual(gb.mmu.read(0x4000), 0x11)
        gb.mmu.write(0x2000, 0)
        self.assertEqual(gb.mmu.read(0x4000), 0x11)
        gb.mmu.write(0x2000, 2)
        self.assertEqual(gb.mmu.read(0x4000), 0x22)
        gb.mmu.write(0x0000, 0x0A)
        gb.mmu.write(0xA000, 0x5A)
        self.assertEqual(gb.mmu.read(0xA000), 0x5A)
        self.assertEqual(gb.mmu.eram[0], 0x5A)

    def test_mbc5_allows_bank_zero(self):
        rom = bytearray(0x8000)
        rom[0x147] = 0x1B
        rom[0x149] = 0x02
        rom[0x0000] = 0xAB
        rom[0x4000] = 0xCD
        gb = GameBoy()
        gb.load(bytes(rom))
        self.assertEqual(gb.mmu.read(0x4000), 0xCD)
        gb.mmu.write(0x2000, 0)
        self.assertEqual(gb.mmu.read(0x4000), 0xAB)


class PpuTests(unittest.TestCase):
    def test_tile_row_uses_bgp(self):
        code = bytes(
            [
                0x3E, 0x00, 0xE0, 0x40,
                0x21, 0x00, 0x80,
                0x3E, 0xFF, 0x22, 0x22,
                0x3E, 0xE4, 0xE0, 0x47,
                0x3E, 0x91, 0xE0, 0x40,
                0x18, 0xFE,
            ]
        )
        gb = _machine(code)
        loop = 0x150 + len(code) - 2
        for _ in range(30):
            if gb.cpu.pc == loop:
                break
            gb.cpu.step()
        self.assertEqual(gb.cpu.pc, loop)
        gb.run_frame()
        self.assertEqual(gb.ppu.fb[0], Z_PACK[3])
        self.assertEqual(gb.ppu.fb[160], Z_PACK[0])


class StateTests(unittest.TestCase):
    def test_state_restores_cpu_memory_and_bank(self):
        rom = bytearray(0x10000)
        rom[0x100] = 0x18
        rom[0x101] = 0xFE
        rom[0x147] = 0x13
        rom[0x149] = 0x03
        rom[0x4000] = 0x11
        rom[0x8000] = 0x22
        gb = GameBoy()
        gb.load(bytes(rom))
        gb.run_frame()
        gb.cpu.a = 0x42
        gb.mmu.wram[0][0] = 0xAB
        gb.mmu.mem[0xC000] = 0xAB
        gb.mmu.write(0x2000, 2)
        gb.mmu.write(0x0000, 0x0A)
        gb.mmu.write(0xA000, 0x5A)
        blob = gb.export_state()

        gb.cpu.a = 0
        gb.cpu.pc = 0x200
        gb.mmu.wram[0][0] = 0
        gb.mmu.mem[0xC000] = 0
        gb.mmu.write(0x2000, 1)
        gb.mmu.eram[0] = 0
        gb.import_state(blob)

        self.assertEqual(gb.cpu.a, 0x42)
        self.assertEqual(gb.cpu.pc, 0x100)
        self.assertEqual(gb.mmu.wram[0][0], 0xAB)
        self.assertEqual(gb.mmu.read(0xC000), 0xAB)
        self.assertEqual(gb.mmu.read(0x4000), 0x22)
        self.assertEqual(gb.mmu.read(0xA000), 0x5A)
        gb.run_frame()
        self.assertEqual(gb.cpu.pc, 0x100)

    def test_state_rejects_a_different_rom(self):
        first = bytearray(0x8000)
        first[0x14E] = 0x12
        second = bytearray(0x8000)
        second[0x14E] = 0x34
        gb = GameBoy()
        gb.load(bytes(first))
        blob = gb.export_state()
        gb.load(bytes(second))
        with self.assertRaises(ValueError):
            gb.import_state(blob)


class HardwareTests(unittest.TestCase):
    def test_timer_falls_on_the_selected_bit(self):
        gb = GameBoy()
        gb.timer.div = 1023
        gb.timer.tac = 0x04
        gb.timer.tima = 0
        gb.timer.tick(1)
        self.assertEqual(gb.timer.tima, 1)
        gb.timer.tick(1)
        self.assertEqual(gb.timer.tima, 1)

    def test_joypad_buttons(self):
        gb = GameBoy()
        gb.joypad.write(0x10)
        gb.joypad.set_button(0x01, True)
        self.assertEqual(gb.joypad.read(), 0xDE)

    def test_frames_are_fast_enough_to_play(self):
        rom = bytearray(0x8000)
        rom[0x100] = 0x18
        rom[0x101] = 0xFE
        gb = GameBoy()
        gb.load(bytes(rom))
        frames = 20
        started = time.perf_counter()
        for _ in range(frames):
            gb.run_frame()
        elapsed = time.perf_counter() - started
        fps = frames / elapsed
        print(f"\nemulated frames/sec: {fps:.1f}")
        self.assertGreaterEqual(fps, 30)


if __name__ == "__main__":
    unittest.main()
