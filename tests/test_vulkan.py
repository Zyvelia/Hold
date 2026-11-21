import unittest

from pokemongb.vulkan import Host, VulkanError, available


class VulkanHostTests(unittest.TestCase):
    @unittest.skipUnless(available(), "Vulkan is not installed")
    def test_red_pixels_roundtrip(self):
        host = Host()
        try:
            raw = host.self_test()
        except VulkanError as exc:
            self.fail(str(exc))
        finally:
            host.close()
        self.assertEqual(raw[:4], bytes([255, 0, 0, 255]), raw[:16].hex())
        self.assertEqual(raw, bytes([255, 0, 0, 255]) * 4)


if __name__ == "__main__":
    unittest.main()
