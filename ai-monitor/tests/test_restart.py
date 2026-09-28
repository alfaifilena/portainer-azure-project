import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lifecycle import observe
from portainer import Portainer
from restart_control import save, recover
from storage import Store
from telegram_alerts import TelegramAlerts


class RestartTests(unittest.TestCase):
    def test_keep_running_manual_stop_and_disable_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "monitor.db")
            client = Mock()
            client.validate_restart_policy = Portainer.validate_restart_policy
            policy = {"Name": "unless-stopped", "MaximumRetryCount": 0}
            live = {"policy": policy, "state": "exited", "managed_by_swarm": False,
                    "started_at": "old", "finished_at": "stop", "restart_count": 0}
            client.restart_settings.side_effect = lambda *args, **kw: dict(live)
            def start(*args):
                live.update(state="running", started_at="new")
            client.start_container.side_effect = start
            c = {"id": "a", "name": "demo", "state": "exited", "finished_at": "stop"}
            self.assertFalse(recover(client, store, 1, c, time.time()))
            choice = {"id": "a", "enabled": True, "expected_policy": policy}
            self.assertTrue(save(client, 1, [choice], {"a"}, "user-jwt", store)["results"][0]["ok"])
            restarted_store = Store(Path(tmp) / "monitor.db")
            self.assertTrue(recover(client, restarted_store, 1, c, time.time()))
            self.assertEqual(c["state"], "running")
            client.start_container.assert_called_once_with(1, "a")
            live["state"] = c["state"] = "exited"
            self.assertFalse(recover(client, store, 1, c, time.time()))
            choice["enabled"] = False
            def update(eid, cid, new_policy, **kwargs):
                live["policy"] = new_policy
                return {}
            client.update_restart_policy.side_effect = update
            self.assertTrue(save(client, 1, [choice], {"a"}, "user-jwt", store)["results"][0]["ok"])
            self.assertFalse(recover(client, store, 1, c, time.time() + 60))
            client.start_container.assert_called_once()

    def test_save_scoped_partial_and_never_starts(self):
        client = Mock()
        client.validate_restart_policy = Portainer.validate_restart_policy
        off = {"Name": "no", "MaximumRetryCount": 0}
        on = {"Name": "unless-stopped", "MaximumRetryCount": 0}
        states = {"a": off, "b": off}
        client.restart_settings.side_effect = lambda eid, cid, **kw: {
            "policy": states[cid], "state": "exited", "managed_by_swarm": False}
        def update(eid, cid, policy, **kwargs):
            self.assertEqual(kwargs, {"jwt": "user-jwt"})
            if cid == "b":
                raise HTTPError("", 403, "", None, None)
            states[cid] = policy
            return {}
        client.update_restart_policy.side_effect = update
        changes = [{"id": cid, "enabled": True, "expected_policy": off} for cid in ("a", "b")]
        with self.assertRaises(ValueError):
            save(client, 1, changes, {"a"}, "user-jwt")
        client.update_restart_policy.assert_not_called()
        result = save(client, 1, changes, {"a", "b"}, "user-jwt")
        self.assertEqual([r["ok"] for r in result["results"]], [True, False])
        self.assertEqual(states["a"], on)
        client.request.assert_not_called()
        changes[0]["enabled"] = False
        changes[0]["expected_policy"] = on
        self.assertTrue(save(client, 1, changes[:1], {"a"}, "user-jwt")["results"][0]["ok"])
        self.assertEqual(states["a"], off)
        self.assertFalse(save(client, 1, changes[:1], {"a"}, "user-jwt")["results"][0]["ok"])

    def test_lifecycle_initial_off_fast_restart_and_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "monitor.db")
            telegram = TelegramAlerts(store, {}, send_fn=Mock())
            telegram.credentials = lambda: ("test-bot", "test-chat")
            c = {"id": "a", "name": "demo", "collection_status": "ok", "state": "exited",
                 "restart_count": 0, "started_at": "first", "finished_at": "end"}
            now = time.time()
            observe(store, telegram, 1, "Docker", c, now)
            self.assertEqual(store.notices(1, 1, {"a"}), [])
            c.update(state="running", started_at="second")
            observe(store, telegram, 1, "Docker", c, now)
            c.update(restart_count=1, started_at="third")
            observe(store, telegram, 1, "Docker", c, now)
            observe(store, telegram, 1, "Docker", c, now)
            self.assertEqual(len(store.notices(1, 1, {"a"})), 3)
            with store.connect() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM telegram_alerts").fetchone()[0], 3)
            c.update(state="exited", finished_at="last")
            observe(store, telegram, 1, "Docker", c, now)
            observe(store, telegram, 1, "Docker", c, now)
            self.assertEqual(len(store.notices(1, 1, {"a"})), 4)
            self.assertTrue(telegram.send_once())
            telegram.send_fn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
