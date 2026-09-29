#!/usr/bin/env python3
"""Watch Apple Store in-store pickup availability for a set of part numbers and alert on Discord."""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

# Config (override via env). PARTS format: "PART=Label,PART=Label"
STORE = os.environ.get("STORE", "R275")
LOCALE = os.environ.get("LOCALE", "ch-fr")
MODEL = os.environ.get("MODEL", "iPhone 18 Pro Max 512GB")
PARTS = dict(
    p.split("=", 1)
    for p in os.environ.get(
        "PARTS", "MJXT4QL/A=Black,MJXV4QL/A=Burgundy,MJXW4QL/A=Glacier,MJXU4QL/A=Silver"
    ).split(",")
)
BUY_URL = os.environ.get("BUY_URL", f"https://www.apple.com/{LOCALE}/shop/buy-iphone")
WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")

PICKUP_URL = f"https://www.apple.com/{LOCALE}/shop/retail/pickup-message"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_seen.txt")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36",
    "Referer": BUY_URL,
    "x-skip-redirect": "true",
}

C = {"g": "\033[32m", "r": "\033[31m", "y": "\033[33m", "b": "\033[1m", "d": "\033[2m", "x": "\033[0m"}
SWATCH = {"Black": "⚫", "Silver": "⚪", "White": "⚪", "Glacier": "🔵", "Blue": "🔵", "Burgundy": "🔴", "Orange": "🟠"}


def fetch(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def check():
    params = {"pl": "true", "store": STORE}
    params.update({f"parts.{i}": p for i, p in enumerate(PARTS)})
    data = json.loads(fetch(PICKUP_URL, params))
    store = next(s for s in data["body"]["stores"] if s["storeNumber"] == STORE)
    return store, store["partsAvailability"]


def status(avail, part):
    a = avail.get(part, {})
    return a.get("pickupDisplay", "unknown"), a.get("pickupSearchQuote", "—").replace("\xa0", " ")


def notify_local(title, msg):
    print("\a", end="")
    if sys.platform == "darwin":
        subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "{title}" sound name "Glass"'],
                       check=False, capture_output=True)


def send_discord(store, avail, new, gone):
    fields = []
    for part, label in PARTS.items():
        state, quote = status(avail, part)
        icon = {"available": "✅", "unavailable": "❌"}.get(state, "⚠️")
        tag = " 🆕" if label in new else ""
        fields.append({"name": f"{SWATCH.get(label, '◻️')} {label}{tag}", "value": f"{icon} {quote}", "inline": True})
    desc = f"**{', '.join(sorted(new))}** available for pickup at **Apple {store['storeName']}**"
    if gone:
        desc += f"\n*No longer available: {', '.join(sorted(gone))}*"
    embed = {
        "title": f"📱 {MODEL} in stock",
        "description": desc,
        "color": 0x34C759,
        "fields": fields[:25],
        "footer": {"text": f"Checked • {datetime.now().astimezone():%d/%m/%Y %H:%M %Z}"},
        "url": BUY_URL,
    }
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps({"embeds": [embed]}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": HEADERS["User-Agent"]},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        print(f"  Discord response: {r.status}")


def render(store, avail):
    now = datetime.now().strftime("%a %d %b %Y · %H:%M:%S")
    w = 64
    where = f"Apple {store['storeName']}, {store.get('city', '')}"
    print(f"\n{C['b']}╭{'─' * w}╮")
    print(f"│ 📱 {MODEL:<{w - 4}}│")
    print(f"│ 📍 {where:<{w - 4}}│")
    print(f"│ {C['d']}🕒 {now:<{w - 4}}{C['x']}{C['b']}│")
    print(f"├{'─' * w}┤{C['x']}")
    available = set()
    for part, label in PARTS.items():
        state, quote = status(avail, part)
        if state == "available":
            icon, col = "✅", C["g"]
            available.add(label)
        elif state == "unavailable":
            icon, col = "❌", C["r"]
        else:
            icon, col = "⚠️ ", C["y"]
        name = f"{SWATCH.get(label, '◻️')} {label:<10} {part:<10}"
        print(f"{C['b']}│{C['x']} {name} {icon} {col}{quote[:w - 30]:<{w - 30}}{C['x']}{C['b']}│{C['x']}")
    print(f"{C['b']}╰{'─' * w}╯{C['x']}")
    return available


def load_state():
    if not os.path.exists(STATE_FILE):
        return set()
    with open(STATE_FILE) as f:
        return {line.strip() for line in f if line.strip()}


def save_state(labels):
    with open(STATE_FILE, "w") as f:
        f.write("".join(f"{c}\n" for c in sorted(labels)))


def run_ci(repeat, interval):
    """Headless mode: `repeat` checks spaced by `interval`s, state persisted in STATE_FILE, alerts via Discord."""
    last, failures = load_state(), 0
    for i in range(repeat):
        if i:
            time.sleep(interval)
        try:
            store, avail = check()
        except Exception as e:
            failures += 1
            print(f"! {datetime.now():%H:%M:%S} check failed: {e}", file=sys.stderr)
            continue
        now_avail = render(store, avail)
        new, gone = now_avail - last, last - now_avail
        if new:
            if WEBHOOK:
                send_discord(store, avail, new, gone)
            else:
                print("  ⚠️  DISCORD_WEBHOOK not set — skipping notification.")
        last = now_avail
        save_state(last)
    if failures == repeat:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-i", "--interval", type=int, default=300, help="seconds between checks (default 300)")
    ap.add_argument("--once", action="store_true", help="check once and exit")
    ap.add_argument("--ci", action="store_true", help="headless mode with Discord alerts (GitHub Actions)")
    ap.add_argument("--repeat", type=int, default=1, help="number of checks in --ci mode (default 1)")
    args = ap.parse_args()

    if args.ci:
        return run_ci(args.repeat, args.interval)
    last = set()
    while True:
        try:
            store, avail = check()
            now_avail = render(store, avail)
            if now_avail - last:
                notify_local(f"{MODEL} in stock", ", ".join(sorted(now_avail - last)))
            last = now_avail
        except Exception as e:
            print(f"{C['y']}! {datetime.now():%H:%M:%S} check failed: {e}{C['x']}", file=sys.stderr)
        if args.once:
            break
        print(f"{C['d']}Next check in {args.interval // 60} min (Ctrl+C to stop)…{C['x']}")
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
