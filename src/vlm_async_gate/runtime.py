"""Small reference runtime for non-blocking, latest-frame VLM inference.

This module is independent of any planner, simulator, or model framework.  It
captures only the temporal contract needed by an asynchronous semantic gate:

* the control loop never waits for inference;
* at most one not-yet-started frame is retained;
* decisions carry their source frame and simulation timestamp;
* stale, low-confidence, invalid, and failed results are not exposed.

The thread-based worker keeps the reference implementation dependency-free.
A GPU deployment should normally put model inference in a separate process
while preserving the same input/output contract.
"""

from __future__ import annotations

import math
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, FrozenSet, Iterable, Optional, Tuple


InferenceFunction = Callable[[Any], Tuple[str, float]]


@dataclass(frozen=True)
class FrameSample:
    """A sensor sample submitted without blocking the control loop."""

    frame_id: int
    simulation_time_s: float
    payload: Any


@dataclass(frozen=True)
class IntentDecision:
    """A validated semantic decision tied to its source observation."""

    frame_id: int
    simulation_time_s: float
    command: str
    confidence: float
    completed_monotonic_s: float


@dataclass(frozen=True)
class WorkerStats:
    """Snapshot of worker counters used for latency and drop monitoring."""

    submitted: int
    dropped_before_inference: int
    completed: int
    failed: int


class LatestFrameWorker:
    """Run inference off the control path and retain only the latest decision."""

    def __init__(
        self,
        infer: InferenceFunction,
        *,
        allowed_commands: Optional[Iterable[str]] = None,
        name: str = "vlm-intent-worker",
    ) -> None:
        self._infer = infer
        self._allowed_commands: Optional[FrozenSet[str]] = (
            frozenset(allowed_commands) if allowed_commands is not None else None
        )
        self._frames: "queue.Queue[FrameSample]" = queue.Queue(maxsize=1)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._started = False
        self._latest: Optional[IntentDecision] = None
        self._submitted = 0
        self._dropped = 0
        self._completed = 0
        self._failed = 0

    def start(self) -> None:
        """Start the worker once."""

        with self._lock:
            if self._started:
                raise RuntimeError("worker has already been started")
            self._started = True
        self._thread.start()

    def submit(self, sample: FrameSample) -> None:
        """Submit immediately, replacing an older queued sample if necessary."""

        with self._lock:
            if not self._started:
                raise RuntimeError("worker must be started before submit")
            if self._stop.is_set():
                raise RuntimeError("worker is closing")
            self._submitted += 1

        while True:
            try:
                self._frames.put_nowait(sample)
                return
            except queue.Full:
                try:
                    self._frames.get_nowait()
                except queue.Empty:
                    continue
                with self._lock:
                    self._dropped += 1

    def latest(
        self,
        *,
        current_simulation_time_s: float,
        max_age_s: float,
        min_confidence: float = 0.0,
    ) -> Optional[IntentDecision]:
        """Return the latest usable decision or ``None`` for planner fallback."""

        if max_age_s < 0.0:
            raise ValueError("max_age_s must be non-negative")
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be in [0, 1]")

        with self._lock:
            decision = self._latest
        if decision is None or decision.confidence < min_confidence:
            return None

        age_s = current_simulation_time_s - decision.simulation_time_s
        if age_s < 0.0 or age_s > max_age_s:
            return None
        return decision

    def stats(self) -> WorkerStats:
        """Return a thread-safe counter snapshot."""

        with self._lock:
            return WorkerStats(
                submitted=self._submitted,
                dropped_before_inference=self._dropped,
                completed=self._completed,
                failed=self._failed,
            )

    def close(self, timeout_s: float = 5.0) -> bool:
        """Request shutdown and return whether the thread stopped in time."""

        self._stop.set()
        if not self._started:
            return True
        self._thread.join(timeout=max(timeout_s, 0.0))
        return not self._thread.is_alive()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                sample = self._frames.get(timeout=0.05)
            except queue.Empty:
                continue

            try:
                command, confidence = self._infer(sample.payload)
                command = str(command)
                confidence = float(confidence)
                if self._allowed_commands is not None and command not in self._allowed_commands:
                    raise ValueError(f"unsupported command: {command}")
                if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                    raise ValueError("confidence must be finite and in [0, 1]")
                decision = IntentDecision(
                    frame_id=sample.frame_id,
                    simulation_time_s=sample.simulation_time_s,
                    command=command,
                    confidence=confidence,
                    completed_monotonic_s=time.monotonic(),
                )
            except Exception:
                with self._lock:
                    self._failed += 1
                continue

            with self._lock:
                if self._latest is None or decision.frame_id >= self._latest.frame_id:
                    self._latest = decision
                self._completed += 1
