"""Nintendo Switch through a Vulkan libretro core.

The core DLL is cores/suyu_libretro.dll. This app does not ship Nintendo
keys or firmware. A retail dump needs the keys file you already have.
"""

from __future__ import annotations

import zlib
from pathlib import Path

from pokemongb.libretro import Core, CoreError
from pokemongb.vulkan import available as vulkan_available

__all__ = ["CoreError", "open_core", "pack_state", "unpack_state"]


def core_path() -> Path:
    return Path(__file__).resolve().parents[1] / "cores" / "suyu_libretro.dll"


def open_core(save_dir: Path) -> Core:
    dll = core_path()
    if not dll.is_file():
        raise CoreError("The Nintendo Switch core is missing (cores/suyu_libretro.dll).")
    if not vulkan_available():
        raise CoreError("Vulkan is not available. Switch games draw on the GPU.")
    return Core(dll, dll.parent / "system", save_dir, hardware="vulkan")


def pack_state(key: str, blob: bytes) -> bytes:
    raw = key.encode("utf-8")
    payload = zlib.compress(blob, 1)
    return b"PSW1" + len(raw).to_bytes(2, "little") + raw + payload


def unpack_state(data: bytes, key: str) -> bytes:
    if len(data) < 6 or not data.startswith(b"PSW1"):
        raise ValueError("That save state is not a Nintendo Switch state.")
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
