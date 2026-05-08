from __future__ import annotations

import os
from pathlib import Path


def available_cpu_count() -> int:
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def available_memory_bytes() -> int | None:
    cgroup_limit = _read_cgroup_memory_limit()
    physical_memory = _physical_memory_bytes()

    if cgroup_limit is None:
        return physical_memory
    if physical_memory is None:
        return cgroup_limit
    return min(cgroup_limit, physical_memory)


def recommended_parallel_jobs() -> int:
    cpu_count = available_cpu_count()
    memory_bytes = available_memory_bytes() or 0
    memory_gib = memory_bytes / float(1024**3) if memory_bytes else 0.0
    if cpu_count >= 16 and memory_gib >= 16:
        return 2
    return 1


def recommended_vp9_cpu_used() -> int:
    cpu_count = available_cpu_count()
    if cpu_count >= 16:
        return 8
    if cpu_count >= 8:
        return 7
    return 6


def _read_cgroup_memory_limit() -> int | None:
    candidates = (
        "/sys/fs/cgroup/memory.max",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",
    )
    for raw_path in candidates:
        path = Path(raw_path)
        if not path.exists():
            continue
        try:
            raw_value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not raw_value or raw_value == "max":
            continue
        try:
            value = int(raw_value)
        except ValueError:
            continue
        if value <= 0 or value >= 1 << 60:
            continue
        return value
    return None


def _physical_memory_bytes() -> int | None:
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        return None
    if page_size <= 0 or page_count <= 0:
        return None
    return int(page_size * page_count)
