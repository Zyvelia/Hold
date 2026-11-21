"""Memory map, cartridge banking, and I/O dispatch."""

from __future__ import annotations

import time

from pokemongb.cart import has_battery, has_rtc, mbc_kind, mbc_name, ram_bytes


class MMU:
    def __init__(self, gb):
        self.gb = gb
        self.mem = bytearray(0x10000)
        self.rom = b""
        self.eram = bytearray()
        self.vram = [bytearray(0x2000), bytearray(0x2000)]
        self.wram = [bytearray(0x1000) for _ in range(8)]
        self.kind = 0
        self.cart_type = 0
        self.rom_banks = 2
        self.rom_bank = 1
        self.rom_bank0 = 0
        self.ram_bank = 0
        self.vram_bank = 0
        self.wram_bank = 1
        self.ram_enable = False
        self.has_ram = False
        self.has_rtc = False
        self.has_battery = False
        self.bank_low = 1
        self.bank_high = 0
        self.mode = 0
        self.rtc_mapped = False
        self.rtc_reg = 0x08
        self.rtc_latch = 0
        self.rtc_zero = time.time()
        self.rtc_halt = False
        self.rtc_carry = False
        self.rtc_frozen = [0, 0, 0, 0, 0]
        self.rtc_latched = [0, 0, 0, 0, 0]
        self.cgb = False
        self.ie = 0
        self.iff = 0x01
        self.sb = 0
        self.sc = 0x7E
        self.key1 = 0
        self.hdma1 = self.hdma2 = self.hdma3 = self.hdma4 = 0
        self.hdma_src = 0
        self.hdma_dst = 0x8000
        self.hdma_remain = 0
        self.hdma_active = False
        self.sram_dirty = False
        self.sram_touch = 0.0
        self.genie: dict[int, tuple[int, int | None]] = {}
        self.name = "ROM"

    def load(self, rom: bytes) -> None:
        if len(rom) % 0x4000:
            rom += bytes(0x4000 - (len(rom) % 0x4000))
        self.rom = rom
        self.genie = {}
        self.mem = bytearray(0x10000)
        self.vram = [bytearray(0x2000), bytearray(0x2000)]
        self.wram = [bytearray(0x1000) for _ in range(8)]
        self.cart_type = rom[0x147]
        self.kind = mbc_kind(self.cart_type)
        self.name = mbc_name(self.cart_type)
        self.cgb = bool(rom[0x143] & 0x80)
        self.gb.cgb = self.cgb
        self.rom_banks = max(1, len(rom) // 0x4000)
        self.rom_bank = 1 % self.rom_banks
        self.rom_bank0 = 0
        self.bank_low = 1
        self.bank_high = 0
        self.mode = 0
        size = ram_bytes(self.cart_type, rom[0x149])
        self.eram = bytearray(size)
        self.has_ram = size > 0
        self.has_rtc = has_rtc(self.cart_type)
        self.has_battery = has_battery(self.cart_type) or self.has_rtc
        self.ram_enable = False
        self.ram_bank = 0
        self.vram_bank = 0
        self.wram_bank = 1
        self.rtc_mapped = False
        self.rtc_reg = 0x08
        self.rtc_latch = 0
        self.rtc_zero = time.time()
        self.rtc_halt = False
        self.rtc_carry = False
        self.rtc_frozen = [0, 0, 0, 0, 0]
        self.rtc_latched = [0, 0, 0, 0, 0]
        self.ie = 0
        self.iff = 0x01
        self.sb = 0
        self.sc = 0x7E
        self.key1 = 0
        self.hdma_active = False
        self.hdma_remain = 0
        self.sram_dirty = False
        self.sram_touch = 0.0
        self._map_rom_low()
        self._map_rom_high()
        self.mem[0xA000:0xC000] = b"\xff" * 0x2000
        self.gb.cpu.mem = self.mem

    def read(self, addr: int) -> int:
        addr &= 0xFFFF
        if addr < 0xFE00:
            if addr < 0x8000 and self.genie:
                hit = self.genie.get(addr)
                if hit is not None:
                    value, compare = hit
                    raw = self.mem[addr]
                    if compare is None or raw == compare:
                        return value
            if 0xA000 <= addr <= 0xBFFF:
                return self._read_eram(addr)
            return self.mem[addr]
        if addr < 0xFEA0:
            return self.mem[addr]
        if addr < 0xFF00:
            return 0xFF
        if addr == 0xFFFF:
            return self.ie
        if addr >= 0xFF80:
            return self.mem[addr]
        return self._read_io(addr)

    def write(self, addr: int, value: int) -> None:
        addr &= 0xFFFF
        value &= 0xFF
        if addr < 0x8000:
            self._mbc_write(addr, value)
            return
        if addr < 0xA000:
            self.vram[self.vram_bank][addr - 0x8000] = value
            self.mem[addr] = value
            return
        if addr < 0xC000:
            self._write_eram(addr, value)
            return
        if addr < 0xE000:
            self._write_wram(addr, value)
            return
        if addr < 0xFE00:
            self._write_wram(addr - 0x2000, value)
            return
        if addr < 0xFEA0:
            self.mem[addr] = value
            return
        if addr < 0xFF00:
            return
        if addr == 0xFFFF:
            self.ie = value
            return
        if addr >= 0xFF80:
            self.mem[addr] = value
            return
        self._write_io(addr, value)

    def import_ram(self, data: bytes) -> None:
        if not self.eram:
            return
        n = min(len(data), len(self.eram))
        self.eram[:n] = data[:n]
        self.ram_enable = True
        self._map_ram()
        self.sram_dirty = False

    def import_rtc(self, info: dict) -> None:
        self.rtc_zero = float(info.get("zero", time.time()))
        self.rtc_halt = bool(info.get("halt", False))
        self.rtc_carry = bool(info.get("carry", False))
        frozen = info.get("frozen") or [0, 0, 0, 0, 0]
        self.rtc_frozen = [int(x) & 0xFF for x in frozen[:5]]
        while len(self.rtc_frozen) < 5:
            self.rtc_frozen.append(0)
        self.rtc_latched = self._live_rtc()

    def _read_eram(self, addr: int) -> int:
        if self.kind == 2:
            if not self.ram_enable:
                return 0xFF
            return self.eram[(addr - 0xA000) & 0x1FF] | 0xF0
        if self.rtc_mapped and self.ram_enable:
            return self.rtc_latched[self.rtc_reg - 8] & 0xFF
        if not self.ram_enable or not self.eram:
            return 0xFF
        return self.mem[addr]

    def _write_eram(self, addr: int, value: int) -> None:
        if self.kind == 2:
            if not self.ram_enable:
                return
            self.eram[(addr - 0xA000) & 0x1FF] = value & 0x0F
            self.sram_dirty = True
            self.sram_touch = time.time()
            return
        if self.rtc_mapped and self.ram_enable:
            self._write_rtc(value)
            return
        if not self.ram_enable or not self.eram:
            return
        off = addr - 0xA000
        if len(self.eram) == 0x800:
            self.eram[off & 0x7FF] = value
            self._map_ram()
        else:
            index = self.ram_bank * 0x2000 + off
            if index < len(self.eram):
                self.eram[index] = value
            self.mem[addr] = value
        self.sram_dirty = True
        self.sram_touch = time.time()

    def _write_wram(self, addr: int, value: int) -> None:
        if addr < 0xD000:
            self.wram[0][addr - 0xC000] = value
        else:
            self.wram[self.wram_bank][addr - 0xD000] = value
        self.mem[addr] = value
        echo = addr + 0x2000
        if echo < 0xFE00:
            self.mem[echo] = value

    def _mbc_write(self, addr: int, value: int) -> None:
        kind = self.kind
        if kind == 0:
            return
        if kind == 2:
            if addr < 0x4000:
                if addr & 0x0100:
                    bank = value & 0x0F
                    self.rom_bank = bank or 1
                    self.rom_bank %= self.rom_banks
                    self._map_rom_high()
                else:
                    self.ram_enable = (value & 0x0F) == 0x0A
            return
        if addr < 0x2000:
            self.ram_enable = (value & 0x0F) == 0x0A
            if not self.rtc_mapped:
                self._map_ram()
            return
        if addr < 0x4000:
            if kind == 1:
                self.bank_low = value & 0x1F
                self._map_rom_mbc1()
            elif kind == 5:
                if addr < 0x3000:
                    self.rom_bank = (self.rom_bank & 0x100) | value
                else:
                    self.rom_bank = (self.rom_bank & 0xFF) | ((value & 1) << 8)
                self.rom_bank %= self.rom_banks
                self._map_rom_high()
            else:
                bank = value & 0x7F
                self.rom_bank = 1 if bank == 0 else bank
                self.rom_bank %= self.rom_banks
                self._map_rom_high()
            return
        if addr < 0x6000:
            if kind == 1:
                self.bank_high = value & 3
                self._map_rom_mbc1()
                self._map_ram()
            elif kind == 5:
                self.ram_bank = value & 0x0F
                self._map_ram()
            elif value <= 0x03:
                self.rtc_mapped = False
                self.ram_bank = value
                self._map_ram()
            elif 0x08 <= value <= 0x0C:
                self.rtc_mapped = True
                self.rtc_reg = value
            return
        if kind == 1:
            self.mode = value & 1
            self._map_rom_mbc1()
            self._map_ram()
        elif kind == 3 and self.has_rtc:
            if self.rtc_latch == 0 and (value & 1):
                self.rtc_latched = self._live_rtc()
            self.rtc_latch = value & 1

    def _map_rom_mbc1(self) -> None:
        low = self.bank_low & 0x1F or 1
        high = self.bank_high & 3
        if self.mode == 0:
            bank0 = 0
            bankn = (high << 5) | low
        else:
            bank0 = high << 5
            bankn = low
        self.rom_bank0 = bank0 % self.rom_banks
        self.rom_bank = bankn % self.rom_banks
        self._map_rom_low()
        self._map_rom_high()

    def _map_rom_low(self) -> None:
        start = self.rom_bank0 * 0x4000
        self.mem[0:0x4000] = self.rom[start : start + 0x4000]

    def _map_rom_high(self) -> None:
        start = self.rom_bank * 0x4000
        self.mem[0x4000:0x8000] = self.rom[start : start + 0x4000]

    def _map_ram(self) -> None:
        if self.kind == 1:
            self.ram_bank = (self.bank_high & 3) if self.mode == 1 else 0
        if not self.eram or not self.ram_enable or self.rtc_mapped:
            self.mem[0xA000:0xC000] = b"\xff" * 0x2000
            return
        if len(self.eram) == 0x800:
            block = bytes(self.eram)
            self.mem[0xA000:0xC000] = (block * 4)[:0x2000]
            return
        banks = max(1, len(self.eram) // 0x2000)
        self.ram_bank %= banks
        start = self.ram_bank * 0x2000
        self.mem[0xA000:0xC000] = self.eram[start : start + 0x2000]

    def _map_vram(self) -> None:
        self.mem[0x8000:0xA000] = self.vram[self.vram_bank]

    def _map_wram(self) -> None:
        bank = self.wram_bank or 1
        self.wram_bank = bank
        self.mem[0xD000:0xE000] = self.wram[bank]
        self.mem[0xF000:0xFE00] = self.wram[bank][:0xE00]

    def _live_rtc(self) -> list[int]:
        if self.rtc_halt:
            regs = self.rtc_frozen[:]
            regs[4] = (regs[4] & 0xC1) | 0x40
            return regs
        elapsed = max(0, int(time.time() - self.rtc_zero))
        days = elapsed // 86400
        carry = self.rtc_carry or days > 511
        days &= 511
        rem = elapsed % 86400
        return [
            rem % 60,
            (rem // 60) % 60,
            (rem // 3600) % 24,
            days & 0xFF,
            ((days >> 8) & 1) | (0x80 if carry else 0),
        ]

    def _write_rtc(self, value: int) -> None:
        regs = self._live_rtc()
        idx = self.rtc_reg - 8
        regs[idx] = value
        if idx == 4:
            self.rtc_halt = bool(value & 0x40)
            self.rtc_carry = bool(value & 0x80)
        days = (regs[3] & 0xFF) | ((regs[4] & 1) << 8)
        total = (((days * 24 + (regs[2] & 31)) * 60 + (regs[1] & 63)) * 60 + (regs[0] & 63))
        self.rtc_frozen = regs
        if not self.rtc_halt:
            self.rtc_zero = time.time() - total
        self.rtc_latched = regs[:]
        self.sram_dirty = True
        self.sram_touch = time.time()

    def _read_io(self, addr: int) -> int:
        gb = self.gb
        if addr == 0xFF00:
            return gb.joypad.read()
        if addr == 0xFF01:
            return self.sb
        if addr == 0xFF02:
            return (self.sc & 0x81) | 0x7E
        if addr == 0xFF04:
            return gb.timer.read_div()
        if addr == 0xFF05:
            return gb.timer.tima
        if addr == 0xFF06:
            return gb.timer.tma
        if addr == 0xFF07:
            return (gb.timer.tac & 0x07) | 0xF8
        if addr == 0xFF0F:
            return self.iff | 0xE0
        if 0xFF10 <= addr <= 0xFF3F:
            return gb.apu.read(addr)
        if 0xFF40 <= addr <= 0xFF4B:
            return gb.ppu.read(addr)
        if addr == 0xFF4D:
            if not self.cgb:
                return 0xFF
            return 0x7E | (self.key1 & 0x81)
        if addr == 0xFF4F:
            if not self.cgb:
                return 0xFF
            return 0xFE | self.vram_bank
        if 0xFF51 <= addr <= 0xFF54:
            return 0xFF
        if addr == 0xFF55:
            if not self.cgb:
                return 0xFF
            if not self.hdma_active:
                return 0xFF
            return ((self.hdma_remain >> 4) - 1) & 0x7F
        if 0xFF68 <= addr <= 0xFF6B:
            return gb.ppu.read(addr) if self.cgb else 0xFF
        if addr == 0xFF70:
            if not self.cgb:
                return 0xFF
            return 0xF8 | self.wram_bank
        return 0xFF

    def _write_io(self, addr: int, value: int) -> None:
        gb = self.gb
        if addr == 0xFF00:
            gb.joypad.write(value)
        elif addr == 0xFF01:
            self.sb = value
        elif addr == 0xFF02:
            self.sc = value & 0x81
            if self.sc == 0x81:
                gb.serial_cc = 0
        elif addr == 0xFF04:
            gb.timer.write_div()
        elif addr == 0xFF05:
            gb.timer.tima = value
        elif addr == 0xFF06:
            gb.timer.tma = value
        elif addr == 0xFF07:
            gb.timer.tac = value
        elif addr == 0xFF0F:
            self.iff = value & 0x1F
        elif 0xFF10 <= addr <= 0xFF3F:
            gb.apu.write(addr, value)
        elif addr == 0xFF46:
            self._dma(value)
        elif 0xFF40 <= addr <= 0xFF4B:
            gb.ppu.write(addr, value)
        elif addr == 0xFF4D and self.cgb:
            self.key1 = (self.key1 & 0x80) | (value & 0x01)
        elif addr == 0xFF4F and self.cgb:
            self.vram_bank = value & 1
            self._map_vram()
        elif addr == 0xFF51 and self.cgb:
            self.hdma1 = value
        elif addr == 0xFF52 and self.cgb:
            self.hdma2 = value
        elif addr == 0xFF53 and self.cgb:
            self.hdma3 = value
        elif addr == 0xFF54 and self.cgb:
            self.hdma4 = value
        elif addr == 0xFF55 and self.cgb:
            self._write_hdma5(value)
        elif 0xFF68 <= addr <= 0xFF6B and self.cgb:
            gb.ppu.write(addr, value)
        elif addr == 0xFF70 and self.cgb:
            bank = value & 0x07
            self.wram_bank = bank or 1
            self._map_wram()

    def _dma(self, value: int) -> None:
        src = value << 8
        mem = self.mem
        for index in range(0xA0):
            mem[0xFE00 + index] = self.read(src + index)

    def _write_hdma5(self, value: int) -> None:
        if self.hdma_active and (value & 0x80) == 0:
            self.hdma_active = False
            self.hdma_remain = 0
            return
        length = ((value & 0x7F) + 1) << 4
        self.hdma_src = ((self.hdma1 << 8) | (self.hdma2 & 0xF0)) & 0xFFFF
        self.hdma_dst = (((self.hdma3 & 0x1F) << 8) | (self.hdma4 & 0xF0)) | 0x8000
        if value & 0x80:
            self.hdma_active = True
            self.hdma_remain = length
        else:
            self._hdma_copy(length)
            self.hdma_active = False
            self.hdma_remain = 0

    def hdma_hblank(self) -> None:
        if not self.hdma_active or self.hdma_remain <= 0:
            return
        self._hdma_copy(0x10)
        self.hdma_remain -= 0x10
        if self.hdma_remain <= 0:
            self.hdma_active = False

    def _hdma_copy(self, length: int) -> None:
        src = self.hdma_src
        dst = self.hdma_dst
        for _ in range(length):
            self.write(dst, self.read(src))
            src = (src + 1) & 0xFFFF
            dst = (dst + 1) & 0xFFFF
        self.hdma_src = src
        self.hdma_dst = dst
