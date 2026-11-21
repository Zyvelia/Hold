"""Full-machine save states. Battery .sav files only keep cartridge RAM."""

from __future__ import annotations

import array
import base64
import json
import time
import zlib

_MAGIC = b"PGB1"

_PULSE = (
    "enabled",
    "dac",
    "duty",
    "duty_pos",
    "length",
    "length_en",
    "volume",
    "env_vol",
    "env_add",
    "env_period",
    "env_timer",
    "freq",
    "period",
    "timer",
    "sweep_period",
    "sweep_neg",
    "sweep_shift",
    "sweep_timer",
    "sweep_en",
    "shadow",
)
_WAVE = (
    "enabled",
    "dac",
    "length",
    "length_en",
    "volume",
    "freq",
    "period",
    "timer",
    "pos",
)
_NOISE = (
    "enabled",
    "dac",
    "length",
    "length_en",
    "volume",
    "env_vol",
    "env_add",
    "env_period",
    "env_timer",
    "clock_shift",
    "width7",
    "divisor",
    "period",
    "timer",
    "lfsr",
)


def rom_id(rom: bytes) -> str:
    if len(rom) < 0x150:
        return "0"
    return f"{len(rom):X}:{rom[0x14D]:02X}{rom[0x14E]:02X}{rom[0x14F]:02X}"


def export_state(gb) -> bytes:
    mmu = gb.mmu
    cpu = gb.cpu
    ppu = gb.ppu
    payload = {
        "version": 1,
        "rom": rom_id(mmu.rom),
        "cpu": {
            "a": cpu.a,
            "f": cpu.f,
            "b": cpu.b,
            "c": cpu.c,
            "d": cpu.d,
            "e": cpu.e,
            "h": cpu.h,
            "l": cpu.l,
            "sp": cpu.sp,
            "pc": cpu.pc,
            "ime": cpu.ime,
            "ei_delay": cpu.ei_delay,
            "halted": cpu.halted,
            "halt_bug": cpu.halt_bug,
        },
        "machine": {
            "cgb": gb.cgb,
            "double_speed": gb.double_speed,
            "credit": gb._credit,
            "serial_cc": gb.serial_cc,
        },
        "mmu": {
            "vram": [_b64(mmu.vram[0]), _b64(mmu.vram[1])],
            "wram": [_b64(bank) for bank in mmu.wram],
            "eram": _b64(mmu.eram),
            "oam": _b64(mmu.mem[0xFE00:0xFEA0]),
            "hram": _b64(mmu.mem[0xFF80:0xFFFF]),
            "rom_bank": mmu.rom_bank,
            "rom_bank0": mmu.rom_bank0,
            "ram_bank": mmu.ram_bank,
            "vram_bank": mmu.vram_bank,
            "wram_bank": mmu.wram_bank,
            "ram_enable": mmu.ram_enable,
            "bank_low": mmu.bank_low,
            "bank_high": mmu.bank_high,
            "mode": mmu.mode,
            "rtc_mapped": mmu.rtc_mapped,
            "rtc_reg": mmu.rtc_reg,
            "rtc_latch": mmu.rtc_latch,
            "rtc_zero": mmu.rtc_zero,
            "rtc_halt": mmu.rtc_halt,
            "rtc_carry": mmu.rtc_carry,
            "rtc_frozen": list(mmu.rtc_frozen),
            "rtc_latched": list(mmu.rtc_latched),
            "ie": mmu.ie,
            "iff": mmu.iff,
            "sb": mmu.sb,
            "sc": mmu.sc,
            "key1": mmu.key1,
            "hdma1": mmu.hdma1,
            "hdma2": mmu.hdma2,
            "hdma3": mmu.hdma3,
            "hdma4": mmu.hdma4,
            "hdma_src": mmu.hdma_src,
            "hdma_dst": mmu.hdma_dst,
            "hdma_remain": mmu.hdma_remain,
            "hdma_active": mmu.hdma_active,
        },
        "ppu": {
            "lcdc": ppu.lcdc,
            "stat": ppu.stat,
            "scy": ppu.scy,
            "scx": ppu.scx,
            "ly": ppu.ly,
            "lyc": ppu.lyc,
            "bgp": ppu.bgp,
            "obp0": ppu.obp0,
            "obp1": ppu.obp1,
            "wy": ppu.wy,
            "wx": ppu.wx,
            "mode": ppu.mode,
            "line_cycles": ppu.line_cycles,
            "window_line": ppu.window_line,
            "window_active": ppu.window_active,
            "stat_line": ppu._stat_line,
            "bgpi": ppu.bgpi,
            "obpi": ppu.obpi,
            "bg_cram": _b64(ppu.bg_cram),
            "obj_cram": _b64(ppu.obj_cram),
            "fb": _b64(ppu.fb.tobytes()),
        },
        "timer": {
            "div": gb.timer.div,
            "tima": gb.timer.tima,
            "tma": gb.timer.tma,
            "tac": gb.timer.tac,
        },
        "joypad": {"select": gb.joypad.select},
        "apu": {
            "master": gb.apu.master,
            "nr50": gb.apu.nr50,
            "nr51": gb.apu.nr51,
            "seq_acc": gb.apu.seq_acc,
            "seq_step": gb.apu.seq_step,
            "sample_acc": gb.apu.sample_acc,
            "ch1": _channel(gb.apu.ch1, _PULSE),
            "ch2": _channel(gb.apu.ch2, _PULSE),
            "ch3": _channel(gb.apu.ch3, _WAVE),
            "ch4": _channel(gb.apu.ch4, _NOISE),
            "wave": _b64(gb.apu.ch3.ram),
        },
    }
    return _MAGIC + zlib.compress(json.dumps(payload).encode("utf-8"), level=6)


def import_state(gb, blob: bytes) -> None:
    if not blob.startswith(_MAGIC):
        raise ValueError("That file is not a Pokemon GB save state.")
    try:
        payload = json.loads(zlib.decompress(blob[len(_MAGIC) :]))
    except Exception as exc:
        raise ValueError("That save state is damaged.") from exc
    if payload.get("version") != 1:
        raise ValueError("That save state is from a newer build.")
    if payload.get("rom") != rom_id(gb.mmu.rom):
        raise ValueError("That save state belongs to a different ROM.")
    _restore(gb, payload)


def _restore(gb, payload: dict) -> None:
    mmu = gb.mmu
    cpu = gb.cpu
    ppu = gb.ppu
    machine = payload["machine"]
    gb.cgb = bool(machine["cgb"])
    gb.double_speed = bool(machine["double_speed"])
    gb._credit = int(machine["credit"])
    gb.serial_cc = int(machine["serial_cc"])

    for name, value in payload["cpu"].items():
        setattr(cpu, name, value)
    cpu.f &= 0xF0
    cpu.mem = mmu.mem

    bank = payload["mmu"]
    mmu.vram[0][:] = _raw(bank["vram"][0], 0x2000)
    mmu.vram[1][:] = _raw(bank["vram"][1], 0x2000)
    for index, encoded in enumerate(bank["wram"]):
        mmu.wram[index][:] = _raw(encoded, 0x1000)
    eram = _raw(bank["eram"])
    if len(eram) != len(mmu.eram):
        raise ValueError("That save state does not match this cartridge RAM.")
    if mmu.eram:
        mmu.eram[:] = eram
    for name in (
        "rom_bank",
        "rom_bank0",
        "ram_bank",
        "vram_bank",
        "wram_bank",
        "ram_enable",
        "bank_low",
        "bank_high",
        "mode",
        "rtc_mapped",
        "rtc_reg",
        "rtc_latch",
        "rtc_zero",
        "rtc_halt",
        "rtc_carry",
        "ie",
        "iff",
        "sb",
        "sc",
        "key1",
        "hdma1",
        "hdma2",
        "hdma3",
        "hdma4",
        "hdma_src",
        "hdma_dst",
        "hdma_remain",
        "hdma_active",
    ):
        setattr(mmu, name, bank[name])
    mmu.rtc_frozen = [int(x) & 0xFF for x in bank["rtc_frozen"]]
    mmu.rtc_latched = [int(x) & 0xFF for x in bank["rtc_latched"]]
    mmu.sram_dirty = True
    mmu.sram_touch = time.time()
    _remap(mmu, _raw(bank["oam"], 0xA0), _raw(bank["hram"], 0x7F))

    picture = payload["ppu"]
    for name in (
        "lcdc",
        "stat",
        "scy",
        "scx",
        "ly",
        "lyc",
        "bgp",
        "obp0",
        "obp1",
        "wy",
        "wx",
        "mode",
        "line_cycles",
        "window_line",
        "window_active",
        "bgpi",
        "obpi",
    ):
        setattr(ppu, name, picture[name])
    ppu._stat_line = bool(picture["stat_line"])
    ppu.cgb = gb.cgb
    ppu.bg_cram[:] = _raw(picture["bg_cram"], 64)
    ppu.obj_cram[:] = _raw(picture["obj_cram"], 64)
    ppu._rebuild_dmg()
    ppu._rebuild_cgb()
    ppu.frame_ready = False
    pixels = _raw(picture["fb"])
    if len(pixels) == len(ppu.fb) * ppu.fb.itemsize:
        ppu.fb = array.array("I")
        ppu.fb.frombytes(pixels)

    timer = payload["timer"]
    gb.timer.div = int(timer["div"]) & 0xFFFF
    gb.timer.tima = int(timer["tima"]) & 0xFF
    gb.timer.tma = int(timer["tma"]) & 0xFF
    gb.timer.tac = int(timer["tac"]) & 0xFF
    gb.joypad.select = int(payload["joypad"]["select"]) & 0x30

    apu = gb.apu
    sound = payload["apu"]
    apu.master = bool(sound["master"])
    apu.nr50 = int(sound["nr50"]) & 0xFF
    apu.nr51 = int(sound["nr51"]) & 0xFF
    apu.seq_acc = int(sound["seq_acc"])
    apu.seq_step = int(sound["seq_step"]) & 7
    apu.sample_acc = int(sound["sample_acc"])
    _apply_channel(apu.ch1, sound["ch1"], _PULSE)
    _apply_channel(apu.ch2, sound["ch2"], _PULSE)
    _apply_channel(apu.ch3, sound["ch3"], _WAVE)
    _apply_channel(apu.ch4, sound["ch4"], _NOISE)
    apu.ch3.ram[:] = _raw(sound["wave"], 16)
    apu.samples = array.array("h")


def _remap(mmu, oam: bytes, hram: bytes) -> None:
    if mmu.kind == 1:
        mmu._map_rom_mbc1()
    else:
        mmu.rom_bank %= mmu.rom_banks
        mmu.rom_bank0 %= mmu.rom_banks
        mmu._map_rom_low()
        mmu._map_rom_high()
    mmu._map_ram()
    mmu.vram_bank &= 1
    mmu._map_vram()
    mmu.wram_bank = mmu.wram_bank or 1
    mmu.mem[0xC000:0xD000] = mmu.wram[0]
    mmu.mem[0xE000:0xF000] = mmu.wram[0]
    mmu._map_wram()
    mmu.mem[0xFE00:0xFEA0] = oam
    mmu.mem[0xFF80:0xFFFF] = hram


def _channel(channel, names: tuple[str, ...]) -> dict:
    return {name: getattr(channel, name) for name in names}


def _apply_channel(channel, data: dict, names: tuple[str, ...]) -> None:
    for name in names:
        setattr(channel, name, data[name])


def _b64(data) -> str:
    return base64.b64encode(bytes(data)).decode("ascii")


def _raw(encoded: str, size: int | None = None) -> bytes:
    data = base64.b64decode(encoded)
    if size is not None and len(data) != size:
        raise ValueError("That save state is damaged.")
    return data
