"""Timer, joypad, and the machine that runs one frame at a time."""

from __future__ import annotations

from pokemongb.apu import APU
from pokemongb.cheats import gb_effect
from pokemongb.cpu import CPU
from pokemongb.mmu import MMU
from pokemongb.ppu import PPU
from pokemongb.state import export_state, import_state


class Timer:
    _BITS = (9, 3, 5, 7)

    def __init__(self, gb):
        self.gb = gb
        self.div = 0
        self.tima = 0
        self.tma = 0
        self.tac = 0xF8

    def reset(self) -> None:
        self.div = 0xAB00
        self.tima = 0
        self.tma = 0
        self.tac = 0xF8

    def read_div(self) -> int:
        return (self.div >> 8) & 0xFF

    def write_div(self) -> None:
        bit = self._BITS[self.tac & 3]
        if (self.tac & 4) and (self.div & (1 << bit)):
            self._inc(1)
        self.div = 0

    def tick(self, cycles: int) -> None:
        if cycles <= 0:
            return
        bit = self._BITS[self.tac & 3]
        start = self.div
        self.div = (self.div + cycles) & 0xFFFF
        if (self.tac & 4) == 0:
            return
        period = 1 << (bit + 1)
        begin = start + 1
        end = start + cycles
        edges = end // period - (begin - 1) // period
        if edges:
            self._inc(edges)

    def _inc(self, count: int) -> None:
        value = self.tima + count
        while value > 0xFF:
            value = self.tma + (value - 256)
            self.gb.mmu.iff |= 0x04
        self.tima = value & 0xFF


class Joypad:
    def __init__(self, gb):
        self.gb = gb
        self.select = 0x30
        self.dirs = 0
        self.buttons = 0

    def reset(self) -> None:
        self.select = 0x30
        self.dirs = 0
        self.buttons = 0

    def write(self, value: int) -> None:
        self.select = value & 0x30

    def read(self) -> int:
        low = 0x0F
        if (self.select & 0x10) == 0:
            low &= (~self.dirs) & 0x0F
        if (self.select & 0x20) == 0:
            low &= (~self.buttons) & 0x0F
        return (self.select & 0x30) | 0xC0 | low

    def set_dir(self, bit: int, down: bool) -> None:
        self._set("dirs", bit, down)

    def set_button(self, bit: int, down: bool) -> None:
        self._set("buttons", bit, down)

    def _set(self, name: str, bit: int, down: bool) -> None:
        current = getattr(self, name)
        if down:
            if (current & bit) == 0:
                self.gb.mmu.iff |= 0x10
            setattr(self, name, current | bit)
        else:
            setattr(self, name, current & ~bit)


class GameBoy:
    def __init__(self):
        self.cgb = False
        self.double_speed = False
        self._credit = 0
        self.serial_cc = 0
        self.mmu = MMU(self)
        self.ppu = PPU(self)
        self.apu = APU(self)
        self.timer = Timer(self)
        self.joypad = Joypad(self)
        self.cpu = CPU(self)
        self.ram_cheats: list[tuple[int, int]] = []
        self.link_in: int | None = None

    def export_state(self) -> bytes:
        return export_state(self)

    def import_state(self, blob: bytes) -> None:
        import_state(self, blob)

    def load(self, rom: bytes) -> None:
        self.double_speed = False
        self._credit = 0
        self.serial_cc = 0
        self.ram_cheats = []
        self.link_in = None
        self.mmu.load(rom)
        self.cpu.reset(self.cgb)
        self.ppu.reset(self.cgb)
        self.apu.reset()
        self.timer.reset()
        self.joypad.reset()

    def set_cheats(self, items: list[tuple[str, str]]) -> None:
        genie: dict[int, tuple[int, int | None]] = {}
        ram: list[tuple[int, int]] = []
        for code, kind in items:
            effect = gb_effect(code, kind)
            if effect is None:
                continue
            mode, address, value, compare = effect
            if mode == "rom":
                genie[address] = (value, compare)
            else:
                ram.append((address, value))
        self.mmu.genie = genie
        self.ram_cheats = ram

    def _complete_serial(self) -> None:
        """Finish one link-cable byte. With no peer, the line reads as 0xFF."""
        self.mmu.sc &= 0x7F
        self.mmu.sb = 0xFF if self.link_in is None else self.link_in & 0xFF
        self.mmu.iff |= 0x08

    def run_frame(self) -> None:
        if self.ram_cheats:
            write = self.mmu.write
            for address, value in self.ram_cheats:
                write(address, value)
        ppu = self.ppu
        mmu = self.mmu
        step = self.cpu.step
        timer_tick = self.timer.tick
        ppu_tick = ppu.tick
        apu_tick = self.apu.tick
        ppu.frame_ready = False
        credit = self._credit
        double = self.double_speed
        audio = 0
        serial = self.serial_cc
        guard = 0
        idle = 0
        while not ppu.frame_ready and guard < 1_000_000:
            cycles = step()
            if cycles < 4:
                cycles = 4
            timer_tick(cycles)
            if double:
                credit += cycles
                dots = credit >> 1
                credit &= 1
            else:
                dots = cycles
            if dots:
                if (mmu.sc & 0x81) == 0x81:
                    serial += dots
                    if serial >= 4096:
                        serial -= 4096
                        self._complete_serial()
                ppu_tick(dots)
                audio += dots
                if audio >= 456:
                    apu_tick(audio)
                    audio = 0
                if ppu.lcdc & 0x80:
                    idle = 0
                else:
                    idle += dots
                    if idle >= 70224:
                        break
            guard += 1
        if audio:
            apu_tick(audio)
        self._credit = credit
        self.serial_cc = serial
        if guard >= 1_000_000 and not ppu.frame_ready and (ppu.lcdc & 0x80):
            raise RuntimeError(
                f"frame stalled at pc={self.cpu.pc:04X} ly={ppu.ly} lcdc={ppu.lcdc:02X}"
            )
