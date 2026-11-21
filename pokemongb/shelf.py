"""Cartridge library and the settings popup for one game."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pokemongb.cheats import KINDS, RamSearch, describe, parse_cheat_file
from pokemongb.library import Game, Library, format_last_played, format_played

_STYLE = """
QDialog, #Shelf, #ShelfBody { background: #0f1115; color: #e6e6e6; }
#Cartridge {
    background: #151922;
    border: 1px solid #252d3d;
    border-radius: 14px;
}
#Cartridge[selected="true"] { border: 2px solid #a78bfa; background: #222039; }
#CartridgeTitle { color: #e6e6e6; font-size: 13px; font-weight: 600; }
#CartridgeSystem { color: #9aa4b2; font-size: 11px; }
#Cover {
    background: #10141d;
    border: 1px solid #252d3d;
    border-radius: 8px;
    color: #9aa4b2;
    font-size: 13px;
}
#CartMenu, #CartStar {
    background: #1b2030;
    color: #e6e6e6;
    border: 1px solid #252d3d;
    border-radius: 8px;
    font-size: 14px;
    padding: 0;
}
QLineEdit, QComboBox, QListWidget {
    background: #1b2030;
    color: #e6e6e6;
    border: 1px solid #252d3d;
    border-radius: 8px;
    padding: 6px 8px;
}
QPushButton {
    background: #1b2030;
    color: #e6e6e6;
    border: 1px solid #252d3d;
    border-radius: 8px;
    padding: 8px 12px;
}
QPushButton:hover { background: #212739; border-color: #a78bfa; }
QPushButton:checked { background: #2a2147; border-color: #a78bfa; }
QCheckBox { color: #e6e6e6; }
#DetectedKind { color: #c4b5fd; font-size: 13px; }
#Hint { color: #9aa4b2; font-size: 12px; }
#LibraryList { background: #10141d; }
#LibraryEmpty, #LibraryNone { color: #9aa4b2; font-size: 16px; }
"""


def _button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return button


def _kind_combo(current: str) -> QComboBox:
    combo = QComboBox()
    combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    for kind, label in KINDS:
        combo.addItem(label, kind)
    index = combo.findData(current or "auto")
    combo.setCurrentIndex(index if index >= 0 else 0)
    return combo


class CartridgeCard(QFrame):
    play = Signal(str)
    configure = Signal(str)
    favorite = Signal(str)

    def __init__(self, game: Game, cover: Path | None, scale: int = 100):
        super().__init__()
        self.game_id = game.id
        self.setObjectName("Cartridge")
        scale = max(70, min(140, int(scale)))
        card_w = int(188 * scale / 100)
        card_h = int(268 * scale / 100)
        cover_w = int(158 * scale / 100)
        cover_h = int(176 * scale / 100)
        self.setFixedSize(card_w, card_h)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(6)

        self.cover = QLabel(game.system)
        self.cover.setObjectName("Cover")
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setFixedSize(cover_w, cover_h)
        self.cover.setWordWrap(True)
        if cover is not None:
            pixmap = QPixmap(str(cover))
            if not pixmap.isNull():
                self.cover.setPixmap(
                    pixmap.scaled(
                        cover_w,
                        cover_h,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        layout.addWidget(self.cover)

        self.menu = _button("···")
        self.menu.setObjectName("CartMenu")
        self.menu.setFixedSize(40, 28)
        self.menu.setParent(self.cover)
        self.menu.move(max(0, cover_w - 46), 6)
        self.menu.clicked.connect(lambda: self.configure.emit(self.game_id))
        self.star = _button("★" if game.favorite else "☆")
        self.star.setObjectName("CartStar")
        self.star.setFixedSize(28, 28)
        self.star.setParent(self.cover)
        self.star.move(6, 6)
        self.star.clicked.connect(lambda: self.favorite.emit(self.game_id))

        title = QLabel(game.title)
        title.setObjectName("CartridgeTitle")
        title.setWordWrap(True)
        title.setFixedHeight(36)
        bits = [game.system]
        played = format_played(game.played)
        if played:
            bits.append(played)
        when = format_last_played(game.last_played)
        if when:
            bits.append(when)
        if game.launches:
            bits.append(f"{game.launches} plays")
        if game.tags:
            bits.append(", ".join(game.tags[:3]))
        system = QLabel(" · ".join(bits))
        system.setObjectName("CartridgeSystem")
        system.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(system)

    def mousePressEvent(self, event) -> None:
        widget = self.childAt(event.pos())
        names: list[str] = []
        while widget is not None and widget is not self:
            names.append(widget.objectName())
            widget = widget.parentWidget()
        if "CartMenu" in names or "CartStar" in names:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.play.emit(self.game_id)
        super().mousePressEvent(event)


class Shelf(QWidget):
    """The menu of cartridges."""

    def __init__(self, library: Library, play, configure, on_change=None, scale: int = 100, listed: bool = False, show_hidden: bool = False):
        super().__init__()
        self.library = library
        self._play = play
        self._configure = configure
        self._on_change = on_change
        self.card_scale = max(70, min(140, int(scale)))
        self.list_mode = bool(listed)
        self.show_hidden = bool(show_hidden)
        self.setObjectName("Shelf")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("LibrarySearch")
        self.search.setPlaceholderText("Search")
        self.search.textChanged.connect(lambda _text: self.refresh())
        self.favorites = QPushButton("Favorites")
        self.favorites.setObjectName("LibraryFavorites")
        self.favorites.setCheckable(True)
        self.favorites.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.favorites.toggled.connect(lambda _on: self.refresh())
        self.sort = QComboBox()
        self.sort.setObjectName("LibrarySort")
        self.sort.addItems(["Recent", "Name", "System", "Play time", "Custom"])
        self.sort.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sort.currentTextChanged.connect(lambda _text: self.refresh())
        self.tag_box = QComboBox()
        self.tag_box.setObjectName("LibraryTags")
        self.tag_box.addItem("All tags")
        self.tag_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tag_box.currentTextChanged.connect(lambda _text: self.refresh())
        self.view = QPushButton("List")
        self.view.setObjectName("LibraryListButton")
        self.view.setCheckable(True)
        self.view.setChecked(self.list_mode)
        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.toggled.connect(self._toggle_list)
        self.hidden_btn = QPushButton("Hidden")
        self.hidden_btn.setObjectName("LibraryHidden")
        self.hidden_btn.setCheckable(True)
        self.hidden_btn.setChecked(self.show_hidden)
        self.hidden_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hidden_btn.toggled.connect(self._toggle_hidden)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.sort)
        bar.addWidget(self.tag_box)
        bar.addWidget(self.view)
        bar.addWidget(self.hidden_btn)
        bar.addWidget(self.favorites)
        root.addLayout(bar)
        self.recent_row = QWidget()
        self.recent_row.setObjectName("RecentRow")
        self.recent_layout = QHBoxLayout(self.recent_row)
        self.recent_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.recent_row)
        self.list = QListWidget()
        self.list.setObjectName("LibraryList")
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.itemClicked.connect(self._play_item)
        self.list.model().rowsMoved.connect(self._rows_moved)
        self.list.hide()
        root.addWidget(self.list, 1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.body = QWidget()
        self.body.setObjectName("ShelfBody")
        self.grid = QGridLayout(self.body)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid.setSpacing(16)
        self.scroll.setWidget(self.body)
        root.addWidget(self.scroll, 1)
        self.setStyleSheet(_STYLE)
        self.cards: list[CartridgeCard] = []
        self._selected_game: str | None = None
        self.refresh()

    def refresh(self) -> None:
        self.cards.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self._fill_recent()
        self._fill_tags()
        games = self._visible_games()
        if not self.library.games:
            self.list.hide()
            self.scroll.show()
            empty = QLabel("Open a ROM and it stays here.")
            empty.setObjectName("LibraryEmpty")
            self.grid.addWidget(empty, 0, 0)
            return
        if not games:
            self.list.hide()
            self.scroll.show()
            empty = QLabel("Nothing matches." if self._searching() else "Hidden games stay out of this list.")
            empty.setObjectName("LibraryNone")
            self.grid.addWidget(empty, 0, 0)
            return
        if self.list_mode:
            self.scroll.hide()
            self.list.show()
            self._fill_list(games)
            self._mark_selection()
            return
        self.list.hide()
        self.scroll.show()
        for index, game in enumerate(games):
            card = CartridgeCard(game, self.library.cover_file(game), self.card_scale)
            card.play.connect(self._play)
            card.configure.connect(self._configure)
            card.favorite.connect(self._toggle_favorite)
            self.cards.append(card)
            self.grid.addWidget(card, index // 4, index % 4)
        self._mark_selection()

    def _selection_ids(self) -> list[str]:
        return [game.id for game in self._visible_games()]

    def _mark_selection(self) -> None:
        ids = self._selection_ids()
        if ids and self._selected_game not in ids:
            self._selected_game = ids[0]
        if not ids:
            self._selected_game = None
        for card in self.cards:
            chosen = card.game_id == self._selected_game
            if card.property("selected") != chosen:
                card.setProperty("selected", chosen)
                card.style().unpolish(card)
                card.style().polish(card)
        if self.list_mode and self._selected_game in ids:
            self.list.setCurrentRow(ids.index(self._selected_game))
        elif self._selected_game in ids:
            for card in self.cards:
                if card.game_id == self._selected_game:
                    self.scroll.ensureWidgetVisible(card)
                    break

    def move_selection(self, direction: str) -> None:
        ids = self._selection_ids()
        if not ids:
            return
        if self._selected_game not in ids:
            self._selected_game = ids[0]
        else:
            idx = ids.index(self._selected_game)
            if self.list_mode:
                delta = -1 if direction in ("left", "up") else 1
            else:
                delta = {"left": -1, "right": 1, "up": -4, "down": 4}.get(direction, 0)
            self._selected_game = ids[max(0, min(len(ids) - 1, idx + delta))]
        self._mark_selection()

    def activate_selection(self) -> None:
        ids = self._selection_ids()
        if not ids:
            return
        if self._selected_game not in ids:
            self._selected_game = ids[0]
        self._play(self._selected_game)

    def keyPressEvent(self, event) -> None:
        keys = {Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down",
                Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right"}
        if event.key() in keys:
            self.move_selection(keys[event.key()])
            event.accept()
        elif event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            self.activate_selection()
            event.accept()
        else:
            super().keyPressEvent(event)

    def _searching(self) -> bool:
        if self.search.text().strip():
            return True
        if self.favorites.isChecked():
            return True
        chosen = self.tag_box.currentText()
        return bool(chosen and chosen != "All tags")

    def _visible_games(self) -> list[Game]:
        text = self.search.text().strip().lower()
        games = self._ordered(list(self.library.games))
        if not self.show_hidden:
            games = [game for game in games if not game.hidden]
        if self.favorites.isChecked():
            games = [game for game in games if game.favorite]
        chosen = self.tag_box.currentText()
        if chosen and chosen != "All tags":
            games = [game for game in games if chosen in game.tags]
        if text:
            games = [
                game
                for game in games
                if text in game.title.lower() or text in game.system.lower() or text in " ".join(game.tags).lower()
            ]
        return games

    def _fill_recent(self) -> None:
        while self.recent_layout.count():
            item = self.recent_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        recent = [game for game in self.library.games if game.last_played > 0 and (self.show_hidden or not game.hidden)]
        recent.sort(key=lambda game: game.last_played, reverse=True)
        if not recent:
            self.recent_row.hide()
            return
        self.recent_row.show()
        for game in recent[:8]:
            button = _button(game.title)
            button.setObjectName("RecentGame")
            button.clicked.connect(lambda _checked=False, game_id=game.id: self._play(game_id))
            self.recent_layout.addWidget(button)
        self.recent_layout.addStretch(1)

    def _fill_list(self, games: list[Game]) -> None:
        self.list.model().blockSignals(True)
        self.list.clear()
        for game in games:
            played = format_played(game.played)
            bits = [game.title, game.system]
            if game.launches:
                bits.append(f"{game.launches} plays")
            if played:
                bits.append(played)
            item = QListWidgetItem(" · ".join(bits))
            item.setData(Qt.ItemDataRole.UserRole, game.id)
            self.list.addItem(item)
        self.list.model().blockSignals(False)

    def _play_item(self, item: QListWidgetItem) -> None:
        game_id = item.data(Qt.ItemDataRole.UserRole)
        if game_id:
            self._play(str(game_id))

    def _rows_moved(self, *_args) -> None:
        ids = []
        for index in range(self.list.count()):
            item = self.list.item(index)
            game_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else ""
            if game_id:
                ids.append(str(game_id))
        self.library.set_order(ids)
        self.sort.blockSignals(True)
        self.sort.setCurrentText("Custom")
        self.sort.blockSignals(False)

    def _toggle_list(self, on: bool) -> None:
        self.list_mode = bool(on)
        self.refresh()
        self._changed()

    def _toggle_hidden(self, on: bool) -> None:
        self.show_hidden = bool(on)
        self.refresh()
        self._changed()

    def _resize_cards(self, value: int) -> None:
        self.card_scale = max(70, min(140, int(value)))
        self.refresh()
        self._changed()

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change()

    def _show_recent(self) -> None:
        menu = QMenu(self)
        menu.setObjectName("RecentMenu")
        recent = [game for game in self.library.games if game.last_played > 0]
        recent.sort(key=lambda game: game.last_played, reverse=True)
        if not recent:
            action = menu.addAction("No games yet")
            action.setEnabled(False)
        for game in recent[:10]:
            menu.addAction(game.title, lambda game_id=game.id: self._play(game_id))
        menu.popup(self.recent_btn.mapToGlobal(self.recent_btn.rect().bottomLeft()))

    def _ordered(self, games: list[Game]) -> list[Game]:
        mode = self.sort.currentText()
        if mode == "Name":
            return sorted(games, key=lambda game: game.title.lower())
        if mode == "System":
            return sorted(games, key=lambda game: (game.system.lower(), game.title.lower()))
        if mode == "Play time":
            return sorted(games, key=lambda game: game.played, reverse=True)
        if mode == "Custom":
            rank = {game_id: index for index, game_id in enumerate(self.library.order)}
            return sorted(games, key=lambda game: rank.get(game.id, 10**6))
        return games

    def _fill_tags(self) -> None:
        tags = sorted({tag for game in self.library.games for tag in game.tags})
        labels = ["All tags", *tags]
        current = [self.tag_box.itemText(index) for index in range(self.tag_box.count())]
        if current == labels:
            return
        chosen = self.tag_box.currentText()
        self.tag_box.blockSignals(True)
        self.tag_box.clear()
        self.tag_box.addItems(labels)
        index = self.tag_box.findText(chosen)
        self.tag_box.setCurrentIndex(index if index >= 0 else 0)
        self.tag_box.blockSignals(False)

    def apply_theme(self, name: str) -> None:
        replacements = {
            "night": {
                "#0f1115": "#0b1020", "#151922": "#12182a",
                "#e6e6e6": "#e7edff", "#10141d": "#090d17",
                "#1b2030": "#182033", "#252d3d": "#2a3550",
                "#212739": "#22304a", "#2a2147": "#1c2f56",
                "#a78bfa": "#72a7ff", "#c4b5fd": "#93bbff",
                "#9aa4b2": "#9aa8c7",
            },
            "contrast": {
                "#0f1115": "#000000", "#151922": "#000000",
                "#e6e6e6": "#ffffff", "#10141d": "#000000",
                "#1b2030": "#000000", "#252d3d": "#ffff00",
                "#212739": "#111111", "#2a2147": "#111111",
                "#a78bfa": "#ffff00", "#c4b5fd": "#ffffff",
                "#9aa4b2": "#ffff00",
            },
        }.get(name, {})
        # Replace tokens in one pass so substituted colors aren't replaced again.
        import re
        sheet = re.sub(r"#[0-9a-fA-F]{6}", lambda m: replacements.get(m.group(), m.group()), _STYLE)
        self.setStyleSheet(sheet)

    def _toggle_favorite(self, game_id: str) -> None:
        game = self.library.get(game_id)
        if game is None:
            return
        self.library.set_favorite(game_id, not game.favorite)
        QTimer.singleShot(0, self.refresh)


class GameSettings(QDialog):
    """Cover image and cheats for one cartridge."""

    def __init__(self, library: Library, game: Game, parent=None):
        super().__init__(parent)
        self.library = library
        self.game = game
        self.library.use_cheat_file(self.game)
        self.game = self.library.get(self.game.id) or self.game
        self.setObjectName("GameSettings")
        self.setWindowTitle(game.title)
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setStyleSheet(_STYLE)
        self._rows: list[tuple[QLineEdit, QLineEdit, QComboBox, QCheckBox]] = []

        root = QVBoxLayout(self)
        root.setSpacing(12)
        heading = QLabel(game.title)
        heading.setStyleSheet("font-size: 18px;")
        system = QLabel(game.system)
        system.setObjectName("Hint")
        root.addWidget(heading)
        root.addWidget(system)
        self.tags_edit = QLineEdit(", ".join(game.tags))
        self.tags_edit.setObjectName("GameTags")
        self.tags_edit.setPlaceholderText("Tags, such as to finish, with Alex")
        self.tags_edit.editingFinished.connect(self._save_tags)
        root.addWidget(self.tags_edit)
        self.hide_box = QCheckBox("Hide from the shelf")
        self.hide_box.setObjectName("HideGame")
        self.hide_box.setChecked(game.hidden)
        self.hide_box.toggled.connect(lambda on: self.library.set_hidden(self.game.id, on))
        root.addWidget(self.hide_box)

        self.preview = QLabel("No image")
        self.preview.setObjectName("Cover")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedSize(158, 176)
        picture_row = QHBoxLayout()
        picture_row.addWidget(self.preview)
        picture_buttons = QVBoxLayout()
        choose = _button("Choose image")
        choose.setObjectName("ChooseImage")
        choose.clicked.connect(self._choose_image)
        clear = _button("Remove image")
        clear.clicked.connect(self._clear_image)
        picture_buttons.addWidget(choose)
        picture_buttons.addWidget(clear)
        picture_buttons.addStretch(1)
        picture_row.addLayout(picture_buttons)
        picture_row.addStretch(1)
        root.addLayout(picture_row)
        self._load_preview()

        cheats_title = QLabel("Cheats")
        cheats_title.setStyleSheet("font-size: 16px;")
        root.addWidget(cheats_title)
        hint = QLabel(
            "Paste a code and Auto names it Game Genie, GameShark, Codebreaker, "
            "or Action Replay. Pick a type when you want to choose it yourself. "
            f"The list is saved as {self.library.cheat_path(self.game).name}, and the game reads that file."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        search = _button("Search RAM")
        search.setObjectName("SearchRam")
        search.clicked.connect(lambda: self.done(2))
        import_codes = _button("Import cheats")
        import_codes.setObjectName("ImportCheats")
        import_codes.clicked.connect(self._import_cheats)
        cheat_buttons = QHBoxLayout()
        cheat_buttons.addWidget(search)
        cheat_buttons.addWidget(import_codes)
        cheat_buttons.addStretch(1)
        root.addLayout(cheat_buttons)
        self.patch_label = QLabel(self._patch_text())
        self.patch_label.setObjectName("PatchLabel")
        patch_row = QHBoxLayout()
        choose_patch = _button("Choose patch")
        choose_patch.setObjectName("ChoosePatch")
        choose_patch.clicked.connect(self._choose_patch)
        clear_patch = _button("Remove patch")
        clear_patch.clicked.connect(self._clear_patch)
        patch_row.addWidget(self.patch_label, 1)
        patch_row.addWidget(choose_patch)
        patch_row.addWidget(clear_patch)
        root.addLayout(patch_row)

        self.cheat_box = QVBoxLayout()
        root.addLayout(self.cheat_box)
        self._rebuild_cheats()

        add_row = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Name")
        self.code_edit = QLineEdit()
        self.code_edit.setObjectName("CheatCode")
        self.code_edit.setPlaceholderText("Paste a code")
        self.kind_combo = _kind_combo("auto")
        self.kind_combo.setObjectName("CheatKind")
        self.detected = QLabel("—")
        self.detected.setObjectName("DetectedKind")
        self.code_edit.textChanged.connect(self._refresh_detected)
        self.kind_combo.currentIndexChanged.connect(self._refresh_detected)
        add = _button("Add")
        add.setObjectName("AddCheat")
        add.clicked.connect(self._add)
        add_row.addWidget(self.name_edit, 1)
        add_row.addWidget(self.code_edit, 2)
        add_row.addWidget(self.kind_combo)
        add_row.addWidget(self.detected)
        add_row.addWidget(add)
        root.addLayout(add_row)

        remove = _button("Remove from library")
        remove.clicked.connect(self._remove_game)
        done = _button("Done")
        done.clicked.connect(self.accept)
        root.addWidget(remove, alignment=Qt.AlignmentFlag.AlignLeft)
        root.addWidget(done, alignment=Qt.AlignmentFlag.AlignRight)

    def _save_tags(self) -> None:
        tags = [part.strip() for part in self.tags_edit.text().split(",")]
        self.library.set_tags(self.game.id, tags)
        self.game = self.library.get(self.game.id) or self.game

    def _load_preview(self) -> None:
        cover = self.library.cover_file(self.game)
        if cover is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("No image")
            return
        pixmap = QPixmap(str(cover))
        if pixmap.isNull():
            self.preview.setText("No image")
            return
        self.preview.setText("")
        self.preview.setPixmap(
            pixmap.scaled(
                158,
                176,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Cartridge image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
        )
        if not path:
            return
        self.library.set_image(self.game.id, Path(path))
        self.game = self.library.get(self.game.id) or self.game
        self._load_preview()

    def _clear_image(self) -> None:
        self.library.clear_image(self.game.id)
        self.game = self.library.get(self.game.id) or self.game
        self._load_preview()

    def _rebuild_cheats(self) -> None:
        while self.cheat_box.count():
            item = self.cheat_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self._rows.clear()
        for index, cheat in enumerate(self.game.cheats):
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            enabled = QCheckBox()
            enabled.setChecked(cheat.enabled)
            name = QLineEdit(cheat.name)
            name.setPlaceholderText("Name")
            code = QLineEdit(cheat.code)
            kind = _kind_combo(cheat.kind)
            remove = _button("×")
            remove.setFixedWidth(36)
            layout.addWidget(enabled)
            layout.addWidget(name, 1)
            layout.addWidget(code, 2)
            layout.addWidget(kind)
            layout.addWidget(remove)
            self.cheat_box.addWidget(row)
            self._rows.append((name, code, kind, enabled))
            enabled.toggled.connect(lambda checked, i=index: self._store(i, enabled=checked))
            name.editingFinished.connect(lambda i=index: self._store(i, name=self._rows[i][0].text()))
            code.editingFinished.connect(lambda i=index: self._store(i, code=self._rows[i][1].text()))
            kind.currentIndexChanged.connect(
                lambda _n, i=index: self._store(i, kind=self._rows[i][2].currentData())
            )
            remove.clicked.connect(lambda _checked=False, i=index: self._remove_cheat(i))

    def _store(self, index: int, **fields) -> None:
        self.library.update_cheat(self.game.id, index, **fields)
        self.game = self.library.get(self.game.id) or self.game

    def _remove_cheat(self, index: int) -> None:
        self.library.remove_cheat(self.game.id, index)
        self.game = self.library.get(self.game.id) or self.game
        self._rebuild_cheats()

    def _refresh_detected(self) -> None:
        kind = self.kind_combo.currentData() or "auto"
        if not self.code_edit.text().strip():
            self.detected.setText("—")
            return
        self.detected.setText(describe(self.code_edit.text(), kind))

    def _patch_text(self) -> str:
        if self.game.patch_name:
            return f"Patch: {self.game.patch_name}"
        return "No patch"

    def _import_cheats(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Cheat list",
            "",
            "Cheat lists (*.cht *.txt)",
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        self.import_text(text)

    def import_text(self, text: str) -> int:
        rows = parse_cheat_file(text)
        added = self.library.add_cheats(self.game.id, rows)
        self.game = self.library.get(self.game.id) or self.game
        self._rebuild_cheats()
        return added

    def _choose_patch(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "IPS or BPS patch",
            "",
            "Patches (*.ips *.bps)",
        )
        if not path:
            return
        self.library.set_patch(self.game.id, Path(path))
        self.game = self.library.get(self.game.id) or self.game
        self.patch_label.setText(self._patch_text())

    def _clear_patch(self) -> None:
        self.library.clear_patch(self.game.id)
        self.game = self.library.get(self.game.id) or self.game
        self.patch_label.setText(self._patch_text())

    def _add(self) -> None:
        cheat = self.library.add_cheat(
            self.game.id,
            self.code_edit.text(),
            self.name_edit.text(),
            self.kind_combo.currentData() or "auto",
        )
        if cheat is None:
            return
        self.game = self.library.get(self.game.id) or self.game
        self.code_edit.clear()
        self.name_edit.clear()
        self.kind_combo.setCurrentIndex(0)
        self._refresh_detected()
        self._rebuild_cheats()

    def _remove_game(self) -> None:
        self.library.remove(self.game.id)
        self.done(1)


class CheatSearchDialog(QDialog):
    """Watch RAM, then keep only the addresses that moved the way you saw."""

    def __init__(self, read_ram, add_code, parent=None):
        super().__init__(parent)
        self.read_ram = read_ram
        self.add_code = add_code
        self.search = RamSearch()
        self.setObjectName("CheatSearch")
        self.setWindowTitle("Cheat search")
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumWidth(420)
        self.setStyleSheet(_STYLE)
        root = QVBoxLayout(self)
        hint = QLabel(
            "Start a search, change something in the game, then narrow. "
            "Increased, decreased, changed, unchanged, or equal to a number."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        start = _button("Start search")
        start.setObjectName("StartSearch")
        start.clicked.connect(self._start)
        root.addWidget(start)
        row = QHBoxLayout()
        self.op = QComboBox()
        self.op.setObjectName("SearchOp")
        self.op.addItems(["Increased", "Decreased", "Changed", "Unchanged", "Equal to"])
        self.value = QLineEdit()
        self.value.setObjectName("SearchValue")
        self.value.setPlaceholderText("Number")
        self.value.setFixedWidth(80)
        narrow = _button("Narrow")
        narrow.setObjectName("NarrowSearch")
        narrow.clicked.connect(self._narrow)
        row.addWidget(self.op, 1)
        row.addWidget(self.value)
        row.addWidget(narrow)
        root.addLayout(row)
        self.count = QLabel("Not started.")
        self.count.setObjectName("SearchCount")
        root.addWidget(self.count)
        self.hits = QVBoxLayout()
        holder = QWidget()
        holder.setLayout(self.hits)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        scroll.setMinimumHeight(180)
        root.addWidget(scroll, 1)

    def _start(self) -> None:
        memory = self.read_ram() or {}
        if not memory:
            self.count.setText("No RAM to search. Start a game first.")
            return
        self.search.start(memory)
        self.count.setText(f"Watching {len(self.search.hits)} addresses. Change the game, then narrow.")
        self._show_hits()

    def _narrow(self) -> None:
        if not self.search.started:
            self.count.setText("Start a search first.")
            return
        op = {
            "Increased": "increased",
            "Decreased": "decreased",
            "Changed": "changed",
            "Unchanged": "unchanged",
            "Equal to": "equal",
        }.get(self.op.currentText(), "changed")
        value = None
        if op == "equal":
            text = self.value.text().strip()
            if not text.isdigit():
                self.count.setText("Type the number to match.")
                return
            value = int(text)
        memory = self.read_ram() or {}
        self.search.narrow(op, memory, value)
        self.count.setText(f"{len(self.search.hits)} addresses left.")
        self._show_hits()

    def _show_hits(self) -> None:
        while self.hits.count():
            item = self.hits.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        shown = list(self.search.hits.items())[:40]
        for addr, value in shown:
            label = f"{addr:04X} = {value:02X}" if addr <= 0xFFFF else f"{addr:08X} = {value:02X}"
            button = _button(label)
            button.clicked.connect(lambda _checked=False, a=addr, v=value: self._add(a, v, button))
            self.hits.addWidget(button)
        if len(self.search.hits) > 40:
            extra = QLabel(f"Showing 40 of {len(self.search.hits)}.")
            extra.setObjectName("Hint")
            self.hits.addWidget(extra)

    def _add(self, addr: int, value: int, button: QPushButton) -> None:
        self.add_code(addr, value)
        button.setText(button.text() + "  added")
