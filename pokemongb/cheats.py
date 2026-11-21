"""Name a cheat code from its shape, and turn Game Boy codes into patches.

Auto picks Game Genie, GameShark, Codebreaker, Action Replay, or a plain
address write. A chosen kind overrides that. The Game Boy patch rules match
the shapes mGBA accepts.
"""

from __future__ import annotations

import re

KINDS = (
    ("auto", "Auto"),
    ("genie", "Game Genie"),
    ("gameshark", "GameShark"),
    ("codebreaker", "Codebreaker"),
    ("actionreplay", "Action Replay"),
    ("address", "Address"),
)
KIND_NAMES = dict(KINDS)

_HEX = "0123456789ABCDEF"
_NES_GENIE = set("APZLGITYEOXUKSVN")


def describe(code: str, kind: str = "auto") -> str:
    """The label to show. Auto reads the code. Any other kind is used as chosen."""
    resolved = kind if kind and kind != "auto" else detect(code)
    return KIND_NAMES.get(resolved, "Code")


def detect(code: str) -> str:
    """Return a kind id, or an empty string when the code has no known shape."""
    compact = re.sub(r"\s+", "", code.strip().upper())
    if not compact:
        return ""
    if re.fullmatch(r"[0-9A-F]{4,8}:[0-9A-F]{2}", compact):
        return "address"
    if re.fullmatch(r"[0-9A-F]{3}-[0-9A-F]{3}(-[0-9A-F]{3})?", compact):
        return "genie"
    if re.fullmatch(r"[0-9A-F]{6}-[0-9A-F]{2}", compact):
        return "codebreaker"
    if "+" in compact:
        parts = compact.split("+")
        if all(re.fullmatch(r"[0-9A-F]{8}", part) for part in parts):
            return "actionreplay"
    if all(char in _NES_GENIE for char in compact) and len(compact) in (6, 8):
        if any(char not in _HEX for char in compact):
            return "genie"
    hex_only = "".join(char for char in compact if char in _HEX)
    if hex_only != compact:
        return ""
    if len(compact) in (6, 9):
        return "genie"
    if len(compact) == 8:
        return "gameshark"
    if len(compact) == 12:
        return "codebreaker"
    if len(compact) >= 16 and len(compact) % 8 == 0:
        return "actionreplay"
    return ""


def gb_effect(code: str, kind: str = "auto") -> tuple[str, int, int, int | None] | None:
    """A Game Boy patch: ("rom"|"ram", address, value, compare)."""
    resolved = kind if kind and kind != "auto" else detect(code)
    if resolved == "genie":
        parsed = _parse_genie(code)
        if parsed is None:
            return None
        address, value, compare = parsed
        return ("rom", address, value, compare)
    if resolved == "gameshark":
        parsed = _parse_gameshark(code)
        if parsed is None:
            return None
        address, value = parsed
        return ("ram", address, value, None)
    if resolved == "codebreaker":
        parsed = _parse_codebreaker(code)
        if parsed is None:
            return None
        address, value = parsed
        return ("ram", address, value, None)
    if resolved == "address":
        parsed = _parse_address(code)
        if parsed is None:
            return None
        address, value = parsed
        return ("ram", address, value, None)
    return None


def _parse_genie(code: str) -> tuple[int, int, int | None] | None:
    compact = "".join(char for char in code.upper() if char in _HEX)
    if len(compact) not in (6, 9):
        return None
    op1 = int(compact[0:3], 16)
    op2 = int(compact[3:6], 16)
    address = (op1 & 0xF) << 8
    address |= (op2 >> 4) & 0xFF
    address |= ((op2 & 0xF) ^ 0xF) << 12
    value = op1 >> 4
    compare = None
    if len(compact) == 9:
        op3 = int(compact[6:9], 16)
        mixed = ((op3 & 0xF00) << 20) | (op3 & 0xF)
        mixed &= 0xFFFFFFFF
        mixed = ((mixed >> 2) | (mixed << 30)) & 0xFFFFFFFF
        mixed = (mixed | (mixed >> 24)) & 0xFFFFFFFF
        compare = (mixed ^ 0xBA) & 0xFF
    return address, value, compare


def _parse_gameshark(code: str) -> tuple[int, int] | None:
    compact = "".join(char for char in code.upper() if char in _HEX)
    if len(compact) != 8:
        return None
    op = int(compact, 16)
    address = ((op & 0xFF) << 8) | ((op >> 8) & 0xFF)
    value = (op >> 16) & 0xFF
    return address, value


def _parse_codebreaker(code: str) -> tuple[int, int] | None:
    compact = re.sub(r"\s+", "", code.strip().upper())
    match = re.fullmatch(r"([0-9A-F]{4})([0-9A-F]{2})-([0-9A-F]{2})", compact)
    if match is None:
        return None
    op1 = int(match.group(1), 16)
    op2 = int(match.group(2), 16)
    value = int(match.group(3), 16)
    return ((op1 << 8) | op2) & 0xFFFF, value


def parse_cheat_file(text: str) -> list[tuple[str, str, bool]]:
    """Codes from a libretro .cht file or a plain list. Each item is name, code, enabled."""
    return [(name, code, enabled) for name, code, enabled, _kind in read_cheat_entries(text)]


def read_cheat_entries(text: str) -> list[tuple[str, str, bool, str]]:
    """Name, code, enabled, and kind from a cheat file."""
    if re.search(r"(?m)^cheats\s*=", text) or "cheat0_code" in text:
        return _parse_cht(text)
    return [(name, code, enabled, "auto") for name, code, enabled in _parse_cheat_lines(text)]


def write_cheat_file(rows: list[tuple[str, str, bool, str]]) -> str:
    """A .cht file the game can read back."""
    lines = [f"cheats = {len(rows)}", ""]
    for index, (name, code, enabled, kind) in enumerate(rows):
        lines.append(f'cheat{index}_desc = "{name.replace(chr(34), "")}"')
        lines.append(f'cheat{index}_code = "{code.replace(chr(34), "")}"')
        lines.append(f"cheat{index}_enable = {'true' if enabled else 'false'}")
        if kind and kind != "auto":
            lines.append(f'cheat{index}_kind = "{kind}"')
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _code_pieces(code: str) -> list[str]:
    text = code.strip().strip('"')
    if not text:
        return []
    if detect(text):
        return [text]
    parts = [part.strip() for part in text.split("+") if part.strip()]
    if len(parts) > 1 and all(detect(part) for part in parts):
        return parts
    return [text]


def _parse_cht(text: str) -> list[tuple[str, str, bool, str]]:
    found: dict[int, dict[str, str]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        match = re.fullmatch(r'cheat(\d+)_(desc|code|enable|kind)\s*=\s*"?(.*?)"?\s*', line)
        if match is None:
            continue
        slot = found.setdefault(int(match.group(1)), {})
        slot[match.group(2)] = match.group(3).strip()
    rows: list[tuple[str, str, bool, str]] = []
    for index in sorted(found):
        slot = found[index]
        code = slot.get("code", "")
        if not code:
            continue
        enabled = slot.get("enable", "true").lower() != "false"
        name = slot.get("desc", "")
        kind = slot.get("kind", "") or "auto"
        for piece in _code_pieces(code):
            rows.append((name, piece, enabled, kind))
    return rows


def _parse_cheat_lines(text: str) -> list[tuple[str, str, bool]]:
    rows: list[tuple[str, str, bool]] = []
    pending = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";") or line.startswith("//"):
            continue
        if detect(line):
            rows.append((pending, line, True))
            pending = ""
            continue
        named = _split_named(line)
        if named is not None:
            pending = ""
            name, code = named
            for piece in _code_pieces(code):
                rows.append((name, piece, True))
            continue
        pending = line
    return rows


def _split_named(line: str) -> tuple[str, str] | None:
    for sep in ("\t", " = ", ": ", "="):
        if sep not in line:
            continue
        left, right = line.split(sep, 1)
        code = right.strip().strip('"')
        name = left.strip().strip('"')
        if name and code and (detect(code) or len(_code_pieces(code)) > 1):
            return name, code
    return None


def _parse_address(code: str) -> tuple[int, int] | None:
    compact = re.sub(r"\s+", "", code.strip().upper())
    match = re.fullmatch(r"([0-9A-F]{4,8}):([0-9A-F]{2})", compact)
    if match is None:
        return None
    return int(match.group(1), 16), int(match.group(2), 16)


class RamSearch:
    """Narrow a RAM snapshot after something in the game changes."""

    def __init__(self) -> None:
        self.hits: dict[int, int] = {}
        self.started = False

    def start(self, memory: dict[int, int]) -> None:
        self.hits = {addr: value & 0xFF for addr, value in memory.items()}
        self.started = True

    def narrow(self, op: str, memory: dict[int, int], value: int | None = None) -> dict[int, int]:
        found: dict[int, int] = {}
        target = None if value is None else value & 0xFF
        for addr, old in self.hits.items():
            if addr not in memory:
                continue
            now = memory[addr] & 0xFF
            old &= 0xFF
            keep = False
            if op == "increased":
                keep = now > old
            elif op == "decreased":
                keep = now < old
            elif op == "changed":
                keep = now != old
            elif op == "unchanged":
                keep = now == old
            elif op == "equal" and target is not None:
                keep = now == target
            if keep:
                found[addr] = now
        self.hits = found
        return found
