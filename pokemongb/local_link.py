"""Two Game Boy sessions connected by a local serial cable."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from PySide6.QtCore import QEvent, QRect, Qt, QTimer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from pokemongb.cart import read_rom, rom_title, save_key
from pokemongb.controls import BY_ACTION
from pokemongb.patch import apply_patch
from pokemongb.picture import gb_picture
from pokemongb.system import GameBoy, LocalLink

_ACTIONS = ("up", "down", "left", "right", "a", "b", "select", "start")


def battery_paths(rom: bytes, directory: Path) -> tuple[Path, Path]:
    key = save_key(rom)
    return directory / f"{key}.sav", directory / f"{key}.rtc.json"


def read_battery(game: GameBoy, sav: Path, rtc: Path) -> None:
    if sav.exists():
        game.mmu.import_ram(sav.read_bytes())
    if game.mmu.has_rtc and rtc.exists():
        game.mmu.import_rtc(json.loads(rtc.read_text(encoding="utf-8")))


def _write_file(path: Path, data: bytes) -> None:
    with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temp = Path(temporary.name)
        try:
            temporary.write(data)
        except OSError:
            temporary.close()
            temp.unlink(missing_ok=True)
            raise
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def write_battery(game: GameBoy, sav: Path, rtc: Path) -> None:
    mmu = game.mmu
    if not mmu.eram and not mmu.has_rtc:
        return
    sav.parent.mkdir(parents=True, exist_ok=True)
    if mmu.has_rtc:
        payload = {"zero": mmu.rtc_zero, "halt": mmu.rtc_halt, "carry": mmu.rtc_carry,
                   "frozen": list(mmu.rtc_frozen)}
        _write_file(rtc, json.dumps(payload).encode("utf-8"))
    if mmu.eram:
        _write_file(sav, bytes(mmu.eram))
    mmu.sram_dirty = False


class _Display(QWidget):
    def __init__(self):
        super().__init__()
        self.image = None
        self.setMinimumSize(160, 144)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())
        if self.image is None:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Choose a Game Boy ROM")
            return
        scale = min(self.width() / 160, self.height() / 144)
        width, height = int(160 * scale), int(144 * scale)
        target = QRect((self.width() - width) // 2, (self.height() - height) // 2, width, height)
        painter.drawImage(target, self.image)


class LocalLinkDialog(QDialog):
    def __init__(self, page, saves: Path, keypad_action):
        super().__init__(page)
        self.page = page
        self.saves = saves
        self.keypad_action = keypad_action
        self.setWindowTitle("Local Game Boy link")
        self.resize(800, 430)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.paths: list[Path | None] = [None, None]
        self.screens = [_Display(), _Display()]
        self.titles = [QLabel("Player 1"), QLabel("Player 2")]
        for title in self.titles:
            title.setTextFormat(Qt.TextFormat.PlainText)
        self.choices = []
        self.profiles = [None, None]
        self.save_paths = []
        self.written: set[Path] = set()
        self.cable = None
        self.save_error = ""
        self.held = [{}, {}]
        self.player = 0
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(17)
        self.timer.timeout.connect(self._tick)
        self.save_timer = QTimer(self)
        self.save_timer.setInterval(1000)
        self.save_timer.timeout.connect(self._flush)

        layout = QVBoxLayout(self)
        players = QHBoxLayout()
        for port in range(2):
            column = QVBoxLayout()
            column.addWidget(self.titles[port])
            column.addWidget(self.screens[port], 1)
            button = QPushButton(f"Choose Player {port + 1} ROM")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda checked=False, p=port: self._choose(p))
            self.choices.append(button)
            column.addWidget(button)
            players.addLayout(column, 1)
        layout.addLayout(players, 1)
        controls = QLabel(
            "Use two controllers, or use your normal keys and the numpad. "
            "Press Tab to switch which player uses your normal keys. "
            "For matching cartridges, Player 2 has a separate battery save."
        )
        controls.setWordWrap(True)
        layout.addWidget(controls)
        self.status = QLabel("Choose two Game Boy or Game Boy Color ROMs.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.start = QPushButton("Connect")
        self.start.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.start.setEnabled(False)
        self.start.clicked.connect(self._connect)
        close = QPushButton("Close")
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.clicked.connect(self.reject)
        buttons.addWidget(self.start)
        buttons.addStretch()
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def _choose(self, port: int) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self, f"Player {port + 1} ROM", str(self.paths[port] or ""),
            "Game Boy ROMs (*.gb *.gbc *.zip)",
        )
        if name:
            self.paths[port] = Path(name)
            self.titles[port].setText(f"Player {port + 1} · {Path(name).name}")
            self.start.setEnabled(all(self.paths))

    def _connect(self) -> None:
        games = []
        roms = []
        profiles = []
        try:
            for path in self.paths:
                rom = read_rom(path)
                profile = self.page.library.by_path(path)
                patch = self.page.library.patch_file(profile)
                if patch is not None:
                    rom = apply_patch(rom, patch.read_bytes())
                game = GameBoy()
                game.load(rom)
                if profile is not None:
                    self.page.library.use_cheat_file(profile)
                    game.set_cheats([(cheat.code, cheat.kind) for cheat in profile.cheats if cheat.enabled])
                games.append(game)
                roms.append(rom)
                profiles.append(profile)
            second = self.saves / "local-link" / "player2" if save_key(roms[0]) == save_key(roms[1]) else self.saves
            self.save_paths = [battery_paths(roms[0], self.saves), battery_paths(roms[1], second)]
            for game, paths in zip(games, self.save_paths):
                read_battery(game, *paths)
        except Exception as exc:
            QMessageBox.warning(self, "Local Game Boy link", str(exc))
            return

        self.cable = LocalLink(*games)
        self.profiles = profiles
        for port, (title, rom) in enumerate(zip(self.titles, roms), 1):
            title.setText(f"Player {port} · {rom_title(rom)}")
        for button in (*self.choices, self.start):
            button.setEnabled(False)
        self._status()
        self.page._start_audio()
        self.setFocus()
        self.timer.start()
        self.save_timer.start()

    def _status(self) -> None:
        self.status.setText(
            f"Cable connected · Keyboard: Player {self.player + 1} · "
            f"{self.cable.transfers} bytes exchanged · Player 1 audio"
            + (f"\n{self.save_error}" if self.save_error else "")
        )

    def _tick(self) -> None:
        pads = self.page._read_pads()
        for game, keys, pad in zip(self.cable.games, self.held, pads):
            actions = set(keys.values()) | set(pad.actions)
            for action in _ACTIONS:
                spec = BY_ACTION[action]
                if spec.gb_dir is not None:
                    game.joypad.set_dir(spec.gb_dir, action in actions)
                if spec.gb_button is not None:
                    game.joypad.set_button(spec.gb_button, action in actions)
        try:
            self.cable.run_frame()
        except Exception as exc:
            self.timer.stop()
            self.status.setText(f"Link stopped: {exc}")
            return
        for game, screen, profile in zip(self.cable.games, self.screens, self.profiles):
            if game.ppu.frame_ready or screen.image is None:
                frame = gb_picture(game.ppu, profile.gb_palette, profile.gb_colors) if profile else game.ppu.fb.tobytes()
                screen.image = QImage(frame, 160, 144, 640, QImage.Format.Format_RGB32).copy()
                screen.update()
        first, second = self.cable.games
        audio = first.apu.take_samples()
        second.apu.take_samples()
        if self.page.audio_io is not None and self.page.sink is not None:
            self.page.audio_io.write(audio[:self.page.sink.bytesFree()])
        self._status()

    def _flush(self, *, closing=False) -> bool:
        if self.cable is None:
            return True
        for game, paths in zip(self.cable.games, self.save_paths):
            if game.mmu.sram_dirty or (closing and game.mmu.has_rtc):
                try:
                    write_battery(game, *paths)
                except OSError as exc:
                    self.save_error = f"Could not save: {exc}"
                    self._status()
                    if closing:
                        QMessageBox.warning(self, "Could not save", str(exc))
                    return False
                self.written.add(paths[0])
        self.save_error = ""
        return True

    def done(self, result: int) -> None:
        if not self._flush(closing=True):
            return
        self.timer.stop()
        self.save_timer.stop()
        super().done(result)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.WindowDeactivate:
            for keys in self.held:
                keys.clear()
        if (event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Tab
                and self.cable is not None and not event.isAutoRepeat()):
            self.player = 1 - self.player
            self._status()
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        if self.cable is not None:
            key = (int(event.key()), bool(event.modifiers() & Qt.KeyboardModifier.KeypadModifier))
            action = self.keypad_action(event)
            port = 1 if action else self.player
            if not action:
                action = next((name for name in _ACTIONS if key[0] in self.page.controls.keys(name)), "")
            if action in _ACTIONS:
                if not event.isAutoRepeat():
                    self.held[port][key] = action
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if not event.isAutoRepeat():
            key = (int(event.key()), bool(event.modifiers() & Qt.KeyboardModifier.KeypadModifier))
            for keys in self.held:
                keys.pop(key, None)
        super().keyReleaseEvent(event)
