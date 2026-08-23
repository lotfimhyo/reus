# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

import time

import psutil
from fastapi import APIRouter, Depends

from infrastructure.security import verify_api_key

router = APIRouter(prefix="/metrics", tags=["metrics"], dependencies=[Depends(verify_api_key)])

_process = psutil.Process()
_start_time = time.time()


def _gpu_usage_percent() -> float | None:
    """
    Read actual GPU utilization through pynvml when an NVIDIA device is present.
    Return None honestly when the library or device is unavailable.
    """
    try:
        import pynvml  # type: ignore

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        pynvml.nvmlShutdown()
        return float(util.gpu)
    except Exception:
        return None


@router.get("/system")
def system_metrics() -> dict:
    with _process.oneshot():
        cpu_percent = _process.cpu_percent(interval=0.1)
        rss_bytes = _process.memory_info().rss
        num_threads = _process.num_threads()
    return {
        "cpu_percent": cpu_percent,
        "ram_rss_bytes": rss_bytes,
        "ram_rss_mb": round(rss_bytes / (1024 * 1024), 2),
        "gpu_percent": _gpu_usage_percent(),
        "threads": num_threads,
        "uptime_seconds": round(time.time() - _start_time, 2),
    }
