#!/usr/bin/env python3
"""Help find the Aerial wallpaper IDs to put in config.json.

Default mode: print the Aerial ID(s) currently selected in System Settings.
Pick a wallpaper in System Settings, run this, copy the ID. Repeat for each
wallpaper you want to use.

--catalog: try to list every Aerial macOS knows about (best effort; the
catalog file's layout is not documented and may differ between versions).
"""
from __future__ import annotations

import argparse
import json
import plistlib
import sys

from wallpaper_switch import DEFAULT_STORE, collect_aerial_ids

CATALOG_PATH = "/Library/Application Support/com.apple.idleassetsd/Customer/entries.json"


def show_current(store):
    try:
        with open(store, "rb") as handle:
            data = plistlib.load(handle)
    except FileNotFoundError:
        print(f"Wallpaper store not found: {store}", file=sys.stderr)
        return 1
    ids = sorted({i for i in collect_aerial_ids(data) if i})
    if not ids:
        print(
            "No Aerial wallpaper is selected. Choose one in System Settings > "
            "Wallpaper first.",
            file=sys.stderr,
        )
        return 1
    for asset_id in ids:
        print(asset_id)
    return 0


def show_catalog():
    try:
        with open(CATALOG_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        print(f"Catalog not found: {CATALOG_PATH}", file=sys.stderr)
        return 1
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Could not read the catalog: {exc}", file=sys.stderr)
        return 1

    assets = data.get("assets", []) if isinstance(data, dict) else []
    if not assets:
        print("The catalog has no 'assets' list; use the default mode instead.", file=sys.stderr)
        return 1
    for asset in assets:
        if not isinstance(asset, dict) or "id" not in asset:
            continue
        name = asset.get("localizedNameKey") or asset.get("accessibilityLabel") or ""
        print(f"{asset['id']}  {name}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--catalog", action="store_true", help="list known Aerials (best effort)")
    args = parser.parse_args(argv)
    return show_catalog() if args.catalog else show_current(args.store)


if __name__ == "__main__":
    sys.exit(main())
