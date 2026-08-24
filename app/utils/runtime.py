"""Lightweight runtime helpers (stdlib only - no extra deps)."""

from __future__ import annotations

import resource
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


def rss_mb() -> float:
    """Return current process RSS in mebibytes (best-effort, Linux-friendly)."""
    status = Path("/proc/self/status")
    if status.is_file():
        try:
            for line in status.read_text(encoding="utf-8").splitlines():
                if line.startswith("VmRSS:"):
                    # Value is in kB on Linux.
                    return int(line.split()[1]) / 1024.0
        except (OSError, ValueError, IndexError):
            pass
    # Fallback: peak RSS (Linux ru_maxrss is kB; macOS is bytes).
    peak = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if peak > 1e7:  # likely bytes (macOS)
        return peak / (1024.0 * 1024.0)
    return peak / 1024.0


def peak_rss_mb() -> float:
    """Return peak RSS (ru_maxrss) in mebibytes for this process."""
    peak = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if peak > 1e7:  # likely bytes (macOS)
        return peak / (1024.0 * 1024.0)
    return peak / 1024.0


@dataclass
class RssStage:
    """One staged RSS sample."""

    name: str
    rss_mb: float
    delta_mb: float
    peak_rss_mb: float


@dataclass
class RssStageLogger:
    """Log absolute RSS + delta after each warm-start / profile stage."""

    stages: list[RssStage] = field(default_factory=list)
    _prev_rss: float | None = field(default=None, repr=False)
    printer: Callable[[str], None] = print

    def mark(self, name: str) -> RssStage:
        """Record RSS after ``name`` completes and print a one-line summary."""
        current = rss_mb()
        peak = peak_rss_mb()
        delta = 0.0 if self._prev_rss is None else current - self._prev_rss
        stage = RssStage(
            name=name,
            rss_mb=current,
            delta_mb=delta,
            peak_rss_mb=peak,
        )
        self.stages.append(stage)
        self._prev_rss = current
        self.printer(
            f"[rss] {name}: {current:.0f} MB  (Δ {delta:+.0f} MB)  "
            f"peak={peak:.0f} MB"
        )
        return stage

    def summary_table(self) -> str:
        """Return a compact absolute/delta table for all recorded stages."""
        if not self.stages:
            return "(no stages)"
        lines = [
            f"{'stage':<28} {'RSS_MB':>8} {'DELTA_MB':>9} {'PEAK_MB':>8}",
            "-" * 58,
        ]
        for stage in self.stages:
            lines.append(
                f"{stage.name:<28} {stage.rss_mb:8.0f} "
                f"{stage.delta_mb:9.0f} {stage.peak_rss_mb:8.0f}"
            )
        return "\n".join(lines)