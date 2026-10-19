#!/usr/bin/env python3
"""Switch the macOS Aerial wallpaper based on the time of day.

Reads a small JSON config that maps times of day to Aerial wallpaper IDs,
picks the entry that applies right now, and writes it into the wallpaper
store that macOS keeps in ~/Library/Application Support/com.apple.wallpaper.
Python standard library only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys

AERIAL_PROVIDER = "com.apple.wallpaper.choice.aerials"
LABEL = "com.custom.wallpaper-switch"
DEFAULT_CONFIG = os.path.expanduser("~/.config/wallpaper-switch/config.json")
DEFAULT_STORE = os.path.expanduser(
    "~/Library/Application Support/com.apple.wallpaper/Store/Index.plist"
)
LOG_PATH = os.path.expanduser("~/Library/Logs/wallpaper-switch.log")
UUID_RE = re.compile(r"^[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}$")


class ConfigError(Exception):
    """Raised when the config file is missing or invalid."""


def log(message):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def parse_hhmm(text):
    """Turn 'HH:MM' into minutes since midnight."""
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", str(text).strip())
    if not match:
        raise ConfigError(f"Invalid time {text!r}; use HH:MM, e.g. '06:00'.")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ConfigError(f"Invalid time {text!r}; hour must be 0-23, minute 0-59.")
    return hour * 60 + minute


def load_periods(path):
    """Load and validate the list of time periods from the JSON config."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        raise ConfigError(
            f"Config not found: {path}. Copy config.example.json there and fill it in."
        )
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config is not valid JSON ({path}): {exc}")

    entries = raw.get("periods") if isinstance(raw, dict) else None
    if not entries or not isinstance(entries, list):
        raise ConfigError("Config needs a non-empty 'periods' list.")

    periods = []
    seen_starts = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ConfigError("Each period must be an object with name, start, asset_id.")
        name = entry.get("name")
        asset_id = str(entry.get("asset_id", ""))
        if not name:
            raise ConfigError("Each period needs a 'name'.")
        if not UUID_RE.match(asset_id):
            raise ConfigError(
                f"Period '{name}' has an invalid asset_id ({asset_id!r}). "
                "Replace the placeholder with a real wallpaper ID (see list_aerials.py)."
            )
        start = parse_hhmm(entry.get("start"))
        if start in seen_starts:
            raise ConfigError(f"Two periods start at the same time ({entry.get('start')}).")
        seen_starts.add(start)
        periods.append({"name": name, "start": start, "asset_id": asset_id})

    periods.sort(key=lambda p: p["start"])
    return periods


def current_period(periods, minutes):
    """Return the period in effect at `minutes` since midnight.

    Before the first start time of the day, the last period of the previous
    day (e.g. 'night') is still in effect.
    """
    chosen = periods[-1]
    for period in periods:
        if period["start"] <= minutes:
            chosen = period
    return chosen


def make_configuration(asset_id):
    return plistlib.dumps({"assetID": asset_id}, fmt=plistlib.FMT_BINARY)


def read_asset_id(configuration):
    if not isinstance(configuration, (bytes, bytearray)):
        return None
    try:
        decoded = plistlib.loads(bytes(configuration))
    except Exception:
        return None
    if isinstance(decoded, dict):
        value = decoded.get("assetID")
        return value if isinstance(value, str) else None
    return None


def collect_aerial_ids(node):
    """Return the asset ID of every Aerial wallpaper choice in the store."""
    found = []
    if isinstance(node, dict):
        choices = node.get("Choices")
        if isinstance(choices, list):
            for choice in choices:
                if isinstance(choice, dict) and choice.get("Provider") == AERIAL_PROVIDER:
                    found.append(read_asset_id(choice.get("Configuration")))
        for value in node.values():
            found.extend(collect_aerial_ids(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(collect_aerial_ids(value))
    return found


def apply_asset(node, asset_id):
    """Point every Aerial choice at `asset_id`.

    Returns (touched, changed): how many Aerial choices exist, and how many
    actually needed to be rewritten. Non-Aerial wallpapers are left alone.
    """
    touched = changed = 0
    if isinstance(node, dict):
        choices = node.get("Choices")
        if isinstance(choices, list):
            for choice in choices:
                if isinstance(choice, dict) and choice.get("Provider") == AERIAL_PROVIDER:
                    touched += 1
                    current = read_asset_id(choice.get("Configuration"))
                    if current is None or current.lower() != asset_id.lower():
                        choice["Configuration"] = make_configuration(asset_id)
                        changed += 1
        for value in node.values():
            t, c = apply_asset(value, asset_id)
            touched += t
            changed += c
    elif isinstance(node, list):
        for value in node:
            t, c = apply_asset(value, asset_id)
            touched += t
            changed += c
    return touched, changed


def write_store(path, data):
    """Write the plist atomically so a crash can't leave a half-written file."""
    tmp = path + ".tmp"
    with open(tmp, "wb") as handle:
        plistlib.dump(data, handle, fmt=plistlib.FMT_BINARY)
    try:
        shutil.copymode(path, tmp)
    except OSError:
        pass
    os.replace(tmp, path)


def restart_wallpaper_agent():
    subprocess.run(
        ["killall", "WallpaperAgent"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def build_launch_agent(periods, script_path, python_path, config_path):
    """Build the LaunchAgent plist that runs this script at each start time."""
    arguments = [python_path, script_path]
    if os.path.abspath(config_path) != os.path.abspath(DEFAULT_CONFIG):
        arguments += ["--config", os.path.abspath(config_path)]
    return {
        "Label": LABEL,
        "ProgramArguments": arguments,
        "RunAtLoad": True,
        "LimitLoadToSessionType": "Aqua",
        "StartCalendarInterval": [
            {"Hour": p["start"] // 60, "Minute": p["start"] % 60} for p in periods
        ],
        "StandardOutPath": LOG_PATH,
        "StandardErrorPath": LOG_PATH,
    }


def build_parser():
    parser = argparse.ArgumentParser(
        description="Switch the macOS Aerial wallpaper based on the time of day."
    )
    parser.add_argument(
        "--config",
        default=os.environ.get("WALLPAPER_SWITCH_CONFIG", DEFAULT_CONFIG),
        help="path to config.json (default: %(default)s)",
    )
    parser.add_argument(
        "--store", default=DEFAULT_STORE, help="path to the wallpaper Index.plist"
    )
    parser.add_argument("--period", help="force a period by name instead of using the clock")
    parser.add_argument("--now", help="pretend the time is HH:MM (for testing)")
    parser.add_argument(
        "--dry-run", action="store_true", help="show what would change without writing"
    )
    parser.add_argument(
        "--no-restart", action="store_true", help="don't restart WallpaperAgent after writing"
    )
    parser.add_argument(
        "--print-launch-agent",
        action="store_true",
        help="print the LaunchAgent plist for this config and exit",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        periods = load_periods(args.config)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.print_launch_agent:
        agent = build_launch_agent(
            periods, os.path.abspath(__file__), sys.executable, args.config
        )
        sys.stdout.buffer.write(plistlib.dumps(agent))
        return 0

    try:
        if args.period:
            matches = [p for p in periods if p["name"] == args.period]
            if not matches:
                names = ", ".join(p["name"] for p in periods)
                raise ConfigError(f"No period named {args.period!r}. Available: {names}.")
            period = matches[0]
        else:
            if args.now:
                minutes = parse_hhmm(args.now)
            else:
                now = datetime.datetime.now()
                minutes = now.hour * 60 + now.minute
            period = current_period(periods, minutes)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        with open(args.store, "rb") as handle:
            data = plistlib.load(handle)
    except FileNotFoundError:
        print(
            f"error: wallpaper store not found at {args.store}. "
            "This tool needs macOS Sonoma (14) or later.",
            file=sys.stderr,
        )
        return 1
    except (plistlib.InvalidFileException, ValueError, OSError) as exc:
        print(f"error: could not read {args.store}: {exc}", file=sys.stderr)
        return 1

    touched, changed = apply_asset(data, period["asset_id"])
    if touched == 0:
        print(
            "error: no Aerial wallpaper found in the store. Pick any Aerial wallpaper "
            "in System Settings > Wallpaper once, then run this again.",
            file=sys.stderr,
        )
        return 1

    if changed == 0:
        log(f"Already on '{period['name']}' wallpaper; nothing to do.")
        return 0

    if args.dry_run:
        log(f"Would switch {changed} wallpaper(s) to '{period['name']}'.")
        return 0

    backup = args.store + ".bak"
    if not os.path.exists(backup):
        shutil.copy2(args.store, backup)

    write_store(args.store, data)
    if not args.no_restart:
        restart_wallpaper_agent()
    log(f"Switched {changed} wallpaper(s) to '{period['name']}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
