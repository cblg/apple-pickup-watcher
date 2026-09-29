# Apple Store Pickup Watcher

Checks in-store pickup availability for a list of Apple part numbers at one Apple Store and posts a Discord embed when something comes into stock. Python stdlib only.

## Setup

1. Add a repository secret **`DISCORD_WEBHOOK`** → your Discord webhook URL
2. Edit the `env:` block in `.github/workflows/check.yml` (`STORE`, `LOCALE`, `MODEL`, `PARTS`, `BUY_URL`)
3. Enable GitHub Actions — runs every 5 min, 5 checks per run (~1/min). Manual trigger via `workflow_dispatch`.

State (`last_seen.txt`) is committed back so only *newly* available items trigger an alert.

## Local

```bash
python3 iphone_finder.py            # loop every 5 min, macOS notification
python3 iphone_finder.py --once     # single check
```
