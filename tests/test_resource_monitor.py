"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

اختبارات لـ ResourceMonitor (infrastructure/cognitive_core/resource/
monitor.py) — كانت 66% مغطاة. تُحاكي psutil وshutil.disk_usage بالكامل
لجعل القراءات حتمية قابلة للاختبار، بدل الاعتماد على حالة الآلة الفعلية
وقت تشغيل الاختبار (غير حتمية أصلًا، وتُنتج اختبارات هشّة).
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from infrastructure.cognitive_core.resource.monitor import ResourceMonitor, ResourceSnapshot


class TestResourceSnapshotDerivedProperties(unittest.TestCase):
    def test_memory_percent_computes_correctly(self):
        snap = ResourceSnapshot(
            cpu_percent=10.0, memory_used_mb=512, memory_total_mb=1024,
            disk_free_gb=10, disk_total_gb=100, timestamp="2026-01-01T00:00:00Z",
        )
        self.assertEqual(snap.memory_percent, 50.0)

    def test_memory_percent_is_zero_not_division_error_when_total_is_zero(self):
        snap = ResourceSnapshot(
            cpu_percent=0, memory_used_mb=0, memory_total_mb=0,
            disk_free_gb=0, disk_total_gb=0, timestamp="t",
        )
        self.assertEqual(snap.memory_percent, 0.0)

    def test_disk_percent_used_computes_correctly(self):
        snap = ResourceSnapshot(
            cpu_percent=0, memory_used_mb=0, memory_total_mb=1,
            disk_free_gb=25, disk_total_gb=100, timestamp="t",
        )
        self.assertEqual(snap.disk_percent_used, 75.0)

    def test_disk_percent_used_is_zero_not_division_error_when_total_is_zero(self):
        snap = ResourceSnapshot(
            cpu_percent=0, memory_used_mb=0, memory_total_mb=1,
            disk_free_gb=0, disk_total_gb=0, timestamp="t",
        )
        self.assertEqual(snap.disk_percent_used, 0.0)


class TestResourceMonitorSnapshot(unittest.TestCase):
    @patch("infrastructure.cognitive_core.resource.monitor.shutil.disk_usage")
    @patch("infrastructure.cognitive_core.resource.monitor.psutil.virtual_memory")
    @patch("infrastructure.cognitive_core.resource.monitor.psutil.cpu_percent")
    def test_snapshot_converts_bytes_to_mb_and_gb_correctly(self, mock_cpu, mock_vmem, mock_disk):
        mock_cpu.return_value = 42.5
        mock_vmem.return_value = MagicMock(used=1024 * 1024 * 500, total=1024 * 1024 * 2000)  # 500MB / 2000MB
        mock_disk.return_value = MagicMock(free=50 * 1024**3, total=200 * 1024**3)  # 50GB / 200GB

        snapshot = ResourceMonitor().snapshot()

        self.assertEqual(snapshot.cpu_percent, 42.5)
        self.assertAlmostEqual(snapshot.memory_used_mb, 500.0)
        self.assertAlmostEqual(snapshot.memory_total_mb, 2000.0)
        self.assertAlmostEqual(snapshot.disk_free_gb, 50.0)
        self.assertAlmostEqual(snapshot.disk_total_gb, 200.0)
        self.assertTrue(snapshot.timestamp)  # طابع زمني حقيقي غير فارغ

    @patch("infrastructure.cognitive_core.resource.monitor.shutil.disk_usage")
    @patch("infrastructure.cognitive_core.resource.monitor.psutil.virtual_memory")
    @patch("infrastructure.cognitive_core.resource.monitor.psutil.cpu_percent")
    def test_snapshot_uses_the_configured_disk_path(self, mock_cpu, mock_vmem, mock_disk):
        mock_cpu.return_value = 0
        mock_vmem.return_value = MagicMock(used=0, total=1)
        mock_disk.return_value = MagicMock(free=0, total=1)

        ResourceMonitor(disk_path="/custom/path").snapshot()

        mock_disk.assert_called_once_with("/custom/path")


class TestHasCapacity(unittest.TestCase):
    def _monitor_with(self, cpu_percent, mem_used_mb, mem_total_mb):
        monitor = ResourceMonitor()
        monitor.snapshot = MagicMock(
            return_value=ResourceSnapshot(
                cpu_percent=cpu_percent, memory_used_mb=mem_used_mb, memory_total_mb=mem_total_mb,
                disk_free_gb=10, disk_total_gb=100, timestamp="t",
            )
        )
        return monitor

    def test_returns_true_when_well_under_both_thresholds(self):
        monitor = self._monitor_with(cpu_percent=20.0, mem_used_mb=200, mem_total_mb=1000)  # 20% mem
        self.assertTrue(monitor.has_capacity())

    def test_returns_false_when_cpu_exceeds_threshold(self):
        monitor = self._monitor_with(cpu_percent=95.0, mem_used_mb=100, mem_total_mb=1000)
        self.assertFalse(monitor.has_capacity())

    def test_returns_false_when_memory_exceeds_threshold(self):
        monitor = self._monitor_with(cpu_percent=10.0, mem_used_mb=950, mem_total_mb=1000)  # 95% mem
        self.assertFalse(monitor.has_capacity())

    def test_custom_thresholds_are_respected(self):
        monitor = self._monitor_with(cpu_percent=60.0, mem_used_mb=100, mem_total_mb=1000)
        self.assertFalse(monitor.has_capacity(max_cpu_percent=50.0))
        self.assertTrue(monitor.has_capacity(max_cpu_percent=70.0))


if __name__ == "__main__":
    unittest.main()
