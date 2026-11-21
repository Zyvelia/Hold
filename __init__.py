"""Emulator module. The standalone copy stays in the PokemonGB folder."""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def register(plugin_manager):
    plugin_manager.register({
        "name": "Emulator",
        "category": "Gaming",
        "desc": "Play Game Boy through Switch, plus the other cartridge, disc, and handheld systems. You load your own ROMs.",
        "icon": "🕹️",
        "qt_page": "pokemongb.page:PokemonGBPage",
    })
