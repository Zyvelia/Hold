"""Playable page. The multi-tool can host this widget later.

Constructor is (parent=None, manager=None), which matches QtModuleShell.
"""

from __future__ import annotations

import array
import fnmatch
import hashlib
import json
import os
import time
import zipfile
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QKeyEvent, QMouseEvent, QPainter, QPixmap, QTransform
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QAudioSource, QMediaDevices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QProgressDialog,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pokemongb.cheats import _parse_address
from pokemongb.cart import (
    gba_save_key,
    gba_title,
    n3ds_header,
    n3ds_save_key,
    n3ds_title,
    nds_save_key,
    nds_title,
    open_rom,
    prepare_3ds,
    prepare_switch,
    rom_title,
    ROM_SUFFIXES,
    save_key,
    switch_save_key,
    switch_title,
)
from pokemongb.controls import BY_ACTION, LEFT_STICK_KINDS, RIGHT_STICK_KINDS, Controls, ControlsDialog, pad_button
import pokemongb.gamepad as gamepad
from pokemongb.gamepad import EMPTY, Pad, read_players
from pokemongb.gba import CoreError, open_core as open_gba
from pokemongb.library import Library, game_id
from pokemongb.local_link import LocalLinkDialog, battery_paths, read_battery, write_battery
from pokemongb.shelf import CheatSearchDialog, GameSettings, Shelf
from pokemongb.gba import pack_state as pack_gba_state
from pokemongb.gba import unpack_state as unpack_gba_state
from pokemongb.libretro import Core
from pokemongb.n3ds import open_core as open_n3ds
from pokemongb.n3ds import pack_state as pack_n3ds_state
from pokemongb.n3ds import unpack_state as unpack_n3ds_state
from pokemongb.nds import open_core as open_nds
from pokemongb.rewind import Rewind
from pokemongb.nds import pack_state as pack_nds_state
from pokemongb.nds import unpack_state as unpack_nds_state
from pokemongb.netplay import NET_ACTIONS, Beacon, Link, Relay, discover, pack_input, unpack_input
from pokemongb.patch import apply_patch
from pokemongb.picture import adjust, blend, gb_picture, screens_top_large
from pokemongb.soundfx import AudioDelay, peak_level, scale_pcm, tone_pcm, wav_header
from pokemongb.netplay import _full_packet as _full_net
from pokemongb.switch import open_core as open_switch
from pokemongb.switch import pack_state as pack_switch_state
from pokemongb.switch import unpack_state as unpack_switch_state
from pokemongb.system import GameBoy
from pokemongb.systems import BY_ID, BY_SUFFIX
from pokemongb.systems import extra_globs
from pokemongb.systems import cores_dir
from pokemongb.systems import module_dir
from pokemongb.systems import place_bios
from pokemongb.systems import locate
from pokemongb.systems import open_core as open_system
from pokemongb.systems import pack_state as pack_system_state
from pokemongb.systems import save_key as system_save_key
from pokemongb.systems import title_of
from pokemongb.systems import unpack_state as unpack_system_state

_HELP = (
    "Arrows move    X is A    Z is B    A is Y    S is X    Enter is Start    Shift is Select\n"
    "Q is L    E is R    F is ZL    G is ZR    C is the DS microphone    "
    "Click the bottom screen    Tab swaps screens    I J K L is the right stick    "
    "Press Space to fast-forward. Press it again for normal speed. "
    "The Speed list runs from quarter speed to 8x. Period advances one frame. Hold R to rewind\n"
    "A controller works too, including a PlayStation pad. The face buttons follow the diamond, "
    "the sticks move the sticks, and clicking the right stick rewinds.\n"
    "Keys 1–5 pick a slot    F5 saves    F8 loads    "
    "Save states opens a menu. Autosave is the top slot and writes itself every few minutes. Slots 1–10 can be named. "
    "A save state freezes the whole game. The battery file only keeps the cartridge save.\n"
    "Master System, Game Gear, SG-1000, PC Engine, Atari 2600, 5200, 7800, "
    "Lynx, Jaguar, Vectrex, Channel F, WonderSwan, Neo Geo Pocket, Virtual Boy, "
    "Supervision, and 32X open from their own ROM. "
    "Game Boy through Nintendo Switch stay as they were. "
    "No BIOS, firmware, or Switch keys are included. "
    "Add BIOS copies the files you pick into this module, the same folder a zmod is built from. "
    "A PlayStation disc can use scph5501.bin in cores\\system when you add that file. "
    "PlayStation 2 uses a BIOS file in cores\\system\\pcsx2\\bios, such as scph39001.bin. "
    "An arcade zip opens as Arcade. Neo Geo needs neogeo.zip in cores\\system\\fbneo. "
    "Xbox needs mcpx_1.0.bin, Complex_4627v1.03.bin, and xbox_hdd.qcow2 in cores\\system\\xemu. "
    "Xbox 360 opens an .xex. Wii U needs keys.txt in cores\\system\\Cemu.\n"
    "Library keeps every ROM you open. The three dots on a cartridge set its picture and cheats.\n"
    "Open ROM accepts more than one file. Those games wait in the library until you pick one.\n"
    "Controls, beside Help, is where you choose which key and which controller button does each action. "
    "Each game keeps its own map after you change it.\n"
    "Fullscreen, the volume slider, and Screenshot are on the bar. "
    "The picture list is Sharp, Smooth, or Scanlines, and also CRT or LCD. "
    "Tools holds square pixels, the bezel, brightness, color, frame blend, a wide stretch, "
    "the speaker, latency, a high or low pass, sound recording, and whether the picture or the sound leads. "
    "The library can list games, hide one, and show the ones you played recently. "
    "The window remembers where it sat. A ROM path on the command line opens that game. "
    "A second controller plays as player 2. "
    "The numpad is player 2 as well: 8, 2, 4, and 6 move, 5 is A, 0 is B, 7 is Y, 9 is X, "
    "plus is Start, minus is Select, 1 is L, and 3 is R.\n"
    "The Zone slider is how far a stick must move.\n"
    "Netplay: one side presses Host, the other presses Join and types that computer's address. "
    "Delay is how many frames the game waits so a far connection stays smooth. "
    "The lobby lists hosts on this network. A password keeps strangers out. Chat sits beside the game. "
    "Rollback repairs a late button. Watch joins without playing. A third and fourth player can join the same host. "
    "A PlayStation pad rumbles. Nintendo 64, Dreamcast, Saturn, Sega CD, PC Engine CD, "
    "Famicom Disk System, and Pokemon Mini open from their own files. "
    "Sega CD can use bios_CD_U.bin, Dreamcast dc_boot.bin and dc_flash.bin, "
    "Saturn saturn_bios.bin, PC Engine CD syscard3.pce, and the Disk System disksys.rom, in cores\\system. "
    "The same game stays in step and the joiner is player 2. "
    "Two Game Boys use that connection as a link cable. "
    "Two Game Boy Advance games use it as a link cable when the core opens its link registers.\n"
    "Fullscreen hides the buttons. Escape brings them back. "
    "DS and 3DS screens can be stacked or side by side.\n"
    "The library has a search box, and a star marks a favorite. "
    "Each cartridge shows how long you have played it. "
    "Cheat search watches RAM: change something in the game, then narrow the list. "
    "Import cheats reads a whole list of codes. Codes you add are saved as a cheat file, and the game reads that file. "
    "Choose patch applies an .ips or .bps file when that game opens.\n"
    "Save states keep a picture from the moment you saved."
)


def screens_side_by_side(frame: bytes, width: int, height: int) -> tuple[bytes, int, int]:
    """Place the top half of a stacked picture to the left of the bottom half."""
    if width <= 0 or height < 2 or height % 2:
        return frame, width, height
    raw = bytes(frame)
    stride = width * 4
    if len(raw) < stride * height:
        return frame, width, height
    half = height // 2
    out = bytearray(stride * 2 * half)
    for line in range(half):
        top = raw[line * stride:(line + 1) * stride]
        bottom = raw[(line + half) * stride:(line + half + 1) * stride]
        start = line * stride * 2
        out[start:start + stride] = top
        out[start + stride:start + stride * 2] = bottom
    return bytes(out), width * 2, half


_P2_KEYS = {
    int(Qt.Key.Key_8): "up",
    int(Qt.Key.Key_2): "down",
    int(Qt.Key.Key_4): "left",
    int(Qt.Key.Key_6): "right",
    int(Qt.Key.Key_5): "a",
    int(Qt.Key.Key_0): "b",
    int(Qt.Key.Key_7): "y",
    int(Qt.Key.Key_9): "x",
    int(Qt.Key.Key_Plus): "start",
    int(Qt.Key.Key_Minus): "select",
    int(Qt.Key.Key_1): "l",
    int(Qt.Key.Key_3): "r",
}


_AUTO = frozenset({"a", "b", "y", "x", "l", "r", "zl", "zr"})


def _p2_action(event: QKeyEvent) -> str:
    if not (event.modifiers() & Qt.KeyboardModifier.KeypadModifier):
        return ""
    return _P2_KEYS.get(int(event.key()), "")

_ROM_FILTER = (
    "ROMs (*.gb *.gbc *.gba *.nds *.3ds *.3dsx *.cci *.cxi *.nsp *.xci *.nro {extra} *.zip)"
)


STATE_SLOTS = 10
AUTO_SLOT = 0


class SaveStatesMenu(QDialog):
    """Popup that lists the autosave and the numbered save-state slots."""

    def __init__(self, page: "PokemonGBPage"):
        super().__init__(page)
        self.page = page
        self.setWindowTitle("Save states")
        self.setObjectName("SaveStatesMenu")
        self.setMinimumWidth(460)
        self.setStyleSheet(
            """
            #SaveStatesMenu { background: #1b1e17; color: #e6efd6; }
            #SlotRow {
                background: #242a1e;
                border: 1px solid #3c4534;
                border-radius: 12px;
            }
            #SlotRow[current="true"] { border: 1px solid #d6e7a4; }
            #SlotName { color: #e6efd6; font-size: 15px; font-weight: 600; }
            #SlotState { color: #9aab86; font-size: 13px; }
            #Hint { color: #8b987c; font-size: 12px; }
            QPushButton {
                background: #343a2c;
                color: #e6efd6;
                border: 1px solid #5d6752;
                border-radius: 8px;
                padding: 8px 14px;
            }
            QPushButton:disabled { color: #66725a; }
            """
        )
        root = QVBoxLayout(self)
        root.setSpacing(10)
        hint = QLabel("Autosave sits at the top. The numbered slots are the ones you save yourself.")
        hint.setObjectName("Hint")
        root.addWidget(hint)
        self._rows: dict[int, QFrame] = {}
        self._states: dict[int, QLabel] = {}
        self._shots: dict[int, QLabel] = {}
        self._loads: dict[int, QPushButton] = {}
        self._names: dict[int, QLabel] = {}
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        slots = QVBoxLayout(body)
        slots.setSpacing(10)
        for slot in (AUTO_SLOT, *range(1, STATE_SLOTS + 1)):
            frame = QFrame()
            frame.setObjectName("SlotRow")
            row = QHBoxLayout(frame)
            shot = QLabel()
            shot.setObjectName(f"SlotShot-{slot}")
            shot.setFixedSize(112, 84)
            shot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name = QLabel(self.page._slot_title(slot))
            name.setObjectName("SlotName")
            state = QLabel()
            state.setObjectName(f"SlotState-{slot}")
            save = QPushButton("Save")
            save.setObjectName(f"SlotSave-{slot}")
            save.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            load = QPushButton("Load")
            load.setObjectName(f"SlotLoad-{slot}")
            load.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            save.clicked.connect(lambda _checked=False, chosen=slot: self._save(chosen))
            load.clicked.connect(lambda _checked=False, chosen=slot: self._load(chosen))
            row.addWidget(shot)
            row.addWidget(name)
            row.addWidget(state, 1)
            if slot != AUTO_SLOT:
                rename = QPushButton("Name")
                rename.setObjectName(f"SlotNameBtn-{slot}")
                rename.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                rename.clicked.connect(lambda _checked=False, chosen=slot: self._rename(chosen))
                row.addWidget(rename)
            row.addWidget(save)
            row.addWidget(load)
            slots.addWidget(frame)
            self._rows[slot] = frame
            self._states[slot] = state
            self._shots[slot] = shot
            self._loads[slot] = load
            self._names[slot] = name
        scroll.setWidget(body)
        scroll.setMinimumHeight(360)
        root.addWidget(scroll, 1)
        close = QPushButton("Close")
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.clicked.connect(self.accept)
        root.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        self.refresh()

    def refresh(self) -> None:
        for slot in self._states:
            self._names[slot].setText(self.page._slot_title(slot))
            saved = self.page._state_file(slot).is_file()
            self._states[slot].setText("Saved" if saved else "Empty")
            picture = self.page._slot_picture(slot)
            if picture.is_file():
                shot = QPixmap(str(picture)).scaled(
                    112,
                    84,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._shots[slot].setPixmap(shot)
                self._shots[slot].setText("")
            else:
                self._shots[slot].setPixmap(QPixmap())
                self._shots[slot].setText("")
            self._loads[slot].setEnabled(saved and self.page.rom is not None)
            current = slot == self.page.state_slot
            self._rows[slot].setProperty("current", current)
            self._rows[slot].style().unpolish(self._rows[slot])
            self._rows[slot].style().polish(self._rows[slot])

    def _save(self, slot: int) -> None:
        self.page._set_slot(slot)
        self.page.save_state()
        self.refresh()

    def _load(self, slot: int) -> None:
        self.page._set_slot(slot)
        self.page.load_state()
        self.refresh()

    def _rename(self, slot: int) -> None:
        current = self.page._slot_title(slot)
        text, ok = QInputDialog.getText(self, "Slot name", "Name", text="" if current.startswith("Slot ") else current)
        if not ok:
            return
        self.page._set_slot_title(slot, text)
        self.refresh()


def _saves_dir() -> Path:
    folder = Path(__file__).resolve().parents[1] / "saves"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _resample(page: "PokemonGBPage", data: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Stereo int16, keeping the fractional position across frames."""
    if not data or src_rate == dst_rate or src_rate <= 0:
        return data
    incoming = array.array("h")
    incoming.frombytes(data[: len(data) & ~3])
    frames = len(incoming) // 2
    if frames == 0:
        return b""
    stereo = array.array("h", [page._audio_hold_l, page._audio_hold_r])
    stereo.extend(incoming)
    step = src_rate / dst_rate
    pos = page._audio_pos
    last = frames
    out = array.array("h")
    while pos < last:
        index = int(pos)
        frac = pos - index
        nxt = index + 1
        for channel in (0, 1):
            sample = stereo[index * 2 + channel]
            mixed = sample + (stereo[nxt * 2 + channel] - sample) * frac
            mixed = int(mixed)
            if mixed > 32767:
                mixed = 32767
            elif mixed < -32768:
                mixed = -32768
            out.append(mixed)
        pos += step
    page._audio_hold_l = incoming[-2]
    page._audio_hold_r = incoming[-1]
    page._audio_pos = pos - frames
    if page._audio_pos < 0:
        page._audio_pos = 0.0
    return out.tobytes()


class _ScreenViewport(QWidget):
    resized = Signal()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.resized.emit()


class _FlowBar(QWidget):
    """Toolbar that wraps onto the next line instead of crushing its buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Toolbar")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._gap = 8
        self._items: list[QWidget] = []
        self._busy = False

    def add(self, widget: QWidget) -> None:
        widget.setParent(self)
        widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._items.append(widget)

    def add_gap(self, width: int) -> None:
        gap = QWidget(self)
        gap.setFixedSize(width, 1)
        self._items.append(gap)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._place(width, apply=False)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place(self.width(), apply=True)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._place(max(self.width(), 1), apply=True)

    def reflow(self) -> None:
        self._place(max(self.width(), 1), apply=True)
        self.updateGeometry()

    def _span(self, widget: QWidget) -> tuple[int, int]:
        hint = widget.sizeHint()
        least = widget.minimumSizeHint()
        width = max(hint.width(), least.width())
        height = max(hint.height(), least.height(), 32)
        if isinstance(widget, QPushButton):
            width = max(width, widget.fontMetrics().horizontalAdvance(widget.text()) + 36)
        return width, height

    def _place(self, width: int, apply: bool) -> int:
        if self._busy:
            return self.minimumHeight()
        limit = max(int(width), 1)
        x = y = 0
        row_h = 0
        for widget in self._items:
            if widget.isHidden():
                continue
            w, h = self._span(widget)
            if x > 0 and x + w > limit:
                y += row_h + self._gap
                x = 0
                row_h = 0
            if apply:
                widget.setGeometry(x, y, w, h)
            x += w + self._gap
            row_h = max(row_h, h)
        total = y + row_h
        if apply and self.minimumHeight() != total:
            self._busy = True
            self.setMinimumHeight(total)
            self._busy = False
        return total


class BiosManager(QDialog):
    """Read-only BIOS presence report; never downloads copyrighted firmware."""

    # Checks follow the locations accepted by systems.place_bios().
    # Presence does NOT validate content, checksum, compatibility or licensing.
    REQUIREMENTS = (
        ("PlayStation", "Recommended", ("scph5501.bin", "scph5500.bin", "scph5502.bin"), "any", ""),
        ("PlayStation 2", "Required", ("scph*.bin", "*.rom1", "*.rom2"), "any", "pcsx2/bios"),
        ("Sega CD", "Required for CD games", ("bios_CD_U.bin", "bios_CD_E.bin", "bios_CD_J.bin"), "any", ""),
        ("Saturn", "Core-dependent", ("saturn_bios.bin", "mpr-17933.bin", "sega_101.bin"), "any", ""),
        ("PC Engine CD", "Required for CD games", ("syscard3.pce",), "any", ""),
        ("Famicom Disk System", "Required for disks", ("disksys.rom",), "any", ""),
        ("Dreamcast", "Core-dependent", ("dc_boot.bin", "dc_flash.bin"), "all", "dc"),
        ("Neo Geo (FBNeo)", "Required for Neo Geo", ("neogeo.zip",), "all", "fbneo"),
        ("Xbox", "Required", ("mcpx_1.0.bin", "Complex_4627v1.03.bin", "xbox_hdd.qcow2"), "all", "xemu"),
        ("Wii U", "Some encrypted games", ("keys.txt",), "all", "Cemu"),
    )

    def __init__(self, page: "PokemonGBPage"):
        super().__init__(page)
        self.page = page
        self.setObjectName("BiosManager")
        self.setWindowTitle("BIOS Manager")
        self.resize(720, 480)
        self.setMinimumWidth(540)
        self.setStyleSheet("""
            #BiosManager { background: #0f1115; color: #e6e6e6; }
            QLabel { color: #e6e6e6; }
            #BiosSummary { color: #c4b5fd; font-weight: 600; }
            #BiosHint { color: #9aa4b2; }
            #BiosRow { background: #151922; border: 1px solid #252d3d; border-radius: 8px; }
            QPushButton { background: #1b2030; color: #e6e6e6; border: 1px solid #252d3d;
                          border-radius: 8px; padding: 8px 12px; }
            QPushButton:hover { border-color: #a78bfa; }
        """)
        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setObjectName("BiosSummary")
        layout.addWidget(self.summary)
        hint = QLabel("File detection only — filenames do not verify BIOS integrity. Some cores use alternate firmware paths.\nOnly import BIOS/firmware you are authorized to use.")
        hint.setObjectName("BiosHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.body = QWidget()
        self.rows = QVBoxLayout(self.body)
        self.rows.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.body)
        layout.addWidget(scroll, 1)
        actions = QHBoxLayout()
        add = QPushButton("Add BIOS files")
        add.clicked.connect(self._add)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        actions.addWidget(add)
        actions.addWidget(refresh)
        actions.addStretch()
        actions.addWidget(close)
        layout.addLayout(actions)
        self.refresh()

    @classmethod
    def scan(cls, root: Path) -> list[tuple[str, str, bool, str]]:
        result = []
        for name, need, patterns, mode, subdir in cls.REQUIREMENTS:
            folder = root / subdir if subdir else root
            matches = []
            for pattern in patterns:
                files = [p for p in folder.glob(pattern) if p.is_file() and p.stat().st_size > 0]
                # Windows names are case insensitive; on other platforms also permit case variants.
                if not files and folder.is_dir():
                    files = [f for f in folder.iterdir() if f.is_file() and f.stat().st_size > 0
                             and fnmatch.fnmatch(f.name.casefold(), pattern.casefold())]
                matches.append(bool(files))
            found = all(matches) if mode == "all" else any(matches)
            result.append((name, need, found, (f"{subdir}/" if subdir else "") + (" + " if mode == "all" else " / ").join(patterns)))
        return result

    def refresh(self) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        entries = self.scan(cores_dir() / "system")
        present = sum(found for _, _, found, _ in entries)
        self.summary.setText(f"Firmware inventory: {present}/{len(entries)} groups detected")
        for system, need, found, patterns in entries:
            frame = QFrame()
            frame.setObjectName("BiosRow")
            line = QVBoxLayout(frame)
            label = QLabel(f"{'✓ Detected' if found else '— Not detected'}  |  {system}  ({need})")
            label.setStyleSheet(f"color: {'#7ed9aa' if found else '#d9b17e'}; font-weight: 600;")
            line.addWidget(label)
            detail = QLabel(patterns)
            detail.setObjectName("BiosHint")
            detail.setWordWrap(True)
            line.addWidget(detail)
            self.rows.addWidget(frame)

    def _add(self) -> None:
        self.page._add_bios()
        self.refresh()


class PokemonGBPage(QWidget):
    def __init__(self, parent=None, manager=None):
        super().__init__(parent)
        self.manager = manager
        self.setObjectName("PokemonGB")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)

        self.gb: GameBoy | None = None
        self.gba: Core | None = None
        self.nds: Core | None = None
        self.n3ds: Core | None = None
        self.switch: Core | None = None
        self.extra: dict[str, Core] = {}
        self.kind: str | None = None
        self._touching = False
        self._down_keys: set[int] = set()
        self._pad_down: set[str] = set()
        self._pad2_down: set[str] = set()
        self._pad: Pad = EMPTY
        self._pad2: Pad = EMPTY
        self.rewind = Rewind()
        self._rewind_warned = False
        self._read_pads = self._pads_from_controllers
        self._fullscreen = False
        self._step_once = False
        self._rate_phase = 0
        self._p2_down: set[str] = set()
        self._touch_size = (160, 144)
        self._crop_origin = (0, 0)
        self._touch_side = False
        self._cheat_dialog = None
        self._autofire = False
        self._auto_phase = 0
        self._play_bank = 0.0
        self._play_mark = 0.0
        self._net_local: list[bytes] = []
        self._net_password = ""
        self._last_join: tuple[str, int, bool] | None = None
        self._reconnect_until = 0.0
        self._reconnect_try = 0.0
        self._ping_at = 0.0
        self._sync_at = 0.0
        self._sync_seen: dict[int, bytes] = {}
        self._desync_noted = False
        self._beacon = Beacon()
        self._relay: Relay | None = None
        self._errors: list[str] = []
        self._rotate = 0
        self._crop = 0
        self._on_top = False
        self._muted_volume = 35
        self._prev_frame: bytes | None = None
        self._tone_state = [0.0, 0.0]
        self._audio_delay = AudioDelay()
        self._wav = None
        self._wav_bytes = 0
        self._mic_hot = False
        self._mic_source = None
        self._mic_io = None
        self._bottom_dialog = None
        self._auto_seconds = 0.0
        self._trace_file = None
        self._trace_left = 0
        self._roll: list[tuple] = []
        self._roll_ok: bool | None = None
        self._predicted: bytes | None = None
        self._session: Link | None = None
        self._link_was_active = False
        self._load_settings()
        self._3ds_name = ""
        self._switch_name = ""
        self._switch_key = ""
        self._extra_name = ""
        self._extra_key = ""
        self.rom: bytes | None = None
        self.paused = False
        self._audio_pos = 0.0
        self._audio_hold_l = 0
        self._audio_hold_r = 0
        self.fast = False
        self.state_slot = 1
        self._queued: Path | None = None
        self._used_patch = False
        self._game_id = ""
        library_root = os.environ.get("POKEMONGB_LIBRARY")
        self.library = Library(Path(library_root) if library_root else _saves_dir())
        controls_path = os.environ.get("POKEMONGB_CONTROLS")
        self.controls = Controls(Path(controls_path) if controls_path else _saves_dir() / "controls.json")
        self._default_controls = self.controls
        self._closed = False
        self._shown = 0
        self._sim = 0
        self._fps_t = time.perf_counter()
        self._fps = 0.0
        self._speed = 0.0
        self.sink = None
        self.audio_io = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        bar = _FlowBar()
        self.open_btn = self._button("Open ROM", self._open)
        self.scan_btn = QPushButton("Scan ROM folder")
        self.scan_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scan_menu = QMenu(self.scan_btn)
        self.rescan_action = scan_menu.addAction("Rescan saved folder", self._rescan_rom_folder)
        self.rescan_action.setEnabled(bool(self._rom_folder))
        scan_menu.addAction("Choose folder…", self._choose_rom_folder)
        self.scan_btn.setMenu(scan_menu)
        self.local_link_btn = self._button("Local Game Boy link", self._open_local_link)
        self.bios_btn = self._button("Add BIOS", self._add_bios)
        self.bios_btn.setObjectName("BiosButton")
        self.library_btn = self._button("Library", self._toggle_library)
        self.pause_btn = self._button("Pause", self._toggle_pause)
        self.reset_btn = self._button("Reset", self._reset)
        self.states_btn = self._button("Save states", self._show_states)
        self.states_btn.setObjectName("SaveStatesButton")
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setObjectName("Volume")
        self.volume.setRange(0, 100)
        self.volume.setValue(self._volume)
        self.volume.setFixedWidth(88)
        self.volume.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.volume.valueChanged.connect(self._set_volume)
        self.mute_btn = self._button("Mute", self._toggle_mute)
        self.mute_btn.setObjectName("MuteButton")
        self.speed_box = QComboBox()
        self.speed_box.setObjectName("SpeedRate")
        self.speed_box.addItems(["0.25x", "0.5x", "1x", "2x", "4x", "8x"])
        self.speed_box.setCurrentText({0.25: "0.25x", 0.5: "0.5x", 1.0: "1x", 2.0: "2x", 4.0: "4x", 8.0: "8x"}.get(self._rate, "1x"))
        self.speed_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.speed_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.speed_box.currentTextChanged.connect(self._set_rate)
        self.zone = QSlider(Qt.Orientation.Horizontal)
        self.zone.setObjectName("Deadzone")
        self.zone.setRange(0, 100)
        self.zone.setValue(self._deadzone)
        self.zone.setFixedWidth(72)
        self.zone.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.zone.setToolTip("Stick deadzone")
        self.zone.valueChanged.connect(self._set_deadzone)
        self.filter_box = QComboBox()
        self.filter_box.setObjectName("PictureFilter")
        self.filter_box.addItems(["Sharp", "Smooth", "Scanlines", "CRT", "LCD"])
        self.filter_box.setCurrentText(
            {"sharp": "Sharp", "smooth": "Smooth", "scanline": "Scanlines", "crt": "CRT", "lcd": "LCD"}.get(self._filter, "Sharp")
        )
        self.filter_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.filter_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.filter_box.currentTextChanged.connect(self._set_filter)
        self.layout_box = QComboBox()
        self.layout_box.setObjectName("ScreenLayout")
        self.layout_box.addItems(["Stacked", "Side by side", "Top large"])
        self.layout_box.setCurrentText(
            {"side": "Side by side", "top": "Top large"}.get(self._layout, "Stacked")
        )
        self.layout_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.layout_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.layout_box.currentTextChanged.connect(self._set_layout)
        self.net_btn = self._button("Netplay", self._show_net)
        self.net_btn.setObjectName("NetplayButton")
        self.search_btn = self._button("Cheat search", self._show_cheat_search)
        self.search_btn.setObjectName("CheatSearchButton")
        self.shot_btn = self._button("Screenshot", self._screenshot)
        self.shot_btn.setObjectName("ScreenshotButton")
        self.copy_btn = self._button("Copy", self._copy_shot)
        self.copy_btn.setObjectName("CopyShot")
        self.full_btn = self._button("Fullscreen", self._toggle_fullscreen)
        self.full_btn.setObjectName("FullscreenButton")
        self.controls_btn = self._button("Controls", self._show_controls)
        self.controls_btn.setObjectName("ControlsButton")
        self.help_btn = self._button("Help", self._show_help)
        self.help_btn.setObjectName("HelpButton")
        self.tools_btn = self._button("Tools", self._show_tools)
        self.tools_btn.setObjectName("ToolsButton")
        # Keep the everyday controls in a compact main toolbar.
        # All existing widget instances, signals, and object names are preserved.
        self.open_btn.setObjectName("PrimaryButton")
        self.library_btn.setObjectName("PrimaryButton")
        self.reset_btn.setObjectName("DangerButton")
        self.bios_manager_btn = self._button("BIOS Manager", self._show_bios_manager)
        self.bios_manager_btn.setObjectName("BiosManagerButton")
        self.refresh_btn = self._button("Refresh", self._refresh_library)
        self.favorites_btn = self._button("Favorites", self._toggle_favorites)
        self.favorites_btn.setCheckable(True)
        self.favorites_btn.setObjectName("LibraryFavoritesShortcut")
        self.more_btn = self._button("More ▾", self._toggle_quick_tools)
        self.more_btn.setObjectName("MoreButton")
        self.more_btn.setCheckable(True)
        self.more_btn.setToolTip("Show advanced emulator controls")
        for widget in (
            self.open_btn, self.library_btn, self.pause_btn, self.reset_btn,
            self.states_btn, self.shot_btn, self.full_btn,
            self.scan_btn, self.local_link_btn, self.refresh_btn, self.favorites_btn,
            self.bios_manager_btn, self.more_btn,
        ):
            bar.add(widget)
        self.toolbar = bar
        root.addWidget(self.toolbar)

        # Secondary controls are available on demand, without occupying
        # space or wrapping into additional rows while the menu is closed.
        self.quick_tools = _FlowBar()
        self.quick_tools.setObjectName("QuickTools")
        for widget in (
            self.bios_btn, self.volume, self.mute_btn, self.speed_box,
            self.zone, self.filter_box, self.layout_box, self.net_btn,
            self.search_btn, self.copy_btn, self.controls_btn,
            self.tools_btn, self.help_btn,
        ):
            self.quick_tools.add(widget)
        self._quick_tools_open = False
        root.addWidget(self.quick_tools)
        self.quick_tools.hide()

        self._frame_pixmap = QPixmap()
        self.viewport = _ScreenViewport()
        self.viewport.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.screen = QLabel("Drop a ROM here", self.viewport)
        self.screen.setObjectName("Screen")
        self.screen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewport.resized.connect(self._draw_screen)
        self.play = QWidget()
        screen_row = QHBoxLayout(self.play)
        screen_row.setContentsMargins(0, 0, 0, 0)
        screen_row.addWidget(self.viewport, 1)
        self.chat_panel = QWidget()
        self.chat_panel.setObjectName("ChatPanel")
        self.chat_panel.setFixedWidth(220)
        chat_layout = QVBoxLayout(self.chat_panel)
        self.chat_ping = QLabel("Ping —")
        self.chat_ping.setObjectName("ChatPing")
        self.chat_view = QPlainTextEdit()
        self.chat_view.setObjectName("ChatView")
        self.chat_view.setReadOnly(True)
        self.chat_line = QLineEdit()
        self.chat_line.setObjectName("ChatLine")
        self.chat_line.setPlaceholderText("Message")
        self.chat_line.returnPressed.connect(self._send_chat)
        chat_layout.addWidget(self.chat_ping)
        chat_layout.addWidget(self.chat_view, 1)
        chat_layout.addWidget(self.chat_line)
        self.chat_panel.hide()
        screen_row.addWidget(self.chat_panel)
        self.shelf = Shelf(
            self.library,
            self._play_game,
            self._open_settings,
            on_change=self._shelf_view,
            scale=self._card_scale,
            listed=self._list_view,
            show_hidden=self._show_hidden,
        )
        self.stack = QStackedWidget()
        self.stack.addWidget(self.play)
        self.stack.addWidget(self.shelf)
        root.addWidget(self.stack, 1)

        self.status = QLabel(
            "NES, Super NES, Mega Drive, 32X, Atari, Vectrex, Channel F, WonderSwan, "
            "Neo Geo Pocket, Virtual Boy, Supervision, PlayStation, PlayStation 2, PSP, "
            "GameCube, Wii, Wii U, Xbox, Xbox 360, Arcade, Game Boy, Advance, DS, 3DS, and Switch"
        )
        self.status.setObjectName("Status")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self._apply_theme()

        self.clock = QTimer(self)
        self.clock.setTimerType(Qt.TimerType.PreciseTimer)
        self.clock.timeout.connect(self._tick)
        if self._on_top:
            self._set_on_top(True)
        self._library_pad_held = set()
        self.library_pad_timer = QTimer(self)
        self.library_pad_timer.setInterval(110)
        self.library_pad_timer.timeout.connect(self._poll_library_gamepad)
        self.library_pad_timer.start()
        self._show_library()

    def _refresh_library(self) -> None:
        self.shelf.refresh()

    def _toggle_favorites(self) -> None:
        self.shelf.favorites.setChecked(not self.shelf.favorites.isChecked())
        self.favorites_btn.setChecked(self.shelf.favorites.isChecked())

    def _show_bios_manager(self) -> None:
        BiosManager(self).exec()

    def _sync_toolbar_mode(self) -> None:
        """Show library actions in Library and gameplay actions in Playing."""
        library = self.stack.currentWidget() is self.shelf
        for widget in (self.refresh_btn, self.favorites_btn, self.bios_manager_btn,
                       self.scan_btn, self.local_link_btn):
            widget.setVisible(library)
        for widget in (self.library_btn, self.pause_btn, self.reset_btn,
                       self.states_btn, self.shot_btn, self.full_btn):
            widget.setVisible(not library)
        self.favorites_btn.setChecked(self.shelf.favorites.isChecked())
        self.toolbar.reflow()

    def _poll_library_gamepad(self) -> None:
        if self.stack.currentWidget() is not self.shelf or QApplication.activeModalWidget() is not None:
            self._library_pad_held.clear()
            return
        first, _ = self._read_pads()
        now = set(first.actions) if first.connected else set()
        pressed = now - self._library_pad_held
        self._library_pad_held = now
        for direction in ("up", "down", "left", "right"):
            if direction in pressed:
                self.shelf.move_selection(direction)
                break
        if "a" in pressed or "start" in pressed:
            self.shelf.activate_selection()
        elif "b" in pressed and self.kind is not None:
            self._toggle_library()

    def _toggle_quick_tools(self) -> None:
        """Expand or collapse the secondary emulator controls."""
        self._quick_tools_open = not self._quick_tools_open
        self.quick_tools.setVisible(self._quick_tools_open and not self._fullscreen)
        self.more_btn.setChecked(self._quick_tools_open)
        self.more_btn.setText("Less ▴" if self._quick_tools_open else "More ▾")
        if self._quick_tools_open:
            self.quick_tools.reflow()

    def _button(self, text: str, handler) -> QPushButton:
        button = QPushButton(text)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(handler)
        return button

    def _add_bios(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add BIOS",
            "",
            "BIOS files (*.bin *.rom *.rom1 *.rom2 *.zip *.pce *.txt *.qcow2);;All files (*.*)",
        )
        files = [Path(path) for path in paths if path]
        if not files:
            return
        placed: list[str] = []
        errors: list[str] = []
        for file in files:
            try:
                dest = place_bios(file)
                placed.append(str(dest))
            except OSError as exc:
                errors.append(f"{file.name}: {exc}")
        if placed:
            QMessageBox.information(
                self,
                "Emulator",
                "Copied into this module:\n" + str(module_dir()) + "\n\n" + "\n".join(placed),
            )
        if errors:
            QMessageBox.warning(self, "Emulator", "Some files were not copied.\n" + "\n".join(errors[:8]))

    def _open(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add ROMs",
            "",
            _ROM_FILTER.format(extra=extra_globs()),
        )
        self._add_roms(paths)

    def _add_roms(self, paths: list[str]) -> None:
        files = [Path(path) for path in paths if path]
        if not files:
            return
        if len(files) == 1:
            self.load_path(str(files[0]))
            return
        errors = []
        for file in files:
            message = self._catalog(file)
            if message:
                errors.append(f"{file.name}: {message}")
        self._show_library()
        if errors:
            QMessageBox.warning(self, "Emulator", "Some files were not added.\n" + "\n".join(errors[:8]))

    def _catalog(self, path: Path) -> str | None:
        """Put a ROM on the shelf without starting it."""
        try:
            self.library.add_catalog((self._catalog_entry(path),))
        except Exception as exc:
            return str(exc)
        return None

    def _catalog_entry(self, path: Path) -> tuple[Path, str, str, str]:
        switch_path = prepare_switch(path)
        if switch_path is not None:
            return path, switch_title(switch_path.name), "Nintendo Switch", "switch"
        cache = _saves_dir() / "_cache" / game_id(path)
        ds_path = prepare_3ds(path, cache)
        if ds_path is not None:
            header = n3ds_header(ds_path)
            return path, n3ds_title(header, ds_path.name), "Nintendo 3DS", "3ds"
        found = locate(path, cache)
        if found is not None:
            source, system = found
            return path, title_of(source.name), system.name, system.id
        data, kind = open_rom(path)
        if kind == "gba":
            title, system = gba_title(data), "Game Boy Advance"
        elif kind == "nds":
            title, system = nds_title(data), "Nintendo DS"
        else:
            color = bool(data[0x143] & 0x80)
            title, system = rom_title(data), "Game Boy Color" if color else "Game Boy"
        return path, title, system, kind

    def _scan_rom_folder(self, folder: Path, cancelled=lambda: False) -> tuple[int, int]:
        known = {game.id for game in self.library.games}
        skipped = 0

        def unreadable(error):
            nonlocal skipped
            skipped += 1

        def entries():
            nonlocal skipped
            for directory, folders, names in os.walk(folder, onerror=unreadable):
                if cancelled():
                    return
                folders[:] = sorted(name for name in folders if name != ".git")
                for name in sorted(names):
                    if cancelled():
                        return
                    path = Path(directory) / name
                    if path.suffix.lower() not in ROM_SUFFIXES and path.suffix.lower() not in BY_SUFFIX:
                        continue
                    if game_id(path) in known:
                        continue
                    try:
                        if path.suffix.lower() == ".exe":
                            with path.open("rb") as handle:
                                if handle.read(8) != b"PS-X EXE":
                                    continue
                        yield self._catalog_entry(path)
                    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile):
                        skipped += 1

        return self.library.add_catalog(entries()), skipped

    def _choose_rom_folder(self) -> None:
        name = QFileDialog.getExistingDirectory(self, "Scan ROM folder", self._rom_folder)
        if not name:
            return
        self._rom_folder = name
        self._save_settings()
        self.rescan_action.setEnabled(True)
        self._run_rom_scan(Path(name))

    def _rescan_rom_folder(self) -> None:
        folder = Path(self._rom_folder)
        if not self._rom_folder or not folder.is_dir():
            self._choose_rom_folder()
            return
        self._run_rom_scan(folder)

    def _run_rom_scan(self, folder: Path) -> None:
        progress = QProgressDialog("Finding supported games…", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        last_poll = 0.0

        def cancelled():
            nonlocal last_poll
            now = time.monotonic()
            if now - last_poll >= 0.04:
                last_poll = now
                QApplication.processEvents()
            return progress.wasCanceled()

        try:
            added, skipped = self._scan_rom_folder(folder, cancelled)
        except OSError as exc:
            progress.close()
            QMessageBox.warning(self, "Scan ROM folder", str(exc))
            return
        stopped = progress.wasCanceled()
        progress.close()
        self._show_library()
        summary = "Scan cancelled" if stopped else "Scan finished"
        self.status.setText(f"{summary} · {added} added · {skipped} unreadable or unsupported")

    def _open_local_link(self) -> None:
        if self._session is not None:
            self.status.setText("Disconnect netplay before opening a local link.")
            return
        try:
            self._flush_save()
        except OSError as exc:
            QMessageBox.warning(self, "Local Game Boy link", str(exc))
            return
        dialog = LocalLinkDialog(self, _saves_dir(), _p2_action)
        dialog.exec()
        if self.kind == "gb" and self.rom is not None and self._save_paths()[0] in dialog.written:
            # A suspended machine could later overwrite the newer linked-session save.
            self.gb = None
            self.rom = None
            self.kind = None
            self._game_id = ""
            self.rewind.clear()
            self._show_library()
        dialog.deleteLater()

    def _show_help(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Help")
        dialog.setObjectName("HelpDialog")
        dialog.setMinimumWidth(640)
        dialog.setStyleSheet(
            "#HelpDialog { background: #1b1e17; color: #e6efd6; }"
            "#Help { color: #d5e2c4; font-size: 13px; }"
        )
        layout = QVBoxLayout(dialog)
        label = QLabel(_HELP)
        label.setObjectName("Help")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)
        layout.addWidget(self._button("Close", dialog.accept), alignment=Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def load_path(self, path: str) -> None:
        file = Path(path)
        self._queued = file
        self._used_patch = False
        try:
            self._load_queued(file)
        finally:
            self._queued = None

    def _load_queued(self, file: Path) -> None:
        try:
            switch_path = prepare_switch(file)
        except Exception as exc:
            QMessageBox.warning(self, "Emulator", str(exc))
            return
        if switch_path is not None:
            self._load_switch(switch_path)
            return
        cache = _saves_dir() / "_cache" / game_id(file)
        try:
            ds_path = prepare_3ds(file, cache)
        except Exception as exc:
            QMessageBox.warning(self, "Emulator", str(exc))
            return
        if ds_path is not None:
            self._load_3ds(ds_path)
            return
        try:
            found = locate(file, cache)
        except Exception as exc:
            QMessageBox.warning(self, "Emulator", str(exc))
            return
        if found is not None:
            source, system = found
            self._load_system(self._patched_file(source), system, original=source)
            return
        try:
            data, kind = open_rom(file)
        except Exception as exc:
            QMessageBox.warning(self, "Emulator", str(exc))
            return
        data = self._patched_bytes(file, data)
        if kind == "gba":
            self._load_gba(data, file)
        elif kind == "nds":
            self._load_nds(data, file)
        else:
            self.load_bytes(data)

    def load_bytes(self, data: bytes) -> None:
        self._flush_save()
        if self.gba is not None and self.gba.game_loaded:
            self.gba.unload()
        if self.nds is not None and self.nds.game_loaded:
            self.nds.unload()
        if self.n3ds is not None and self.n3ds.game_loaded:
            self.n3ds.unload()
        if self.switch is not None and self.switch.game_loaded:
            self.switch.unload()
        for core in self.extra.values():
            if core.game_loaded:
                core.unload()
        gb = self.gb if self.gb is not None else GameBoy()
        try:
            gb.load(data)
        except Exception as exc:
            self.clock.stop()
            self.status.setText(f"Could not start that ROM: {exc}")
            return
        self.gb = gb
        self.kind = "gb"
        self.rom = data
        self._restore_save()
        self._begin()

    def _load_gba(self, data: bytes, source: Path) -> None:
        try:
            core = self.gba if self.gba is not None else open_gba(_saves_dir())
        except CoreError as exc:
            self.status.setText(str(exc))
            return
        self.gba = core
        try:
            if core.game_loaded:
                if self.kind == "gba":
                    core.store_sram()
                core.unload()
            core.load(self._gba_file(source, data), save_name=gba_save_key(data))
        except CoreError as exc:
            self.status.setText(f"Could not start that ROM: {exc}")
            return
        self._release_others("gba")
        self.kind = "gba"
        self.rom = data
        self._begin()

    def _load_nds(self, data: bytes, source: Path) -> None:
        try:
            core = self.nds if self.nds is not None else open_nds(_saves_dir())
        except CoreError as exc:
            self.status.setText(str(exc))
            return
        self.nds = core
        key = nds_save_key(data)
        try:
            if core.game_loaded:
                if self.kind == "nds":
                    core.store_sram()
                core.unload()
            core.load(self._nds_file(source, data), save_name=key, content_name=f"{key}.nds")
        except CoreError as exc:
            self.status.setText(f"Could not start that ROM: {exc}")
            return
        self._release_others("nds")
        self.kind = "nds"
        self.rom = data
        self._touching = False
        self._begin()

    def _load_3ds(self, source: Path) -> None:
        header = n3ds_header(source)
        try:
            core = self.n3ds if self.n3ds is not None else open_n3ds(_saves_dir())
        except CoreError as exc:
            self.status.setText(str(exc))
            return
        self.n3ds = core
        try:
            if core.game_loaded:
                core.unload()
            core.load(self._patched_file(source), save_name=n3ds_save_key(header), full_path_only=True)
        except CoreError as exc:
            self.status.setText(f"Could not start that ROM: {exc}")
            return
        self._release_others("3ds")
        self.kind = "3ds"
        self.rom = header
        self._3ds_name = source.name
        self._touching = False
        self._down_keys.clear()
        self._begin()

    def _load_switch(self, source: Path) -> None:
        try:
            core = self.switch if self.switch is not None else open_switch(_saves_dir())
        except CoreError as exc:
            self.status.setText(str(exc))
            return
        self.switch = core
        try:
            if core.game_loaded:
                core.unload()
            core.load(self._patched_file(source), save_name=switch_save_key(source), full_path_only=True)
        except CoreError as exc:
            detail = core.messages[-1] if core.messages else ""
            self.status.setText(f"Could not start that ROM: {exc}" + (f" {detail}" if detail else ""))
            return
        except Exception as exc:
            self.switch = None
            self.status.setText(f"Could not start that ROM: {exc}")
            return
        self._release_others("switch")
        self.kind = "switch"
        self.rom = source.name.encode()
        self._switch_name = source.name
        self._switch_key = switch_save_key(source)
        self._touching = False
        self._down_keys.clear()
        self._begin()

    def _load_system(self, source: Path, system, original: Path | None = None) -> None:
        core = None
        previous = None
        for system_id, loaded in self.extra.items():
            if BY_ID[system_id].dll == system.dll:
                core = loaded
                previous = system_id
                break
        if core is None:
            try:
                core = open_system(system, _saves_dir())
            except CoreError as exc:
                self.status.setText(str(exc))
                return
        if previous is not None and previous != system.id:
            del self.extra[previous]
        self.extra[system.id] = core
        named = original or source
        key = system_save_key(system, named)
        try:
            if core.game_loaded:
                core.unload()
            core.load(source, save_name=key, full_path_only=system.full_path)
        except CoreError as exc:
            detail = core.messages[-1] if core.messages else ""
            self.status.setText(f"Could not start that ROM: {exc}" + (f" {detail}" if detail else ""))
            return
        except Exception as exc:
            self.extra.pop(system.id, None)
            self.status.setText(f"Could not start that ROM: {exc}")
            return
        self._release_others(system.id)
        self.kind = system.id
        self.rom = named.name.encode()
        self._extra_name = title_of(named.name)
        self._extra_key = key
        self._touching = False
        self._down_keys.clear()
        self._begin()

    def _nds_file(self, source: Path, data: bytes) -> Path:
        if source.suffix.lower() == ".nds" and not self._used_patch:
            return source
        folder = _saves_dir() / "_cache"
        folder.mkdir(exist_ok=True)
        dest = folder / f"{nds_save_key(data)}.nds"
        dest.write_bytes(data)
        return dest

    def _core(self) -> Core | None:
        if self.kind == "gba":
            return self.gba
        if self.kind == "nds":
            return self.nds
        if self.kind == "3ds":
            return self.n3ds
        if self.kind == "switch":
            return self.switch
        return self.extra.get(self.kind or "")

    def _touch_core(self) -> Core | None:
        if self.kind == "nds":
            return self.nds
        if self.kind == "3ds":
            return self.n3ds
        return None

    def _release_others(self, keep: str) -> None:
        """Flush the game that is running, then unload every other core."""
        self._flush_save()
        if keep != "gba" and self.gba is not None and self.gba.game_loaded:
            self.gba.unload()
        if keep != "nds" and self.nds is not None and self.nds.game_loaded:
            self.nds.unload()
        if keep != "3ds" and self.n3ds is not None and self.n3ds.game_loaded:
            self.n3ds.unload()
        if keep != "switch" and self.switch is not None and self.switch.game_loaded:
            self.switch.unload()
        for system_id, core in self.extra.items():
            if system_id != keep and core.game_loaded:
                core.unload()

    def _game_patch(self, path: Path) -> Path | None:
        game = self.library.by_path(path)
        if game is None and self._queued is not None:
            game = self.library.by_path(self._queued)
        return self.library.patch_file(game)

    def _patched_bytes(self, path: Path, data: bytes) -> bytes:
        patch = self._game_patch(path)
        if patch is None:
            return data
        try:
            patched = apply_patch(data, patch.read_bytes())
        except ValueError as exc:
            self._log(str(exc))
            self._notice(str(exc))
            return data
        self._used_patch = True
        return patched

    def _patched_file(self, source: Path) -> Path:
        patch = self._game_patch(source)
        if patch is None:
            return source
        try:
            data = apply_patch(source.read_bytes(), patch.read_bytes())
        except ValueError as exc:
            self._log(str(exc))
            self._notice(str(exc))
            return source
        folder = _saves_dir() / "_cache"
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / f"{source.stem}.patched{source.suffix}"
        dest.write_bytes(data)
        return dest

    def _gba_file(self, source: Path, data: bytes) -> Path:
        if source.suffix.lower() == ".gba" and not self._used_patch:
            return source
        folder = _saves_dir() / "_cache"
        folder.mkdir(exist_ok=True)
        dest = folder / f"{gba_save_key(data)}.gba"
        dest.write_bytes(data)
        return dest

    def _begin(self) -> None:
        self._audio_pos = 0.0
        self._audio_hold_l = 0
        self._audio_hold_r = 0
        self._start_audio()
        self.paused = False
        self.pause_btn.setText("Pause")
        self._fps_t = time.perf_counter()
        self._shown = 0
        self._sim = 0
        self._fps = 0.0
        self._speed = 0.0
        self._prev_frame = None
        self._frame_pixmap = QPixmap()
        self.screen.setText("Waiting for video…")
        self._show_play()
        self._draw_screen()
        self.clock.start(16)
        if self._queued is not None:
            self._remember(self._queued)
        self._use_game_controls()
        self._apply_cheats()
        self.rewind.clear()
        self._rewind_warned = False
        self._refresh_status()
        self.setFocus()

    def _remember(self, path: Path) -> None:
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen" and not os.environ.get("POKEMONGB_LIBRARY"):
            return
        title, system, system_id = self._library_identity()
        game = self.library.remember(path, title, system, system_id)
        self._game_id = game.id
        self.library.mark_played(game.id)

    def _library_identity(self) -> tuple[str, str, str]:
        kind = self.kind or ""
        rom = self.rom or b""
        if kind == "gb" and len(rom) > 0x143:
            color = bool(rom[0x143] & 0x80)
            return rom_title(rom), "Game Boy Color" if color else "Game Boy", "gb"
        if kind == "gba" and len(rom) >= 0xAC:
            return gba_title(rom), "Game Boy Advance", "gba"
        if kind == "nds" and len(rom) >= 0x10:
            return nds_title(rom), "Nintendo DS", "nds"
        if kind == "3ds":
            return n3ds_title(rom, self._3ds_name), "Nintendo 3DS", "3ds"
        if kind == "switch":
            return switch_title(self._switch_name), "Nintendo Switch", "switch"
        system = BY_ID.get(kind)
        if system is not None:
            return self._extra_name or system.name, system.name, system.id
        return "ROM", "ROM", kind

    def _apply_cheats(self) -> None:
        game = self.library.get(self._game_id) if self._game_id else None
        self.library.use_cheat_file(game)
        enabled = [cheat for cheat in game.cheats if cheat.enabled] if game else []
        if self.kind == "gb" and self.gb is not None:
            self.gb.set_cheats([(cheat.code, cheat.kind) for cheat in enabled])
        core = self._core()
        if core is not None and core.game_loaded:
            core.set_cheats(
                [cheat.code for cheat in enabled if not (self.kind != "gb" and cheat.kind == "address")]
            )
        self._poke_found()

    def _resume_clock(self) -> None:
        if self.paused or self.kind is None or self.stack.currentWidget() is self.shelf:
            return
        self.clock.start(16)

    def _show_play(self) -> None:
        self.stack.setCurrentWidget(self.play)
        self.library_btn.setText("Library")
        self._sync_toolbar_mode()

    def _show_library(self) -> None:
        self._commit_play()
        self.clock.stop()
        self.shelf.refresh()
        self.stack.setCurrentWidget(self.shelf)
        self._sync_toolbar_mode()
        self.library_btn.setText("Back" if self.kind is not None else "Library")
        count = len(self.library.games)
        if count == 0:
            self.status.setText("Open a ROM and it stays in this list.")
        else:
            word = "game" if count == 1 else "games"
            self.status.setText(f"{count} {word} in the library")

    def _toggle_library(self) -> None:
        if self.stack.currentWidget() is self.shelf:
            if self.kind is None:
                self.shelf.refresh()
                return
            self._show_play()
            self._resume_clock()
            self.setFocus()
            return
        self._show_library()

    def _play_game(self, game_id: str) -> None:
        game = self.library.get(game_id)
        if game is not None:
            self.load_path(game.path)

    def _open_settings(self, game_id: str) -> None:
        game = self.library.get(game_id)
        if game is None:
            return
        dialog = GameSettings(self.library, game, self)
        dialog.exec()
        if dialog.result() == 2:
            self._show_cheat_search()
        if self.library.get(game_id) is None:
            if self._game_id == game_id:
                self._game_id = ""
                self._apply_cheats()
        elif self._game_id == game_id:
            self._apply_cheats()
            self._prev_frame = None
            self._present()
        if self.stack.currentWidget() is self.shelf:
            self._show_library()
        else:
            self.shelf.refresh()

    def _toggle_pause(self) -> None:
        if self.kind is None:
            return
        self.paused = not self.paused
        if self.paused:
            self._commit_play()
            self.clock.stop()
            self._flush_save()
            self.pause_btn.setText("Resume")
        else:
            self.pause_btn.setText("Pause")
            self._resume_clock()
            self.setFocus()

    def _reset(self) -> None:
        core = self._core()
        if core is not None and core.game_loaded:
            core.reset()
            self._apply_cheats()
            self.rewind.clear()
            self._rewind_warned = False
            self._resume_clock()
            self.setFocus()
            return
        if self.rom is None or self.gb is None or self.kind != "gb":
            return
        self._flush_save()
        self.gb.load(self.rom)
        self._restore_save()
        self._apply_cheats()
        self.rewind.clear()
        self._rewind_warned = False
        self._resume_clock()
        self.setFocus()

    def _tick(self) -> None:
        if self.paused or self.kind is None:
            return
        core = self._core()
        if self.kind == "gb":
            if self.gb is None:
                return
        elif core is None or not core.game_loaded:
            return
        self._poll_mic()
        self._poll_gamepad()
        self._count_play()
        self._apply_autofire()
        self._drain_core_log()
        linked = self._session is not None and self._session.ready
        if self._session is not None and self._session.error:
            self._handle_net_error()
        if linked:
            payload = self._pack_local()
            delayed = payload
            if self._session.mode == "play":
                self._net_local.append(payload)
                if len(self._net_local) > self._session.delay:
                    delayed = self._net_local.pop(0)
                else:
                    delayed = pack_input(0, (0, 0, 0, 0), 0xFF, False)
            self._offer_state()
            if self._session.spectating:
                if not self._watch_net():
                    return
            elif (
                self._session.mode == "play"
                and not self._session.crowd
                and self._session.seat <= 2
                and not self._session._peers
            ):
                if not self._rollback_net(payload, delayed):
                    return
            else:
                remote = self._session.exchange(payload)
                if remote is None:
                    return
                self._apply_remote(remote, delayed if self._session.mode == "play" else None)
                if self._session.role == "host":
                    seats = self._session.publish(_full_net(payload))
                    if len(seats) > 2:
                        self._apply_seats(seats)
                bundle = self._session.take_bundle()
                if bundle:
                    self._apply_seats(bundle)
            self._net_sideband()
        elif self._action_held("rewind"):
            self._rewind_back()
            return
        stepping = self._step_once
        if stepping:
            self._step_once = False
        rate = 1.0 if linked or self.fast or stepping else self._rate
        if rate < 1:
            self._rate_phase += 1
            every = max(2, int(round(1 / rate)))
            if self._rate_phase % every != 0:
                return
        if not linked:
            self._rewind_store()
        frames = 0
        drew_frame = False
        started = time.perf_counter()
        if linked or stepping or rate <= 1:
            limit = 1 if not self.fast or linked or stepping else self._fast_frames
        else:
            limit = int(rate)
        if self.fast and not linked and not stepping:
            limit = self._fast_frames
        try:
            while True:
                if core is not None:
                    core.run()
                    drew_frame = core.frame is not None
                else:
                    self.gb.run_frame()
                    drew_frame |= self.gb.ppu.frame_ready
                frames += 1
                if frames >= limit or time.perf_counter() - started >= 0.05:
                    break
        except Exception as exc:
            self.clock.stop()
            self.status.setText(f"Emulator error: {exc}")
            return
        if drew_frame:
            self._present()
        self._poke_found()
        self._pump_audio(discard=self.fast or rate > 1)
        if stepping:
            self.paused = True
            self.pause_btn.setText("Resume")
            self.clock.stop()
        if self.kind == "gb":
            mmu = self.gb.mmu
            if mmu.sram_dirty and time.time() - mmu.sram_touch > 0.5:
                self._flush_save()
        elif self._sim % 120 == 0:
            self._flush_save()
        self._shown += int(drew_frame)
        self._sim += frames
        now = time.perf_counter()
        if now - self._fps_t >= 0.5:
            elapsed = now - self._fps_t
            self._fps = self._shown / elapsed
            target = core.fps if core is not None else 59.7275
            self._speed = (self._sim / elapsed) / target * 100 if target else 0.0
            self._shown = 0
            self._sim = 0
            self._fps_t = now
            self._refresh_status()

    def _present(self) -> None:
        core = self._core()
        if core is not None:
            if core.frame is None:
                return
            frame, width, height = core.frame
            self._touch_side = self._layout == "side" and self.kind in ("nds", "3ds")
            frame, width, height = self._trim_frame(frame, width, height)
            self._touch_size = (width, height)
            self._show_bottom(frame, width, height)
            if self._layout == "top" and self.kind in ("nds", "3ds"):
                frame, width, height = screens_top_large(frame, width, height)
            elif self._touch_side:
                frame, width, height = screens_side_by_side(frame, width, height)
        else:
            if self.gb is None:
                return
            game = self.library.get(self._game_id) if self._game_id else None
            frame = gb_picture(self.gb.ppu, game.gb_palette, game.gb_colors) if game else self.gb.ppu.fb.tobytes()
            width, height = 160, 144
            frame, width, height = self._trim_frame(frame, width, height)
            self._touch_size = (width, height)
            self._touch_side = False
        if self._blend:
            mixed = blend(self._prev_frame, frame)
            self._prev_frame = frame
            frame = mixed
        else:
            self._prev_frame = None
        frame = adjust(frame, self._brightness, self._contrast, self._color, self._palette)
        image = QImage(frame, width, height, width * 4, QImage.Format.Format_RGB32).copy()
        self._frame_pixmap = QPixmap.fromImage(image)
        self._draw_screen()

    def _draw_screen(self) -> None:
        viewport_w, viewport_h = self.viewport.width(), self.viewport.height()
        if self._frame_pixmap.isNull():
            width, height = self._screen_box()
            self._place_screen(min(width, viewport_w), min(height, viewport_h))
            return

        width, height = self._frame_pixmap.width(), self._frame_pixmap.height()
        frame_pad = self._bezel_px() * 2
        # Leave the screen hidden when the bezel cannot fit.
        if min(viewport_w, viewport_h) <= frame_pad:
            self._place_screen(0, 0)
            return
        avail_w, avail_h = viewport_w - frame_pad, viewport_h - frame_pad
        if self._rotate in (90, 270):
            avail_w, avail_h = avail_h, avail_w
        display_w = max(width, height * 16 / 9) if self._aspect == "wide" else width
        fitted = min(avail_w / display_w, avail_h / height)
        if not self._fullscreen:
            preferred = self._normal_scale(width, height) * self._picture_size / 100
            fitted = min(fitted, preferred)
            if self.kind == "switch":
                fitted = min(fitted, 1280 / display_w)
            if self._integer and fitted >= 1:
                fitted = int(fitted)
        show_w = max(1, int(display_w * fitted))
        show_h = max(1, int(height * fitted))
        transform = (
            Qt.TransformationMode.SmoothTransformation
            if self._filter == "smooth"
            else Qt.TransformationMode.FastTransformation
        )
        pixmap = self._frame_pixmap.scaled(show_w, show_h, Qt.AspectRatioMode.IgnoreAspectRatio, transform)
        if self._filter in ("scanline", "crt", "lcd"):
            painter = QPainter(pixmap)
            if self._filter == "lcd":
                painter.setPen(QColor(0, 0, 0, 70))
                for line in range(0, pixmap.height(), 3):
                    painter.drawLine(0, line, pixmap.width(), line)
                for column in range(0, pixmap.width(), 3):
                    painter.drawLine(column, 0, column, pixmap.height())
            else:
                painter.setPen(QColor(0, 0, 0, 140 if self._filter == "crt" else 110))
                for line in range(0, pixmap.height(), 2):
                    painter.drawLine(0, line, pixmap.width(), line)
                if self._filter == "crt":
                    painter.fillRect(0, 0, pixmap.width(), 8, QColor(0, 0, 0, 90))
                    painter.fillRect(0, pixmap.height() - 8, pixmap.width(), 8, QColor(0, 0, 0, 90))
            painter.end()
        if self._rotate:
            pixmap = pixmap.transformed(QTransform().rotate(self._rotate), transform)
        self.screen.setPixmap(pixmap)
        self._place_screen(pixmap.width() + frame_pad, pixmap.height() + frame_pad)

    def _place_screen(self, width: int, height: int) -> None:
        self.screen.setGeometry(
            (self.viewport.width() - width) // 2,
            (self.viewport.height() - height) // 2,
            width,
            height,
        )

    def _refresh_status(self) -> None:
        if self.rom is None:
            return
        if self.kind == "gba":
            speed = f"{self._speed:.0f}%" if self._speed else "—"
            fps = f"{self._fps:.0f} fps" if self._fps else "starting"
            self.status.setText(
                f"{gba_title(self.rom)}   ·   Game Boy Advance   ·   "
                f"slot {self.state_slot}   ·   {fps}   ·   {speed}{self._link_phrase()}"
            )
            return
        if self.kind == "nds":
            speed = f"{self._speed:.0f}%" if self._speed else "—"
            fps = f"{self._fps:.0f} fps" if self._fps else "starting"
            self.status.setText(
                f"{nds_title(self.rom)}   ·   Nintendo DS   ·   "
                f"slot {self.state_slot}   ·   {fps}   ·   {speed}"
            )
            return
        if self.kind == "3ds":
            speed = f"{self._speed:.0f}%" if self._speed else "—"
            fps = f"{self._fps:.0f} fps" if self._fps else "starting"
            self.status.setText(
                f"{n3ds_title(self.rom, self._3ds_name)}   ·   Nintendo 3DS   ·   "
                f"slot {self.state_slot}   ·   {fps}   ·   {speed}"
            )
            return
        if self.kind == "switch":
            speed = f"{self._speed:.0f}%" if self._speed else "—"
            fps = f"{self._fps:.0f} fps" if self._fps else "starting"
            self.status.setText(
                f"{switch_title(self._switch_name)}   ·   Nintendo Switch   ·   "
                f"slot {self.state_slot}   ·   {fps}   ·   {speed}"
            )
            return
        system = BY_ID.get(self.kind or "")
        if system is not None:
            speed = f"{self._speed:.0f}%" if self._speed else "—"
            fps = f"{self._fps:.0f} fps" if self._fps else "starting"
            self.status.setText(
                f"{self._extra_name}   ·   {system.name}   ·   "
                f"slot {self.state_slot}   ·   {fps}   ·   {speed}"
            )
            return
        if self.gb is None:
            return
        mode = "Game Boy Color" if self.gb.cgb else "Game Boy"
        speed = f"{self._speed:.0f}%" if self._speed else "—"
        if not self.gb.ppu.lcdc & 0x80:
            fps = "LCD off"
        else:
            fps = f"{self._fps:.0f} fps" if self._fps else "waiting for video"
        self.status.setText(
            f"{rom_title(self.rom)}   ·   {mode}   ·   {self.gb.mmu.name}   ·   "
            f"slot {self.state_slot}   ·   {fps}   ·   {speed}"
        )

    def _output_device(self):
        chosen = self._speaker
        for device in QMediaDevices.audioOutputs():
            ident = bytes(device.id()).decode("utf-8", "replace")
            if chosen and ident == chosen:
                return device
        return QMediaDevices.defaultAudioOutput()

    def _restart_audio(self) -> None:
        if self.sink is not None:
            self.sink.stop()
        self.sink = None
        self.audio_io = None
        self._start_audio()

    def _start_audio(self) -> None:
        if self.sink is not None:
            return
        try:
            fmt = QAudioFormat()
            fmt.setSampleRate(44100)
            fmt.setChannelCount(2)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            device = self._output_device()
            if device is None or device.isNull():
                return
            self.sink = QAudioSink(device, fmt, self)
            self.sink.setVolume(self._volume / 100)
            self.sink.setBufferSize(max(1024, int(44100 * 4 * self._latency / 1000)))
            self.audio_io = self.sink.start()
        except Exception:
            self.sink = None
            self.audio_io = None

    def _pump_audio(self, discard: bool) -> None:
        core = self._core()
        if core is not None:
            data = core.take_audio()
            if data and not discard:
                data = _resample(self, data, int(round(core.sample_rate)), 44100)
        elif self.gb is not None:
            data = self.gb.apu.take_samples()
        else:
            return
        if discard or not data or self.audio_io is None or self.sink is None:
            return
        gain = self._volumes.get(self.kind or "", 100) / 100
        data = scale_pcm(data, gain)
        data = tone_pcm(data, self._tone, self._tone_state)
        self._audio_delay.ms = self._lead_ms
        data = self._audio_delay.push(data)
        if self._wav is not None and data:
            self._wav.write(data)
            self._wav_bytes += len(data)
        free = self.sink.bytesFree()
        if free > 0 and data:
            self.audio_io.write(data[:free])

    def _save_paths(self) -> tuple[Path, Path]:
        return battery_paths(self.rom or b"", _saves_dir())

    def _flush_save(self) -> None:
        core = self._core()
        if core is not None and core.game_loaded:
            core.store_sram()
            return
        if self.gb is not None and self.rom is not None and (self.gb.mmu.eram or self.gb.mmu.has_rtc):
            write_battery(self.gb, *self._save_paths())

    def _restore_save(self) -> None:
        if self.gb is not None and self.rom is not None:
            read_battery(self.gb, *self._save_paths())

    def _set_slot(self, slot: int) -> None:
        self.state_slot = slot
        self._notice(self._slot_title(slot))

    def _show_states(self) -> None:
        SaveStatesMenu(self).exec()

    def _state_path(self) -> Path:
        return self._state_file(self.state_slot)

    def _state_file(self, slot: int) -> Path:
        if self.kind == "gba":
            key = gba_save_key(self.rom or b"")
            return _saves_dir() / f"{key}.slot{slot}.gba.state"
        if self.kind == "nds":
            key = nds_save_key(self.rom or b"")
            return _saves_dir() / f"{key}.slot{slot}.nds.state"
        if self.kind == "3ds":
            key = n3ds_save_key(self.rom or b"")
            return _saves_dir() / f"{key}.slot{slot}.3ds.state"
        if self.kind == "switch":
            return _saves_dir() / f"{self._switch_key}.slot{slot}.switch.state"
        if self.kind in BY_ID:
            return _saves_dir() / f"{self._extra_key}.slot{slot}.{self.kind}.state"
        key = save_key(self.rom or b"")
        return _saves_dir() / f"{key}.slot{slot}.state"

    def _slot_picture(self, slot: int) -> Path:
        state = self._state_file(slot)
        return state.with_name(state.name + ".png")

    def _saved_slot(self) -> None:
        pixmap = self.screen.pixmap()
        if pixmap is not None and not pixmap.isNull():
            path = self._slot_picture(self.state_slot)
            path.parent.mkdir(parents=True, exist_ok=True)
            pixmap.save(str(path), "PNG")
        if self.state_slot == AUTO_SLOT:
            self._notice("Autosave")
        else:
            self._notice(f"Saved slot {self.state_slot}")

    def _slot_label_path(self, slot: int) -> Path:
        state = self._state_file(slot)
        return state.with_name(state.name + ".label")

    def _slot_title(self, slot: int) -> str:
        if slot == AUTO_SLOT:
            return "Autosave"
        path = self._slot_label_path(slot)
        try:
            text = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
        except OSError:
            text = ""
        return text or f"Slot {slot}"

    def _set_slot_title(self, slot: int, text: str) -> None:
        path = self._slot_label_path(slot)
        path.parent.mkdir(parents=True, exist_ok=True)
        clean = text.strip()[:40]
        if clean:
            path.write_text(clean, encoding="utf-8")
        elif path.is_file():
            path.unlink()

    def _settings_path(self) -> Path:
        override = os.environ.get("POKEMONGB_SETTINGS")
        return Path(override) if override else _saves_dir() / "settings.json"

    def _load_settings(self) -> None:
        self._volume = 35
        self._fast_frames = 8
        self._filter = "sharp"
        self._rate = 1.0
        self._layout = "stack"
        self._delay = 0
        self._deadzone = 24
        self._integer = False
        self._bezel = "thin"
        self._brightness = 0
        self._contrast = 0
        self._color = 0
        self._palette = ""
        self._blend = False
        self._aspect = "pixel"
        self._bottom_window = False
        self._speaker = ""
        self._latency = 80
        self._tone = "off"
        self._lead_ms = 0
        self._volumes: dict[str, int] = {}
        self._pc_mic = False
        self._picture_size = 100
        self._text = 100
        self._theme = "dark"
        self._card_scale = 100
        self._list_view = False
        self._show_hidden = False
        self._rom_folder = ""
        self._geometry: list[int] | None = None
        gamepad.deadzone_percent = self._deadzone
        path = self._settings_path()
        if not path.is_file():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        volume = raw.get("volume")
        if isinstance(volume, int):
            self._volume = max(0, min(100, volume))
        speed = raw.get("speed")
        if isinstance(speed, int):
            self._fast_frames = max(2, min(16, speed))
        picture = raw.get("filter")
        if picture in ("sharp", "smooth", "scanline", "crt", "lcd"):
            self._filter = picture
        rate = raw.get("rate")
        if isinstance(rate, (int, float)) and float(rate) in (0.25, 0.5, 1.0, 2.0, 4.0, 8.0):
            self._rate = float(rate)
        layout = raw.get("layout")
        if layout in ("stack", "side", "top"):
            self._layout = layout
        delay = raw.get("delay")
        if isinstance(delay, int):
            self._delay = max(0, min(8, delay))
        zone = raw.get("deadzone")
        if isinstance(zone, int):
            self._deadzone = max(0, min(100, zone))
        if raw.get("autofire") is True:
            self._autofire = True
        rotate = raw.get("rotate")
        if isinstance(rotate, int) and rotate in (0, 90, 180, 270):
            self._rotate = rotate
        crop = raw.get("crop")
        if isinstance(crop, int):
            self._crop = max(0, min(12, crop))
        if raw.get("on_top") is True:
            self._on_top = True
        if raw.get("integer") is True:
            self._integer = True
        bezel = raw.get("bezel")
        if bezel in ("none", "thin", "thick"):
            self._bezel = bezel
        for key, attr, low, high in (
            ("brightness", "_brightness", -50, 50),
            ("contrast", "_contrast", -50, 50),
            ("color", "_color", -50, 50),
            ("lead", "_lead_ms", -80, 80),
        ):
            value = raw.get(key)
            if isinstance(value, int):
                setattr(self, attr, max(low, min(high, value)))
        palette = raw.get("palette")
        if palette in ("", "protanopia", "deuteranopia", "tritanopia"):
            self._palette = palette
        if raw.get("blend") is True:
            self._blend = True
        aspect = raw.get("aspect")
        if aspect in ("pixel", "wide"):
            self._aspect = aspect
        if raw.get("bottom") is True:
            self._bottom_window = True
        speaker = raw.get("speaker")
        if isinstance(speaker, str):
            self._speaker = speaker
        latency = raw.get("latency")
        if isinstance(latency, int):
            self._latency = max(20, min(200, latency))
        tone = raw.get("tone")
        if tone in ("off", "low", "high"):
            self._tone = tone
        volumes = raw.get("volumes")
        if isinstance(volumes, dict):
            self._volumes = {
                str(key): max(0, min(100, int(value)))
                for key, value in volumes.items()
                if isinstance(value, int)
            }
        if raw.get("pc_mic") is True:
            self._pc_mic = True
        size = raw.get("picture_size")
        if isinstance(size, int):
            self._picture_size = max(70, min(140, size))
        text = raw.get("text")
        if text in (100, 125, 150):
            self._text = text
        theme = raw.get("theme")
        if theme in ("dark", "night", "contrast"):
            self._theme = theme
        card = raw.get("card_scale")
        if isinstance(card, int):
            self._card_scale = max(70, min(140, card))
        if raw.get("list_view") is True:
            self._list_view = True
        if raw.get("show_hidden") is True:
            self._show_hidden = True
        folder = raw.get("rom_folder")
        if isinstance(folder, str):
            self._rom_folder = folder
        geo = raw.get("geometry")
        if isinstance(geo, list) and len(geo) == 4 and all(isinstance(item, int) for item in geo):
            self._geometry = geo
        self._audio_delay.ms = self._lead_ms
        gamepad.deadzone_percent = self._deadzone

    def _save_settings(self) -> None:
        path = self._settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "volume": self._volume,
                    "speed": self._fast_frames,
                    "filter": self._filter,
                    "rate": self._rate,
                    "layout": self._layout,
                    "delay": self._delay,
                    "deadzone": self._deadzone,
                    "autofire": self._autofire,
                    "rotate": self._rotate,
                    "crop": self._crop,
                    "on_top": self._on_top,
                    "integer": self._integer,
                    "bezel": self._bezel,
                    "brightness": self._brightness,
                    "contrast": self._contrast,
                    "color": self._color,
                    "palette": self._palette,
                    "blend": self._blend,
                    "aspect": self._aspect,
                    "bottom": self._bottom_window,
                    "speaker": self._speaker,
                    "latency": self._latency,
                    "tone": self._tone,
                    "lead": self._lead_ms,
                    "volumes": self._volumes,
                    "pc_mic": self._pc_mic,
                    "picture_size": self._picture_size,
                    "text": self._text,
                    "theme": self._theme,
                    "card_scale": self._card_scale,
                    "list_view": self._list_view,
                    "show_hidden": self._show_hidden,
                    "rom_folder": self._rom_folder,
                    "geometry": self._geometry,
                }
            ),
            encoding="utf-8",
        )

    def _set_volume(self, value: int) -> None:
        self._volume = int(value)
        if self._volume > 0:
            self.mute_btn.setText("Mute")
        if self.sink is not None:
            self.sink.setVolume(self._volume / 100)
        self._save_settings()

    def _toggle_mute(self) -> None:
        if self._volume > 0:
            self._muted_volume = self._volume
            self.volume.setValue(0)
            self.mute_btn.setText("Unmute")
            return
        self.volume.setValue(self._muted_volume or 35)

    def _trim_frame(self, frame: bytes, width: int, height: int) -> tuple[bytes, int, int]:
        self._crop_origin = (0, 0)
        if self._crop <= 0 or width < 8 or height < 8:
            return frame, width, height
        dx = int(width * self._crop / 100)
        dy = int(height * self._crop / 100)
        if dx < 1 and dy < 1:
            return frame, width, height
        if dx * 2 >= width or dy * 2 >= height:
            return frame, width, height
        new_w = width - dx * 2
        new_h = height - dy * 2
        row = width * 4
        out = bytearray(new_w * new_h * 4)
        stride = new_w * 4
        for y in range(new_h):
            start = (y + dy) * row + dx * 4
            out[y * stride:(y + 1) * stride] = frame[start:start + stride]
        self._crop_origin = (dx, dy)
        return bytes(out), new_w, new_h

    def _cycle_rotate(self, button: QPushButton) -> None:
        self._rotate = (self._rotate + 90) % 360
        button.setText(f"Rotate {self._rotate}")
        self._save_settings()
        self._present()

    def _set_crop(self, value: int) -> None:
        self._crop = max(0, min(12, int(value)))
        self._save_settings()
        self._present()

    def _set_on_top(self, on: bool) -> None:
        self._on_top = bool(on)
        window = self.window()
        if window is not None:
            window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._on_top)
            window.show()
        self._save_settings()

    def _log(self, text: str) -> None:
        clean = str(text).strip()
        if not clean:
            return
        self._errors.append(clean)
        if len(self._errors) > 200:
            del self._errors[:-200]

    def _drain_core_log(self) -> None:
        core = self._core()
        if core is None or not core.messages:
            return
        for text in core.messages:
            self._log(text)
        core.messages.clear()

    def _show_tools(self) -> None:
        dialog = getattr(self, "_tools", None)
        if dialog is not None and dialog.isVisible():
            dialog.raise_()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Tools")
        dialog.setObjectName("ToolsDialog")
        layout = QVBoxLayout(dialog)
        rotate = QPushButton(f"Rotate {self._rotate}")
        rotate.setObjectName("RotateButton")
        rotate.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        rotate.clicked.connect(lambda: self._cycle_rotate(rotate))
        crop_label = QLabel("Crop overscan")
        crop = QSlider(Qt.Orientation.Horizontal)
        crop.setObjectName("Crop")
        crop.setRange(0, 12)
        crop.setValue(self._crop)
        crop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        crop.valueChanged.connect(self._set_crop)
        top = QCheckBox("Always on top")
        top.setObjectName("AlwaysOnTop")
        top.setChecked(self._on_top)
        top.toggled.connect(self._set_on_top)
        memory = QPushButton("Memory")
        memory.setObjectName("MemoryButton")
        memory.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        memory.clicked.connect(self._show_memory)
        trace = QPushButton("Trace")
        trace.setObjectName("TraceButton")
        trace.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        trace.clicked.connect(self._toggle_trace)
        errors = QPushButton("Error log")
        errors.setObjectName("ErrorLogButton")
        errors.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        errors.clicked.connect(self._show_errors)
        for widget in (rotate, crop_label, crop, top, memory, trace, errors):
            layout.addWidget(widget)
        layout.addWidget(self._look_panel())
        dialog.show()
        self._tools = dialog

    def _bezel_px(self) -> int:
        return {"none": 0, "thick": 28}.get(self._bezel, 10)

    def _normal_scale(self, width: int, height: int) -> int:
        """Whole pixels at a size you can play, matched to this picture."""
        if width <= 0 or height <= 0:
            return 1
        return max(1, min(960 // width, 800 // height))

    def _screen_box(self) -> tuple[int, int]:
        return int(720 * self._picture_size / 100), int(576 * self._picture_size / 100)

    def _apply_theme(self) -> None:
        """Style the emulator to match the dark multi-tool shell."""
        palettes = {
            "dark": ("#0f1115", "#e6e6e6", "#0b0e14", "#252d3d", "#1b2030",
                     "#9aa4b2", "#212739", "#161c29", "#a78bfa", "#c4b5fd", "#2a2147"),
            "night": ("#0b1020", "#e7edff", "#090d17", "#2a3550", "#182033",
                      "#9aa8c7", "#22304a", "#18243b", "#72a7ff", "#93bbff", "#1c2f56"),
            "contrast": ("#000000", "#ffffff", "#000000", "#ffff00", "#000000",
                         "#ffff00", "#111111", "#222222", "#ffff00", "#ffffff", "#111111"),
        }
        bg, fg, screen, border, button, muted, hover, pressed, accent, accent_hover, accent_fill = (
            palettes.get(self._theme, palettes["dark"])
        )
        bezel = {"none": 0, "thick": 28}.get(self._bezel, 10)
        size = max(11, int(13 * self._text / 100))
        self.setStyleSheet(
            f"""
            #PokemonGB {{ background: {bg}; color: {fg}; }}
            #Toolbar, #QuickTools {{ background: {bg}; border: 0; }}
            #Screen {{
                background: {screen}; color: {muted};
                border: {bezel}px solid {border}; border-radius: 12px;
                font-size: 16px;
            }}
            #Status {{ color: {muted}; font-size: {size + 1}px; }}
            QPushButton {{
                background: {button}; color: {fg};
                border: 1px solid {border}; border-radius: 8px;
                padding: 8px 12px; font-size: {size}px;
            }}
            QPushButton:hover {{ background: {hover}; border-color: {accent}; }}
            QPushButton:pressed {{ background: {pressed}; }}
            QPushButton:checked {{ background: {accent_fill}; border-color: {accent}; }}
            #PrimaryButton, #SaveStatesButton {{
                background: {accent_fill}; border-color: {accent}; color: {fg};
            }}
            #PrimaryButton:hover, #SaveStatesButton:hover {{ border-color: {accent_hover}; }}
            #DangerButton {{ border-color: #9f4559; background: #2b1924; }}
            #DangerButton:hover {{ border-color: #ff6b87; background: #4a2435; }}
            #MoreButton:checked {{ background: {accent_fill}; border-color: {accent}; }}
            QComboBox, QLineEdit, QPlainTextEdit {{
                background: {button}; color: {fg};
                border: 1px solid {border}; border-radius: 8px;
                padding: 7px 10px; font-size: {size}px;
                selection-background-color: {accent_fill};
            }}
            QComboBox:hover, QLineEdit:hover {{ border-color: {accent}; }}
            QComboBox QAbstractItemView {{
                background: {button}; color: {fg};
                selection-background-color: {accent_fill};
                border: 1px solid {border};
            }}
            QSlider::groove:horizontal {{
                background: {button}; height: 6px; border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {accent}; width: 14px;
                margin: -5px 0; border-radius: 7px;
            }}
            QSlider::sub-page:horizontal {{ background: {accent_fill}; border-radius: 3px; }}
            QCheckBox, QLabel {{ color: {fg}; }}
            """
        )
        if hasattr(self, "shelf"):
            self.shelf.apply_theme(self._theme)
        font = self.font()
        if not hasattr(self, "_base_point"):
            self._base_point = font.pointSize() if font.pointSize() > 0 else 10
        font.setPointSize(max(8, int(self._base_point * self._text / 100)))
        self.setFont(font)
        if isinstance(getattr(self, "toolbar", None), _FlowBar):
            self.toolbar.reflow()
        if isinstance(getattr(self, "quick_tools", None), _FlowBar):
            self.quick_tools.reflow()

    def _shelf_view(self) -> None:
        self._list_view = self.shelf.list_mode
        self._card_scale = self.shelf.card_scale
        self._show_hidden = self.shelf.show_hidden
        self._save_settings()

    def _look_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        integer = QCheckBox("Square pixels")
        integer.setObjectName("IntegerScale")
        integer.setChecked(self._integer)
        integer.toggled.connect(self._set_integer)
        bezel = QComboBox()
        bezel.setObjectName("Bezel")
        bezel.addItems(["Thin bezel", "Thick bezel", "No bezel"])
        bezel.setCurrentText({"thin": "Thin bezel", "thick": "Thick bezel", "none": "No bezel"}.get(self._bezel, "Thin bezel"))
        bezel.currentTextChanged.connect(self._set_bezel)
        bright = self._named_slider("Brightness", "Brightness", -50, 50, self._brightness, self._set_brightness)
        contrast = self._named_slider("Contrast", "Contrast", -50, 50, self._contrast, self._set_contrast)
        color = self._named_slider("Color", "Color", -50, 50, self._color, self._set_color)
        palette = QComboBox()
        palette.setObjectName("Palette")
        palette.addItems(["Full color", "Red-weak", "Green-weak", "Blue-weak"])
        palette.setCurrentIndex({"protanopia": 1, "deuteranopia": 2, "tritanopia": 3}.get(self._palette, 0))
        palette.currentIndexChanged.connect(self._set_palette)
        blend_box = QCheckBox("Blend frames")
        blend_box.setObjectName("FrameBlend")
        blend_box.setChecked(self._blend)
        blend_box.toggled.connect(self._set_blend)
        aspect = QComboBox()
        aspect.setObjectName("Aspect")
        aspect.addItems(["Pixel", "Wide"])
        aspect.setCurrentText("Wide" if self._aspect == "wide" else "Pixel")
        aspect.currentTextChanged.connect(self._set_aspect)
        bottom = QCheckBox("Bottom screen in its own window")
        bottom.setObjectName("BottomWindow")
        bottom.setChecked(self._bottom_window)
        bottom.toggled.connect(self._set_bottom)
        speaker = QComboBox()
        speaker.setObjectName("Speaker")
        speaker.addItem("Default speaker", "")
        for device in QMediaDevices.audioOutputs():
            ident = bytes(device.id()).decode("utf-8", "replace")
            speaker.addItem(device.description(), ident)
        index = speaker.findData(self._speaker)
        speaker.blockSignals(True)
        speaker.setCurrentIndex(index if index >= 0 else 0)
        speaker.blockSignals(False)
        speaker.currentIndexChanged.connect(lambda _index: self._set_speaker(str(speaker.currentData() or "")))
        latency = self._named_slider("Latency", "Latency", 20, 200, self._latency, self._set_latency)
        tone = QComboBox()
        tone.setObjectName("Tone")
        tone.addItems(["Tone off", "Low pass", "High pass"])
        tone.setCurrentText({"low": "Low pass", "high": "High pass"}.get(self._tone, "Tone off"))
        tone.currentTextChanged.connect(self._set_tone)
        lead = self._named_slider("Sound delay", "SoundDelay", -80, 80, self._lead_ms, self._set_lead)
        system_volume = self._named_slider(
            "This system",
            "SystemVolume",
            0,
            100,
            self._volumes.get(self.kind or "", 100),
            self._set_system_volume,
        )
        mic = QCheckBox("PC microphone as the DS mic")
        mic.setObjectName("PcMic")
        mic.setChecked(self._pc_mic)
        mic.toggled.connect(self._set_pc_mic)
        record = QPushButton("Stop recording" if self._wav is not None else "Record sound")
        record.setObjectName("RecordSound")
        record.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        record.clicked.connect(lambda: self._toggle_recording(record))
        text = QComboBox()
        text.setObjectName("TextSize")
        text.addItems(["Text 100%", "Text 125%", "Text 150%"])
        text.setCurrentText(f"Text {self._text}%")
        text.currentTextChanged.connect(self._set_text)
        theme = QComboBox()
        theme.setObjectName("Theme")
        theme.addItems(["Dark", "Night", "High contrast"])
        theme.setCurrentText({"night": "Night", "contrast": "High contrast"}.get(self._theme, "Dark"))
        theme.currentTextChanged.connect(self._set_theme)
        for widget in (
            integer, bezel, bright, contrast, color, palette, blend_box, aspect, bottom,
            speaker, latency, tone, lead, system_volume, mic, record, text, theme,
        ):
            layout.addWidget(widget)
        return panel

    def _named_slider(self, label: str, name: str, low: int, high: int, value: int, slot) -> QWidget:
        wrap = QWidget()
        column = QVBoxLayout(wrap)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(QLabel(label))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setObjectName(name)
        slider.setRange(low, high)
        slider.setValue(value)
        slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        slider.valueChanged.connect(slot)
        column.addWidget(slider)
        return wrap

    def _set_integer(self, on: bool) -> None:
        self._integer = bool(on)
        self._save_settings()
        self._present()

    def _set_bezel(self, text: str) -> None:
        self._bezel = {"Thick bezel": "thick", "No bezel": "none"}.get(text, "thin")
        self._save_settings()
        self._apply_theme()
        self._draw_screen()

    def _set_brightness(self, value: int) -> None:
        self._brightness = int(value)
        self._save_settings()
        self._present()

    def _set_contrast(self, value: int) -> None:
        self._contrast = int(value)
        self._save_settings()
        self._present()

    def _set_color(self, value: int) -> None:
        self._color = int(value)
        self._save_settings()
        self._present()

    def _set_palette(self, index: int) -> None:
        self._palette = {1: "protanopia", 2: "deuteranopia", 3: "tritanopia"}.get(index, "")
        self._save_settings()
        self._present()

    def _set_blend(self, on: bool) -> None:
        self._blend = bool(on)
        self._prev_frame = None
        self._save_settings()

    def _set_aspect(self, text: str) -> None:
        self._aspect = "wide" if text == "Wide" else "pixel"
        self._save_settings()
        self._present()

    def _set_bottom(self, on: bool) -> None:
        self._bottom_window = bool(on)
        self._save_settings()
        self._present()

    def _set_picture_size(self, value: int) -> None:
        self._picture_size = max(70, min(140, int(value)))
        self._save_settings()
        self._present()

    def _set_speaker(self, ident: str) -> None:
        self._speaker = ident
        self._save_settings()
        self._restart_audio()

    def _set_latency(self, value: int) -> None:
        self._latency = max(20, min(200, int(value)))
        self._save_settings()
        self._restart_audio()

    def _set_tone(self, text: str) -> None:
        self._tone = {"Low pass": "low", "High pass": "high"}.get(text, "off")
        self._tone_state = [0.0, 0.0]
        self._save_settings()

    def _set_lead(self, value: int) -> None:
        self._lead_ms = max(-80, min(80, int(value)))
        self._audio_delay.ms = self._lead_ms
        self._audio_delay.queue.clear()
        self._save_settings()

    def _set_system_volume(self, value: int) -> None:
        if self.kind:
            self._volumes[self.kind] = max(0, min(100, int(value)))
            self._save_settings()

    def _set_pc_mic(self, on: bool) -> None:
        self._pc_mic = bool(on)
        if not on:
            self._mic_hot = False
            self._stop_mic()
        self._save_settings()

    def _set_text(self, text: str) -> None:
        self._text = {"Text 125%": 125, "Text 150%": 150}.get(text, 100)
        self._save_settings()
        self._apply_theme()

    def _set_theme(self, text: str) -> None:
        self._theme = {"Night": "night", "High contrast": "contrast"}.get(text, "dark")
        self._save_settings()
        self._apply_theme()

    def _toggle_recording(self, button: QPushButton) -> None:
        if self._wav is not None:
            self._stop_recording()
            button.setText("Record sound")
            self._notice("Sound saved.")
            return
        path = _saves_dir() / "sound.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("wb")
        handle.write(wav_header(0))
        self._wav = handle
        self._wav_bytes = 0
        button.setText("Stop recording")

    def _stop_recording(self) -> None:
        handle = self._wav
        self._wav = None
        if handle is None:
            return
        try:
            handle.seek(0)
            handle.write(wav_header(self._wav_bytes))
            handle.close()
        except OSError:
            pass

    def _stop_mic(self) -> None:
        if self._mic_source is not None:
            self._mic_source.stop()
        self._mic_source = None
        self._mic_io = None

    def _poll_mic(self) -> None:
        self._mic_hot = False
        if not self._pc_mic:
            return
        try:
            if self._mic_source is None:
                fmt = QAudioFormat()
                fmt.setSampleRate(44100)
                fmt.setChannelCount(1)
                fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
                device = QMediaDevices.defaultAudioInput()
                if device is None or device.isNull():
                    return
                self._mic_source = QAudioSource(device, fmt, self)
                self._mic_io = self._mic_source.start()
            if self._mic_io is None:
                return
            data = self._mic_io.readAll().data()
            self._mic_hot = peak_level(data) > 2500
        except Exception:
            self._stop_mic()

    def _show_bottom(self, frame: bytes, width: int, height: int) -> None:
        if not self._bottom_window or self.kind not in ("nds", "3ds") or height < 2:
            if self._bottom_dialog is not None:
                self._bottom_dialog.hide()
            return
        dialog = self._bottom_dialog
        if dialog is None:
            dialog = QDialog(self)
            dialog.setWindowTitle("Bottom screen")
            dialog.setObjectName("BottomWindowDialog")
            label = QLabel()
            label.setObjectName("BottomScreen")
            layout = QVBoxLayout(dialog)
            layout.addWidget(label)
            self._bottom_dialog = dialog
        half = height // 2
        stride = width * 4
        raw = bytes(frame)
        if len(raw) < stride * height:
            return
        bottom = raw[half * stride:]
        image = QImage(bottom, width, half, stride, QImage.Format.Format_RGB32)
        dialog.findChild(QLabel, "BottomScreen").setPixmap(QPixmap.fromImage(image).scaled(width * 2, half * 2))
        dialog.show()

    def _remember_window(self, window) -> None:
        if window is None or window is self or self._fullscreen or not window.isVisible():
            return
        rect = window.geometry()
        if rect.width() < 200 or rect.height() < 200:
            return
        self._geometry = [rect.x(), rect.y(), rect.width(), rect.height()]
        self._save_settings()

    def apply_window(self, window) -> None:
        geo = self._geometry
        if not geo or len(geo) != 4:
            return
        window.setGeometry(geo[0], geo[1], max(200, geo[2]), max(200, geo[3]))

    def wheelEvent(self, event) -> None:
        super().wheelEvent(event)

    def _show_memory(self) -> None:
        dialog = getattr(self, "_memory_dialog", None)
        if dialog is not None and dialog.isVisible():
            dialog.raise_()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Memory")
        dialog.setObjectName("MemoryDialog")
        layout = QVBoxLayout(dialog)
        view = QPlainTextEdit()
        view.setObjectName("MemoryView")
        view.setReadOnly(True)
        view.setMinimumSize(420, 280)
        layout.addWidget(view)

        def refresh() -> None:
            bar = view.verticalScrollBar()
            place = bar.value()
            view.setPlainText(self._memory_text())
            bar.setValue(place)

        timer = QTimer(dialog)
        timer.timeout.connect(refresh)
        timer.start(400)
        refresh()
        dialog.show()
        self._memory_dialog = dialog

    def _memory_text(self) -> str:
        if self.kind == "gb" and self.gb is not None:
            start = 0xC000
            read = self.gb.mmu.read
            lines = []
            for row in range(16):
                addr = start + row * 16
                data = bytes(read((addr + index) & 0xFFFF) for index in range(16))
                lines.append(f"{addr:04X}  " + " ".join(f"{byte:02X}" for byte in data))
            return "\n".join(lines)
        core = self._core()
        if core is None:
            return "Open a game to see its RAM."
        ram = core.system_ram()
        if not ram:
            return "This core has not published its RAM yet."
        start = min(ram)
        lines = []
        for row in range(16):
            addr = start + row * 16
            data = [ram.get(addr + index) for index in range(16)]
            if any(byte is None for byte in data):
                break
            lines.append(f"{addr:04X}  " + " ".join(f"{byte:02X}" for byte in data))
        return "\n".join(lines) or "This core has not published its RAM yet."

    def _toggle_trace(self) -> None:
        if self._trace_file is not None:
            if self.gb is not None:
                self.gb.cpu.trace = None
            self._trace_file.close()
            self._trace_file = None
            self._log(f"Trace stopped. {self._trace_left} lines left unused.")
            self._notice("Trace stopped.")
            return
        if self.kind != "gb" or self.gb is None:
            self._log("This system does not expose its instructions.")
            self._notice("This system does not expose its instructions.")
            return
        path = _saves_dir() / "trace.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._trace_file = path.open("w", encoding="utf-8")
        self._trace_left = 20000

        def hook(pc: int, op: int) -> None:
            handle = self._trace_file
            if handle is None or self._trace_left <= 0:
                return
            self._trace_left -= 1
            handle.write(f"{pc:04X} {op:02X}\n")

        self.gb.cpu.trace = hook
        self._notice(f"Trace is writing to {path.name}.")

    def _show_errors(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Error log")
        dialog.setObjectName("ErrorLogDialog")
        layout = QVBoxLayout(dialog)
        view = QPlainTextEdit("\n".join(self._errors) or "No messages yet.")
        view.setObjectName("ErrorLog")
        view.setReadOnly(True)
        view.setMinimumSize(420, 240)
        layout.addWidget(view)
        dialog.show()
        self._error_dialog = dialog

    def _send_chat(self) -> None:
        text = self.chat_line.text().strip()
        if not text:
            return
        self.chat_line.clear()
        self._append_chat("You", text)
        if self._session is not None and self._session.ready:
            self._session.send_chat(text)

    def _append_chat(self, who: str, text: str) -> None:
        self.chat_panel.show()
        self.chat_view.appendPlainText(f"{who}: {text}")

    def _fingerprint(self) -> bytes:
        if self.kind == "gb" and self.gb is not None:
            cpu = self.gb.cpu
            blob = bytes((cpu.a, cpu.f, cpu.b, cpu.c, cpu.d, cpu.e)) + cpu.pc.to_bytes(2, "little")
            return hashlib.blake2s(blob, digest_size=8).digest()
        core = self._core()
        if core is not None and core.frame:
            raw = bytes(core.frame[0][:64])
            return hashlib.blake2s(raw, digest_size=8).digest()
        return b"\0" * 8

    def _plain_size(self, pixmap: QPixmap) -> tuple[int, int]:
        if self._rotate % 180:
            return pixmap.height(), pixmap.width()
        return pixmap.width(), pixmap.height()

    def _unrotate_point(self, px: int, py: int, width: int, height: int) -> tuple[int, int]:
        turn = self._rotate % 360
        if turn == 90:
            return py, width - 1 - px
        if turn == 270:
            return height - 1 - py, px
        if turn == 180:
            return width - 1 - px, height - 1 - py
        return px, py

    def _handle_net_error(self) -> None:
        session = self._session
        if session is None or not session.error:
            return
        message = session.error
        session.error = ""
        now = time.perf_counter()
        if session.role == "guest" and self._last_join:
            if self._reconnect_until == 0:
                self._reconnect_until = now + 8
                self._log("Reconnecting...")
            if now < self._reconnect_until:
                if now - self._reconnect_try >= 1:
                    self._reconnect_try = now
                    self._reconnect()
                return
        self._reconnect_until = 0
        self._log(message)
        self._notice(message)

    def _reconnect(self) -> None:
        old = self._session
        target = self._last_join
        if old is None or target is None:
            return
        host, port, relay = target
        link = self._prepare_net()
        if link is None:
            return
        link.room = old.room
        try:
            link.join(host, port, relay=relay, spectate=old.spectating)
        except OSError as exc:
            link.error = str(exc)
        if link.ready:
            old.close()
            self._session = link
            self._net_local.clear()
            self._reconnect_until = 0
            self._desync_noted = False
            self._sync_seen.clear()
            self._log("Reconnected.")
            self._notice("Reconnected.")
            return
        link.close()

    def _net_sideband(self) -> None:
        session = self._session
        if session is None or not session.ready:
            return
        now = time.perf_counter()
        if session.ping_ms:
            self.chat_ping.setText(f"Ping {session.ping_ms} ms")
        if now - self._ping_at >= 1:
            self._ping_at = now
            session.ping()
        if now - self._sync_at >= 2:
            self._sync_at = now
            digest = self._fingerprint()
            session.send_sync(session.frame, digest)
            self._sync_seen[session.frame] = digest
            if len(self._sync_seen) > 8:
                oldest = min(self._sync_seen)
                self._sync_seen.pop(oldest, None)
        for frame, digest in session.take_sync():
            mine = self._sync_seen.get(frame)
            if mine and mine != digest and not self._desync_noted:
                self._desync_noted = True
                self._notice("The games have drifted apart.")
        for text in session.take_chat():
            self._append_chat("Them", text)

    def _set_fast(self, value: int) -> None:
        self._fast_frames = max(2, min(16, int(value)))
        self._save_settings()

    def _set_net_delay(self, value: int, label: QLabel) -> None:
        self._delay = max(0, min(8, int(value)))
        label.setText(f"Delay {self._delay} frames")
        self._save_settings()

    def _set_deadzone(self, value: int) -> None:
        self._deadzone = max(0, min(100, int(value)))
        gamepad.deadzone_percent = self._deadzone
        self._save_settings()

    def _set_autofire(self, on: bool) -> None:
        self._autofire = False
        self._auto_phase = 0

    def _set_rate(self, text: str) -> None:
        self._rate = {"0.25x": 0.25, "0.5x": 0.5, "1x": 1.0, "2x": 2.0, "4x": 4.0, "8x": 8.0}.get(text, 1.0)
        self._rate_phase = 0
        self._save_settings()

    def _set_layout(self, text: str) -> None:
        self._layout = {"Side by side": "side", "Top large": "top"}.get(text, "stack")
        self._save_settings()
        self._present()

    def _set_filter(self, text: str) -> None:
        self._filter = {
            "Sharp": "sharp",
            "Smooth": "smooth",
            "Scanlines": "scanline",
            "CRT": "crt",
            "LCD": "lcd",
        }.get(text, "sharp")
        self._save_settings()
        self._present()

    def _toggle_fullscreen(self) -> None:
        window = self.window()
        self._fullscreen = not self._fullscreen
        if window is not None and window is not self:
            if self._fullscreen:
                window.showFullScreen()
            else:
                window.showNormal()
        self.full_btn.setText("Window" if self._fullscreen else "Fullscreen")
        self.toolbar.setVisible(not self._fullscreen)
        self.quick_tools.setVisible(not self._fullscreen and self._quick_tools_open)
        self.status.setVisible(not self._fullscreen)
        self._draw_screen()

    def _screenshot(self) -> None:
        pixmap = self.screen.pixmap()
        if pixmap is None or pixmap.isNull():
            self._notice("Nothing to capture.")
            return
        folder = _saves_dir() / "screenshots"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{time.strftime('%Y%m%d-%H%M%S')}.png"
        pixmap.save(str(path), "PNG")
        self._notice(path.name)

    def _copy_shot(self) -> None:
        pixmap = self.screen.pixmap()
        if pixmap is None or pixmap.isNull():
            self._notice("Nothing to capture.")
            return
        QGuiApplication.clipboard().setPixmap(pixmap)
        self._notice("Copied.")

    def _use_game_controls(self) -> None:
        if not self._game_id:
            self.controls = self._default_controls
            return
        path = self._default_controls.path.parent / "controls" / f"{self._game_id}.json"
        if path.is_file():
            self.controls = Controls(path)
        else:
            self.controls = self._default_controls.copy_to(path)

    def save_state(self) -> None:
        if self.rom is None:
            return
        if self.kind == "gba" and self.gba is not None and self.gba.game_loaded:
            path = self._state_path()
            path.write_bytes(pack_gba_state(gba_save_key(self.rom), self.gba.serialize()))
            self._saved_slot()
            return
        if self.kind == "nds" and self.nds is not None and self.nds.game_loaded:
            path = self._state_path()
            path.write_bytes(pack_nds_state(nds_save_key(self.rom), self.nds.serialize()))
            self._saved_slot()
            return
        if self.kind == "3ds" and self.n3ds is not None and self.n3ds.game_loaded:
            path = self._state_path()
            path.write_bytes(pack_n3ds_state(n3ds_save_key(self.rom), self.n3ds.serialize()))
            self._saved_slot()
            return
        if self.kind == "switch" and self.switch is not None and self.switch.game_loaded:
            try:
                blob = self.switch.serialize()
            except CoreError as exc:
                self._notice(str(exc))
                return
            path = self._state_path()
            path.write_bytes(pack_switch_state(self._switch_key, blob))
            self._saved_slot()
            return
        system_core = self.extra.get(self.kind or "")
        if self.kind in BY_ID and system_core is not None and system_core.game_loaded:
            try:
                blob = system_core.serialize()
            except CoreError as exc:
                self._notice(str(exc))
                return
            path = self._state_path()
            path.write_bytes(pack_system_state(self.kind or "", self._extra_key, blob))
            self._saved_slot()
            return
        if self.gb is None or self.kind != "gb":
            return
        path = self._state_path()
        path.write_bytes(self.gb.export_state())
        self._saved_slot()

    def load_state(self) -> None:
        if self.rom is None:
            return
        path = self._state_path()
        if not path.exists():
            self._notice(f"No save in slot {self.state_slot}")
            return
        try:
            blob = path.read_bytes()
            if self.kind == "gba" and self.gba is not None and self.gba.game_loaded:
                self.gba.unserialize(unpack_gba_state(blob, gba_save_key(self.rom)))
            elif self.kind == "nds" and self.nds is not None and self.nds.game_loaded:
                self.nds.unserialize(unpack_nds_state(blob, nds_save_key(self.rom)))
            elif self.kind == "3ds" and self.n3ds is not None and self.n3ds.game_loaded:
                self.n3ds.unserialize(unpack_n3ds_state(blob, n3ds_save_key(self.rom)))
            elif self.kind == "switch" and self.switch is not None and self.switch.game_loaded:
                self.switch.unserialize(unpack_switch_state(blob, self._switch_key))
            elif self.kind in BY_ID and self.extra.get(self.kind) is not None and self.extra[self.kind].game_loaded:
                self.extra[self.kind].unserialize(unpack_system_state(blob, self.kind, self._extra_key))
            elif self.gb is not None and self.kind == "gb":
                self.gb.import_state(blob)
            else:
                return
        except (ValueError, CoreError) as exc:
            self._notice(str(exc))
            return
        self._present()
        self._notice(f"Loaded slot {self.state_slot}")
        self.rewind.clear()
        self._rewind_warned = False

    def _notice(self, text: str) -> None:
        self.status.setText(text)
        self._log(text)

    def _link_phrase(self) -> str:
        session = self._session
        if session is None or not session.ready or session.mode != "link" or self.kind != "gba":
            return ""
        core = self._core()
        if core is None or not core._io_base:
            return "   ·   cable connected, registers not open"
        return "   ·   cable connected"

    def _ram_map(self) -> dict[int, int]:
        if self.kind == "gb" and self.gb is not None:
            data: dict[int, int] = {}
            for index, byte in enumerate(self.gb.mmu.wram[0]):
                data[0xC000 + index] = byte
            bank = self.gb.mmu.wram_bank or 1
            for index, byte in enumerate(self.gb.mmu.wram[bank]):
                data[0xD000 + index] = byte
            eram = self.gb.mmu.eram
            if eram:
                if len(eram) <= 0x800:
                    window = eram
                else:
                    slot = self.gb.mmu.ram_bank * 0x2000
                    window = eram[slot:slot + 0x2000]
                for index, byte in enumerate(window[:0x2000]):
                    data[0xA000 + index] = byte
            return data
        core = self._core()
        if core is None or not getattr(core, "game_loaded", False):
            return {}
        reader = getattr(core, "system_ram", None)
        if reader is None:
            return {}
        return reader()

    def _poke_found(self) -> None:
        if self.kind == "gb" or not self._game_id:
            return
        core = self._core()
        game = self.library.get(self._game_id)
        if core is None or game is None or not hasattr(core, "poke_ram"):
            return
        for cheat in game.cheats:
            if not cheat.enabled or cheat.kind != "address":
                continue
            parsed = _parse_address(cheat.code)
            if parsed is not None:
                core.poke_ram(parsed[0], parsed[1])

    def _add_searched_cheat(self, addr: int, value: int) -> None:
        if not self._game_id:
            self._notice("Open a game from the library first.")
            return
        code = f"{addr:04X}:{value:02X}" if addr <= 0xFFFF else f"{addr:08X}:{value:02X}"
        self.library.add_cheat(self._game_id, code, name="Search", kind="address")
        self._apply_cheats()

    def _show_cheat_search(self) -> None:
        if self._cheat_dialog is None:
            self._cheat_dialog = CheatSearchDialog(self._ram_map, self._add_searched_cheat, self)
        self._cheat_dialog.show()
        self._cheat_dialog.raise_()

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.library_pad_timer.stop()
        self.clock.stop()
        self._commit_play()
        self._beacon.stop()
        if self._relay is not None:
            self._relay.close()
            self._relay = None
        if self._trace_file is not None:
            if self.gb is not None:
                self.gb.cpu.trace = None
            self._trace_file.close()
            self._trace_file = None
        if self._session is not None:
            self._session.close()
            self._session = None
        self._flush_save()
        if self.gba is not None:
            self.gba.close()
            self.gba = None
        if self.nds is not None:
            self.nds.close()
            self.nds = None
        if self.n3ds is not None:
            self.n3ds.close()
            self.n3ds = None
        if self.switch is not None:
            self.switch.close()
            self.switch = None
        for core in self.extra.values():
            core.close()
        self.extra.clear()
        self._remember_window(self.window())
        self._stop_recording()
        self._stop_mic()
        if self.sink is not None:
            self.sink.stop()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat():
            return
        p2 = _p2_action(event)
        if p2 and self.kind is not None:
            self._p2_down.add(p2)
            self._apply_action(p2, True, 1)
            self._set_circle()
            return
        key = int(event.key())
        if self.stack.currentWidget() is self.shelf:
            keys = {Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down",
                    Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right"}
            if event.key() in keys:
                self.shelf.move_selection(keys[event.key()])
                return
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.shelf.activate_selection()
                return
        actions = self.controls.actions_for(key)
        if key == Qt.Key.Key_Escape and self._fullscreen and not actions:
            self._toggle_fullscreen()
            return
        slot = next((action for action in actions if action.startswith("slot")), "")
        if slot:
            self._set_slot(int(slot[-1]))
            return
        if self.kind is None:
            return
        if "autofire" in actions:
            return
        if "step" in actions:
            self._step_once = True
            self.paused = False
            self.pause_btn.setText("Pause")
            if not self.clock.isActive():
                self.clock.start(16)
            return
        if "save" in actions:
            self.save_state()
            return
        if "load" in actions:
            self.load_state()
            return
        if "fast" in actions:
            self.fast = not self.fast
            return
        if not actions:
            return
        self._down_keys.add(key)
        for action in actions:
            self._apply_action(action, True)
        self._set_circle()

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat() or self.kind is None:
            return
        p2 = _p2_action(event)
        if p2:
            self._p2_down.discard(p2)
            if not self._port_holds(p2, 1):
                self._apply_action(p2, False, 1)
            self._set_circle()
            return
        key = int(event.key())
        actions = self.controls.actions_for(key)
        if key not in self._down_keys:
            return
        self._down_keys.discard(key)
        for action in actions:
            if not self._action_held(action):
                self._apply_action(action, False)
        self._set_circle()

    def _action_held(self, action: str) -> bool:
        if action == "mic" and self._mic_hot:
            return True
        if action in self._pad_down:
            return True
        return any(key in self._down_keys for key in self.controls.keys(action))

    def _poll_gamepad(self) -> None:
        first, second = self._read_pads()
        self._pad = first
        self._pad2 = second
        self._take_pad(first, self._pad_down, 0)
        self._take_pad(second, self._pad2_down, 1)
        self._set_circle()

    def _take_pad(self, pad: Pad, held: set[str], port: int) -> None:
        now = set(pad.actions)
        pressed = now - held
        released = held - now
        held.clear()
        held.update(now)
        for action in pressed:
            if port == 1 and (action in ("rewind", "fast", "save", "load", "swap", "mic") or action.startswith("slot")):
                continue
            if port == 0 and (action in ("rewind", "fast", "save", "load") or action.startswith("slot")):
                continue
            self._apply_action(action, True, port)
        for action in released:
            if port == 1 and (action in ("rewind", "fast", "save", "load", "swap", "mic") or action.startswith("slot")):
                continue
            if port == 0 and (action in ("rewind", "fast", "save", "load") or action.startswith("slot")):
                continue
            if not self._port_holds(action, port):
                self._apply_action(action, False, port)

    def _port_holds(self, action: str, port: int) -> bool:
        if port == 0:
            return self._action_held(action)
        return action in self._pad2_down or action in self._p2_down

    def _pads_from_controllers(self) -> tuple[Pad, Pad]:
        return read_players(self.controls.pad)

    def _capture_blob(self) -> bytes | None:
        if self.kind == "gb" and self.gb is not None:
            return self.gb.export_state()
        core = self._core()
        if core is None or not core.game_loaded:
            return None
        try:
            return core.serialize()
        except CoreError:
            return None

    def _restore_blob(self, blob: bytes) -> bool:
        try:
            if self.kind == "gb" and self.gb is not None:
                self.gb.import_state(blob)
                return True
            core = self._core()
            if core is None or not core.game_loaded:
                return False
            core.unserialize(blob)
            return True
        except (ValueError, CoreError):
            return False

    def _rewind_store(self) -> None:
        if self.rewind.disabled:
            return
        blob = self._capture_blob()
        if blob is None:
            self.rewind.disabled = True
            self._warn_rewind()
            return
        if not self.rewind.configured:
            self.rewind.configure(blob)
            if self.rewind.disabled:
                self._warn_rewind()
                return
        self.rewind.push(blob)

    def _rewind_back(self) -> None:
        blob = self.rewind.pop()
        if blob is None or not self._restore_blob(blob):
            return
        self._present()

    def _warn_rewind(self) -> None:
        if self._rewind_warned:
            return
        self._rewind_warned = True
        self._notice("This game cannot rewind.")

    def _apply_action(self, action: str, down: bool, port: int = 0) -> None:
        spec = BY_ACTION.get(action)
        if spec is None:
            return
        if self.kind == "gb":
            if port != 0 or self.gb is None:
                return
            if spec.gb_dir is not None:
                self.gb.joypad.set_dir(spec.gb_dir, down)
            if spec.gb_button is not None:
                self.gb.joypad.set_button(spec.gb_button, down)
            return
        core = self._core()
        button = pad_button(action, self.kind or "")
        if core is None or button is None:
            return
        buttons = core.buttons if port == 0 else core.buttons_p2
        if down:
            buttons[button] = True
            return
        buttons[button] = any(
            self._port_holds(other, port) and pad_button(other, self.kind or "") == button
            for other in BY_ACTION
        )

    def _set_circle(self) -> None:
        kind = self.kind or ""
        core = self._core()
        if core is None or kind not in LEFT_STICK_KINDS and kind not in RIGHT_STICK_KINDS:
            return
        for port, pad in ((0, self._pad), (1, self._pad2)):
            analog = core.analog if port == 0 else core.analog_p2
            if kind in LEFT_STICK_KINDS:
                analog[0] = self._stick("left", "right", pad, port)
                analog[1] = self._stick("up", "down", pad, port)
            if kind in RIGHT_STICK_KINDS:
                analog[2] = self._stick("rstick_left", "rstick_right", pad, port)
                analog[3] = self._stick("rstick_up", "rstick_down", pad, port)

    def _stick(self, negative: str, positive: str, pad: Pad, port: int) -> int:
        axis = {
            ("left", "right"): "lx",
            ("up", "down"): "ly",
            ("rstick_left", "rstick_right"): "rx",
            ("rstick_up", "rstick_down"): "ry",
        }.get((negative, positive))
        if axis is not None:
            raw = getattr(pad, axis)
            if raw:
                return raw
        value = 0
        if self._port_holds(positive, port):
            value += 32767
        if self._port_holds(negative, port):
            value -= 32767
        return max(-32768, min(32767, value))

    def _local_held(self) -> set[str]:
        held = set(self._pad_down)
        for action in NET_ACTIONS:
            if any(key in self._down_keys for key in self.controls.keys(action)):
                held.add(action)
        if self._autofire and self._auto_phase >= 2:
            held.difference_update(_AUTO)
        return held

    def _apply_autofire(self) -> None:
        if not self._autofire:
            return
        self._auto_phase = (self._auto_phase + 1) % 4
        down = self._auto_phase < 2
        for action in _AUTO:
            if self._action_held(action):
                self._apply_action(action, down, 0)
            if action in self._pad2_down or action in self._p2_down:
                self._apply_action(action, down, 1)

    def _count_play(self) -> None:
        now = time.perf_counter()
        gap = now - self._play_mark if self._play_mark else 0
        if 0 < gap < 0.5:
            self._play_bank += gap
            self._auto_seconds += gap
        self._play_mark = now
        if self._auto_seconds >= 180 and self.rom is not None:
            self._auto_seconds = 0
            chosen = self.state_slot
            self.state_slot = AUTO_SLOT
            self.save_state()
            self.state_slot = chosen
        if self._play_bank >= 5:
            self._commit_play()
            self._play_mark = now

    def _commit_play(self) -> None:
        bank = self._play_bank
        self._play_bank = 0.0
        self._play_mark = 0.0
        if bank <= 0 or not self._game_id:
            return
        self.library.add_play(self._game_id, bank)

    def _pack_local(self) -> bytes:
        held = self._local_held()
        bits = 0
        for index, action in enumerate(NET_ACTIONS):
            if action in held:
                bits |= 1 << index
        pad = self._pad

        def axis(negative: str, positive: str, raw: int) -> int:
            if raw:
                return raw
            value = 0
            if positive in held:
                value += 32767
            if negative in held:
                value -= 32767
            return max(-32768, min(32767, value))

        analog = (
            axis("left", "right", pad.lx),
            axis("up", "down", pad.ly),
            axis("rstick_left", "rstick_right", pad.rx),
            axis("rstick_up", "rstick_down", pad.ry),
        )
        sb = self.gb.mmu.sb if self.gb is not None else 0xFF
        active = bool(self.gb is not None and (self.gb.mmu.sc & 0x80))
        if self.kind == "gba" and self._session is not None and self._session.mode == "link":
            core = self._core()
            half, started = core.gba_link_read() if core is not None else (0, False)
            bits = (half & 0xFFFF) << 16
            active = started
        return pack_input(bits, analog, sb, active)

    def _capture_net(self) -> bytes:
        try:
            if self.kind == "gb" and self.gb is not None:
                return self.gb.export_state()
            core = self._core()
            if core is not None and core.game_loaded:
                return core.serialize()
        except Exception:
            return b""
        return b""

    def _restore_net(self, blob: bytes) -> bool:
        if not blob:
            return False
        try:
            if self.kind == "gb" and self.gb is not None:
                self.gb.import_state(blob)
                return True
            core = self._core()
            if core is not None and core.game_loaded:
                core.unserialize(blob)
                return True
        except Exception:
            return False
        return False

    def _run_one(self) -> None:
        core = self._core()
        if core is not None:
            core.run()
        elif self.gb is not None:
            self.gb.run_frame()

    def _offer_state(self) -> None:
        session = self._session
        if session is None:
            return
        if session.want_state and session.role == "host":
            session.send_state(self._capture_net())
        incoming = session.take_state()
        if incoming and session.role != "host" and self._restore_net(incoming):
            self._roll.clear()
            self._notice("Caught up to the host.")

    def _watch_net(self) -> bool:
        session = self._session
        if session is None:
            return False
        bundle = session.take_bundle()
        if not bundle:
            return False
        self._apply_seats(bundle)
        return True

    def _rollback_net(self, payload: bytes, delayed: bytes) -> bool:
        session = self._session
        if session is None:
            return False
        frame = session.frame
        snap = self._capture_net()
        if self._roll_ok is None:
            self._roll_ok = 0 < len(snap) <= 1_000_000
        if not self._roll_ok:
            snap = b""
        remote = session.exchange(payload, wait=0.004 if self._roll_ok else 0.12)
        guessed = False
        if remote is None:
            if not self._roll_ok:
                return False
            remote = self._predicted or pack_input(0, (0, 0, 0, 0), 0xFF, False)
            session.advance()
            guessed = True
        else:
            self._predicted = remote
        for late_frame, late_body in session.take_late():
            self._repair(late_frame, late_body)
        self._roll.append((frame, snap, delayed, remote, guessed))
        if len(self._roll) > 8:
            del self._roll[:-8]
        self._apply_remote(remote, delayed)
        return True

    def _repair(self, frame: int, real: bytes) -> None:
        for index, (saved_frame, snap, local, used, guessed) in enumerate(self._roll):
            if saved_frame != frame or not guessed or unpack_input(used)[:2] == unpack_input(real)[:2]:
                continue
            if not self._restore_net(snap):
                return
            self._roll[index] = (saved_frame, snap, local, real, False)
            for saved_frame, _snap, local, remote, _guessed in self._roll[index:]:
                self._apply_remote(remote, local)
                self._run_one()
            return

    def _apply_seats(self, seats: dict[int, bytes]) -> None:
        for seat, packet in seats.items():
            bits, analog, _sb, _active = unpack_input(packet)
            actions = {NET_ACTIONS[index] for index in range(len(NET_ACTIONS)) if bits & (1 << index)}
            self._force_player(actions, analog, seat - 1)

    def _apply_remote(self, packet: bytes, local: bytes | None = None) -> None:
        bits, analog, sb, active = unpack_input(packet)
        session = self._session
        if session is None:
            return
        if session.mode == "link" and self.kind == "gba":
            core = self._core()
            if core is not None:
                core.gba_link_apply((bits >> 16) & 0xFFFF)
            self._link_was_active = False
            return
        if session.mode == "link" and self.gb is not None:
            self.gb.link_in = sb
            if active and not self._link_was_active and (self.gb.mmu.sc & 0x81) != 0x81:
                self.gb._complete_serial()
            self._link_was_active = active
            return
        self._link_was_active = False
        actions = {NET_ACTIONS[index] for index in range(len(NET_ACTIONS)) if bits & (1 << index)}
        if local is None:
            local_actions = self._local_held()
            local_analog = self._local_analog()
        else:
            local_bits, local_analog, _sb, _active = unpack_input(local)
            local_actions = {NET_ACTIONS[index] for index in range(len(NET_ACTIONS)) if local_bits & (1 << index)}
        if session.role == "guest":
            self._force_player(actions, analog, 0)
            self._force_player(local_actions, local_analog, 1)
        else:
            self._force_player(local_actions, local_analog, 0)
            self._force_player(actions, analog, 1)

    def _local_analog(self) -> tuple[int, int, int, int]:
        held = self._local_held()
        pad = self._pad

        def axis(negative: str, positive: str, raw: int) -> int:
            if raw:
                return raw
            value = 0
            if positive in held:
                value += 32767
            if negative in held:
                value -= 32767
            return max(-32768, min(32767, value))

        return (
            axis("left", "right", pad.lx),
            axis("up", "down", pad.ly),
            axis("rstick_left", "rstick_right", pad.rx),
            axis("rstick_up", "rstick_down", pad.ry),
        )

    def _force_player(self, actions: set[str], analog: tuple[int, int, int, int], port: int) -> None:
        if self.kind == "gb" or port not in (0, 1, 2, 3):
            return
        core = self._core()
        if core is None:
            return
        pads = (core.buttons, core.buttons_p2, core.buttons_p3, core.buttons_p4)
        sticks_all = (core.analog, core.analog_p2, core.analog_p3, core.analog_p4)
        buttons = pads[port]
        for index in range(len(buttons)):
            buttons[index] = False
        for action in actions:
            button = pad_button(action, self.kind or "")
            if button is not None and button < len(buttons):
                buttons[button] = True
        sticks = sticks_all[port]
        sticks[0], sticks[1], sticks[2], sticks[3] = analog

    def _show_net(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Netplay")
        dialog.setObjectName("NetplayDialog")
        layout = QVBoxLayout(dialog)
        status = QLabel(self._net_status())
        status.setWordWrap(True)
        layout.addWidget(status)
        delay_row = QHBoxLayout()
        delay_label = QLabel(f"Delay {self._delay} frames")
        delay_label.setObjectName("NetDelayLabel")
        delay = QSlider(Qt.Orientation.Horizontal)
        delay.setObjectName("NetDelay")
        delay.setRange(0, 8)
        delay.setValue(self._delay)
        delay.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        delay.valueChanged.connect(lambda value: self._set_net_delay(value, delay_label))
        delay_row.addWidget(delay_label)
        delay_row.addWidget(delay, 1)
        layout.addLayout(delay_row)
        hint = QLabel("A link cable stays in step. Delay is for playing the same game together. Ping is in the chat panel.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        password = QLineEdit(self._net_password)
        password.setObjectName("NetPassword")
        password.setPlaceholderText("Password")
        password.setEchoMode(QLineEdit.EchoMode.Password)
        password.textChanged.connect(lambda text: setattr(self, "_net_password", text))
        layout.addWidget(password)
        lobby = QListWidget()
        lobby.setObjectName("LobbyList")
        find = QPushButton("Find")
        find.setObjectName("FindLobby")
        find.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        find.clicked.connect(lambda: self._fill_lobby(lobby, status))
        lobby.itemClicked.connect(lambda item: self._join_lobby(item, dialog, status))
        layout.addWidget(find)
        layout.addWidget(lobby)
        host = QPushButton("Host")
        join = QPushButton("Join")
        relay = QPushButton("Relay")
        relay.setObjectName("RelayButton")
        stop = QPushButton("Disconnect")
        join_relay = QCheckBox("This address is a relay")
        join_relay.setObjectName("JoinRelay")
        for button in (host, join, relay, stop):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        host.clicked.connect(lambda: self._host_net(dialog, status))
        watch = QCheckBox("Watch")
        watch.setObjectName("NetWatch")
        join.clicked.connect(lambda: self._join_net(dialog, status, join_relay.isChecked(), watch.isChecked()))
        relay.clicked.connect(lambda: self._start_relay(status))
        stop.clicked.connect(lambda: self._stop_net(status))
        layout.addWidget(host)
        layout.addWidget(join)
        layout.addWidget(watch)
        layout.addWidget(join_relay)
        layout.addWidget(relay)
        layout.addWidget(stop)
        dialog.exec()

    def _net_status(self) -> str:
        session = self._session
        if session is None or not session.ready and session.role != "host":
            if session is not None and session.error:
                return session.error
            return "Host opens port 5555. Join types that computer's address, such as 192.168.1.20:5555."
        if session.ready and session.mode == "link":
            return "Link cable connected."
        if session.ready and session.spectating:
            return "Watching."
        if session.ready:
            who = f"player {session.seat}."
            wait = f" Delay is {session.delay} frames." if session.delay else ""
            ping = f" Ping {session.ping_ms} ms." if session.ping_ms else ""
            return "Playing together. You are " + who + wait + ping
        if session.role == "host":
            return "Waiting for the other side to join port 5555."
        return session.error or "Connecting."

    def _prepare_net(self) -> Link | None:
        if self.rom is None or self.kind is None:
            self._notice("Open a game first.")
            return None
        link = Link()
        link.delay = self._delay
        link.password = self._net_password
        self._net_local.clear()
        link.set_game(hashlib.blake2s(self.rom[:0x1000], digest_size=8).digest(), self.kind or "")
        return link

    def _host_net(self, dialog: QDialog, status: QLabel) -> None:
        link = self._prepare_net()
        if link is None:
            status.setText("Open a game first.")
            return
        if self._session is not None:
            self._session.close()
        try:
            link.host(5555)
        except OSError as exc:
            status.setText(str(exc))
            return
        self._session = link
        self._desync_noted = False
        self._sync_seen.clear()
        self.chat_panel.show()
        title = self._library_identity()[0]
        self._beacon.start(5555, title, bool(self._net_password), False)
        status.setText(self._net_status())
        dialog.accept()

    def _join_net(self, dialog: QDialog, status: QLabel, relay: bool = False, spectate: bool = False) -> None:
        link = self._prepare_net()
        if link is None:
            status.setText("Open a game first.")
            return
        text, ok = QInputDialog.getText(self, "Join", "Address", text="127.0.0.1:5555")
        if not ok or not text.strip():
            return
        host, _, port_text = text.strip().rpartition(":")
        if not host:
            host, port_text = text.strip(), "5555"
        try:
            port = int(port_text)
        except ValueError:
            status.setText("Use an address like 192.168.1.20:5555.")
            return
        if self._session is not None:
            self._session.close()
        try:
            link.join(host, port, relay=relay, spectate=spectate)
        except OSError as exc:
            status.setText(str(exc))
            return
        self._session = link
        if link.error:
            status.setText(link.error)
            return
        self._last_join = (host, port, relay)
        self._reconnect_until = 0
        self._desync_noted = False
        self._sync_seen.clear()
        self.chat_panel.show()
        status.setText(self._net_status())
        dialog.accept()

    def _join_lobby(self, item: QListWidgetItem, dialog: QDialog, status: QLabel) -> None:
        entry = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, dict):
            return
        if entry.get("password") and not self._net_password:
            status.setText("Type the password first.")
            return
        link = self._prepare_net()
        if link is None:
            status.setText("Open a game first.")
            return
        host = str(entry.get("host", ""))
        port = int(entry.get("port", 5555))
        relay = bool(entry.get("relay"))
        if self._session is not None:
            self._session.close()
        try:
            link.join(host, port, relay=relay)
        except OSError as exc:
            status.setText(str(exc))
            return
        self._session = link
        if link.error:
            status.setText(link.error)
            return
        self._last_join = (host, port, relay)
        self._reconnect_until = 0
        self.chat_panel.show()
        status.setText(self._net_status())
        dialog.accept()

    def _fill_lobby(self, lobby: QListWidget, status: QLabel) -> None:
        lobby.clear()
        found = discover(0.6)
        if not found:
            status.setText("Nobody on this network is hosting yet.")
            return
        for entry in found:
            label = f"{entry['title']}   {entry['host']}:{entry['port']}"
            if entry.get("password"):
                label += "   password"
            if entry.get("relay"):
                label += "   relay"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            lobby.addItem(item)
        status.setText(f"{len(found)} on this network.")

    def _start_relay(self, status: QLabel) -> None:
        if self._relay is not None:
            self._relay.close()
        relay = Relay()
        try:
            port = relay.start(5555)
        except OSError as exc:
            status.setText(str(exc))
            return
        self._relay = relay
        self._beacon.start(port, "Relay", False, True)
        status.setText(f"Relay is open on port {port}. Both players join that address.")

    def _stop_net(self, status: QLabel) -> None:
        self._last_join = None
        self._reconnect_until = 0
        self._beacon.stop()
        if self._relay is not None:
            self._relay.close()
            self._relay = None
        if self._session is not None:
            self._session.close()
            self._session = None
        self._net_local.clear()
        self.chat_panel.hide()
        if self.gb is not None:
            self.gb.link_in = None
        status.setText(self._net_status())

    def _show_controls(self) -> None:
        name = self._library_identity()[1] if self.kind else ""
        ControlsDialog(self.controls, self, kind=self.kind, system_name=name).exec()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.setFocus()
        if self._touch_core() is None or event.button() != Qt.MouseButton.LeftButton:
            return
        self._touching = True
        self._move_touch(event.position().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._touch_core() is not None and self._touching:
            self._move_touch(event.position().toPoint())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        core = self._touch_core()
        if core is None:
            return
        self._touching = False
        core.pointer_pressed = False

    def _move_touch(self, pos) -> None:
        core = self._touch_core()
        if core is None or core.frame is None:
            return
        local = self.screen.mapFrom(self, pos)
        rect = self.screen.contentsRect()
        pixmap = self.screen.pixmap()
        if pixmap is None or pixmap.isNull():
            core.pointer_pressed = False
            return
        origin_x = rect.x() + max(0, (rect.width() - pixmap.width()) // 2)
        origin_y = rect.y() + max(0, (rect.height() - pixmap.height()) // 2)
        px = local.x() - origin_x
        py = local.y() - origin_y
        px, py = self._unrotate_point(px, py, pixmap.width(), pixmap.height())
        plain_w, plain_h = self._plain_size(pixmap)
        if px < 0 or py < 0 or px >= plain_w or py >= plain_h:
            core.pointer_pressed = False
            return
        width, height = self._touch_size
        if self._touch_side and height >= 2:
            orig_w, orig_h = self._touch_size
            half_w = plain_w / 2
            half_h = orig_h / 2
            if px >= half_w:
                fx = (px - half_w) * orig_w / max(half_w, 1)
                fy = py * half_h / plain_h + half_h
            else:
                fx = px * orig_w / max(half_w, 1)
                fy = py * half_h / plain_h
            dx, dy = self._crop_origin
            core.set_pointer(fx + dx, fy + dy, True)
            return
        dx, dy = self._crop_origin
        core.set_pointer(dx + px * width / plain_w, dy + py * height / plain_h, True)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        self._add_roms([url.toLocalFile() for url in urls if url.isLocalFile()])

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)
