"""Cartridge header helpers. No ROM data lives in this project."""

from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path

RAM_SIZES = {
    0x00: 0,
    0x01: 0x800,
    0x02: 0x2000,
    0x03: 0x8000,
    0x04: 0x20000,
    0x05: 0x10000,
}

_MBC_NAMES = {
    0x00: "ROM",
    0x01: "MBC1",
    0x02: "MBC1+RAM",
    0x03: "MBC1+RAM+Battery",
    0x05: "MBC2",
    0x06: "MBC2+Battery",
    0x08: "ROM+RAM",
    0x09: "ROM+RAM+Battery",
    0x0F: "MBC3+Timer+Battery",
    0x10: "MBC3+Timer+RAM+Battery",
    0x11: "MBC3",
    0x12: "MBC3+RAM",
    0x13: "MBC3+RAM+Battery",
    0x19: "MBC5",
    0x1A: "MBC5+RAM",
    0x1B: "MBC5+RAM+Battery",
    0x1C: "MBC5+Rumble",
    0x1D: "MBC5+Rumble+RAM",
    0x1E: "MBC5+Rumble+RAM+Battery",
}


def mbc_kind(cart_type: int) -> int:
    """Return 0, 1, 2, 3, or 5. Unknown types are treated as plain ROM."""
    if cart_type in (0x01, 0x02, 0x03):
        return 1
    if cart_type in (0x05, 0x06):
        return 2
    if cart_type in (0x0F, 0x10, 0x11, 0x12, 0x13):
        return 3
    if cart_type in (0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E):
        return 5
    return 0


def mbc_name(cart_type: int) -> str:
    return _MBC_NAMES.get(cart_type, f"type {cart_type:02X}")


def has_rtc(cart_type: int) -> bool:
    return cart_type in (0x0F, 0x10)


def has_battery(cart_type: int) -> bool:
    return cart_type in (0x03, 0x06, 0x09, 0x0F, 0x10, 0x13, 0x1B, 0x1E)


def ram_bytes(cart_type: int, size_code: int) -> int:
    if cart_type in (0x05, 0x06):
        return 0x200
    return RAM_SIZES.get(size_code, 0)


def _zip_rom_name(zf: zipfile.ZipFile) -> str:
    names = [n for n in zf.namelist() if not n.endswith("/")]
    gb = [n for n in names if n.lower().endswith((".gb", ".gbc"))]
    gba = [n for n in names if n.lower().endswith(".gba")]
    nds = [n for n in names if n.lower().endswith(".nds")]
    if gb:
        return gb[0]
    if gba:
        return gba[0]
    if nds:
        return nds[0]
    raise ValueError("That zip does not contain a .gb, .gbc, .gba, or .nds file.")


def open_rom(path: Path) -> tuple[bytes, str]:
    """Return ROM bytes and ``gb``, ``gba``, or ``nds``."""
    path = Path(path)
    data = path.read_bytes()
    name = path.name
    if path.suffix.lower() == ".zip" or data[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(path) as zf:
            name = _zip_rom_name(zf)
            data = zf.read(name)
    suffix = Path(name).suffix.lower()
    if suffix == ".gba":
        kind = "gba"
    elif suffix == ".nds":
        kind = "nds"
    elif suffix in (".gb", ".gbc"):
        kind = "gb"
    else:
        raise ValueError("Open a .gb, .gbc, .gba, or .nds file.")
    if kind == "gba" and len(data) < 0xC0:
        raise ValueError("That file is too small to be a Game Boy Advance ROM.")
    elif kind == "nds" and len(data) < 0x160:
        raise ValueError("That file is too small to be a Nintendo DS ROM.")
    elif kind == "gb" and len(data) < 0x150:
        raise ValueError("That file is too small to be a Game Boy ROM.")
    return data, kind


def read_rom(path: Path) -> bytes:
    data, kind = open_rom(path)
    if kind != "gb":
        raise ValueError("That file is not a Game Boy ROM.")
    return data


def rom_title(rom: bytes) -> str:
    cgb = bool(rom[0x143] & 0x80)
    end = 0x143 if cgb else 0x144
    raw = rom[0x134:end].split(b"\x00", 1)[0]
    title = "".join(chr(b) if 32 <= b < 127 else "" for b in raw).strip()
    return title or "Unknown"


def save_key(rom: bytes) -> str:
    title = rom_title(rom)
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in title).strip() or "rom"
    return f"{safe}_{rom[0x14E]:02X}{rom[0x14F]:02X}"


def gba_title(rom: bytes) -> str:
    raw = rom[0xA0:0xAC].split(b"\x00", 1)[0]
    title = "".join(chr(b) if 32 <= b < 127 else "" for b in raw).strip()
    return title or "Unknown"


def gba_save_key(rom: bytes) -> str:
    title = gba_title(rom)
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in title).strip() or "gba"
    code = "".join(chr(b) if 32 <= b < 127 else "" for b in rom[0xAC:0xB0]) or "XXXX"
    return f"{safe}_{code}"


def _header_text(raw: bytes) -> str:
    text = "".join(chr(b) if 32 <= b < 127 else "" for b in raw.split(b"\x00", 1)[0]).strip()
    return text


def nds_title(rom: bytes) -> str:
    return _header_text(rom[0x000:0x00C]) or "Unknown"


def nds_save_key(rom: bytes) -> str:
    title = nds_title(rom)
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in title).strip() or "nds"
    code = _header_text(rom[0x00C:0x010]) or "XXXX"
    return f"{safe}_{code}"


_3DS_SUFFIXES = (".3ds", ".cci", ".cxi", ".3dsx", ".app", ".bcci", ".bcxi")


def n3ds_header(path: Path) -> bytes:
    with Path(path).open("rb") as handle:
        return handle.read(0x200)


def n3ds_title(header: bytes, filename: str) -> str:
    stem = Path(filename).stem
    title = "".join(ch if ch.isalnum() or ch in " _-" else " " for ch in stem).strip()
    return title or "Nintendo 3DS"


def n3ds_save_key(header: bytes) -> str:
    if len(header) >= 0x110 and header[0x100:0x104] == b"NCSD":
        return "3DS_" + header[0x108:0x110].hex().upper()
    if header[:4] == b"NCCH" and len(header) >= 0x120:
        return "3DS_" + header[0x118:0x120].hex().upper()
    if header[:4] == b"3DSX":
        return "3DSX_" + header[:16].hex().upper()
    return "3DS_ROM"


def prepare_3ds(path: Path, cache: Path) -> Path | None:
    """Return a real file path for a 3DS ROM. None means this is another console."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in _3DS_SUFFIXES:
        if not path.is_file() or path.stat().st_size < 0x20:
            raise ValueError("That file is too small to be a Nintendo 3DS ROM.")
        return path
    magic = b""
    if suffix != ".zip":
        with path.open("rb") as handle:
            magic = handle.read(4)
        if magic != b"PK\x03\x04":
            return None
    with zipfile.ZipFile(path) as zf:
        names = [name for name in zf.namelist() if not name.endswith("/")]

        def matching(*suffixes: str) -> list[str]:
            wanted = tuple(suffixes)
            return [name for name in names if Path(name).suffix.lower() in wanted]

        if matching(".gb", ".gbc") or matching(".gba") or matching(".nds"):
            return None
        chosen = matching(*_3DS_SUFFIXES)
        if not chosen:
            return None
        info = zf.getinfo(chosen[0])
        if info.file_size < 0x20:
            raise ValueError("That file is too small to be a Nintendo 3DS ROM.")
        cache.mkdir(parents=True, exist_ok=True)
        dest = cache / Path(chosen[0]).name
        if not dest.is_file() or dest.stat().st_size != info.file_size:
            with zf.open(info) as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out)
        return dest


_SWITCH_SUFFIXES = (".nsp", ".xci", ".nro", ".nso", ".nca")


def switch_title(filename: str) -> str:
    stem = Path(filename).stem
    title = "".join(ch if ch.isalnum() or ch in " _-" else " " for ch in stem).strip()
    return title or "Nintendo Switch"


def switch_save_key(path: Path) -> str:
    digest = hashlib.blake2s(digest_size=8)
    with Path(path).open("rb") as handle:
        digest.update(handle.read(0x1000))
    digest.update(str(Path(path).stat().st_size).encode())
    return "SW_" + digest.hexdigest().upper()


def prepare_switch(path: Path) -> Path | None:
    """Return a Switch ROM path. None means this file is another console."""
    path = Path(path)
    if path.suffix.lower() not in _SWITCH_SUFFIXES:
        return None
    if not path.is_file() or path.stat().st_size < 0x40:
        raise ValueError("That file is too small to be a Nintendo Switch ROM.")
    return path
