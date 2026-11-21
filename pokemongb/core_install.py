"""Install supported Windows cores and Dolphin data from Libretro."""

from __future__ import annotations

import platform
import shutil
import struct
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pokemongb.systems import BY_ID, OPTIONAL_CONSOLES, cores_dir

_SOURCE = "https://buildbot.libretro.com/nightly/windows/x86_64/latest/"
_DOLPHIN_SOURCE = "https://buildbot.libretro.com/assets/system/Dolphin.zip"
_LIMIT = 64 * 1024 * 1024


@dataclass(frozen=True)
class PokemonPlatform:
    name: str
    core: str | None
    games: str
    files: str


POKEMON_PLATFORMS = (
    PokemonPlatform("Game Boy / Game Boy Color", None, "Red, Blue, Green, Yellow, Gold, Silver, Crystal",
                    ".gb, .gbc"),
    PokemonPlatform("Game Boy Advance", "mgba_libretro.dll", "Ruby, Sapphire, Emerald, FireRed, LeafGreen",
                    ".gba"),
    PokemonPlatform("Nintendo DS", "melonds_libretro.dll", "Diamond, Pearl, Platinum, HeartGold, SoulSilver, Black and White",
                    ".nds"),
    PokemonPlatform("Nintendo 3DS", "azahar_libretro.dll", "X and Y, Omega Ruby and Alpha Sapphire, Sun and Moon",
                    ".3ds, .cci, .cxi"),
    PokemonPlatform("Nintendo 64", BY_ID["n64"].dll, "Pokémon Stadium, Stadium 2, Snap, Puzzle League",
                    ".n64, .z64, .v64"),
    PokemonPlatform("Nintendo GameCube / Wii", BY_ID["gc"].dll,
                    "Colosseum, XD, Pokémon Box, Battle Revolution, PokéPark",
                    ".iso, .rvz, .gcz, .wbfs, WiiWare .wad"),
    PokemonPlatform("Wii U", BY_ID["wiiu"].dll, "Pokkén Tournament, Pokémon Rumble U",
                    ".wua, .wud, .wux, .rpx, .tmd"),
    PokemonPlatform("Pokémon Mini", BY_ID["min"].dll, "Pokémon Party mini, Pinball mini, Puzzle Collection",
                    ".min, .pkm"),
    PokemonPlatform("Nintendo Switch", "suyu_libretro.dll", "Let's Go, Sword and Shield, Legends, Scarlet and Violet",
                    ".nsp, .xci"),
)
POKEMON_DOWNLOADS = tuple(
    platform.core for platform in POKEMON_PLATFORMS
    if platform.core is not None and platform.core != "suyu_libretro.dll"
)
_INSTALLABLE = frozenset([*(system.dll for system in OPTIONAL_CONSOLES), *POKEMON_DOWNLOADS])


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


def _download(url: str, path: Path) -> None:
    with urllib.request.urlopen(url, timeout=30) as response, path.open("wb") as output:
        remaining = _LIMIT
        while chunk := response.read(min(65536, remaining + 1)):
            remaining -= len(chunk)
            if remaining < 0:
                raise ValueError("The download exceeded 64 MiB.")
            output.write(chunk)


def install_core(filename: str, directory: Path | None = None) -> Path:
    if filename not in _INSTALLABLE:
        raise ValueError("This core is not in the download catalog.")
    if not can_install_windows_core():
        raise RuntimeError("The built-in core installer requires 64-bit Windows on an x64 PC.")
    directory = cores_dir() if directory is None else directory
    target = directory / filename
    if target.is_file():
        return target
    if target.exists():
        raise OSError(f"A directory occupies the core path: {target}")
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".core-", dir=directory) as folder:
        archive_path = Path(folder) / "core.zip"
        _download(_SOURCE + filename + ".zip", archive_path)
        dll = Path(folder) / filename
        with zipfile.ZipFile(archive_path) as archive:
            members = [
                entry for entry in archive.infolist()
                if not entry.is_dir() and Path(entry.filename).name == filename
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


def dolphin_assets_present(directory: Path) -> bool:
    sys = directory / "system" / "dolphin-emu" / "Sys"
    return (sys / "codehandler.bin").is_file() and (sys / "GameSettings").is_dir()


def install_dolphin_assets(directory: Path | None = None) -> None:
    directory = cores_dir() if directory is None else directory
    if dolphin_assets_present(directory):
        return
    target = directory / "system" / "dolphin-emu" / "Sys"
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dolphin-", dir=target.parent) as folder:
        staged = Path(folder) / "Sys"
        download = staged.parent / "Dolphin.zip"
        _download(_DOLPHIN_SOURCE, download)
        with zipfile.ZipFile(download) as archive:
            license_name = "dolphin-emu/license.txt"
            if license_name in archive.namelist():
                license_info = archive.getinfo(license_name)
                if license_info.file_size > _LIMIT:
                    raise ValueError("Dolphin's license file exceeded 64 MiB.")
                (staged.parent / "license.txt").write_bytes(archive.read(license_info))
            remaining = _LIMIT
            for entry in archive.infolist():
                parts = PurePosixPath(entry.filename).parts
                if entry.is_dir() or parts[:2] != ("dolphin-emu", "Sys") or len(parts) < 3:
                    continue
                relative = parts[2:]
                if any(part in {".", ".."} or "\\" in part or ":" in part for part in relative):
                    raise ValueError("Dolphin's archive contains an invalid path.")
                remaining -= entry.file_size
                if remaining < 0:
                    raise ValueError("Dolphin's system files exceeded 64 MiB.")
                output = staged.joinpath(*relative)
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as incoming, output.open("wb") as file:
                    shutil.copyfileobj(incoming, file)
        if not (staged / "codehandler.bin").is_file() or not (staged / "GameSettings").is_dir():
            raise ValueError("Dolphin's archive is missing required system files.")
        license_source = staged.parent / "license.txt"
        license_target = target.parent / "license.txt"
        if license_source.is_file() and not license_target.exists():
            license_source.replace(license_target)
        if not target.exists():
            staged.replace(target)
            return
        for source in staged.rglob("*"):
            if source.is_file():
                dest = target / source.relative_to(staged)
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    source.replace(dest)
