"""Sharp SM83 CPU. Timings are in T-cycles."""

from __future__ import annotations

Z = 0x80
N = 0x40
H = 0x20
C = 0x10


class CPU:
    __slots__ = (
        "gb",
        "mmu",
        "mem",
        "a",
        "f",
        "b",
        "c",
        "d",
        "e",
        "h",
        "l",
        "sp",
        "pc",
        "ime",
        "ei_delay",
        "halted",
        "halt_bug",
        "trace",
    )

    def __init__(self, gb):
        self.gb = gb
        self.mmu = gb.mmu
        self.mem = gb.mmu.mem
        self.a = self.f = self.b = self.c = 0
        self.d = self.e = self.h = self.l = 0
        self.sp = 0xFFFE
        self.pc = 0x0100
        self.ime = False
        self.ei_delay = False
        self.halted = False
        self.halt_bug = False
        self.trace = None

    def reset(self, cgb: bool) -> None:
        if cgb:
            self.a, self.f = 0x11, 0x80
            self.b, self.c = 0x00, 0x00
            self.d, self.e = 0xFF, 0x56
            self.h, self.l = 0x00, 0x0D
        else:
            self.a, self.f = 0x01, 0xB0
            self.b, self.c = 0x00, 0x13
            self.d, self.e = 0x00, 0xD8
            self.h, self.l = 0x01, 0x4D
        self.sp = 0xFFFE
        self.pc = 0x0100
        self.ime = False
        self.ei_delay = False
        self.halted = False
        self.halt_bug = False
        self.mem = self.mmu.mem

    def step(self) -> int:
        mmu = self.mmu
        pending = mmu.ie & mmu.iff & 0x1F
        if pending:
            if self.halted:
                self.halted = False
            if self.ime:
                return self._interrupt(pending)
        elif self.halted:
            return 4
        pc = self.pc
        if pc < 0xFE00 or 0xFF80 <= pc < 0xFFFF:
            op = self.mem[pc]
        else:
            op = mmu.read(pc)
        if self.halt_bug:
            self.halt_bug = False
        else:
            self.pc = (pc + 1) & 0xFFFF
        trace = self.trace
        if trace is not None:
            trace(pc, op)
        if op == 0x00:
            if self.ei_delay:
                self.ime = True
                self.ei_delay = False
            return 4
        cycles = self._exec(op)
        if self.ei_delay:
            self.ime = True
            self.ei_delay = False
        return cycles

    def _interrupt(self, pending: int) -> int:
        self.ime = False
        self.halted = False
        self.ei_delay = False
        mmu = self.mmu
        for bit in range(5):
            if pending & (1 << bit):
                mmu.iff &= ~(1 << bit)
                self._push(self.pc)
                self.pc = 0x40 + (bit << 3)
                return 20
        return 4

    def _fetch(self) -> int:
        pc = self.pc
        if pc < 0xFE00 or 0xFF80 <= pc < 0xFFFF:
            op = self.mem[pc]
        else:
            op = self.mmu.read(pc)
        if self.halt_bug:
            self.halt_bug = False
        else:
            self.pc = (pc + 1) & 0xFFFF
        return op

    def _read(self, addr: int) -> int:
        return self.mmu.read(addr)

    def _write(self, addr: int, value: int) -> None:
        self.mmu.write(addr, value)

    def _hl(self) -> int:
        return (self.h << 8) | self.l

    def _set_hl(self, value: int) -> None:
        self.h = (value >> 8) & 0xFF
        self.l = value & 0xFF

    def _bc(self) -> int:
        return (self.b << 8) | self.c

    def _set_bc(self, value: int) -> None:
        self.b = (value >> 8) & 0xFF
        self.c = value & 0xFF

    def _de(self) -> int:
        return (self.d << 8) | self.e

    def _set_de(self, value: int) -> None:
        self.d = (value >> 8) & 0xFF
        self.e = value & 0xFF

    def _push(self, value: int) -> None:
        sp = (self.sp - 1) & 0xFFFF
        self.mmu.write(sp, (value >> 8) & 0xFF)
        sp = (sp - 1) & 0xFFFF
        self.mmu.write(sp, value & 0xFF)
        self.sp = sp

    def _pop(self) -> int:
        sp = self.sp
        lo = self.mmu.read(sp)
        sp = (sp + 1) & 0xFFFF
        hi = self.mmu.read(sp)
        self.sp = (sp + 1) & 0xFFFF
        return (hi << 8) | lo

    def _get_r(self, index: int) -> int:
        if index == 0:
            return self.b
        if index == 1:
            return self.c
        if index == 2:
            return self.d
        if index == 3:
            return self.e
        if index == 4:
            return self.h
        if index == 5:
            return self.l
        if index == 6:
            return self._read(self._hl())
        return self.a

    def _set_r(self, index: int, value: int) -> None:
        value &= 0xFF
        if index == 0:
            self.b = value
        elif index == 1:
            self.c = value
        elif index == 2:
            self.d = value
        elif index == 3:
            self.e = value
        elif index == 4:
            self.h = value
        elif index == 5:
            self.l = value
        elif index == 6:
            self._write(self._hl(), value)
        else:
            self.a = value

    def _get_rp(self, pair: int) -> int:
        if pair == 0:
            return self._bc()
        if pair == 1:
            return self._de()
        if pair == 2:
            return self._hl()
        return self.sp

    def _set_rp(self, pair: int, value: int) -> None:
        value &= 0xFFFF
        if pair == 0:
            self._set_bc(value)
        elif pair == 1:
            self._set_de(value)
        elif pair == 2:
            self._set_hl(value)
        else:
            self.sp = value

    def _get_rp2(self, pair: int) -> int:
        if pair == 0:
            return self._bc()
        if pair == 1:
            return self._de()
        if pair == 2:
            return self._hl()
        return (self.a << 8) | self.f

    def _set_rp2(self, pair: int, value: int) -> None:
        if pair == 0:
            self._set_bc(value)
        elif pair == 1:
            self._set_de(value)
        elif pair == 2:
            self._set_hl(value)
        else:
            self.a = (value >> 8) & 0xFF
            self.f = value & 0xF0

    def _cond(self, cc: int) -> bool:
        if cc == 0:
            return (self.f & Z) == 0
        if cc == 1:
            return (self.f & Z) != 0
        if cc == 2:
            return (self.f & C) == 0
        return (self.f & C) != 0

    def _add(self, value: int, carry: bool = False) -> None:
        cin = 1 if carry and (self.f & C) else 0
        a = self.a
        result = a + value + cin
        flags = 0
        if (result & 0xFF) == 0:
            flags |= Z
        if ((a & 0x0F) + (value & 0x0F) + cin) > 0x0F:
            flags |= H
        if result > 0xFF:
            flags |= C
        self.a = result & 0xFF
        self.f = flags

    def _sub(self, value: int, carry: bool = False) -> None:
        cin = 1 if carry and (self.f & C) else 0
        a = self.a
        result = a - value - cin
        flags = N
        if (result & 0xFF) == 0:
            flags |= Z
        if (a & 0x0F) < ((value & 0x0F) + cin):
            flags |= H
        if result < 0:
            flags |= C
        self.a = result & 0xFF
        self.f = flags

    def _alu(self, op: int, value: int) -> None:
        if op == 0:
            self._add(value)
        elif op == 1:
            self._add(value, True)
        elif op == 2:
            self._sub(value)
        elif op == 3:
            self._sub(value, True)
        elif op == 4:
            self.a &= value
            self.f = H | (Z if self.a == 0 else 0)
        elif op == 5:
            self.a ^= value
            self.f = Z if self.a == 0 else 0
        elif op == 6:
            self.a |= value
            self.f = Z if self.a == 0 else 0
        else:
            self._cp(value)

    def _cp(self, value: int) -> None:
        a = self.a
        result = a - value
        flags = N
        if (result & 0xFF) == 0:
            flags |= Z
        if (a & 0x0F) < (value & 0x0F):
            flags |= H
        if result < 0:
            flags |= C
        self.f = flags

    def _inc_r(self, index: int) -> int:
        value = self._get_r(index)
        result = (value + 1) & 0xFF
        flags = self.f & C
        if result == 0:
            flags |= Z
        if (value & 0x0F) == 0x0F:
            flags |= H
        self.f = flags
        self._set_r(index, result)
        return 12 if index == 6 else 4

    def _dec_r(self, index: int) -> int:
        value = self._get_r(index)
        result = (value - 1) & 0xFF
        flags = (self.f & C) | N
        if result == 0:
            flags |= Z
        if (value & 0x0F) == 0:
            flags |= H
        self.f = flags
        self._set_r(index, result)
        return 12 if index == 6 else 4

    def _add_hl(self, value: int) -> None:
        hl = self._hl()
        result = hl + value
        flags = self.f & Z
        if ((hl & 0x0FFF) + (value & 0x0FFF)) > 0x0FFF:
            flags |= H
        if result > 0xFFFF:
            flags |= C
        self.f = flags
        self._set_hl(result)

    def _add_sp_e(self, offset: int) -> int:
        signed = offset if offset < 128 else offset - 256
        sp = self.sp
        flags = 0
        if ((sp & 0x0F) + (offset & 0x0F)) > 0x0F:
            flags |= H
        if ((sp & 0xFF) + (offset & 0xFF)) > 0xFF:
            flags |= C
        self.f = flags
        return (sp + signed) & 0xFFFF

    def _daa(self) -> None:
        a = self.a
        n = bool(self.f & N)
        h = bool(self.f & H)
        carry = bool(self.f & C)
        if not n:
            if h or (a & 0x0F) > 9:
                a += 0x06
            if carry or a > 0x9F:
                a += 0x60
                carry = True
        else:
            corr = 0
            if h:
                corr |= 0x06
            if carry:
                corr |= 0x60
            a = (a - corr) & 0xFF
        a &= 0xFF
        self.a = a
        flags = 0
        if a == 0:
            flags |= Z
        if n:
            flags |= N
        if carry:
            flags |= C
        self.f = flags

    def _jr(self, take: bool) -> int:
        offset = self._fetch()
        if not take:
            return 8
        signed = offset if offset < 128 else offset - 256
        self.pc = (self.pc + signed) & 0xFFFF
        return 12

    def _jp(self, take: bool) -> int:
        lo = self._fetch()
        hi = self._fetch()
        if not take:
            return 12
        self.pc = (hi << 8) | lo
        return 16

    def _call(self, take: bool) -> int:
        lo = self._fetch()
        hi = self._fetch()
        if not take:
            return 12
        self._push(self.pc)
        self.pc = (hi << 8) | lo
        return 24

    def _halt(self) -> int:
        if not self.ime and (self.mmu.ie & self.mmu.iff & 0x1F):
            self.halt_bug = True
        else:
            self.halted = True
        return 4

    def _stop(self) -> int:
        self.pc = (self.pc + 1) & 0xFFFF
        mmu = self.mmu
        if self.gb.cgb and (mmu.key1 & 0x01):
            mmu.key1 ^= 0x80
            mmu.key1 &= 0xFE
            self.gb.double_speed = bool(mmu.key1 & 0x80)
        return 4

    def _exec(self, op: int) -> int:
        if op == 0xCB:
            return self._cb(self._fetch())
        x = op >> 6
        y = (op >> 3) & 7
        z = op & 7
        if x == 1:
            if op == 0x76:
                return self._halt()
            value = self._get_r(z)
            self._set_r(y, value)
            return 8 if y == 6 or z == 6 else 4
        if x == 2:
            self._alu(y, self._get_r(z))
            return 8 if z == 6 else 4
        if x == 0:
            return self._x0(y, z)
        return self._x3(y, z)

    def _x0(self, y: int, z: int) -> int:
        if z == 0:
            if y == 0:
                return 4
            if y == 1:
                addr = self._fetch() | (self._fetch() << 8)
                self._write(addr, self.sp & 0xFF)
                self._write((addr + 1) & 0xFFFF, (self.sp >> 8) & 0xFF)
                return 20
            if y == 2:
                return self._stop()
            if y == 3:
                return self._jr(True)
            return self._jr(self._cond(y - 4))
        if z == 1:
            pair = y >> 1
            if (y & 1) == 0:
                self._set_rp(pair, self._fetch() | (self._fetch() << 8))
                return 12
            self._add_hl(self._get_rp(pair))
            return 8
        if z == 2:
            if y == 0:
                self._write(self._bc(), self.a)
            elif y == 1:
                self.a = self._read(self._bc())
            elif y == 2:
                self._write(self._de(), self.a)
            elif y == 3:
                self.a = self._read(self._de())
            elif y == 4:
                hl = self._hl()
                self._write(hl, self.a)
                self._set_hl((hl + 1) & 0xFFFF)
            elif y == 5:
                hl = self._hl()
                self.a = self._read(hl)
                self._set_hl((hl + 1) & 0xFFFF)
            elif y == 6:
                hl = self._hl()
                self._write(hl, self.a)
                self._set_hl((hl - 1) & 0xFFFF)
            else:
                hl = self._hl()
                self.a = self._read(hl)
                self._set_hl((hl - 1) & 0xFFFF)
            return 8
        if z == 3:
            pair = y >> 1
            value = self._get_rp(pair)
            if (y & 1) == 0:
                value = (value + 1) & 0xFFFF
            else:
                value = (value - 1) & 0xFFFF
            self._set_rp(pair, value)
            return 8
        if z == 4:
            return self._inc_r(y)
        if z == 5:
            return self._dec_r(y)
        if z == 6:
            self._set_r(y, self._fetch())
            return 12 if y == 6 else 8
        if y == 0:
            carry = (self.a >> 7) & 1
            self.a = ((self.a << 1) | carry) & 0xFF
            self.f = C if carry else 0
        elif y == 1:
            carry = self.a & 1
            self.a = (self.a >> 1) | (carry << 7)
            self.f = C if carry else 0
        elif y == 2:
            carry = (self.a >> 7) & 1
            old = 1 if self.f & C else 0
            self.a = ((self.a << 1) | old) & 0xFF
            self.f = C if carry else 0
        elif y == 3:
            carry = self.a & 1
            old = 1 if self.f & C else 0
            self.a = (self.a >> 1) | (old << 7)
            self.f = C if carry else 0
        elif y == 4:
            self._daa()
        elif y == 5:
            self.a ^= 0xFF
            self.f = (self.f & (Z | C)) | N | H
        elif y == 6:
            self.f = (self.f & Z) | C
        else:
            self.f = (self.f & Z) | (0 if self.f & C else C)
        return 4

    def _x3(self, y: int, z: int) -> int:
        if z == 0:
            if y < 4:
                take = self._cond(y)
                if not take:
                    return 8
                self.pc = self._pop()
                return 20
            if y == 4:
                self._write(0xFF00 | self._fetch(), self.a)
                return 12
            if y == 5:
                self.sp = self._add_sp_e(self._fetch())
                return 16
            if y == 6:
                self.a = self._read(0xFF00 | self._fetch())
                return 12
            self._set_hl(self._add_sp_e(self._fetch()))
            return 12
        if z == 1:
            pair = y >> 1
            if (y & 1) == 0:
                self._set_rp2(pair, self._pop())
                return 12
            if pair == 0:
                self.pc = self._pop()
                return 16
            if pair == 1:
                self.pc = self._pop()
                self.ime = True
                self.ei_delay = False
                return 16
            if pair == 2:
                self.pc = self._hl()
                return 4
            self.sp = self._hl()
            return 8
        if z == 2:
            if y < 4:
                return self._jp(self._cond(y))
            if y == 4:
                self._write(0xFF00 | self.c, self.a)
                return 8
            if y == 5:
                addr = self._fetch() | (self._fetch() << 8)
                self._write(addr, self.a)
                return 16
            if y == 6:
                self.a = self._read(0xFF00 | self.c)
                return 8
            addr = self._fetch() | (self._fetch() << 8)
            self.a = self._read(addr)
            return 16
        if z == 3:
            if y == 0:
                return self._jp(True)
            if y == 6:
                self.ime = False
                self.ei_delay = False
                return 4
            if y == 7:
                self.ei_delay = True
                return 4
            return 4
        if z == 4:
            if y < 4:
                return self._call(self._cond(y))
            return 4
        if z == 5:
            pair = y >> 1
            if (y & 1) == 0:
                self._push(self._get_rp2(pair))
                return 16
            if pair == 0:
                return self._call(True)
            return 4
        if z == 6:
            self._alu(y, self._fetch())
            return 8
        self._push(self.pc)
        self.pc = y << 3
        return 16

    def _cb(self, op: int) -> int:
        x = op >> 6
        y = (op >> 3) & 7
        z = op & 7
        value = self._get_r(z)
        if x == 0:
            value = self._rotate(y, value)
            self._set_r(z, value)
            return 16 if z == 6 else 8
        if x == 1:
            flags = self.f & C
            flags |= H
            if (value & (1 << y)) == 0:
                flags |= Z
            self.f = flags
            return 12 if z == 6 else 8
        if x == 2:
            self._set_r(z, value & ~(1 << y))
        else:
            self._set_r(z, value | (1 << y))
        return 16 if z == 6 else 8

    def _rotate(self, kind: int, value: int) -> int:
        if kind == 0:  # RLC
            carry = (value >> 7) & 1
            value = ((value << 1) | carry) & 0xFF
        elif kind == 1:  # RRC
            carry = value & 1
            value = (value >> 1) | (carry << 7)
        elif kind == 2:  # RL
            carry = (value >> 7) & 1
            old = 1 if self.f & C else 0
            value = ((value << 1) | old) & 0xFF
        elif kind == 3:  # RR
            carry = value & 1
            old = 1 if self.f & C else 0
            value = (value >> 1) | (old << 7)
        elif kind == 4:  # SLA
            carry = (value >> 7) & 1
            value = (value << 1) & 0xFF
        elif kind == 5:  # SRA
            carry = value & 1
            value = (value >> 1) | (value & 0x80)
        elif kind == 6:  # SWAP
            value = ((value & 0x0F) << 4) | (value >> 4)
            self.f = Z if value == 0 else 0
            return value
        else:  # SRL
            carry = value & 1
            value = value >> 1
        self.f = (Z if value == 0 else 0) | (C if carry else 0)
        return value
