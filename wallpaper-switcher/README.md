# wallpaper-switcher

Automatically switches your Mac's Aerial wallpaper through the day: morning, day, sunset, night. Because Aerial wallpapers also show on the lock screen, the lock screen follows along.

It's a small Python script (standard library only) plus a macOS LaunchAgent that runs it at login and at each time you choose.

## How it works

1. `config.json` maps times of day to Aerial wallpaper IDs.
2. `wallpaper_switch.py` picks the entry that applies right now and writes it into the wallpaper store macOS keeps at `~/Library/Application Support/com.apple.wallpaper/Store/Index.plist`.
3. It restarts `WallpaperAgent` so the change shows immediately.
4. A LaunchAgent generated from the same config triggers the script at login and at each start time, so the schedule lives in one place.

Safety features: only Aerial wallpapers are touched, an untouched backup (`Index.plist.bak`) is made on the first change, writes are atomic, nothing is rewritten if the wallpaper is already correct, and placeholder IDs are rejected with a clear error.

## Requirements

- macOS Sonoma (14) or later
- `/usr/bin/python3` (macOS prompts you to install the Command Line Tools if it's missing)

## Install

```bash
git clone <this-repo-url>
cd wallpaper-switcher
./install.sh
```

The first run creates `~/.config/wallpaper-switch/config.json` and stops so you can fill in your wallpaper IDs.

### Find your wallpaper IDs

1. In System Settings > Wallpaper, select the Aerial wallpaper you want for a time of day.
2. Run `python3 ~/Library/Scripts/wallpaper-switch/list_aerials.py` and copy the ID it prints.
3. Repeat for each period and paste the IDs into `config.json`.

`list_aerials.py --catalog` also tries to list every Aerial macOS knows about, but that file's layout is undocumented and may vary by version.

Then run `./install.sh` again. Edit the `start` times in `config.json` and re-run `./install.sh` any time to change the schedule.

## Usage

```bash
python3 wallpaper_switch.py --dry-run        # show what would change
python3 wallpaper_switch.py --period night   # force a period now
python3 wallpaper_switch.py --now 18:30      # pretend it's 18:30
```

Logs go to `~/Library/Logs/wallpaper-switch.log`.

## Uninstall

```bash
./uninstall.sh
```

To restore your original settings, copy `Index.plist.bak` over `Index.plist` and run `killall WallpaperAgent`.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The tests run on any OS using fake wallpaper-store data. They cover time-boundary logic, config validation, backups, idempotence, and LaunchAgent generation.

## Limitations

- The wallpaper store format is undocumented, so a future macOS update could break this. The script fails with an error rather than guessing.
- The tests don't touch a real macOS wallpaper store; check on your own Mac with `--dry-run` first.
- If your Mac is asleep at a scheduled time, launchd runs the job when it wakes, but missed intervals are merged into a single run.

## License

MIT
