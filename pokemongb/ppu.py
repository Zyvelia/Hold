"""Scanline PPU. One dot is one T-cycle in normal speed."""

from __future__ import annotations

import array

Z_PACK = (
    0xFFE0F8D0,
    0xFF88C070,
    0xFF346856,
    0xFF081820,
)


def _build_tables() -> tuple[list[bytes], list[bytes]]:
    straight = [b""] * 65536
    flipped = [b""] * 65536
    for hi in range(256):
        for lo in range(256):
            row = bytearray(8)
            for bit in range(8):
                src = 7 - bit
                row[bit] = (((hi >> src) & 1) << 1) | ((lo >> src) & 1)
            key = (hi << 8) | lo
            straight[key] = bytes(row)
            flipped[key] = bytes(reversed(row))
    return straight, flipped


EXPAND, HEXPAND = _build_tables()


def _tile_addr(tile: int, unsigned: bool) -> int:
    if unsigned:
        return tile << 4
    if tile < 128:
        return 0x1000 + (tile << 4)
    return 0x1000 - ((256 - tile) << 4)


def _pack555(word: int) -> int:
    r = word & 31
    g = (word >> 5) & 31
    b = (word >> 10) & 31
    return (
        0xFF000000
        | (((r << 3) | (r >> 2)) << 16)
        | (((g << 3) | (g >> 2)) << 8)
        | ((b << 3) | (b >> 2))
    )


def _paint8(line, index, pri, x, colors, pal, pri_bit) -> None:
    c0, c1, c2, c3, c4, c5, c6, c7 = colors
    line[x] = pal[c0]
    line[x + 1] = pal[c1]
    line[x + 2] = pal[c2]
    line[x + 3] = pal[c3]
    line[x + 4] = pal[c4]
    line[x + 5] = pal[c5]
    line[x + 6] = pal[c6]
    line[x + 7] = pal[c7]
    index[x] = c0
    index[x + 1] = c1
    index[x + 2] = c2
    index[x + 3] = c3
    index[x + 4] = c4
    index[x + 5] = c5
    index[x + 6] = c6
    index[x + 7] = c7
    pri[x] = pri_bit
    pri[x + 1] = pri_bit
    pri[x + 2] = pri_bit
    pri[x + 3] = pri_bit
    pri[x + 4] = pri_bit
    pri[x + 5] = pri_bit
    pri[x + 6] = pri_bit
    pri[x + 7] = pri_bit


class PPU:
    def __init__(self, gb):
        self.gb = gb
        self.fb = array.array("I", [Z_PACK[0]] * (160 * 144))
        self.line = array.array("I", [Z_PACK[0]] * 160)
        self.bg_index = bytearray(160)
        self.bg_pri = bytearray(160)
        self.lcdc = 0x91
        self.stat = 0
        self.scy = 0
        self.scx = 0
        self.ly = 0
        self.lyc = 0
        self.bgp = 0xFC
        self.obp0 = 0xFF
        self.obp1 = 0xFF
        self.wy = 0
        self.wx = 0
        self.mode = 2
        self.line_cycles = 0
        self.window_line = 0
        self.window_active = False
        self.frame_ready = False
        self._stat_line = False
        self.cgb = False
        self.dmg_bg = list(Z_PACK)
        self.dmg_obp0 = list(Z_PACK)
        self.dmg_obp1 = list(Z_PACK)
        self.bg_cram = bytearray(64)
        self.obj_cram = bytearray(64)
        self.bgpi = 0
        self.obpi = 0
        self.cgb_bg = [[Z_PACK[3]] * 4 for _ in range(8)]
        self.cgb_obj = [[Z_PACK[3]] * 4 for _ in range(8)]
        self._rebuild_dmg()

    def reset(self, cgb: bool) -> None:
        self.cgb = cgb
        blank = Z_PACK[0]
        for i in range(160 * 144):
            self.fb[i] = blank
        self.lcdc = 0x91
        self.stat = 0
        self.scy = 0
        self.scx = 0
        self.ly = 0
        self.lyc = 0
        self.bgp = 0xFC
        self.obp0 = 0xFF
        self.obp1 = 0xFF
        self.wy = 0
        self.wx = 0
        self.mode = 2
        self.line_cycles = 0
        self.window_line = 0
        self.window_active = False
        self.frame_ready = False
        self._stat_line = False
        self.bg_cram = bytearray(64)
        self.obj_cram = bytearray(64)
        self.bgpi = 0
        self.obpi = 0
        grays = (0x7FFF, 0x56B5, 0x294A, 0x0000)
        for pal in range(8):
            for color in range(4):
                word = grays[color]
                self.bg_cram[pal * 8 + color * 2] = word & 0xFF
                self.bg_cram[pal * 8 + color * 2 + 1] = word >> 8
                self.obj_cram[pal * 8 + color * 2] = word & 0xFF
                self.obj_cram[pal * 8 + color * 2 + 1] = word >> 8
        self._rebuild_dmg()
        self._rebuild_cgb()

    def tick(self, dots: int) -> None:
        if (self.lcdc & 0x80) == 0 or dots <= 0:
            return
        cycles = self.line_cycles + dots
        mode = self.mode
        if self.ly >= 144 or mode == 0:
            limit = 456
        elif mode == 2:
            limit = 80
        else:
            limit = 252
        if cycles < limit:
            self.line_cycles = cycles
            return
        self.line_cycles = cycles
        while self.line_cycles >= self._limit():
            self._cross()

    def read(self, addr: int) -> int:
        if addr == 0xFF40:
            return self.lcdc
        if addr == 0xFF41:
            return self._read_stat()
        if addr == 0xFF42:
            return self.scy
        if addr == 0xFF43:
            return self.scx
        if addr == 0xFF44:
            return 0 if (self.lcdc & 0x80) == 0 else self.ly
        if addr == 0xFF45:
            return self.lyc
        if addr == 0xFF47:
            return self.bgp
        if addr == 0xFF48:
            return self.obp0
        if addr == 0xFF49:
            return self.obp1
        if addr == 0xFF4A:
            return self.wy
        if addr == 0xFF4B:
            return self.wx
        if addr == 0xFF68:
            return self.bgpi
        if addr == 0xFF69:
            return self.bg_cram[self.bgpi & 0x3F]
        if addr == 0xFF6A:
            return self.obpi
        if addr == 0xFF6B:
            return self.obj_cram[self.obpi & 0x3F]
        return 0xFF

    def write(self, addr: int, value: int) -> None:
        if addr == 0xFF40:
            self._set_lcdc(value)
        elif addr == 0xFF41:
            self.stat = value & 0x78
            self._update_stat()
        elif addr == 0xFF42:
            self.scy = value
        elif addr == 0xFF43:
            self.scx = value
        elif addr == 0xFF45:
            self.lyc = value
            self._update_stat()
        elif addr == 0xFF47:
            self.bgp = value
            self._rebuild_dmg()
        elif addr == 0xFF48:
            self.obp0 = value
            self._rebuild_dmg()
        elif addr == 0xFF49:
            self.obp1 = value
            self._rebuild_dmg()
        elif addr == 0xFF4A:
            self.wy = value
        elif addr == 0xFF4B:
            self.wx = value
        elif addr == 0xFF68:
            self.bgpi = value & 0xBF
        elif addr == 0xFF69:
            self.bg_cram[self.bgpi & 0x3F] = value
            if self.bgpi & 0x80:
                self.bgpi = (self.bgpi & 0x80) | ((self.bgpi + 1) & 0x3F)
            self._rebuild_cgb()
        elif addr == 0xFF6A:
            self.obpi = value & 0xBF
        elif addr == 0xFF6B:
            self.obj_cram[self.obpi & 0x3F] = value
            if self.obpi & 0x80:
                self.obpi = (self.obpi & 0x80) | ((self.obpi + 1) & 0x3F)
            self._rebuild_cgb()

    def _set_lcdc(self, value: int) -> None:
        was = self.lcdc & 0x80
        self.lcdc = value
        now = value & 0x80
        if was and not now:
            self.ly = 0
            self.mode = 0
            self.line_cycles = 0
            self.window_line = 0
            self.window_active = False
            self._stat_line = False
        elif now and not was:
            self.ly = 0
            self.mode = 2
            self.line_cycles = 0
            self.window_line = 0
            self.window_active = False

    def _limit(self) -> int:
        if self.ly >= 144:
            return 456
        if self.mode == 2:
            return 80
        if self.mode == 3:
            return 252
        return 456

    def _cross(self) -> None:
        if self.ly < 144:
            if self.mode == 2:
                self.mode = 3
                self._render_line(self.ly)
                self._update_stat()
                return
            if self.mode == 3:
                self.mode = 0
                self.gb.mmu.hdma_hblank()
                self._update_stat()
                return
        self.line_cycles -= 456
        self._next_ly()

    def _next_ly(self) -> None:
        self.ly += 1
        if self.ly == 144:
            self.mode = 1
            self.gb.mmu.iff |= 0x01
            self.frame_ready = True
        elif self.ly == 154:
            self.ly = 0
            self.mode = 2
        elif self.ly < 144:
            self.mode = 2
        self._update_stat()

    def _read_stat(self) -> int:
        if (self.lcdc & 0x80) == 0:
            return 0x80 | (self.stat & 0x78)
        match = 0x04 if self.ly == self.lyc else 0
        return 0x80 | (self.stat & 0x78) | match | (self.mode & 0x03)

    def _stat_signal(self) -> bool:
        if (self.lcdc & 0x80) == 0:
            return False
        stat = self.stat
        mode = self.mode
        if mode == 0 and stat & 0x08:
            return True
        if mode == 1 and stat & 0x10:
            return True
        if mode == 2 and stat & 0x20:
            return True
        if self.ly == self.lyc and stat & 0x40:
            return True
        return False

    def _update_stat(self) -> None:
        signal = self._stat_signal()
        if signal and not self._stat_line:
            self.gb.mmu.iff |= 0x02
        self._stat_line = signal

    def _rebuild_dmg(self) -> None:
        shades = Z_PACK

        def mapped(reg: int) -> list[int]:
            return [shades[(reg >> (i * 2)) & 3] for i in range(4)]

        self.dmg_bg = mapped(self.bgp)
        self.dmg_obp0 = mapped(self.obp0)
        self.dmg_obp1 = mapped(self.obp1)

    def _rebuild_cgb(self) -> None:
        for pal in range(8):
            for color in range(4):
                boff = pal * 8 + color * 2
                word = self.bg_cram[boff] | (self.bg_cram[boff + 1] << 8)
                self.cgb_bg[pal][color] = _pack555(word)
                word = self.obj_cram[boff] | (self.obj_cram[boff + 1] << 8)
                self.cgb_obj[pal][color] = _pack555(word)

    def _render_line(self, ly: int) -> None:
        line = self.line
        if ly == 0:
            self.window_active = False
            self.window_line = 0
        lcdc = self.lcdc
        window_ok = bool(lcdc & 0x20) and (self.cgb or bool(lcdc & 0x01))
        if window_ok and ly == self.wy:
            self.window_active = True
        if not self.cgb and not (lcdc & 0x01):
            shade = self.dmg_bg[0]
            for x in range(160):
                line[x] = shade
            self.bg_index[:] = b"\x00" * 160
            self.bg_pri[:] = b"\x00" * 160
        else:
            bg_map = 0x1C00 if lcdc & 0x08 else 0x1800
            self._paint_map(line, 0, 160, self.scx, (self.scy + ly) & 0xFF, bg_map)
            if self.window_active and self.wx <= 166:
                win_map = 0x1C00 if lcdc & 0x40 else 0x1800
                origin = self.wx - 7
                if origin < 0:
                    self._paint_map(line, 0, 160, -origin, self.window_line, win_map)
                elif origin < 160:
                    self._paint_map(line, origin, 160, 0, self.window_line, win_map)
                self.window_line = (self.window_line + 1) & 0xFF
        if lcdc & 0x02:
            self._sprites(ly, line)
        start = ly * 160
        self.fb[start : start + 160] = line

    def _paint_map(self, line, x0: int, x1: int, src_x: int, src_y: int, map_base: int) -> None:
        index = self.bg_index
        pri = self.bg_pri
        v0 = self.gb.mmu.vram[0]
        v1 = self.gb.mmu.vram[1]
        unsigned = bool(self.lcdc & 0x10)
        cgb = self.cgb
        row = src_y & 7
        map_y = (src_y >> 3) << 5
        x = x0
        sx = src_x & 0xFF
        while x < x1:
            tile_x = (sx >> 3) & 31
            attr = 0
            tile = v0[map_base + map_y + tile_x]
            if cgb:
                attr = v1[map_base + map_y + tile_x]
                bank = (attr >> 3) & 1
                trow = (7 - row) if attr & 0x40 else row
                hflip = bool(attr & 0x20)
                pal = self.cgb_bg[attr & 7]
                pbit = 1 if attr & 0x80 else 0
            else:
                bank = 0
                trow = row
                hflip = False
                pal = self.dmg_bg
                pbit = 0
            src = v1 if bank else v0
            off = _tile_addr(tile, unsigned) + (trow << 1)
            colors = (HEXPAND if hflip else EXPAND)[(src[off + 1] << 8) | src[off]]
            fine = sx & 7
            n = 8 - fine
            if x + n > x1:
                n = x1 - x
            if fine == 0 and n == 8:
                _paint8(line, index, pri, x, colors, pal, pbit)
            else:
                for i in range(n):
                    color = colors[fine + i]
                    line[x + i] = pal[color]
                    index[x + i] = color
                    pri[x + i] = pbit
            x += n
            sx = (sx + n) & 0xFF

    def _sprites(self, ly: int, line) -> None:
        mem = self.gb.mmu.mem
        height = 16 if self.lcdc & 0x04 else 8
        found = []
        for i in range(40):
            sy = mem[0xFE00 + i * 4] - 16
            if sy <= ly < sy + height:
                found.append(i)
                if len(found) == 10:
                    break
        if not self.cgb:
            found.sort(key=lambda i: mem[0xFE00 + i * 4 + 1])
        master = (not self.cgb) or bool(self.lcdc & 0x01)
        v0 = self.gb.mmu.vram[0]
        v1 = self.gb.mmu.vram[1]
        for i in reversed(found):
            base = 0xFE00 + i * 4
            sy = mem[base] - 16
            sx0 = mem[base + 1] - 8
            tile = mem[base + 2]
            flags = mem[base + 3]
            row = ly - sy
            if flags & 0x40:
                row = height - 1 - row
            if height == 16:
                tile &= 0xFE
            if row >= 8:
                tile = (tile + 1) & 0xFF
                row -= 8
            bank = ((flags >> 3) & 1) if self.cgb else 0
            src = v1 if bank else v0
            off = (tile << 4) + (row << 1)
            colors = (HEXPAND if flags & 0x20 else EXPAND)[(src[off + 1] << 8) | src[off]]
            if self.cgb:
                pal = self.cgb_obj[flags & 7]
            else:
                pal = self.dmg_obp1 if flags & 0x10 else self.dmg_obp0
            behind = bool(flags & 0x80)
            for px in range(8):
                sx = sx0 + px
                if sx < 0 or sx >= 160:
                    continue
                color = colors[px]
                if color == 0:
                    continue
                if master and self.bg_index[sx] and (behind or (self.cgb and self.bg_pri[sx])):
                    continue
                line[sx] = pal[color]
