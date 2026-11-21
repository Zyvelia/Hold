import unittest

from pokemongb.gl import Host, available


@unittest.skipUnless(available(), "OpenGL is not available")
class GlHostTests(unittest.TestCase):
    def test_red_pixels_round_trip(self):
        host = Host()
        try:
            raw = host.self_test()
        finally:
            host.close()
        self.assertEqual(raw[:4], bytes([0, 0, 255, 255]))
        self.assertEqual(raw, bytes([0, 0, 255, 255]) * 4)
