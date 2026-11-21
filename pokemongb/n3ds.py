"""Nintendo 3DS through the Azahar libretro core.

The picture is drawn in software, so this window does not need a graphics driver.
Azahar keeps cartridge saves itself. This app does not ship Nintendo system files.
"""

from __future__ import annotations

import zlib
from pathlib import Path

from pokemongb.libretro import Core, CoreError

__all__ = ["CoreError", "open_core", "pack_state", "unpack_state"]

_OPTIONS = {
    b"citra_graphics_api": b"Software",
    b"citra_layout_option": b"default",
    b"citra_use_cpu_jit": b"enabled",
    b"citra_resolution_factor": b"1",
    b"citra_is_new_3ds": b"Old 3DS",
    b"citra_region_value": b"Auto",
    b"citra_language": b"English",
    b"citra_touch_touchscreen": b"enabled",
    b"citra_mouse_touchscreen": b"enabled",
    b"citra_audio_emulation": b"hle",
}


def core_path() -> Path:
    return Path(__file__).resolve().parents[1] / "cores" / "azahar_libretro.dll"


def open_core(save_dir: Path) -> Core:
    dll = core_path()
    if not dll.is_file():
        raise CoreError("The Nintendo 3DS core is missing (cores/azahar_libretro.dll).")
    return Core(dll, dll.parent / "system", save_dir, variables=dict(_OPTIONS))


def pack_state(key: str, blob: bytes) -> bytes:
    raw = key.encode("utf-8")
    payload = zlib.compress(blob, 1)
    return b"P3DS" + len(raw).to_bytes(2, "little") + raw + payload


def unpack_state(data: bytes, key: str) -> bytes:
    if len(data) < 6 or not data.startswith(b"P3DS"):
        raise ValueError("That save state is not a Nintendo 3DS state.")
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
