import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from pokemongb.core_install import (
    POKEMON_DOWNLOADS, POKEMON_PLATFORMS, dolphin_assets_present, install_core, install_dolphin_assets,
)
from pokemongb.library import Library
from pokemongb.page import PokemonGBPage
from pokemongb.systems import BY_ID, bios_dir, cores_dir, locate, locate_as


def core_archive(name):
    dll = bytearray(88)
    dll[:2] = b"MZ"
    dll[60:64] = (64).to_bytes(4, "little")
    dll[64:70] = b"PE\0\0\x64\x86"
    dll[86:88] = (0x2000).to_bytes(2, "little")
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(name, bytes(dll))
        archive.writestr("../ignored.txt", b"ignored")
    return io.BytesIO(data.getvalue()), bytes(dll)


class OptionalConsoleTests(unittest.TestCase):
    def test_unique_extensions_and_explicit_shared_extensions(self):
        formats = (("game.col", "coleco"), ("game.cv", "coleco"), ("game.int", "intv"),
                   ("game.mgw", "gamewatch"))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, console in formats:
                path = root / name
                path.write_bytes(bytes(32))
                self.assertEqual(locate(path, root / "cache"), (path, BY_ID[console]))
            disc = root / "disc.chd"
            disc.write_bytes(bytes(32))
            self.assertEqual(locate(disc, root / "cache")[1].id, "ps1")
            for console in ("3do", "neocd", "pcfx"):
                self.assertEqual(locate_as(disc, root / "cache", BY_ID[console]), disc)
            with self.assertRaises(ValueError):
                locate_as(disc, root / "cache", BY_ID["intv"])

    def test_archive_extracts_only_the_selected_game(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "game.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../nested/game.bin", bytes(32))
                archive.writestr("readme.txt", b"notes")
            game = locate_as(path, root / "cache", BY_ID["odyssey2"])
            self.assertEqual(game, root / "cache" / "game.bin")
            self.assertEqual(game.read_bytes(), bytes(32))
        self.assertEqual(bios_dir("ng-lo.rom"), cores_dir() / "system" / "neocd")

    def test_install_uses_expected_dll_and_leaves_existing_files(self):
        system = BY_ID["coleco"]
        response, expected = core_archive(system.dll)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch("pokemongb.core_install.can_install_windows_core", return_value=True):
                with patch("pokemongb.core_install.urllib.request.urlopen", return_value=response) as request:
                    target = install_core(system.dll, root)
                    self.assertEqual(target.read_bytes(), expected)
                    self.assertEqual(set(root.iterdir()), {target})
                    self.assertEqual(install_core(system.dll, root), target)
                self.assertEqual(request.call_count, 1)
                self.assertTrue(request.call_args.args[0].startswith("https://buildbot.libretro.com/"))

    def test_pokemon_platforms_and_shared_game_formats(self):
        self.assertIsNone(POKEMON_PLATFORMS[0].core)
        self.assertIn("dolphin_libretro.dll", POKEMON_DOWNLOADS)
        self.assertNotIn("suyu_libretro.dll", POKEMON_DOWNLOADS)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            wii = root / "wii.rvz"
            wii.write_bytes(bytes(32))
            self.assertEqual(locate_as(wii, root, BY_ID["wii"]), wii)
            title = root / "title.tmd"
            title.write_bytes(bytes(32))
            self.assertEqual(locate_as(title, root, BY_ID["wiiu"]), title)

    def test_dolphin_install_keeps_user_settings_and_license(self):
        response = io.BytesIO()
        with zipfile.ZipFile(response, "w") as archive:
            archive.writestr("dolphin-emu/Sys/codehandler.bin", b"handler")
            archive.writestr("dolphin-emu/Sys/GameSettings/GAME.ini", b"defaults")
            archive.writestr("dolphin-emu/license.txt", b"license")
        response.seek(0)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dest = root / "system" / "dolphin-emu"
            settings = dest / "Sys" / "GameSettings" / "GAME.ini"
            settings.parent.mkdir(parents=True)
            settings.write_bytes(b"custom")
            with patch("pokemongb.core_install.urllib.request.urlopen", return_value=response) as request:
                install_dolphin_assets(root)
                self.assertTrue(dolphin_assets_present(root))
                self.assertEqual(settings.read_bytes(), b"custom")
                self.assertEqual((dest / "license.txt").read_bytes(), b"license")
                install_dolphin_assets(root)
            self.assertEqual(request.call_count, 1)

    def test_console_installer_button_reports_completion(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with (
                patch("pokemongb.page._saves_dir", return_value=root),
                patch("pokemongb.page.cores_dir", return_value=root / "cores"),
                patch("pokemongb.page.can_install_windows_core", return_value=True),
                patch("pokemongb.page.QInputDialog.getItem", return_value=("ColecoVision", True)),
                patch("pokemongb.page.install_core") as install,
            ):
                page = PokemonGBPage()
                try:
                    page.core_btn.click()
                    install.assert_called_once_with(BY_ID["coleco"].dll)
                    self.assertIn("ColecoVision core installed", page.status.text())
                finally:
                    page.close()

    def test_open_as_choice_is_remembered_and_used_even_for_chd(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            disc = root / "disc.chd"
            disc.write_bytes(bytes(32))
            with patch("pokemongb.page._saves_dir", return_value=root):
                page = PokemonGBPage()
                try:
                    entry = page.library.remember(disc, "Disc", "PlayStation", "ps1")
                    page.library.set_favorite(entry.id, True)
                    with (
                        patch("pokemongb.page.QInputDialog.getItem", return_value=("Neo Geo CD", True)),
                        patch("pokemongb.page.QFileDialog.getOpenFileNames", return_value=([str(disc)], "")),
                        patch.object(page, "_load_system") as load,
                    ):
                        page._open_as_console()
                        page._play_game(entry.id)
                        self.assertEqual(load.call_count, 2)
                        self.assertTrue(all(call.args[:2] == (disc, BY_ID["neocd"]) for call in load.call_args_list))
                    record = Library(root).get(entry.id)
                    self.assertEqual(record.system_id, "neocd")
                    self.assertTrue(record.favorite)
                finally:
                    page.close()
