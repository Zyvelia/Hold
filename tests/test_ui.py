import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from pokemongb.page import PokemonGBPage, SaveStatesMenu
from pokemongb.ppu import Z_PACK


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_frame_reaches_the_screen(self):
        page = PokemonGBPage()
        rom = bytearray(0x8000)
        rom[0x100] = 0x18
        rom[0x101] = 0xFE
        page.load_bytes(bytes(rom))
        page._tick()
        pixmap = page.screen.pixmap()
        self.assertIsNotNone(pixmap)
        self.assertFalse(pixmap.isNull())
        image = QImage(page.gb.ppu.fb.tobytes(), 160, 144, 640, QImage.Format.Format_RGB32)
        self.assertEqual(image.pixel(0, 0) & 0xFFFFFF, Z_PACK[0] & 0xFFFFFF)
        page.shutdown()

    def test_save_state_button_roundtrip(self):
        page = PokemonGBPage()
        rom = bytearray(0x8000)
        rom[0x100] = 0x18
        rom[0x101] = 0xFE
        rom[0x134:0x13F] = b"STATECHECK"
        page.load_bytes(bytes(rom))
        page._tick()
        page.gb.cpu.a = 0x3C
        page.gb.mmu.wram[0][4] = 0x77
        page.save_state()
        page.gb.cpu.a = 0x00
        page.gb.mmu.wram[0][4] = 0x00
        page.load_state()
        self.assertEqual(page.gb.cpu.a, 0x3C)
        self.assertEqual(page.gb.mmu.wram[0][4], 0x77)
        page._state_path().unlink(missing_ok=True)
        page._slot_picture(page.state_slot).unlink(missing_ok=True)
        page.shutdown()

    def test_save_states_menu_shows_slots(self):
        page = PokemonGBPage()
        rom = bytearray(0x8000)
        rom[0x100] = 0x18
        rom[0x101] = 0xFE
        rom[0x134:0x13F] = b"SLOTMENU"
        page.load_bytes(bytes(rom))
        menu = SaveStatesMenu(page)
        self.assertEqual(page.states_btn.text(), "Save states")
        self.assertEqual(len(menu._states), 11)
        self.assertEqual(menu._names[0].text(), "Autosave")
        self.assertEqual(menu._states[1].text(), "Empty")
        self.assertFalse(menu._loads[1].isEnabled())
        menu._save(2)
        self.assertEqual(page.state_slot, 2)
        self.assertEqual(menu._states[2].text(), "Saved")
        self.assertTrue(menu._loads[2].isEnabled())
        self.assertTrue(page._state_file(2).is_file())
        page.gb.cpu.a = 0x3C
        page.save_state()
        page.gb.cpu.a = 0x00
        menu._load(2)
        self.assertEqual(page.gb.cpu.a, 0x3C)
        page._state_file(2).unlink(missing_ok=True)
        page._slot_picture(2).unlink(missing_ok=True)
        page.shutdown()


if __name__ == "__main__":
    unittest.main()
