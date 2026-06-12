# Overnight render — launchd install

Schedules `scripts/overnight.sh` at **01:00 daily** on this Mac (render is local; Railway
can't run the 45-min Chromium render).

## Install
```bash
cp deploy/launchd/com.untoldgame.overnight.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.untoldgame.overnight.plist
launchctl list | grep untoldgame   # confirm it's registered
```

## Run it now (test, without waiting for 01:00)
```bash
launchctl start com.untoldgame.overnight
tail -f logs/overnight-$(date +%Y-%m-%d).log
```

## Uninstall
```bash
launchctl unload ~/Library/LaunchAgents/com.untoldgame.overnight.plist
rm ~/Library/LaunchAgents/com.untoldgame.overnight.plist
```

## Notes
- If the Mac is **asleep** at 01:00, launchd fires on the next wake, not at 01:00. To
  guarantee a wall-clock run, schedule a wake: `sudo pmset repeat wake MTWRFSU 00:55:00`.
- Logs: per-day `logs/overnight-YYYY-MM-DD.log` (full transcript) + `logs/launchd.{out,err}.log`.
- A macOS notification fires on completion with the produced-status summary.
