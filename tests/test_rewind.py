import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from pokemongb.gamepad import EMPTY, interpret
from pokemongb.page import PokemonGBPage
from pokemongb.rewind import Rewind


def _rom() -> bytes:
    rom = bytearray(0x8000)
    rom[0x100] = 0x18
    rom[0x101] = 0xFE
    rom[0x134:0x13F] = b"REWIND"
    return bytes(rom)


class RewindTests(unittest.TestCase):
    def test_stride_and_cap(self):
        rewind = Rewind(max_bytes=10, max_count=2)
        rewind.configure(b"abcd")
        self.assertFalse(rewind.disabled)
        rewind.stride = 2
        rewind.push(b"aaaa")
        rewind.push(b"bbbb")
        self.assertEqual(rewind.pop(), b"bbbb")
        self.assertIsNone(rewind.pop())
        rewind.stride = 1
        rewind.push(b"1234")
        rewind.push(b"5678")
        rewind.push(b"90ab")
        self.assertLessEqual(rewind.bytes, 10)
        self.assertEqual(rewind.pop(), b"90ab")

    def test_huge_state_is_disabled(self):
        rewind = Rewind(max_bytes=4)
        rewind.configure(b"12345")
        self.assertTrue(rewind.disabled)
        rewind.push(b"12345")
        self.assertIsNone(rewind.pop())

    def test_hold_r_steps_back(self):
        app = QApplication.instance() or QApplication([])
        page = PokemonGBPage()
        page.load_bytes(_rom())
        page.clock.stop()
        page._read_pads = lambda: (EMPTY, EMPTY)
        page.gb.cpu.a = 0x42
        page._rewind_store()
        page.gb.cpu.a = 0x07
        page._down_keys.add(int(Qt.Key.Key_R))
        page._tick()
        self.assertEqual(page.gb.cpu.a, 0x42)
        page.shutdown()
        self.assertIsNotNone(app)


class GamepadTests(unittest.TestCase):
    def test_face_buttons_follow_the_diamond(self):
        south = interpret(0x1000, 0, 0, 0, 0, 0, 0)
        east = interpret(0x2000, 0, 0, 0, 0, 0, 0)
        west = interpret(0x4000, 0, 0, 0, 0, 0, 0)
        north = interpret(0x8000, 0, 0, 0, 0, 0, 0)
        self.assertIn("b", south.actions)
        self.assertIn("a", east.actions)
        self.assertIn("y", west.actions)
        self.assertIn("x", north.actions)

    def test_stick_up_is_negative_and_right_click_rewinds(self):
        pad = interpret(0x0080, 0, 0, 0, 30000, 20000, 0)
        self.assertIn("rewind", pad.actions)
        self.assertIn("up", pad.actions)
        self.assertLess(pad.ly, 0)
        self.assertGreater(pad.rx, 0)
        self.assertIn("rstick_right", pad.actions)

    def test_page_presses_and_releases_b(self):
        app = QApplication.instance() or QApplication([])
        page = PokemonGBPage()
        page.load_bytes(_rom())
        page.clock.stop()
        page._read_pads = lambda: (interpret(0x1000, 0, 0, 0, 0, 0, 0), EMPTY)
        page._poll_gamepad()
        self.assertEqual(page.gb.joypad.buttons & 0x02, 0x02)
        page._read_pads = lambda: (EMPTY, EMPTY)
        page._poll_gamepad()
        self.assertEqual(page.gb.joypad.buttons & 0x02, 0)
        page.shutdown()
        self.assertIsNotNone(app)


if __name__ == "__main__":
    unittest.main()
