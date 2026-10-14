import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from unreal_native_display import allocated_a40_bus_id, nvidia_xorg_config, xorg_command


class AllocatedDisplay(unittest.TestCase):
    def test_actual_target_hex_bus_maps_to_only_allocated_device(self):
        bus = allocated_a40_bus_id("NVIDIA A40, 00000000:4F:00.0\n")
        self.assertEqual(bus, "PCI:79:0:0")
        config = nvidia_xorg_config(bus)
        self.assertIn('BusID "PCI:79:0:0"', config)
        self.assertIn('Option "ProbeAllGpus" "False"', config)
        self.assertIn('Option "AutoAddGPU" "False"', config)
        self.assertNotIn("UseDisplayDevice", config)
        self.assertIn('Driver "nvidia"', config)
        self.assertNotIn("dummy", config)
        self.assertIn("Virtual 1280 720", config)

    def test_no_other_gpu_or_ambiguous_allocation_or_config_injection(self):
        for output in ("NVIDIA A40, 00000000:4F:00.0\nNVIDIA A40, 00000000:50:00.0",
                       "NVIDIA A100, 00000000:4F:00.0", "", "NVIDIA A40, 00000001:4F:00.0",
                       "NVIDIA A40, PCI:79:0:0", "NVIDIA A40, 00000000:4F:FF.0"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                allocated_a40_bus_id(output)
        with self.assertRaises(ValueError):
            nvidia_xorg_config('PCI:79:0:0"\nDriver "dummy')

    def test_display_stays_authenticated_and_tcp_disabled(self):
        command = xorg_command("/private/config", "/private/cookie", "/private/log")
        self.assertEqual(command[command.index("-auth") + 1], "/private/cookie")
        self.assertEqual(command[command.index("-nolisten") + 1], "tcp")
        self.assertNotIn("-ac", command)
        self.assertNotIn("cookie-value", command)


if __name__ == "__main__":
    unittest.main()
