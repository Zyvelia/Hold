import tempfile
import unittest
from pathlib import Path

from pokemongb.cart import prepare_switch, switch_save_key
from pokemongb.libretro import CoreError
from pokemongb.switch import core_path, open_core, pack_state, unpack_state


class SwitchCartTests(unittest.TestCase):
    def test_nsp_is_routed_and_gb_is_not(self):
        with tempfile.TemporaryDirectory() as folder:
            rom = Path(folder) / "Sword.nsp"
            rom.write_bytes(b"\x00" * 0x80)
            self.assertEqual(prepare_switch(rom), rom)
            other = Path(folder) / "red.gb"
            other.write_bytes(b"\x00" * 0x200)
            self.assertIsNone(prepare_switch(other))
            self.assertTrue(switch_save_key(rom).startswith("SW_"))

    def test_state_wrapper_rejects_another_game(self):
        packed = pack_state("SW_AA", b"state-bytes")
        self.assertEqual(unpack_state(packed, "SW_AA"), b"state-bytes")
        with self.assertRaises(ValueError):
            unpack_state(packed, "SW_BB")

    def test_missing_core_is_reported(self):
        if core_path().is_file():
            return
        with self.assertRaises(CoreError) as caught:
            open_core(Path("."))
        self.assertIn("suyu_libretro.dll", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
