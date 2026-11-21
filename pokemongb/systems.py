"""Cartridge and disc systems that share one libretro loader.

Game Boy, Game Boy Advance, DS, 3DS, and Switch stay on their own loaders.
This catalog is every other machine the window can start. No BIOS is shipped.
"""

from __future__ import annotations

import hashlib
import shutil
import struct
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

from pokemongb.libretro import Core, CoreError

__all__ = [
    "BY_ID",
    "BY_SUFFIX",
    "CoreError",
    "System",
    "bios_dir",
    "extra_globs",
    "locate",
    "open_core",
    "place_bios",
    "pack_state",
    "save_key",
    "title_of",
    "unpack_state",
]


@dataclass(frozen=True)
class System:
    id: str
    name: str
    dll: str
    suffixes: tuple[str, ...]
    full_path: bool
    scale: int = 2
    variables: tuple[tuple[bytes, bytes], ...] = ()
    hardware: str | None = None
    manual_suffixes: tuple[str, ...] = ()

    @property
    def open_suffixes(self) -> tuple[str, ...]:
        return self.suffixes + self.manual_suffixes


_SYSTEMS = (
    System("nes", "NES", "fceumm_libretro.dll", (".nes", ".unf", ".unif"), True),
    System("snes", "Super NES", "snes9x_libretro.dll", (".sfc", ".smc", ".swc", ".fig"), False),
    System(
        "md",
        "Mega Drive",
        "genesis_plus_gx_libretro.dll",
        (".md", ".mdx", ".gen", ".smd"),
        True,
    ),
    System("sms", "Master System", "genesis_plus_gx_libretro.dll", (".sms",), True),
    System("gg", "Game Gear", "genesis_plus_gx_libretro.dll", (".gg",), True),
    System("sg", "SG-1000", "genesis_plus_gx_libretro.dll", (".sg",), True),
    System("pce", "PC Engine", "mednafen_pce_fast_libretro.dll", (".pce",), True),
    System(
        "ps1",
        "PlayStation",
        "pcsx_rearmed_libretro.dll",
        (".cue", ".chd", ".pbp", ".exe", ".ccd", ".toc", ".m3u"),
        True,
        variables=((b"pcsx_rearmed_bios", b"auto"),),
    ),
    System(
        "gc",
        "GameCube",
        "dolphin_libretro.dll",
        (".gcm", ".gcz", ".rvz", ".tgc", ".dol", ".elf", ".iso"),
        True,
        scale=1,
        hardware="opengl",
        variables=(
            (b"dolphin_renderer", b"Hardware"),
            (b"dolphin_main_cpu_thread", b"disabled"),
            (b"dolphin_skip_gc_bios", b"enabled"),
        ),
        manual_suffixes=(".ciso", ".wia", ".m3u"),
    ),
    System(
        "wii",
        "Wii",
        "dolphin_libretro.dll",
        (".wbfs", ".wad", ".wia"),
        True,
        scale=1,
        hardware="opengl",
        variables=(
            (b"dolphin_renderer", b"Hardware"),
            (b"dolphin_main_cpu_thread", b"disabled"),
            (b"dolphin_skip_gc_bios", b"enabled"),
        ),
        manual_suffixes=(".iso", ".rvz", ".gcz", ".ciso", ".m3u"),
    ),
    System(
        "psp",
        "PSP",
        "ppsspp_libretro.dll",
        (".cso", ".prx"),
        True,
        variables=((b"ppsspp_software_rendering", b"enabled"),),
    ),
    System("a2600", "Atari 2600", "stella2014_libretro.dll", (".a26",), False),
    System("a5200", "Atari 5200", "a5200_libretro.dll", (".a52",), False),
    System("a7800", "Atari 7800", "prosystem_libretro.dll", (".a78", ".cdf"), False),
    System("lynx", "Atari Lynx", "handy_libretro.dll", (".lnx", ".lyx"), False),
    System("jaguar", "Atari Jaguar", "virtualjaguar_libretro.dll", (".j64", ".jag"), False),
    System("vectrex", "Vectrex", "vecx_libretro.dll", (".vec",), False),
    System("channelf", "Channel F", "freechaf_libretro.dll", (".chf",), False),
    System("ws", "WonderSwan", "mednafen_wswan_libretro.dll", (".ws", ".wsc", ".pc2"), False),
    System("ngp", "Neo Geo Pocket", "mednafen_ngp_libretro.dll", (".ngp", ".ngc", ".ngpc", ".npc"), True),
    System("vb", "Virtual Boy", "mednafen_vb_libretro.dll", (".vb", ".vboy"), False),
    System("sv", "Supervision", "potator_libretro.dll", (".sv",), False),
    System("s32x", "32X", "picodrive_libretro.dll", (".32x",), True),
    System("fds", "Famicom Disk System", "fceumm_libretro.dll", (".fds",), True),
    System("min", "Pokemon Mini", "pokemini_libretro.dll", (".min", ".pkm"), False),
    System(
        "n64",
        "Nintendo 64",
        "mupen64plus_next_libretro.dll",
        (".n64", ".z64", ".v64"),
        True,
        scale=2,
        hardware="opengl",
        manual_suffixes=(".bin",),
    ),
    System(
        "dc",
        "Dreamcast",
        "flycast_libretro.dll",
        (".cdi", ".gdi"),
        True,
        scale=1,
        hardware="opengl",
    ),
    System("mcd", "Sega CD", "genesis_plus_gx_libretro.dll", (), True),
    System("pcecd", "PC Engine CD", "mednafen_pce_fast_libretro.dll", (), True),
    System("saturn", "Saturn", "mednafen_saturn_libretro.dll", (), True),
    System(
        "ps2",
        "PlayStation 2",
        "pcsx2_libretro.dll",
        (".ciso", ".mdf", ".nrg", ".dump", ".img", ".zso"),
        True,
        scale=1,
        hardware="opengl",
        variables=((b"pcsx2_renderer", b"OpenGL"),),
    ),
    System("arcade", "Arcade", "fbneo_libretro.dll", (), False, scale=2),
    System(
        "xbox",
        "Xbox",
        "xemu_libretro.dll",
        (".xiso",),
        True,
        scale=1,
        hardware="vulkan",
    ),
    System(
        "x360",
        "Xbox 360",
        "xenia_edge_libretro.dll",
        (".xex", ".zar", ".xcp"),
        True,
        scale=1,
        hardware="vulkan",
    ),
    System(
        "wiiu",
        "Wii U",
        "cemu_libretro.dll",
        (".wud", ".wux", ".wua", ".rpx"),
        True,
        scale=1,
        hardware="vulkan",
        manual_suffixes=(".iso", ".elf", ".tmd"),
    ),
)

OPTIONAL_CONSOLES = (
    System("coleco", "ColecoVision", "gearcoleco_libretro.dll", (".col", ".cv"), False,
           manual_suffixes=(".bin", ".rom")),
    System("intv", "Intellivision", "freeintv_libretro.dll", (".int",), False,
           manual_suffixes=(".bin", ".rom")),
    System("odyssey2", "Odyssey² / Videopac", "o2em_libretro.dll", (), False,
           manual_suffixes=(".bin",)),
    System("3do", "3DO", "opera_libretro.dll", (), True,
           manual_suffixes=(".chd", ".cue", ".iso", ".bin")),
    System("neocd", "Neo Geo CD", "neocd_libretro.dll", (), True,
           manual_suffixes=(".chd", ".cue")),
    System("pcfx", "PC-FX", "mednafen_pcfx_libretro.dll", (), True,
           manual_suffixes=(".chd", ".cue", ".ccd", ".toc")),
    System("gamewatch", "Game & Watch", "gw_libretro.dll", (".mgw",), False),
)

OPTIONAL_BY_ID = {system.id: system for system in OPTIONAL_CONSOLES}
_ALL_SYSTEMS = _SYSTEMS + OPTIONAL_CONSOLES
BY_ID = {system.id: system for system in _ALL_SYSTEMS}
BY_SUFFIX = {suffix: system for system in _ALL_SYSTEMS for suffix in system.suffixes}
EXPLICIT_CONSOLES = OPTIONAL_CONSOLES + tuple(BY_ID[name] for name in ("n64", "gc", "wii", "wiiu"))
EXPLICIT_BY_ID = {system.id: system for system in EXPLICIT_CONSOLES}
_HANDHELD = {".gb", ".gbc", ".gba", ".nds"}


def cores_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "cores"


def module_dir() -> Path:
    """Folder that holds this copy of the module.

    Publisher packs this directory into the zmod. An installed zmod runs from
    the marketplace overlay, which is a different path than the source tree.
    """
    return Path(__file__).resolve().parents[1]


def bios_dir(filename: str, size: int = 0) -> Path:
    """Where a BIOS file belongs inside this module."""
    system = cores_dir() / "system"
    name = Path(filename).name.lower()
    if name in {"neocd_f.rom", "neocd_sf.rom", "front-sp1.bin", "neocd_t.rom",
                "neocd_st.rom", "top-sp1.bin", "neocd_z.rom", "neocd_sz.rom", "neocd.bin",
                "ng-lo.rom", "000-lo.lo", "uni-bioscd.rom"}:
        return system / "neocd"
    if name == "neogeo.zip":
        return system / "fbneo"
    if name in {"mcpx_1.0.bin", "complex_4627v1.03.bin", "xbox_hdd.qcow2"} or name.startswith("mcpx_"):
        return system / "xemu"
    if name == "keys.txt":
        return system / "Cemu"
    stem = name.replace("-", "").replace("_", "")
    ps2 = size >= 1024 * 1024 or name.endswith((".rom1", ".rom2", ".erom"))
    if "90001" in stem or "39001" in stem or "50001" in stem or "70012" in stem:
        ps2 = True
    if name.startswith("scph") and ps2:
        return system / "pcsx2" / "bios"
    return system


def place_bios(source: Path) -> Path:
    """Copy a BIOS file into this module. Returns the file that was written."""
    source = Path(source)
    dest_dir = bios_dir(source.name, source.stat().st_size)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / source.name
    if source.resolve() != dest.resolve():
        shutil.copy2(source, dest)
    return dest


def extra_globs() -> str:
    return " ".join(f"*{suffix}" for suffix in sorted(BY_SUFFIX))


def open_core(system: System, save_dir: Path) -> Core:
    dll = cores_dir() / system.dll
    if not dll.is_file():
        install = " Open Library → Console cores to install it." if system.id in OPTIONAL_BY_ID else ""
        raise CoreError(f"The {system.name} core is missing (cores/{system.dll}).{install}")
    system_root = dll.parent / "system"
    if system.id == "ps2":
        (system_root / "pcsx2" / "bios").mkdir(parents=True, exist_ok=True)
    elif system.id == "arcade":
        (system_root / "fbneo").mkdir(parents=True, exist_ok=True)
    elif system.id == "xbox":
        (system_root / "xemu").mkdir(parents=True, exist_ok=True)
    elif system.id == "x360":
        (system_root / "Xenia-Edge").mkdir(parents=True, exist_ok=True)
    elif system.id == "wiiu":
        (system_root / "Cemu").mkdir(parents=True, exist_ok=True)
    return Core(
        dll,
        dll.parent / "system",
        save_dir,
        variables=dict(system.variables),
        hardware=system.hardware,
    )


def title_of(filename: str) -> str:
    stem = Path(filename).stem
    title = "".join(ch if ch.isalnum() or ch in " _-" else " " for ch in stem).strip()
    return title or "ROM"


def save_key(system: System, path: Path) -> str:
    digest = hashlib.blake2s(digest_size=8)
    with Path(path).open("rb") as handle:
        digest.update(handle.read(0x1000))
    digest.update(str(Path(path).stat().st_size).encode())
    return f"{system.id}_" + digest.hexdigest().upper()


def _prefer(path: Path) -> System | None:
    """Pick PSP or GameCube when the suffix is shared."""
    suffix = path.suffix.lower()
    if suffix not in {".iso", ".elf", ".pbp"}:
        return None
    try:
        with path.open("rb") as handle:
            head = handle.read(0x30)
            if suffix == ".elf" and head[:4] == b"\x7fELF" and len(head) >= 40:
                machine = int.from_bytes(head[18:20], "little")
                flags = int.from_bytes(head[36:40], "little")
                if machine == 8 and (flags & 0x00FF0000) == 0x00920000:
                    return BY_ID["ps2"]
                if machine == 8:
                    return BY_ID["psp"]
                return None
            if suffix == ".pbp" and head[:4] == b"\x00PBP" and len(head) >= 0x28:
                offsets = struct.unpack_from("<8I", head, 8)
                if offsets[6] != offsets[7]:
                    return BY_ID["psp"]
                return None
            if suffix == ".iso" and len(head) >= 0x20:
                if head[0x1C:0x20] == bytes.fromhex("C2339F3D"):
                    return BY_ID["gc"]
                if head[0x18:0x1C] == bytes.fromhex("5D1C9EA3"):
                    return BY_ID["wii"]
                handle.seek(0x8000)
                pvd = handle.read(40)
                if len(pvd) >= 6 and pvd[1:6] == b"CD001":
                    if len(pvd) >= 40 and pvd[8:40].upper().startswith(b"PLAYSTATION"):
                        return BY_ID["ps2"]
                    return BY_ID["psp"]
                handle.seek(0x10000)
                if handle.read(21).startswith(b"MICROSOFT*XBOX*MEDIA"):
                    return BY_ID["xbox"]
    except OSError:
        return None
    return None


def _sniff_disc(path: Path) -> System | None:
    """Tell a Sega CD, Saturn, or PC Engine CD from a PlayStation cue."""
    if path.suffix.lower() != ".cue":
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    folded = text.lower()
    if "pce" in path.stem.lower() or "pc engine" in folded or "pcengine" in folded:
        return BY_ID["pcecd"]
    names = []
    for line in text.splitlines():
        if '"' not in line:
            continue
        names.append(line.split('"', 2)[1])
    for name in names:
        disc = path.parent / name
        try:
            with disc.open("rb") as handle:
                head = handle.read(0x200)
        except OSError:
            continue
        if b"SEGADISCSYSTEM" in head or b"SEGADISC" in head:
            return BY_ID["mcd"]
        if b"SEGASATURN" in head:
            return BY_ID["saturn"]
    return None


def locate_as(path: Path, cache: Path, system: System) -> Path:
    """Use the chosen console for ambiguous extensions such as BIN or CHD."""
    suffix = path.suffix.lower()
    if suffix == ".zip" and not system.full_path:
        with zipfile.ZipFile(path) as archive:
            matches = [
                entry for entry in archive.infolist()
                if not entry.is_dir() and not entry.filename.startswith("__MACOSX/")
                and Path(entry.filename).suffix.lower() in system.open_suffixes
            ]
            if len(matches) != 1:
                raise ValueError(f"Choose a ZIP with exactly one {system.name} game.")
            entry = matches[0]
            cache.mkdir(parents=True, exist_ok=True)
            path = cache / Path(entry.filename).name
            with archive.open(entry) as source, path.open("wb") as target:
                shutil.copyfileobj(source, target)
    elif suffix not in system.open_suffixes:
        allowed = ", ".join(system.open_suffixes)
        raise ValueError(f"{system.name} opens these file types: {allowed}.")
    if not path.is_file() or path.stat().st_size < 16:
        raise ValueError(f"That file is too small to be a {system.name} game.")
    return path


def locate(path: Path, cache: Path) -> tuple[Path, System] | None:
    """Return a ROM path and its system, or None when another loader should try."""
    path = Path(path)
    suffix = path.suffix.lower()
    system = _prefer(path) if path.is_file() else None
    if system is None:
        system = _sniff_disc(path) or BY_SUFFIX.get(suffix)
    elif suffix == ".cue":
        system = _sniff_disc(path) or system
    if system is not None:
        if not path.is_file() or path.stat().st_size < 16:
            raise ValueError(f"That file is too small to be a {system.name} ROM.")
        return path, system
    if suffix != ".zip":
        return None
    with zipfile.ZipFile(path) as zf:
        names = [name for name in zf.namelist() if not name.endswith("/") and not name.startswith("__MACOSX")]
        if any(Path(name).suffix.lower() in _HANDHELD for name in names):
            return None
        for name in names:
            system = BY_SUFFIX.get(Path(name).suffix.lower())
            if system is None:
                continue
            cache.mkdir(parents=True, exist_ok=True)
            dest = cache / Path(name).name
            with zf.open(name) as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out)
            if dest.stat().st_size < 16:
                raise ValueError(f"That file is too small to be a {system.name} ROM.")
            sniffed = _prefer(dest)
            return dest, sniffed or system
        if _arcade_names(names):
            return path, BY_ID["arcade"]
    return None


def _arcade_names(names: list[str]) -> bool:
    """A zip of ROM chips, rather than one console file packed inside."""
    chips = 0
    for name in names:
        suffix = Path(name).suffix.lower()
        if suffix in {"", ".bin", ".rom"}:
            chips += 1
    return chips >= 2 and chips * 2 >= len(names)


def pack_state(system_id: str, key: str, blob: bytes) -> bytes:
    raw = f"{system_id}\n{key}".encode("utf-8")
    return b"PXS1" + len(raw).to_bytes(2, "little") + raw + zlib.compress(blob, 1)


def unpack_state(data: bytes, system_id: str, key: str) -> bytes:
    if len(data) < 6 or not data.startswith(b"PXS1"):
        raise ValueError("That save state is not for this system.")
    length = int.from_bytes(data[4:6], "little")
    if len(data) < 6 + length:
        raise ValueError("That save state is damaged.")
    found = data[6:6 + length].decode("utf-8", errors="replace")
    system, _, found_key = found.partition("\n")
    if system != system_id or found_key != key:
        raise ValueError("That save state belongs to a different game.")
    return zlib.decompress(data[6 + length:])
