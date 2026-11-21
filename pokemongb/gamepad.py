"""Read an Xbox-style controller through XInput.

The face buttons follow the diamond in the Controls window: the bottom button
is B, the right button is A, the left button is Y, and the top button is X.
Clicking the right stick rewinds.
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

DEADZONE = 7849
TRIGGER = 30
# Percent of the stick range that counts as centered. The window slider writes this.
deadzone_percent = 24


def axis_deadzone() -> int:
    percent = max(0, min(100, int(deadzone_percent)))
    return int(percent * 32767 / 100)

# Physical buttons. The Controls window can send each one to a different action.
_BITS = (
    (0x0001, "dup"),
    (0x0002, "ddown"),
    (0x0004, "dleft"),
    (0x0008, "dright"),
    (0x0010, "start"),
    (0x0020, "back"),
    (0x0040, "l3"),
    (0x0080, "r3"),
    (0x0100, "lb"),
    (0x0200, "rb"),
    (0x1000, "south"),
    (0x2000, "east"),
    (0x4000, "west"),
    (0x8000, "north"),
)

DEFAULT_PAD: dict[str, tuple[str, ...]] = {
    "up": ("dup",),
    "down": ("ddown",),
    "left": ("dleft",),
    "right": ("dright",),
    "a": ("east",),
    "b": ("south",),
    "y": ("west",),
    "x": ("north",),
    "start": ("start",),
    "select": ("back",),
    "l": ("lb",),
    "r": ("rb",),
    "zl": ("lt",),
    "zr": ("rt",),
    "swap": ("l3",),
    "rewind": ("r3",),
}

PAD_LABELS = {
    "dup": "D-up",
    "ddown": "D-down",
    "dleft": "D-left",
    "dright": "D-right",
    "start": "Start",
    "back": "Back",
    "l3": "L3",
    "r3": "R3",
    "lb": "LB",
    "rb": "RB",
    "south": "Bottom",
    "east": "Right",
    "west": "Left",
    "north": "Top",
    "lt": "LT",
    "rt": "RT",
}


@dataclass(frozen=True)
class Pad:
    actions: frozenset[str] = frozenset()
    lx: int = 0
    ly: int = 0
    rx: int = 0
    ry: int = 0
    connected: bool = False


EMPTY = Pad()


@dataclass(frozen=True)
class RawPad:
    buttons: frozenset[str] = frozenset()
    lx: int = 0
    ly: int = 0
    rx: int = 0
    ry: int = 0
    connected: bool = False


class _Gamepad(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_ushort),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class _State(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_ulong), ("Gamepad", _Gamepad)]


def _scale(raw: int, deadzone: int = DEADZONE) -> int:
    """Map a stick axis to -32768..32767, treating the dead zone as zero."""
    zone = max(0, min(32000, int(deadzone)))
    if zone <= 0:
        return max(-32768, min(32767, raw))
    if abs(raw) < zone:
        return 0
    sign = 1 if raw > 0 else -1
    span = max(1, 32767 - zone)
    magnitude = min(1.0, (abs(raw) - zone) / span)
    return max(-32768, min(32767, int(sign * magnitude * 32767)))


def raw_from(
    buttons: int,
    left_trigger: int,
    right_trigger: int,
    thumb_lx: int,
    thumb_ly: int,
    thumb_rx: int,
    thumb_ry: int,
    deadzone: int | None = None,
) -> RawPad:
    """XInput's Y axes are positive upward. The sticks here are positive downward."""
    zone = DEADZONE if deadzone is None else deadzone
    held = {name for bit, name in _BITS if buttons & bit}
    if left_trigger > TRIGGER:
        held.add("lt")
    if right_trigger > TRIGGER:
        held.add("rt")
    return RawPad(
        frozenset(held),
        _scale(thumb_lx, zone),
        -_scale(thumb_ly, zone),
        _scale(thumb_rx, zone),
        -_scale(thumb_ry, zone),
        True,
    )


def map_pad(raw: RawPad, bindings: dict[str, list[str]] | dict[str, tuple[str, ...]]) -> Pad:
    """Apply a control map, then let the sticks move even when the d-pad is rebound."""
    actions: set[str] = set()
    for action, buttons in bindings.items():
        if any(button in raw.buttons for button in buttons):
            actions.add(action)
    if raw.ly < 0:
        actions.add("up")
    elif raw.ly > 0:
        actions.add("down")
    if raw.lx < 0:
        actions.add("left")
    elif raw.lx > 0:
        actions.add("right")
    if raw.ry < 0:
        actions.add("rstick_up")
    elif raw.ry > 0:
        actions.add("rstick_down")
    if raw.rx < 0:
        actions.add("rstick_left")
    elif raw.rx > 0:
        actions.add("rstick_right")
    return Pad(frozenset(actions), raw.lx, raw.ly, raw.rx, raw.ry, raw.connected)


def interpret(
    buttons: int,
    left_trigger: int,
    right_trigger: int,
    thumb_lx: int,
    thumb_ly: int,
    thumb_rx: int,
    thumb_ry: int,
) -> Pad:
    """Turn one XInput packet into actions using the default button map."""
    return map_pad(
        raw_from(buttons, left_trigger, right_trigger, thumb_lx, thumb_ly, thumb_rx, thumb_ry),
        DEFAULT_PAD,
    )


_xinput = None
_tried = False
_xinput_count = 0


def _library():
    global _xinput, _tried
    if _tried:
        return _xinput
    _tried = True
    if sys.platform != "win32":
        return None
    for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            lib = ctypes.WinDLL(name)
        except OSError:
            continue
        lib.XInputGetState.argtypes = [ctypes.c_uint, ctypes.POINTER(_State)]
        lib.XInputGetState.restype = ctypes.c_uint
        _xinput = lib
        break
    return _xinput


class _Vibration(ctypes.Structure):
    _fields_ = [("wLeftMotorSpeed", ctypes.c_ushort), ("wRightMotorSpeed", ctypes.c_ushort)]


def set_rumble(port: int, strong: int, weak: int) -> None:
    """Left motor is the heavy rumble. Right motor is the light one."""
    lib = _library()
    if lib is not None and 0 <= port <= 3 and hasattr(lib, "XInputSetState"):
        if not getattr(lib, "_rumble_ready", False):
            lib.XInputSetState.argtypes = [ctypes.c_uint, ctypes.POINTER(_Vibration)]
            lib.XInputSetState.restype = ctypes.c_uint
            lib._rumble_ready = True
        vib = _Vibration(
            max(0, min(65535, int(strong))),
            max(0, min(65535, int(weak))),
        )
        lib.XInputSetState(int(port), ctypes.byref(vib))
    from pokemongb.sony import rumble_index

    rumble_index(int(port) - _xinput_count, strong, weak)


def live_raw() -> list[RawPad]:
    """Connected controllers, lowest XInput index first."""
    global _xinput_count
    lib = _library()
    if lib is None:
        _xinput_count = 0
        return []
    found: list[RawPad] = []
    for index in range(4):
        state = _State()
        if lib.XInputGetState(index, ctypes.byref(state)) != 0:
            continue
        pad = state.Gamepad
        found.append(
            raw_from(
                int(pad.wButtons),
                int(pad.bLeftTrigger),
                int(pad.bRightTrigger),
                int(pad.sThumbLX),
                int(pad.sThumbLY),
                int(pad.sThumbRX),
                int(pad.sThumbRY),
                deadzone=axis_deadzone(),
            )
        )
    _xinput_count = len(found)
    return found


def read_players(bindings: dict[str, list[str]] | dict[str, tuple[str, ...]]) -> tuple[Pad, Pad]:
    """Player 1 and player 2. Xbox pads come first, then a PlayStation pad."""
    from pokemongb.sony import sony_pads

    found = live_raw() + sony_pads()
    first = map_pad(found[0], bindings) if found else EMPTY
    second = map_pad(found[1], bindings) if len(found) > 1 else EMPTY
    return first, second


def held_buttons() -> set[str]:
    """Physical buttons held on the first controller, for the Controls window."""
    found = live_raw()
    return set(found[0].buttons) if found else set()
