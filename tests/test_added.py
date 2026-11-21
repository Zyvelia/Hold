import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from pokemongb.library import Library
from pokemongb.sony import sony_rumble_report
from pokemongb.systems import locate
from pokemongb.netplay import Beacon, Link, Relay, discover, pack_beacon, pack_input, parse_beacon, unpack_input
from pokemongb.page import PokemonGBPage
from pokemongb.shelf import Shelf


def _rom(name: bytes = b"ADDED") -> bytes:
    rom = bytearray(0x8000)
    rom[0x100] = 0x18
    rom[0x101] = 0xFE
    rom[0x134:0x134 + len(name)] = name
    return bytes(rom)


class AddedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_password_chat_ping_and_relay(self):
        host = Link()
        guest = Link()
        host.password = "secret"
        guest.password = "secret"
        host.set_game(b"samegame", "nes")
        guest.set_game(b"samegame", "nes")
        port = host.host(0)
        guest.join("127.0.0.1", port)
        self.assertTrue(guest.ready, guest.error)
        guest.send_chat("hello")
        guest.ping()
        seen = []
        for _ in range(40):
            seen.extend(host.take_chat())
            if seen:
                break
            time.sleep(0.02)
        self.assertEqual(seen, ["hello"])
        time.sleep(0.05)
        self.assertGreaterEqual(guest.ping_ms, 0)
        host.send_sync(1, b"abcdefgh")
        time.sleep(0.1)
        self.assertEqual(guest.take_sync(), [(1, b"abcdefgh")])
        host.close()
        guest.close()

        blocked = Link()
        blocked.password = "nope"
        blocked.set_game(b"samegame", "nes")
        host = Link()
        host.password = "secret"
        host.set_game(b"samegame", "nes")
        port = host.host(0)
        blocked.join("127.0.0.1", port)
        self.assertIn("password", blocked.error)
        host.close()
        blocked.close()

        relay = Relay()
        port = relay.start(0)
        left = Link()
        right = Link()
        left.set_game(b"samegame", "nes")
        right.set_game(b"samegame", "nes")
        threads = [
            threading.Thread(target=left.join, args=("127.0.0.1", port), kwargs={"relay": True}),
            threading.Thread(target=right.join, args=("127.0.0.1", port), kwargs={"relay": True}),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(3)
        self.assertTrue(left.ready, left.error)
        self.assertTrue(right.ready, right.error)
        self.assertEqual(sorted([left.role, right.role]), ["guest", "host"])
        found = {}

        def trade(link, bits, key):
            found[key] = unpack_input(link.exchange(pack_input(bits, (0, 0, 0, 0), 0, False)))

        traders = [
            threading.Thread(target=trade, args=(left, 1, "left")),
            threading.Thread(target=trade, args=(right, 2, "right")),
        ]
        for thread in traders:
            thread.start()
        for thread in traders:
            thread.join(2)
        self.assertEqual(found["left"][0], 2)
        self.assertEqual(found["right"][0], 1)
        left.close()
        right.close()
        relay.close()

    def test_lobby_beacon(self):
        parsed = parse_beacon(pack_beacon(5555, "Blue", True, False))
        self.assertEqual(parsed["title"], "Blue")
        self.assertTrue(parsed["password"])
        beacon = Beacon()
        beacon.start(4242, "Blue", True, False)
        try:
            found = discover(0.8)
        finally:
            beacon.stop()
        self.assertTrue(any(item["title"] == "Blue" and item["port"] == 4242 for item in found))

    def test_picture_tools_autosave_and_shelf(self):
        with tempfile.TemporaryDirectory() as folder:
            os.environ["POKEMONGB_SETTINGS"] = str(Path(folder) / "settings.json")
            os.environ["POKEMONGB_LIBRARY"] = str(Path(folder) / "library")
            os.environ["POKEMONGB_CONTROLS"] = str(Path(folder) / "controls.json")
            page = PokemonGBPage()
            try:
                page.volume.setValue(40)
                page._toggle_mute()
                self.assertEqual(page.volume.value(), 0)
                self.assertEqual(page.mute_btn.text(), "Unmute")
                page._toggle_mute()
                self.assertEqual(page.volume.value(), 40)
                page.load_bytes(_rom(b"AUTOSAVE99"))
                page._tick()
                before = page.screen.pixmap().size()
                page._rotate = 90
                page._present()
                turned = page.screen.pixmap().size()
                self.assertEqual(turned.width(), before.height())
                self.assertEqual(turned.height(), before.width())
                page._rotate = 0
                page._crop = 10
                page._present()
                cropped = page.screen.pixmap().size()
                self.assertLess(cropped.width(), before.width())
                self.assertLess(cropped.height(), before.height())
                page._set_on_top(True)
                self.assertTrue(page.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
                page._set_on_top(False)
                self.assertIn("C000", page._memory_text())
                page._log("refused save")
                self.assertIn("refused save", page._errors)
                page._toggle_trace()
                page._tick()
                page._toggle_trace()
                self.assertTrue((Path(__file__).resolve().parents[1] / "saves" / "trace.log").is_file())
                chosen = page.state_slot
                page._auto_seconds = 180
                page._count_play()
                self.assertEqual(page.state_slot, chosen)
                self.assertTrue(page._state_file(0).is_file())
                self.assertEqual(page._slot_title(0), "Autosave")
            finally:
                page._state_file(0).unlink(missing_ok=True)
                page._slot_picture(0).unlink(missing_ok=True)
                (Path(__file__).resolve().parents[1] / "saves" / "trace.log").unlink(missing_ok=True)
                page.shutdown()
                os.environ.pop("POKEMONGB_SETTINGS", None)
                os.environ.pop("POKEMONGB_LIBRARY", None)
                os.environ.pop("POKEMONGB_CONTROLS", None)

        with tempfile.TemporaryDirectory() as folder:
            library = Library(Path(folder))
            first = Path(folder) / "zeta.gb"
            second = Path(folder) / "alpha.gb"
            first.write_bytes(b"z")
            second.write_bytes(b"a")
            zeta = library.remember(first, "Zeta", "Game Boy", "gb")
            alpha = library.remember(second, "Alpha", "NES", "nes")
            library.set_tags(alpha.id, ["to finish"])
            library.mark_played(zeta.id)
            shelf = Shelf(library, lambda _game: None, lambda _game: None)
            shelf.sort.setCurrentText("Name")
            from PySide6.QtWidgets import QLabel

            flat = [[label.text() for label in card.findChildren(QLabel)] for card in shelf.cards]
            self.assertEqual(flat[0][1], "Alpha")
            self.assertIn("to finish", flat[0][2])
            self.assertIn("Oct", flat[1][2])
            self.assertEqual(alpha.tags, ["to finish"])
            self.assertGreater(zeta.last_played, 0)

    def test_rumble_report_and_new_systems(self):
        dual = sony_rumble_report(True, 65535, 0)
        self.assertEqual(dual[0], 0x02)
        self.assertEqual(dual[4], 255)
        self.assertEqual(dual[3], 0)
        plain = sony_rumble_report(False, 0, 65535)
        self.assertEqual(plain[0], 0x05)
        self.assertEqual(plain[5], 0)
        self.assertEqual(plain[4], 255)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            n64 = root / "mario.z64"
            n64.write_bytes(b"\0" * 32)
            fds = root / "disk.fds"
            fds.write_bytes(b"\0" * 32)
            mini = root / "poke.min"
            mini.write_bytes(b"\0" * 32)
            self.assertEqual(locate(n64, root / "cache")[1].id, "n64")
            self.assertEqual(locate(fds, root / "cache")[1].id, "fds")
            self.assertEqual(locate(mini, root / "cache")[1].id, "min")
            disc = root / "track.bin"
            disc.write_bytes(b"SEGADISCSYSTEM" + b"\0" * 16)
            cue = root / "game.cue"
            cue.write_text('FILE "track.bin" BINARY\n', encoding="utf-8")
            self.assertEqual(locate(cue, root / "cache")[1].id, "mcd")
            saturn = root / "saturn.bin"
            saturn.write_bytes(b"\0" * 16 + b"SEGASATURN" + b"\0" * 8)
            saturn_cue = root / "disc.cue"
            saturn_cue.write_text('FILE "saturn.bin" BINARY\n', encoding="utf-8")
            self.assertEqual(locate(saturn_cue, root / "cache")[1].id, "saturn")

    def test_seats_spectator_state_and_late_buttons(self):
        host = Link()
        guest = Link()
        third = Link()
        watch = Link()
        for link in (host, guest, third, watch):
            link.set_game(b"samegame", "nes")
        port = host.host(0)
        guest.join("127.0.0.1", port)
        self.assertTrue(guest.ready, guest.error)
        self.assertEqual(guest.seat, 2)
        third.join("127.0.0.1", port)
        watch.join("127.0.0.1", port, spectate=True)
        self.assertTrue(third.ready, third.error)
        self.assertEqual(third.seat, 3)
        self.assertTrue(watch.spectating, watch.error)
        self.assertEqual(watch.seat, 9)
        host.send_state(b"snapshot-of-the-moment")
        found = b""
        for _ in range(40):
            found = guest.take_state()
            if found:
                break
            time.sleep(0.02)
        self.assertEqual(found, b"snapshot-of-the-moment")
        host._inbox[0] = pack_input(7, (0, 0, 0, 0), 0, False)
        host.frame = 2
        late = host.take_late()
        self.assertEqual(unpack_input(late[0][1])[0], 7)
        host.close()
        guest.close()
        third.close()
        watch.close()


if __name__ == "__main__":
    unittest.main()
