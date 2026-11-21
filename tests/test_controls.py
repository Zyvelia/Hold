import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QRect, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLabel

from pokemongb.controls import Controls, ControlsDialog
from pokemongb.page import PokemonGBPage


def _press(page: PokemonGBPage, key: int) -> None:
    page.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))


def _release(page: PokemonGBPage, key: int) -> None:
    page.keyReleaseEvent(QKeyEvent(QEvent.Type.KeyRelease, key, Qt.KeyboardModifier.NoModifier))


class ControlMapTests(unittest.TestCase):
    def test_defaults_and_rebind_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "controls.json"
            controls = Controls(path)
            self.assertEqual(controls.actions_for(Qt.Key.Key_X), ["a"])
            self.assertEqual(controls.actions_for(Qt.Key.Key_Z), ["b"])
            self.assertIn("select", controls.actions_for(Qt.Key.Key_Shift))
            self.assertIn("select", controls.actions_for(Qt.Key.Key_Backspace))
            controls.assign("up", Qt.Key.Key_W)
            self.assertEqual(controls.actions_for(Qt.Key.Key_W), ["up"])
            self.assertEqual(controls.actions_for(Qt.Key.Key_Up), [])
            controls.assign("b", Qt.Key.Key_X)
            self.assertEqual(controls.actions_for(Qt.Key.Key_X), ["b"])
            self.assertEqual(controls.keys("a"), [])
            again = Controls(path)
            self.assertEqual(again.actions_for(Qt.Key.Key_W), ["up"])
            again.reset()
            self.assertEqual(again.actions_for(Qt.Key.Key_X), ["a"])

    def test_page_uses_the_new_key(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            os.environ["POKEMONGB_CONTROLS"] = str(Path(folder) / "controls.json")
            try:
                page = PokemonGBPage()
                rom = bytearray(0x8000)
                rom[0x100] = 0x18
                rom[0x101] = 0xFE
                page.load_bytes(bytes(rom))
                _press(page, Qt.Key.Key_Z)
                self.assertEqual(page.gb.joypad.buttons & 0x02, 0x02)
                _release(page, Qt.Key.Key_Z)
                self.assertEqual(page.gb.joypad.buttons & 0x02, 0)
                _press(page, Qt.Key.Key_Space)
                self.assertTrue(page.fast)
                _release(page, Qt.Key.Key_Space)
                self.assertTrue(page.fast)
                _press(page, Qt.Key.Key_Space)
                self.assertFalse(page.fast)
                page.controls.assign("b", int(Qt.Key.Key_M))
                _press(page, Qt.Key.Key_Z)
                self.assertEqual(page.gb.joypad.buttons & 0x02, 0)
                _press(page, Qt.Key.Key_M)
                self.assertEqual(page.gb.joypad.buttons & 0x02, 0x02)
                _press(page, Qt.Key.Key_2)
                self.assertEqual(page.state_slot, 2)
                dialog = ControlsDialog(page.controls, page)
                dialog._arm("a")
                dialog.keyPressEvent(
                    QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_K, Qt.KeyboardModifier.NoModifier)
                )
                self.assertEqual(page.controls.actions_for(Qt.Key.Key_K), ["a"])
                self.assertEqual(dialog._buttons["a"].text(), "K")
                titles = [label.text() for label in dialog.findChildren(QLabel, "CardTitle")]
                self.assertEqual(
                    titles,
                    ["MOVE", "BUTTONS", "SHOULDERS", "RIGHT STICK", "PLAY", "SAVE STATES"],
                )
                self.assertEqual(page.controls_btn.text(), "Controls")
                dialog.resize(980, 860)
                dialog.show()
                app.processEvents()

                def placed(action_id: str) -> QRect:
                    button = dialog._buttons[action_id]
                    origin = button.mapTo(dialog, button.rect().topLeft())
                    return QRect(origin, button.size())

                placed_keys = {
                    action_id: placed(action_id)
                    for action_id in ("up", "left", "right", "down", "y", "a", "rstick_up", "rstick_left")
                }
                for action_id, rect in placed_keys.items():
                    self.assertGreaterEqual(rect.height(), 36, action_id)
                    self.assertGreaterEqual(rect.width(), 80, action_id)
                self.assertFalse(placed_keys["up"].intersects(placed_keys["left"]))
                self.assertFalse(placed_keys["up"].intersects(placed_keys["down"]))
                self.assertFalse(placed_keys["left"].intersects(placed_keys["right"]))
                self.assertFalse(placed_keys["rstick_up"].intersects(placed_keys["rstick_left"]))
                dialog.close()
                game_boy = ControlsDialog(page.controls, page, kind="gb", system_name="Game Boy")
                self.assertNotIn("y", game_boy._buttons)
                self.assertNotIn("rstick_up", game_boy._buttons)
                self.assertIn("a", game_boy._buttons)
                self.assertEqual(game_boy.windowTitle(), "Game Boy controls")
                names = {
                    action_id: game_boy._buttons[action_id].parentWidget().findChild(QLabel, "ActionName").text()
                    for action_id in ("a", "b")
                }
                self.assertEqual(names, {"a": "A", "b": "B"})
                playstation = ControlsDialog(page.controls, page, kind="ps1", system_name="PlayStation")
                face = {
                    action_id: playstation._buttons[action_id].parentWidget().findChild(QLabel, "ActionName").text()
                    for action_id in ("x", "y", "a", "b")
                }
                self.assertEqual(face, {"x": "Triangle", "y": "Square", "a": "Circle", "b": "Cross"})
                self.assertIn("rstick_up", playstation._buttons)
                game_boy.close()
                playstation.close()
                page.shutdown()
            finally:
                os.environ.pop("POKEMONGB_CONTROLS", None)
        self.assertIsNotNone(app)
