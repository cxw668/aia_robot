from __future__ import annotations

import unittest

from app.auth_security import FailedLoginTracker


class FailedLoginTrackerTests(unittest.TestCase):
    def test_tracker_locks_after_threshold_and_expires(self) -> None:
        tracker = FailedLoginTracker(
            max_failures=2,
            window_seconds=60,
            lockout_seconds=30,
        )

        self.assertEqual(tracker.record_failure("alice", now=100.0), 0)
        self.assertEqual(tracker.record_failure("alice", now=110.0), 30)
        self.assertGreater(tracker.get_retry_after("alice", now=120.0), 0)
        self.assertEqual(tracker.get_retry_after("alice", now=141.0), 0)

    def test_success_reset_clears_failures_and_lockout(self) -> None:
        tracker = FailedLoginTracker(
            max_failures=2,
            window_seconds=60,
            lockout_seconds=30,
        )

        self.assertEqual(tracker.record_failure("alice", now=100.0), 0)
        tracker.reset("alice")
        self.assertEqual(tracker.record_failure("alice", now=110.0), 0)
        self.assertEqual(tracker.get_retry_after("alice", now=111.0), 0)
