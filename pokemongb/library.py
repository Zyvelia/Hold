"""Games this window has opened, with a cover and the cheats for each one."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from pokemongb.cheats import read_cheat_entries, write_cheat_file

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


@dataclass
class Cheat:
    code: str
    name: str = ""
    enabled: bool = True
    kind: str = "auto"

    def to_json(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "enabled": self.enabled,
            "kind": self.kind,
        }

    @classmethod
    def from_json(cls, raw: dict) -> "Cheat":
        return cls(
            code=str(raw.get("code", "")),
            name=str(raw.get("name", "")),
            enabled=bool(raw.get("enabled", True)),
            kind=str(raw.get("kind", "auto")) or "auto",
        )


@dataclass
class Game:
    id: str
    path: str
    title: str
    system: str
    system_id: str
    image: str = ""
    favorite: bool = False
    played: float = 0.0
    last_played: float = 0.0
    launches: int = 0
    hidden: bool = False
    patch: str = ""
    patch_name: str = ""
    tags: list[str] = field(default_factory=list)
    cheats: list[Cheat] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "path": self.path,
            "title": self.title,
            "system": self.system,
            "system_id": self.system_id,
            "image": self.image,
            "favorite": self.favorite,
            "played": self.played,
            "last_played": self.last_played,
            "launches": self.launches,
            "hidden": self.hidden,
            "patch": self.patch,
            "patch_name": self.patch_name,
            "tags": list(self.tags),
            "cheats": [cheat.to_json() for cheat in self.cheats],
        }

    @classmethod
    def from_json(cls, raw: dict) -> "Game":
        cheats = [Cheat.from_json(item) for item in raw.get("cheats", []) if isinstance(item, dict)]
        return cls(
            id=str(raw.get("id", "")),
            path=str(raw.get("path", "")),
            title=str(raw.get("title", "")) or "ROM",
            system=str(raw.get("system", "")) or "ROM",
            system_id=str(raw.get("system_id", "")),
            image=str(raw.get("image", "")),
            favorite=bool(raw.get("favorite", False)),
            played=float(raw.get("played", 0) or 0),
            last_played=float(raw.get("last_played", 0) or 0),
            launches=int(raw.get("launches", 0) or 0),
            hidden=bool(raw.get("hidden", False)),
            patch=str(raw.get("patch", "")),
            patch_name=str(raw.get("patch_name", "")),
            tags=[str(item) for item in raw.get("tags", []) if str(item).strip()],
            cheats=cheats,
        )


def format_last_played(stamp: float) -> str:
    if stamp <= 0:
        return ""
    return time.strftime("%b %d", time.localtime(stamp))


def format_played(seconds: float) -> str:
    """A short play-time label. Empty when the game has not been played."""
    total = max(0, int(seconds))
    if total <= 0:
        return ""
    if total < 60:
        return f"{total}s"
    minutes = total // 60
    if minutes < 60:
        return f"{minutes}m"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins:02d}m"


def game_id(path: Path) -> str:
    try:
        key = str(path.resolve())
    except OSError:
        key = str(Path(path).absolute())
    return hashlib.blake2s(key.lower().encode(), digest_size=8).hexdigest()


class Library:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.covers = self.folder / "covers"
        self.patches = self.folder / "patches"
        self.cheat_dir = self.folder / "cheats"
        self._cht_stamp: dict[str, bytes] = {}
        self.path = self.folder / "library.json"
        self.games: list[Game] = []
        self.order: list[str] = []
        self._load()

    def remember(self, path: Path, title: str, system: str, system_id: str) -> Game:
        path = Path(path)
        found = self.by_path(path)
        if found is None:
            found = Game(
                id=game_id(path),
                path=str(path),
                title=title or path.stem,
                system=system or "ROM",
                system_id=system_id,
            )
            self.games.insert(0, found)
        else:
            found.title = title or found.title
            found.system = system or found.system
            found.system_id = system_id or found.system_id
            found.path = str(path)
            self.games.remove(found)
            self.games.insert(0, found)
        found.launches += 1
        self._save()
        return found

    def get(self, game_id_: str) -> Game | None:
        for game in self.games:
            if game.id == game_id_:
                return game
        return None

    def by_path(self, path: Path) -> Game | None:
        key = game_id(path)
        return self.get(key)

    def set_tags(self, game_id_: str, tags: list[str]) -> None:
        game = self.get(game_id_)
        if game is None:
            return
        game.tags = [item.strip() for item in tags if item.strip()]
        self._save()

    def mark_played(self, game_id_: str) -> None:
        game = self.get(game_id_)
        if game is None:
            return
        game.last_played = time.time()
        self._save()

    def add_play(self, game_id_: str, seconds: float) -> None:
        game = self.get(game_id_)
        if game is None or seconds <= 0:
            return
        game.played += float(seconds)
        self._save()

    def set_hidden(self, game_id_: str, hidden: bool) -> None:
        game = self.get(game_id_)
        if game is None:
            return
        game.hidden = bool(hidden)
        self._save()

    def set_order(self, game_ids: list[str]) -> None:
        self.order = [item for item in game_ids if self.get(item) is not None]
        self._save()

    def set_favorite(self, game_id_: str, favorite: bool) -> None:
        game = self.get(game_id_)
        if game is None:
            return
        game.favorite = bool(favorite)
        self._save()

    def remove(self, game_id_: str) -> None:
        game = self.get(game_id_)
        if game is None:
            return
        self.clear_image(game_id_)
        self.clear_patch(game_id_)
        cheat_path = self.cheat_dir / f"{game.id}.cht"
        if cheat_path.is_file():
            cheat_path.unlink()
        self._cht_stamp.pop(game.id, None)
        self.games = [item for item in self.games if item.id != game_id_]
        self._save()

    def set_image(self, game_id_: str, source: Path) -> Path | None:
        game = self.get(game_id_)
        source = Path(source)
        if game is None or not source.is_file():
            return None
        if source.suffix.lower() not in _IMAGE_SUFFIXES:
            return None
        self.covers.mkdir(parents=True, exist_ok=True)
        dest = self.covers / f"{game.id}{source.suffix.lower()}"
        if source.resolve() != dest.resolve():
            shutil.copyfile(source, dest)
        self.clear_image(game_id_, keep=dest.name)
        game.image = dest.name
        self._save()
        return dest

    def clear_image(self, game_id_: str, keep: str = "") -> None:
        game = self.get(game_id_)
        if game is None:
            return
        if game.image and game.image != keep:
            leftover = self.covers / game.image
            if leftover.is_file():
                leftover.unlink()
        if not keep:
            game.image = ""
            self._save()

    def cover_file(self, game: Game) -> Path | None:
        if not game.image:
            return None
        path = self.covers / game.image
        return path if path.is_file() else None

    def add_cheats(self, game_id_: str, rows: list[tuple[str, str, bool]]) -> int:
        game = self.get(game_id_)
        if game is None:
            return 0
        added = 0
        for name, code, enabled in rows:
            text = code.strip()
            if not text:
                continue
            game.cheats.append(Cheat(code=text, name=name.strip(), enabled=bool(enabled), kind="auto"))
            added += 1
        if added:
            self._write_cheat_file(game)
        return added

    def set_patch(self, game_id_: str, source: Path) -> Path | None:
        game = self.get(game_id_)
        source = Path(source)
        if game is None or not source.is_file() or source.suffix.lower() not in {".ips", ".bps"}:
            return None
        self.patches.mkdir(parents=True, exist_ok=True)
        dest = self.patches / f"{game.id}{source.suffix.lower()}"
        self.clear_patch(game_id_, keep=dest.name)
        if source.resolve() != dest.resolve():
            shutil.copyfile(source, dest)
        game.patch = dest.name
        game.patch_name = source.name
        self._save()
        return dest

    def clear_patch(self, game_id_: str, keep: str = "") -> None:
        game = self.get(game_id_)
        if game is None:
            return
        if game.patch and game.patch != keep:
            leftover = self.patches / game.patch
            if leftover.is_file():
                leftover.unlink()
        if not keep:
            game.patch = ""
            game.patch_name = ""
            self._save()

    def patch_file(self, game: Game | None) -> Path | None:
        if game is None or not game.patch:
            return None
        path = self.patches / game.patch
        return path if path.is_file() else None

    def add_cheat(self, game_id_: str, code: str, name: str = "", kind: str = "auto") -> Cheat | None:
        game = self.get(game_id_)
        text = code.strip()
        if game is None or not text:
            return None
        cheat = Cheat(code=text, name=name.strip(), enabled=True, kind=kind or "auto")
        game.cheats.append(cheat)
        self._write_cheat_file(game)
        return cheat

    def update_cheat(self, game_id_: str, index: int, **fields) -> None:
        game = self.get(game_id_)
        if game is None or index < 0 or index >= len(game.cheats):
            return
        cheat = game.cheats[index]
        if "code" in fields:
            cheat.code = str(fields["code"]).strip()
        if "name" in fields:
            cheat.name = str(fields["name"]).strip()
        if "enabled" in fields:
            cheat.enabled = bool(fields["enabled"])
        if "kind" in fields:
            cheat.kind = str(fields["kind"]) or "auto"
        self._write_cheat_file(game)

    def remove_cheat(self, game_id_: str, index: int) -> None:
        game = self.get(game_id_)
        if game is None or index < 0 or index >= len(game.cheats):
            return
        del game.cheats[index]
        self._write_cheat_file(game)

    def cheat_path(self, game: Game) -> Path:
        return self.cheat_dir / f"{game.id}.cht"

    def use_cheat_file(self, game: Game | None) -> None:
        """Make the cheat file the list the game runs."""
        if game is None:
            return
        path = self.cheat_path(game)
        if not path.is_file():
            if game.cheats:
                self._write_cheat_file(game)
            return
        try:
            raw = path.read_bytes()
        except OSError:
            return
        digest = hashlib.blake2s(raw, digest_size=8).digest()
        if self._cht_stamp.get(game.id) == digest:
            return
        game.cheats = [
            Cheat(code=code, name=name, enabled=enabled, kind=kind or "auto")
            for name, code, enabled, kind in read_cheat_entries(raw.decode("utf-8", "replace"))
        ]
        self._cht_stamp[game.id] = digest
        self._save()

    def _write_cheat_file(self, game: Game) -> None:
        self.cheat_dir.mkdir(parents=True, exist_ok=True)
        path = self.cheat_path(game)
        rows = [(cheat.name, cheat.code, cheat.enabled, cheat.kind) for cheat in game.cheats]
        raw = write_cheat_file(rows).encode("utf-8")
        path.write_bytes(raw)
        self._cht_stamp[game.id] = hashlib.blake2s(raw, digest_size=8).digest()
        self._save()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        games = []
        for item in raw.get("games", []):
            if isinstance(item, dict) and item.get("id") and item.get("path"):
                games.append(Game.from_json(item))
        self.games = games
        self.order = [item for item in raw.get("order", []) if isinstance(item, str)]

    def _save(self) -> None:
        payload = {"games": [game.to_json() for game in self.games], "order": list(self.order)}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
