import os
import tempfile
import threading
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from pokemongb.netplay import Link, pack_input, unpack_input
from pokemongb.page import PokemonGBPage
from pokemongb.sony import parse_sony
from pokemongb.system import GameBoy


def _rom() -> bytes:
    rom = bytearray(0x8000)
    rom[0x100] = 0x18
    rom[0x101] = 0xFE
    rom[0x134:0x13F] = b"LINKTEST"
    return bytes(rom)


class LinkTests(unittest.TestCase):
    def test_serial_uses_the_peer_byte(self):
        gb = GameBoy()
        gb.link_in = 0x42
        gb._complete_serial()
        self.assertEqual(gb.mmu.sb, 0x42)
        self.assertEqual(gb.mmu.sc & 0x80, 0)
        gb.link_in = None
        gb._complete_serial()
        self.assertEqual(gb.mmu.sb, 0xFF)

    def test_playstation_cross_is_the_bottom_button(self):
        report = bytearray(64)
        report[0] = 0x01
        report[1] = 128
        report[2] = 128
        report[3] = 128
        report[4] = 128
        report[5] = 0x02 | 0x20
        pad = parse_sony(bytes(report), False)
        self.assertIsNotNone(pad)
        assert pad is not None
        self.assertIn("south", pad.buttons)
        self.assertIn("dright", pad.buttons)

    def test_two_windows_trade_a_frame(self):
        host = Link()
        guest = Link()
        host.set_game(b"samegame", "nes")
        guest.set_game(b"samegame", "nes")
        port = host.host(0)
        guest.join("127.0.0.1", port)
        self.assertTrue(host.ready)
        self.assertEqual(host.mode, "play")
        results: dict[str, bytes | None] = {}

        def run(name: str, link: Link, payload: bytes) -> None:
            results[name] = link.exchange(payload)

        threads = [
            threading.Thread(target=run, args=("host", host, pack_input(1, (0, 0, 0, 0), 0x11, False))),
            threading.Thread(target=run, args=("guest", guest, pack_input(2, (0, 0, 0, 0), 0x22, True))),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
        self.assertIsNotNone(results.get("host"))
        bits, _analog, sb, active = unpack_input(results["host"] or b"")
        self.assertEqual(bits, 2)
        self.assertEqual(sb, 0x22)
        self.assertTrue(active)
        host.close()
        guest.close()

    def test_delay_uses_the_input_from_earlier(self):
        host = Link()
        guest = Link()
        host.delay = 1
        guest.delay = 0
        host.set_game(b"samegame", "nes")
        guest.set_game(b"samegame", "nes")
        port = host.host(0)
        guest.join("127.0.0.1", port)
        self.assertEqual(host.mode, "play")
        self.assertEqual(host.delay, 1)
        self.assertEqual(guest.delay, 1)
        outs: dict[str, list[bytes | None]] = {"host": [], "guest": []}

        def run(name: str, link: Link, first: bytes, second: bytes) -> None:
            outs[name].append(link.exchange(first))
            outs[name].append(link.exchange(second))

        threads = [
            threading.Thread(
                target=run,
                args=("host", host, pack_input(1, (0, 0, 0, 0), 0, False), pack_input(3, (0, 0, 0, 0), 0, False)),
            ),
            threading.Thread(
                target=run,
                args=("guest", guest, pack_input(2, (0, 0, 0, 0), 0, False), pack_input(4, (0, 0, 0, 0), 0, False)),
            ),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
        self.assertEqual(len(outs["host"]), 2)
        first_bits, *_rest = unpack_input(outs["host"][0] or b"")
        second_bits, *_rest = unpack_input(outs["host"][1] or b"")
        self.assertEqual(first_bits, 0)
        self.assertEqual(second_bits, 2)
        host.close()
        guest.close()

    def test_game_boy_link_allows_different_carts(self):
        host = Link()
        guest = Link()
        host.set_game(b"cart-one", "gb")
        guest.set_game(b"cart-two", "gb")
        port = host.host(0)
        guest.join("127.0.0.1", port)
        self.assertEqual(host.mode, "link")
        self.assertEqual(guest.mode, "link")
        host.close()
        guest.close()

    def test_gba_link_allows_different_carts(self):
        host = Link()
        guest = Link()
        host.set_game(b"cart-one", "gba")
        guest.set_game(b"cart-two", "gba")
        port = host.host(0)
        guest.join("127.0.0.1", port)
        self.assertEqual(host.mode, "link")
        self.assertEqual(guest.mode, "link")
        host.close()
        guest.close()

    def test_fast_slider_and_scanlines(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            os.environ["POKEMONGB_SETTINGS"] = str(Path(folder) / "settings.json")
            try:
                page = PokemonGBPage()
                page.load_bytes(_rom())
                page.clock.stop()
                page._read_pads = lambda: (page._pad, page._pad)
                calls: list[int] = []
                original = page.gb.run_frame

                def wrapped() -> None:
                    calls.append(1)
                    original()

                page.gb.run_frame = wrapped
                page.fast = True
                page._fast_frames = 3
                page._tick()
                self.assertEqual(len(calls), 3)
                page.fast = False
                page.filter_box.setCurrentText("Scanlines")
                page._present()
                self.assertEqual(page._filter, "scanline")
                self.assertFalse(page.screen.pixmap().isNull())
                page.shutdown()
            finally:
                os.environ.pop("POKEMONGB_SETTINGS", None)
        self.assertIsNotNone(app)


if __name__ == "__main__":
    unittest.main()
