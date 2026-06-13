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

## Staying awake (two separate requirements)

You do **not** need a Terminal or Claude session open — launchd runs the job standalone.
But the Mac must be (1) powered on and (2) awake at 01:00. Two distinct things keep it running:

1. **Wake at 01:00.** launchd's calendar trigger does **not** wake a sleeping Mac — if it's
   asleep at 01:00, the job fires on the *next* wake (i.e. when you open it), not at 01:00.
   To guarantee a wall-clock run, schedule a wake ~5 min early:
   ```bash
   sudo pmset repeat wake MTWRFSU 00:55:00
   pmset -g sched   # confirm the repeating wake is listed
   ```
2. **Stay awake through the 45-min render.** `scripts/overnight.sh` re-execs itself under
   `caffeinate -i -s`, holding an idle/system-sleep assertion for the whole run so the Mac
   can't doze off mid-render. Nothing to configure — it's built in.

Also keep it **on AC power** — a closed-lid MacBook on battery sleeps regardless of the
above. Simplest reliable setup: plugged in, lid open (display can sleep), `pmset` wake set.

## Notes
- Logs: per-day `logs/overnight-YYYY-MM-DD.log` (full transcript) + `logs/launchd.{out,err}.log`.
- A macOS notification fires on completion with the produced-status summary.
