import json
import os
import plistlib
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import wallpaper_switch as ws  # noqa: E402

MORNING = "11111111-1111-1111-1111-111111111111"
DAY = "22222222-2222-2222-2222-222222222222"
SUNSET = "33333333-3333-3333-3333-333333333333"
NIGHT = "44444444-4444-4444-4444-444444444444"

CONFIG = {
    "periods": [
        {"name": "morning", "start": "06:00", "asset_id": MORNING},
        {"name": "day", "start": "10:00", "asset_id": DAY},
        {"name": "sunset", "start": "17:00", "asset_id": SUNSET},
        {"name": "night", "start": "19:30", "asset_id": NIGHT},
    ]
}


def make_store(asset_id):
    aerial = {"Provider": ws.AERIAL_PROVIDER, "Configuration": ws.make_configuration(asset_id)}
    photo = {"Provider": "com.apple.wallpaper.choice.image", "Configuration": b"keep-me"}
    return {
        "AllSpacesAndDisplays": {
            "Desktop": {"Content": {"Choices": [dict(aerial)]}},
            "Idle": {"Content": {"Choices": [dict(aerial)]}},
        },
        "Displays": {"ABC": {"Desktop": {"Content": {"Choices": [photo]}}}},
    }


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


class PeriodTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = os.path.join(self.tmp.name, "config.json")
        write_json(self.cfg, CONFIG)
        self.periods = ws.load_periods(self.cfg)

    def name_at(self, hhmm):
        return ws.current_period(self.periods, ws.parse_hhmm(hhmm))["name"]

    def test_boundaries(self):
        cases = {
            "00:00": "night",
            "05:59": "night",
            "06:00": "morning",
            "09:59": "morning",
            "10:00": "day",
            "16:59": "day",
            "17:00": "sunset",
            "19:29": "sunset",
            "19:30": "night",
            "23:59": "night",
        }
        for hhmm, expected in cases.items():
            self.assertEqual(self.name_at(hhmm), expected, hhmm)


class ConfigTests(unittest.TestCase):
    def load(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            write_json(path, payload)
            return ws.load_periods(path)

    def test_placeholder_ids_rejected(self):
        bad = {"periods": [{"name": "day", "start": "10:00", "asset_id": "YOUR_DAY_UUID"}]}
        with self.assertRaises(ws.ConfigError):
            self.load(bad)

    def test_duplicate_start_rejected(self):
        bad = {
            "periods": [
                {"name": "a", "start": "10:00", "asset_id": DAY},
                {"name": "b", "start": "10:00", "asset_id": NIGHT},
            ]
        }
        with self.assertRaises(ws.ConfigError):
            self.load(bad)

    def test_bad_time_rejected(self):
        with self.assertRaises(ws.ConfigError):
            ws.parse_hhmm("25:00")
        with self.assertRaises(ws.ConfigError):
            ws.parse_hhmm("noon")


class StoreTests(unittest.TestCase):
    def test_only_aerials_are_changed(self):
        data = make_store(MORNING)
        touched, changed = ws.apply_asset(data, NIGHT)
        self.assertEqual((touched, changed), (2, 2))
        self.assertEqual(ws.collect_aerial_ids(data), [NIGHT, NIGHT])
        photo = data["Displays"]["ABC"]["Desktop"]["Content"]["Choices"][0]
        self.assertEqual(photo["Configuration"], b"keep-me")

    def test_idempotent(self):
        data = make_store(NIGHT)
        self.assertEqual(ws.apply_asset(data, NIGHT), (2, 0))

    def test_case_insensitive_match(self):
        data = make_store(NIGHT.lower())
        self.assertEqual(ws.apply_asset(data, NIGHT.upper()), (2, 0))


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = os.path.join(self.tmp.name, "config.json")
        self.store = os.path.join(self.tmp.name, "Index.plist")
        write_json(self.cfg, CONFIG)

    def write_store(self, data):
        with open(self.store, "wb") as handle:
            plistlib.dump(data, handle, fmt=plistlib.FMT_BINARY)

    def read_ids(self):
        with open(self.store, "rb") as handle:
            return ws.collect_aerial_ids(plistlib.load(handle))

    def run_main(self, now, *extra):
        return ws.main(
            ["--config", self.cfg, "--store", self.store, "--now", now, "--no-restart", *extra]
        )

    def test_switches_and_creates_backup_once(self):
        self.write_store(make_store(MORNING))
        self.assertEqual(self.run_main("18:00"), 0)
        self.assertEqual(self.read_ids(), [SUNSET, SUNSET])
        backup = self.store + ".bak"
        self.assertTrue(os.path.exists(backup))
        with open(backup, "rb") as handle:
            self.assertEqual(ws.collect_aerial_ids(plistlib.load(handle)), [MORNING, MORNING])
        self.assertEqual(self.run_main("21:00"), 0)
        self.assertEqual(self.read_ids(), [NIGHT, NIGHT])
        with open(backup, "rb") as handle:
            self.assertEqual(ws.collect_aerial_ids(plistlib.load(handle)), [MORNING, MORNING])

    def test_dry_run_does_not_write(self):
        self.write_store(make_store(MORNING))
        self.assertEqual(self.run_main("21:00", "--dry-run"), 0)
        self.assertEqual(self.read_ids(), [MORNING, MORNING])
        self.assertFalse(os.path.exists(self.store + ".bak"))

    def test_forced_period(self):
        self.write_store(make_store(MORNING))
        self.assertEqual(ws.main(
            ["--config", self.cfg, "--store", self.store, "--period", "day", "--no-restart"]
        ), 0)
        self.assertEqual(self.read_ids(), [DAY, DAY])

    def test_no_aerial_is_an_error(self):
        data = {"Displays": {"X": {"Content": {"Choices": [
            {"Provider": "com.apple.wallpaper.choice.image", "Configuration": b"x"}
        ]}}}}
        self.write_store(data)
        self.assertEqual(self.run_main("12:00"), 1)

    def test_missing_store_is_an_error(self):
        self.assertEqual(self.run_main("12:00"), 1)

    def test_launch_agent_matches_schedule(self):
        periods = ws.load_periods(self.cfg)
        agent = ws.build_launch_agent(periods, "/x/script.py", "/usr/bin/python3", ws.DEFAULT_CONFIG)
        times = [(i["Hour"], i["Minute"]) for i in agent["StartCalendarInterval"]]
        self.assertEqual(times, [(6, 0), (10, 0), (17, 0), (19, 30)])
        self.assertTrue(agent["RunAtLoad"])
        plistlib.dumps(agent)


if __name__ == "__main__":
    unittest.main()
