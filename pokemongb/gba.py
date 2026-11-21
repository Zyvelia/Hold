"""Game Boy Advance through the mGBA libretro core.

mGBA supplies its own stand-in BIOS, so this app does not ship Nintendo's BIOS.
"""

from __future__ import annotations

from pathlib import Path

from pokemongb.libretro import Core, CoreError

__all__ = ["CoreError", "open_core", "pack_state", "unpack_state"]

_BIOS_OFF = {
    b"mgba_use_bios": b"OFF",
    b"mgba_skip_bios": b"ON",
}


def core_path() -> Path:
    return Path(__file__).resolve().parents[1] / "cores" / "mgba_libretro.dll"


def open_core(save_dir: Path) -> Core:
    dll = core_path()
    if not dll.is_file():
        raise CoreError("The Game Boy Advance core is missing (cores/mgba_libretro.dll).")
    return Core(dll, dll.parent / "system", save_dir, variables=dict(_BIOS_OFF))


def pack_state(key: str, blob: bytes) -> bytes:
    raw = key.encode("utf-8")
    return b"PGBA" + len(raw).to_bytes(2, "little") + raw + blob


def unpack_state(data: bytes, key: str) -> bytes:
    if len(data) < 6 or not data.startswith(b"PGBA"):
        raise ValueError("That save state is not a Game Boy Advance state.")
    length = int.from_bytes(data[4:6], "little")
    if len(data) < 6 + length:
        raise ValueError("That save state is damaged.")
    found = data[6:6 + length].decode("utf-8", errors="replace")
    if found != key:
        raise ValueError("That save state belongs to a different game.")
    return data[6 + length:]
