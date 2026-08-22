"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

ResourceMonitor — the CPU/Memory/Storage half of Layer 2's mandate from the
master architecture doc, section 2.2: "يجب أن يدير النظام موارده تلقائيًا...
ثم يحدد أفضل مكان لتنفيذ كل مهمة."

Design decision: psutil was chosen for cross-platform CPU/memory sampling
instead of hand-rolling /proc parsing, because it is already available in
this environment and gives consistent readings across Linux/macOS/Windows —
important since Local Mode should not assume a specific OS. GPU and Network
monitoring (also listed in the vision doc) are deliberately deferred: there
is no GPU workload to observe yet in this phase, and network monitoring is
only meaningful once Hybrid/Cloud mode exists.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone

import psutil


@dataclass(frozen=True)
class ResourceSnapshot:
    """A point-in-time reading of local machine resources."""

    cpu_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_free_gb: float
    disk_total_gb: float
    timestamp: str

    @property
    def memory_percent(self) -> float:
        if self.memory_total_mb == 0:
            return 0.0
        return (self.memory_used_mb / self.memory_total_mb) * 100.0

    @property
    def disk_percent_used(self) -> float:
        if self.disk_total_gb == 0:
            return 0.0
        return ((self.disk_total_gb - self.disk_free_gb) / self.disk_total_gb) * 100.0


class ResourceMonitor:
    """Samples local CPU, memory, and disk usage."""

    def __init__(self, disk_path: str = "/", cpu_sample_interval: float = 0.1):
        self.disk_path = disk_path
        self.cpu_sample_interval = cpu_sample_interval

    def snapshot(self) -> ResourceSnapshot:
        cpu_percent = psutil.cpu_percent(interval=self.cpu_sample_interval)
        vm = psutil.virtual_memory()
        disk = shutil.disk_usage(self.disk_path)

        return ResourceSnapshot(
            cpu_percent=cpu_percent,
            memory_used_mb=vm.used / (1024 * 1024),
            memory_total_mb=vm.total / (1024 * 1024),
            disk_free_gb=disk.free / (1024**3),
            disk_total_gb=disk.total / (1024**3),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def has_capacity(
        self, max_cpu_percent: float = 90.0, max_memory_percent: float = 90.0
    ) -> bool:
        """
        A simple local-mode admission check: is there enough headroom to
        start another task? This is the "أفضل مكان لتنفيذ كل مهمة" decision
        for Local Mode, where the only place is this machine — the check
        degenerates to "is this machine currently overloaded".
        """
        snap = self.snapshot()
        return (
            snap.cpu_percent < max_cpu_percent
            and snap.memory_percent < max_memory_percent
        )
