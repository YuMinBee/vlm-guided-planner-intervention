from __future__ import annotations

import threading
import time
import unittest

from vlm_async_gate import FrameSample, LatestFrameWorker


COMMANDS = {"lane_follow", "left", "right", "stop"}


def wait_until(predicate, timeout_s=1.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class LatestFrameWorkerTest(unittest.TestCase):
    def test_intermediate_queued_frame_is_dropped(self):
        first_started = threading.Event()
        release_first = threading.Event()
        calls = []

        def infer(payload):
            calls.append(payload)
            if payload == 1:
                first_started.set()
                release_first.wait(1.0)
            return "lane_follow", 0.9

        worker = LatestFrameWorker(infer, allowed_commands=COMMANDS)
        worker.start()
        try:
            worker.submit(FrameSample(1, 0.1, 1))
            self.assertTrue(first_started.wait(1.0))
            worker.submit(FrameSample(2, 0.2, 2))
            worker.submit(FrameSample(3, 0.3, 3))
            release_first.set()
            self.assertTrue(wait_until(lambda: worker.stats().completed == 2))
            self.assertEqual(calls, [1, 3])
            self.assertEqual(worker.stats().dropped_before_inference, 1)
            self.assertEqual(worker.latest(
                current_simulation_time_s=0.4,
                max_age_s=0.2,
            ).frame_id, 3)
        finally:
            release_first.set()
            self.assertTrue(worker.close())

    def test_stale_and_low_confidence_results_fall_back(self):
        worker = LatestFrameWorker(lambda _: ("right", 0.6), allowed_commands=COMMANDS)
        worker.start()
        try:
            worker.submit(FrameSample(10, 1.0, object()))
            self.assertTrue(wait_until(lambda: worker.stats().completed == 1))
            self.assertIsNotNone(worker.latest(
                current_simulation_time_s=1.4,
                max_age_s=0.5,
                min_confidence=0.5,
            ))
            self.assertIsNone(worker.latest(
                current_simulation_time_s=1.4,
                max_age_s=0.5,
                min_confidence=0.7,
            ))
            self.assertIsNone(worker.latest(
                current_simulation_time_s=1.6,
                max_age_s=0.5,
                min_confidence=0.5,
            ))
        finally:
            self.assertTrue(worker.close())

    def test_failure_does_not_replace_last_good_decision(self):
        def infer(payload):
            if payload == "bad":
                raise RuntimeError("inference failed")
            return "left", 0.8

        worker = LatestFrameWorker(infer, allowed_commands=COMMANDS)
        worker.start()
        try:
            worker.submit(FrameSample(20, 2.0, "good"))
            self.assertTrue(wait_until(lambda: worker.stats().completed == 1))
            worker.submit(FrameSample(21, 2.1, "bad"))
            self.assertTrue(wait_until(lambda: worker.stats().failed == 1))
            decision = worker.latest(
                current_simulation_time_s=2.2,
                max_age_s=0.5,
            )
            self.assertEqual(decision.frame_id, 20)
            self.assertEqual(worker.stats().completed, 1)
        finally:
            self.assertTrue(worker.close())


if __name__ == "__main__":
    unittest.main()
