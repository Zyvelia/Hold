"""Install optional Windows cores from the official Libretro buildbot."""

from __future__ import annotations

import platform
import shutil
import struct
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from pokemongb.systems import OPTIONAL_BY_ID, System, cores_dir

_SOURCE = "https://buildbot.libretro.com/nightly/windows/x86_64/latest/"
_LIMIT = 64 * 1024 * 1024


def can_install_windows_core() -> bool:
    return (
        platform.system() == "Windows"
        and platform.machine().lower() in {"amd64", "x86_64"}
        and struct.calcsize("P") == 8
    )


def _is_x64_dll(path: Path) -> bool:
    with path.open("rb") as dll:
        header = dll.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            return False
        dll.seek(int.from_bytes(header[60:64], "little"))
        pe = dll.read(24)
    return (
        len(pe) == 24
        and pe[:6] == b"PE\0\0\x64\x86"
        and bool(int.from_bytes(pe[22:24], "little") & 0x2000)
    )


def install_core(system: System, directory: Path | None = None) -> Path:
    if OPTIONAL_BY_ID.get(system.id) != system:
        raise ValueError("This core is not in the optional console catalog.")
    if not can_install_windows_core():
        raise RuntimeError("The built-in installer requires 64-bit Windows on an x64 PC.")
    directory = cores_dir() if directory is None else directory
    target = directory / system.dll
    if target.is_file():
        return target
    if target.exists():
        raise OSError(f"A directory occupies the core path: {target}")
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".core-", dir=directory) as folder:
        archive_path = Path(folder) / "core.zip"
        with urllib.request.urlopen(_SOURCE + system.dll + ".zip", timeout=30) as response:
            with archive_path.open("wb") as archive:
                remaining = _LIMIT
                while chunk := response.read(min(65536, remaining + 1)):
                    remaining -= len(chunk)
                    if remaining < 0:
                        raise ValueError("The core download exceeded 64 MiB.")
                    archive.write(chunk)
        dll = Path(folder) / system.dll
        with zipfile.ZipFile(archive_path) as archive:
            members = [
                entry for entry in archive.infolist()
                if not entry.is_dir() and Path(entry.filename).name == system.dll
            ]
            if len(members) != 1 or not 0 < members[0].file_size <= _LIMIT:
                raise ValueError("Libretro's archive does not contain the expected core.")
            with archive.open(members[0]) as incoming, dll.open("wb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)
        if not _is_x64_dll(dll):
            raise ValueError("The downloaded core is not a Windows x64 DLL.")
        if not target.is_file():
            dll.replace(target)
    return target
