"""Nintendo DS through the melonDS libretro core.

melonDS includes FreeBIOS, so this app does not ship Nintendo's DS BIOS or firmware.
Direct boot skips the firmware menu and starts the cartridge.
"""

from __future__ import annotations

import zlib
from pathlib import Path

from pokemongb.libretro import Core, CoreError

__all__ = ["CoreError", "open_core", "pack_state", "unpack_state"]

_OPTIONS = {
    b"melonds_console_mode": b"DS",
    b"melonds_boot_directly": b"enabled",
    b"melonds_screen_layout": b"Top/Bottom",
    b"melonds_screen_gap": b"0",
    b"melonds_touch_mode": b"Touch",
    b"melonds_opengl_renderer": b"disabled",
    b"melonds_threaded_renderer": b"disabled",
    b"melonds_jit_enable": b"enabled",
    b"melonds_language": b"English",
    b"melonds_use_fw_settings": b"disabled",
}


def core_path() -> Path:
    return Path(__file__).resolve().parents[1] / "cores" / "melonds_libretro.dll"


def open_core(save_dir: Path) -> Core:
    dll = core_path()
    if not dll.is_file():
        raise CoreError("The Nintendo DS core is missing (cores/melonds_libretro.dll).")
    return Core(dll, dll.parent / "system", save_dir, variables=dict(_OPTIONS))


def pack_state(key: str, blob: bytes) -> bytes:
    raw = key.encode("utf-8")
    payload = zlib.compress(blob, 1)
    return b"PNDS" + len(raw).to_bytes(2, "little") + raw + payload


def unpack_state(data: bytes, key: str) -> bytes:
    if len(data) < 6 or not data.startswith(b"PNDS"):
        raise ValueError("That save state is not a Nintendo DS state.")
    length = int.from_bytes(data[4:6], "little")
    if len(data) < 6 + length:
        raise ValueError("That save state is damaged.")
    found = data[6:6 + length].decode("utf-8", errors="replace")
    if found != key:
        raise ValueError("That save state belongs to a different game.")
    try:
        return zlib.decompress(data[6 + length:])
    except zlib.error as exc:
        raise ValueError("That save state is damaged.") from exc
