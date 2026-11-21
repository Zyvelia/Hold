"""Which keyboard key performs each game action.

The defaults match the keys the window shipped with. A saved file replaces
them. One key belongs to one action: assigning it somewhere else lifts it
from the previous action.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pokemongb.gamepad import DEFAULT_PAD, PAD_LABELS, held_buttons
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Kinds that treat the shoulder triggers and the Tab key as L2/R2/L3.
TRIGGER_KINDS = frozenset({"3ds", "switch", "ps1", "ps2", "psp", "gc", "wii", "xbox", "x360", "wiiu"})
# D-pad also tilts the left stick on these machines.
LEFT_STICK_KINDS = TRIGGER_KINDS
RIGHT_STICK_KINDS = frozenset({"switch", "ps1", "ps2", "psp", "gc", "wii", "xbox", "x360", "wiiu"})


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    defaults: tuple[int, ...]
    gb_dir: int | None = None
    gb_button: int | None = None
    pad: int | None = None
    # "" every core, "not_gba" skips Game Boy Advance, "triggers" only the
    # machines with ZL/ZR, "swap" is the screen-swap / L3 key.
    pad_where: str = ""


def _k(*names: str) -> tuple[int, ...]:
    return tuple(getattr(Qt.Key, name) for name in names)


ACTIONS: tuple[Action, ...] = (
    Action("up", "Up", _k("Key_Up"), gb_dir=0x04, pad=4),
    Action("down", "Down", _k("Key_Down"), gb_dir=0x08, pad=5),
    Action("left", "Left", _k("Key_Left"), gb_dir=0x02, pad=6),
    Action("right", "Right", _k("Key_Right"), gb_dir=0x01, pad=7),
    Action("a", "A", _k("Key_X"), gb_button=0x01, pad=8),
    Action("b", "B", _k("Key_Z"), gb_button=0x02, pad=0),
    Action("y", "Y", _k("Key_A"), pad=1, pad_where="not_gba"),
    Action("x", "X", _k("Key_S"), pad=9, pad_where="not_gba"),
    Action("start", "Start", _k("Key_Return", "Key_Enter"), gb_button=0x08, pad=3),
    Action("select", "Select", _k("Key_Shift", "Key_Backspace"), gb_button=0x04, pad=2),
    Action("l", "L", _k("Key_Q"), pad=10),
    Action("r", "R", _k("Key_E"), pad=11),
    Action("zl", "ZL", _k("Key_F"), pad=12, pad_where="triggers"),
    Action("zr", "ZR", _k("Key_G"), pad=13, pad_where="triggers"),
    Action("mic", "Microphone", _k("Key_C"), pad=12, pad_where="not_gba"),
    Action("swap", "Swap screens", _k("Key_Tab"), pad_where="swap"),
    Action("rstick_up", "Right stick up", _k("Key_I")),
    Action("rstick_down", "Right stick down", _k("Key_K")),
    Action("rstick_left", "Right stick left", _k("Key_J")),
    Action("rstick_right", "Right stick right", _k("Key_L")),
    Action("fast", "Fast-forward", _k("Key_Space")),
    Action("rewind", "Rewind", _k("Key_R")),
    Action("step", "Step", _k("Key_Period")),
    Action("autofire", "Auto", _k("Key_V")),
    Action("save", "Save state", _k("Key_F5")),
    Action("load", "Load state", _k("Key_F8")),
    Action("slot1", "Slot 1", _k("Key_1")),
    Action("slot2", "Slot 2", _k("Key_2")),
    Action("slot3", "Slot 3", _k("Key_3")),
    Action("slot4", "Slot 4", _k("Key_4")),
    Action("slot5", "Slot 5", _k("Key_5")),
)

BY_ACTION = {action.id: action for action in ACTIONS}

# Face order for a diamond is top, left, right, bottom.
_NINTENDO = ("x", "y", "a", "b")
_STICK = ("rstick_up", "rstick_left", "rstick_right", "rstick_down")


@dataclass(frozen=True)
class PadView:
    """The buttons a machine actually has, with that machine's names."""

    face: tuple[str, ...]
    face_cross: bool
    captions: dict[str, str]
    shoulders: tuple[str, ...]
    stick: tuple[str, ...]
    stick_captions: tuple[str, str, str, str]
    play: tuple[str, ...]


def _view(
    face: tuple[str, ...],
    *,
    cross: bool = True,
    captions: dict[str, str] | None = None,
    shoulders: tuple[str, ...] = (),
    stick: tuple[str, ...] = (),
    stick_captions: tuple[str, str, str, str] = ("Up", "Left", "Right", "Down"),
    play: tuple[str, ...] = ("start", "select"),
) -> PadView:
    return PadView(face, cross, captions or {}, shoulders, stick, stick_captions, play)


_SONY = {"x": "Triangle", "y": "Square", "a": "Circle", "b": "Cross", "l": "L1", "r": "R1", "zl": "L2", "zr": "R2", "swap": "L3"}
_XBOX = {"x": "Y", "y": "X", "a": "B", "b": "A", "l": "LB", "r": "RB", "zl": "LT", "zr": "RT", "swap": "LS", "start": "Start", "select": "Back"}
_FULL = _view(
    _NINTENDO,
    shoulders=("l", "r", "zl", "zr"),
    stick=_STICK,
    play=("start", "select", "mic", "swap"),
)
_PAD_VIEWS: dict[str, PadView] = {
    "gb": _view(("b", "a"), cross=False),
    "gba": _view(("b", "a"), cross=False, shoulders=("l", "r")),
    "nes": _view(("b", "a"), cross=False),
    "fds": _view(("b", "a"), cross=False),
    "snes": _view(_NINTENDO, shoulders=("l", "r")),
    "nds": _view(_NINTENDO, shoulders=("l", "r"), play=("start", "select", "mic", "swap")),
    "3ds": _view(_NINTENDO, shoulders=("l", "r", "zl", "zr"), play=("start", "select", "mic", "swap")),
    "switch": _view(
        _NINTENDO,
        captions={"start": "+", "select": "−", "swap": "L3"},
        shoulders=("l", "r", "zl", "zr"),
        stick=_STICK,
        play=("start", "select", "swap"),
    ),
    "n64": _view(
        ("b", "a"),
        cross=False,
        captions={"a": "A", "b": "B", "zl": "Z"},
        shoulders=("l", "r", "zl"),
        stick=_STICK,
        stick_captions=("C-up", "C-left", "C-right", "C-down"),
        play=("start",),
    ),
    "gc": _view(
        _NINTENDO,
        captions={"zl": "Z"},
        shoulders=("l", "r", "zl"),
        stick=_STICK,
        stick_captions=("C-up", "C-left", "C-right", "C-down"),
        play=("start",),
    ),
    "wii": _view(
        _NINTENDO,
        captions={"start": "+", "select": "−", "zl": "ZL", "zr": "ZR"},
        shoulders=("l", "r", "zl", "zr"),
        stick=_STICK,
        play=("start", "select"),
    ),
    "wiiu": _view(
        _NINTENDO,
        captions={"start": "+", "select": "−", "swap": "L3"},
        shoulders=("l", "r", "zl", "zr"),
        stick=_STICK,
        play=("start", "select", "swap"),
    ),
    "ps1": _view(_NINTENDO, captions=_SONY, shoulders=("l", "r", "zl", "zr"), stick=_STICK, play=("start", "select", "swap")),
    "ps2": _view(_NINTENDO, captions=_SONY, shoulders=("l", "r", "zl", "zr"), stick=_STICK, play=("start", "select", "swap")),
    "psp": _view(_NINTENDO, captions={"x": "Triangle", "y": "Square", "a": "Circle", "b": "Cross", "l": "L", "r": "R"}, shoulders=("l", "r"), play=("start", "select")),
    "xbox": _view(_NINTENDO, captions=_XBOX, shoulders=("l", "r", "zl", "zr"), stick=_STICK, play=("start", "select", "swap")),
    "x360": _view(_NINTENDO, captions=_XBOX, shoulders=("l", "r", "zl", "zr"), stick=_STICK, play=("start", "select", "swap")),
    "md": _view(("b", "a", "y", "x", "l", "r"), cross=False, captions={"b": "A", "a": "B", "y": "C", "x": "X", "l": "Y", "r": "Z"}, play=("start", "select")),
    "mcd": _view(("b", "a", "y", "x", "l", "r"), cross=False, captions={"b": "A", "a": "B", "y": "C", "x": "X", "l": "Y", "r": "Z"}, play=("start", "select")),
    "s32x": _view(("b", "a", "y", "x", "l", "r"), cross=False, captions={"b": "A", "a": "B", "y": "C", "x": "X", "l": "Y", "r": "Z"}, play=("start", "select")),
    "saturn": _view(("b", "a", "y", "x", "l", "r"), cross=False, captions={"b": "A", "a": "B", "y": "C", "x": "X", "l": "Y", "r": "Z"}, play=("start",)),
    "sms": _view(("b", "a"), cross=False, captions={"b": "1", "a": "2"}),
    "gg": _view(("b", "a"), cross=False, captions={"b": "1", "a": "2"}),
    "sg": _view(("b", "a"), cross=False, captions={"b": "1", "a": "2"}),
    "pce": _view(("b", "a"), cross=False, captions={"b": "I", "a": "II", "start": "Run"}),
    "pcecd": _view(("b", "a"), cross=False, captions={"b": "I", "a": "II", "start": "Run"}),
    "dc": _view(_NINTENDO, shoulders=("l", "r"), play=("start",)),
    "arcade": _view(("y", "x", "l", "b", "a", "r"), cross=False, captions={"y": "1", "x": "2", "l": "3", "b": "4", "a": "5", "r": "6"}, play=("start", "select")),
    "a2600": _view(("b",), cross=False, captions={"b": "Fire"}, play=("start", "select")),
    "vb": _view(("b", "a"), cross=False, shoulders=("l", "r")),
}


def pad_view(kind: str | None) -> PadView:
    """The control layout for the open game. An empty kind shows every button."""
    if not kind:
        return _FULL
    return _PAD_VIEWS.get(kind, _FULL)


def pad_button(action_id: str, kind: str) -> int | None:
    """Libretro button index for this action on this machine, if it has one."""
    action = BY_ACTION.get(action_id)
    if action is None or kind in ("", "gb"):
        return None
    if action.pad_where == "swap":
        if kind == "gba":
            return None
        return 14 if kind in TRIGGER_KINDS else 13
    if action.pad is None:
        return None
    if action.pad_where == "triggers":
        return action.pad if kind in TRIGGER_KINDS else None
    if action.pad_where == "not_gba" and kind == "gba":
        return None
    return action.pad


def key_name(key: int) -> str:
    text = QKeySequence(key).toString()
    return text or "Unknown"


class Controls:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.bind: dict[str, list[int]] = {action.id: list(action.defaults) for action in ACTIONS}
        self.pad: dict[str, list[str]] = {action.id: list(DEFAULT_PAD.get(action.id, ())) for action in ACTIONS}
        self._load()

    def keys(self, action_id: str) -> list[int]:
        return list(self.bind.get(action_id, []))

    def actions_for(self, key: int) -> list[str]:
        return [action.id for action in ACTIONS if key in self.bind.get(action.id, [])]

    def label(self, action_id: str) -> str:
        keys = self.keys(action_id)
        if not keys:
            return "None"
        return ", ".join(key_name(key) for key in keys)

    def assign(self, action_id: str, key: int) -> None:
        if action_id not in self.bind or key <= 0:
            return
        for other, keys in self.bind.items():
            if other != action_id and key in keys:
                keys.remove(key)
        self.bind[action_id] = [key]
        self.save()

    def pad_label(self, action_id: str) -> str:
        buttons = self.pad.get(action_id, [])
        if not buttons:
            return "No pad"
        return ", ".join(PAD_LABELS.get(button, button) for button in buttons)

    def assign_pad(self, action_id: str, button: str) -> None:
        if action_id not in self.pad or button not in PAD_LABELS:
            return
        for other, buttons in self.pad.items():
            if other != action_id and button in buttons:
                buttons.remove(button)
        self.pad[action_id] = [button]
        self.save()

    def copy_to(self, path: Path) -> "Controls":
        """A game-specific map that is written only after a change."""
        other = Controls.__new__(Controls)
        other.path = Path(path)
        other.bind = {key: list(value) for key, value in self.bind.items()}
        other.pad = {key: list(value) for key, value in self.pad.items()}
        return other

    def reset(self) -> None:
        self.bind = {action.id: list(action.defaults) for action in ACTIONS}
        self.pad = {action.id: list(DEFAULT_PAD.get(action.id, ())) for action in ACTIONS}
        self.save()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        claimed: set[int] = set()
        seen: set[str] = set()
        for action in ACTIONS:
            value = raw.get(action.id)
            if not isinstance(value, list):
                continue
            keys = [int(item) for item in value if isinstance(item, int) and item > 0]
            self.bind[action.id] = keys
            claimed.update(keys)
            seen.add(action.id)
        for action in ACTIONS:
            if action.id in seen:
                continue
            self.bind[action.id] = [key for key in action.defaults if key not in claimed]
        pad_raw = raw.get("pad")
        if not isinstance(pad_raw, dict):
            return
        claimed_pad: set[str] = set()
        seen_pad: set[str] = set()
        for action in ACTIONS:
            value = pad_raw.get(action.id)
            if not isinstance(value, list):
                continue
            buttons = [str(item) for item in value if isinstance(item, str) and item in PAD_LABELS]
            self.pad[action.id] = buttons
            claimed_pad.update(buttons)
            seen_pad.add(action.id)
        for action in ACTIONS:
            if action.id in seen_pad:
                continue
            self.pad[action.id] = [button for button in DEFAULT_PAD.get(action.id, ()) if button not in claimed_pad]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {action.id: self.bind.get(action.id, []) for action in ACTIONS}
        payload["pad"] = {action.id: self.pad.get(action.id, []) for action in ACTIONS}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class ControlsDialog(QDialog):
    """Click an action, then press the key it should use."""

    def __init__(self, controls: Controls, parent=None, kind: str | None = None, system_name: str = ""):
        super().__init__(parent)
        self.controls = controls
        self.kind = kind or ""
        self.system_name = system_name
        self.view = pad_view(kind)
        self._listen: str | None = None
        self._pad_listen: str | None = None
        self._pad_baseline: set[str] = set()
        self._buttons: dict[str, QPushButton] = {}
        self._pad_buttons: dict[str, QPushButton] = {}
        self._pad_timer = QTimer(self)
        self._pad_timer.setInterval(30)
        self._pad_timer.timeout.connect(self._poll_pad)
        self.setWindowTitle(f"{system_name} controls" if system_name else "Controls")
        self.setObjectName("ControlsDialog")
        self.setMinimumSize(920, 640)
        self.resize(980, 760)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(
            """
            #ControlsDialog, #ControlBody { background: #1b1e17; color: #e6efd6; }
            #Hint { color: #8b987c; font-size: 13px; }
            #Banner {
                background: #2c3424;
                color: #e7f0d4;
                border: 1px solid #4d5a3e;
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 14px;
            }
            #ControlCard {
                background: #242a1e;
                border: 1px solid #3c4534;
                border-radius: 16px;
            }
            #CardTitle {
                color: #9aab86;
                font-size: 11px;
                font-weight: 600;
            }
            #ActionName { color: #c5d4b4; font-size: 12px; }
            QPushButton[keycap="true"] {
                background: #12160f;
                color: #f4f7ee;
                border: 1px solid #66725a;
                border-bottom: 3px solid #2c3426;
                border-radius: 10px;
                padding: 4px 8px;
                font-size: 14px;
                font-weight: 600;
                min-width: 72px;
                min-height: 36px;
            }
            QPushButton[keycap="true"]:hover { background: #1c2418; }
            QPushButton[keycap="true"][listening="true"] {
                background: #3a4628;
                color: #f6ffe4;
                border: 1px solid #d6e7a4;
                border-bottom: 3px solid #8ea85a;
            }
            QPushButton[pad="true"] {
                background: #1c2418;
                color: #d6e7a4;
                border: 1px solid #4d5a3e;
                border-radius: 8px;
                padding: 2px 6px;
                font-size: 11px;
                min-width: 72px;
                min-height: 22px;
            }
            QPushButton[pad="true"][listening="true"] {
                background: #3a4628;
                border: 1px solid #d6e7a4;
            }
            QPushButton[bar="true"] {
                background: #343a2c;
                color: #e6efd6;
                border: 1px solid #5d6752;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton[bar="true"]:hover { background: #3e4634; }
            """
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)
        hint = QLabel("Click a key, then press the new one. Click the pad name under it, then press a controller button.")
        hint.setObjectName("Hint")
        root.addWidget(hint)
        shown = system_name or "Every button"
        self.banner = QLabel(f"{shown}. The name on the key is what your keyboard sends.")
        self.banner.setObjectName("Banner")
        root.addWidget(self.banner)

        body = QWidget()
        body.setObjectName("ControlBody")
        board = QGridLayout(body)
        board.setSpacing(12)
        view = self.view
        board.addWidget(self._card("Move", self._cross(("up", "left", "right", "down"))), 0, 0)
        if view.face_cross and len(view.face) == 4:
            board.addWidget(self._card("Buttons", self._cross(view.face)), 0, 1)
        else:
            board.addWidget(self._card("Buttons", self._row(view.face)), 0, 1)
        next_row = 1
        if view.shoulders:
            board.addWidget(self._card("Shoulders", self._row(view.shoulders)), next_row, 0)
        if view.stick:
            board.addWidget(
                self._card("Right stick", self._cross(view.stick, view.stick_captions)),
                next_row,
                1 if view.shoulders else 0,
            )
        if view.shoulders or view.stick:
            next_row += 1
        board.addWidget(
            self._card("Play", self._row(view.play + ("fast", "rewind", "step"))),
            next_row,
            0,
            1,
            2,
        )
        board.addWidget(
            self._card("Save states", self._row(("slot1", "slot2", "slot3", "slot4", "slot5", "save", "load"))),
            next_row + 1,
            0,
            1,
            2,
        )
        board.setColumnStretch(0, 1)
        board.setColumnStretch(1, 1)
        board.setRowStretch(0, 0)
        board.setRowStretch(1, 0)
        board.setSizeConstraint(QGridLayout.SizeConstraint.SetMinimumSize)
        body.setMinimumHeight(body.sizeHint().height())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        bar = QHBoxLayout()
        bar.addWidget(self._bar_button("Defaults", self._restore))
        bar.addStretch(1)
        bar.addWidget(self._bar_button("Close", self.accept))
        root.addLayout(bar)
        self._refresh()

    def _card(self, title: str, content: QWidget) -> QFrame:
        frame = QFrame()
        frame.setObjectName("ControlCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)
        heading = QLabel(title.upper())
        heading.setObjectName("CardTitle")
        heading.setFixedHeight(16)
        layout.addWidget(heading)
        content.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        layout.addWidget(content, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        layout.addStretch(1)
        return frame

    def _cross(
        self,
        action_ids: tuple[str, str, str, str],
        captions: tuple[str, str, str, str] | None = None,
    ) -> QWidget:
        up, left, right, down = action_ids
        if captions is None:
            captions = (None, None, None, None)
        cap_up, cap_left, cap_right, cap_down = captions
        host = QWidget()
        host.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        for row in range(3):
            grid.setRowMinimumHeight(row, 108)
        for column in range(3):
            grid.setColumnMinimumWidth(column, 100)
        grid.addWidget(self._keycap(up, cap_up), 0, 1, Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(self._keycap(left, cap_left), 1, 0, Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(self._keycap(right, cap_right), 1, 2, Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(self._keycap(down, cap_down), 2, 1, Qt.AlignmentFlag.AlignCenter)
        host.setMinimumSize(340, 360)
        return host

    def _row(self, action_ids: tuple[str, ...]) -> QWidget:
        host = QWidget()
        row = QHBoxLayout(host)
        row.setSpacing(8)
        row.setContentsMargins(0, 0, 0, 0)
        for action_id in action_ids:
            row.addWidget(self._keycap(action_id))
        host.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        host.setMinimumHeight(max(host.sizeHint().height(), 64))
        return host

    def _keycap(self, action_id: str, caption: str | None = None) -> QWidget:
        action = BY_ACTION[action_id]
        box = QWidget()
        box.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        name = QLabel(caption or self.view.captions.get(action_id, action.label))
        name.setObjectName("ActionName")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setFixedHeight(18)
        name.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        button = QPushButton()
        button.setProperty("keycap", True)
        button.style().unpolish(button)
        button.style().polish(button)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setObjectName(f"Bind-{action.id}")
        button.setMinimumSize(88, 42)
        button.setFixedHeight(42)
        button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        button.clicked.connect(lambda _checked=False, chosen=action.id: self._arm(chosen))
        self._buttons[action.id] = button
        pad = QPushButton()
        pad.setProperty("pad", True)
        pad.style().unpolish(pad)
        pad.style().polish(pad)
        pad.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        pad.setObjectName(f"Pad-{action.id}")
        pad.setMinimumSize(88, 26)
        pad.setFixedHeight(26)
        pad.clicked.connect(lambda _checked=False, chosen=action.id: self._arm_pad(chosen))
        self._pad_buttons[action.id] = pad
        layout.addWidget(name)
        layout.addWidget(button)
        layout.addWidget(pad)
        box.setMinimumSize(88, 96)
        return box

    def _bar_button(self, text: str, handler) -> QPushButton:
        button = QPushButton(text)
        button.setProperty("bar", True)
        button.style().unpolish(button)
        button.style().polish(button)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(handler)
        return button

    def _arm(self, action_id: str) -> None:
        self._pad_listen = None
        self._pad_timer.stop()
        self._listen = action_id
        self._refresh()
        self.setFocus()

    def _arm_pad(self, action_id: str) -> None:
        self._listen = None
        self._pad_listen = action_id
        self._pad_baseline = held_buttons()
        self._refresh()
        self._pad_timer.start()
        self.setFocus()

    def _poll_pad(self) -> None:
        if self._pad_listen is None:
            self._pad_timer.stop()
            return
        held = held_buttons()
        fresh = held - self._pad_baseline
        self._pad_baseline &= held
        if not fresh:
            return
        self.controls.assign_pad(self._pad_listen, sorted(fresh)[0])
        self._pad_listen = None
        self._pad_timer.stop()
        self._refresh()

    def _restore(self) -> None:
        self._listen = None
        self._pad_listen = None
        self._pad_timer.stop()
        self.controls.reset()
        self._refresh()

    def _caption(self, action_id: str) -> str:
        return self.view.captions.get(action_id, BY_ACTION[action_id].label)

    def _refresh(self) -> None:
        if self._pad_listen:
            self.banner.setText(f"Press a controller button for {self._caption(self._pad_listen)}. Escape cancels.")
        elif self._listen:
            self.banner.setText(f"Press a key for {self._caption(self._listen)}. Escape cancels.")
        else:
            lead = f"{self.system_name}. " if self.system_name else ""
            self.banner.setText(f"{lead}The name on the key is what your keyboard sends. The name under it is the controller.")
        for action in ACTIONS:
            button = self._buttons.get(action.id)
            if button is None:
                continue
            listening = self._listen == action.id
            button.setText("Press" if listening else self.controls.label(action.id))
            button.setProperty("listening", listening)
            button.style().unpolish(button)
            button.style().polish(button)
            pad = self._pad_buttons[action.id]
            pad_listening = self._pad_listen == action.id
            pad.setText("Press" if pad_listening else self.controls.pad_label(action.id))
            pad.setProperty("listening", pad_listening)
            pad.style().unpolish(pad)
            pad.style().polish(pad)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and not event.isAutoRepeat():
            if self._listen is not None or self._pad_listen is not None:
                self._listen = None
                self._pad_listen = None
                self._pad_timer.stop()
                self._refresh()
                return
        if self._listen is None or event.isAutoRepeat():
            super().keyPressEvent(event)
            return
        self.controls.assign(self._listen, int(event.key()))
        self._listen = None
        self._refresh()

    def done(self, code: int) -> None:
        self._pad_timer.stop()
        super().done(code)
