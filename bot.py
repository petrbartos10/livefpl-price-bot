import hashlib
import json
import os
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

LIVEFPL_URL = "https://www.livefpl.net/prices"
STATE_FILE = Path("state.json")


def fetch_summary():
    r = requests.get(
        LIVEFPL_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    start = next((i for i, ln in enumerate(lines) if "Already reached target" in ln), None)
    if start is None:
        raise RuntimeError("Block not found.")

    window = lines[start:start + 250]

    pos_price_re = re.compile(r"^(GK|DEF|MID|FW)\s+£\d+(\.\d+)?$")
    pct_re = re.compile(r"^-?\d+(\.\d+)?%$")

    items = []
    i = 0
    while i < len(window):
        if pos_price_re.match(window[i]):
            pos_price = window[i]
            name = window[i - 1] if i - 1 >= 0 else None

            pct = None
            for j in range(i + 1, min(i + 6, len(window))):
                if pct_re.match(window[j]):
                    pct = window[j]
                    break

            if name and pct:
                items.append((name, pos_price, pct))
                i = j + 1
                continue
        i += 1

    risers = []
    fallers = []
    for name, pos_price, pct in items:
        val = float(pct.replace("%", ""))
        if val >= 100:
            risers.append((name, pos_price, pct))
        elif val <= -100:
            fallers.append((name, pos_price, pct))

    return risers, fallers


def format_message(risers, fallers):
    def fmt(lst):
        if not lst:
            return "• (none)"
        return "\n".join([f"• {n} — {pp} — {pct}" for n, pp, pct in lst])

    return (
        "💥 **LiveFPL – Potential Price Changes**\n\n"
        f"📈 **Risers**\n{fmt(risers)}\n\n"
        f"📉 **Fallers**\n{fmt(fallers)}"
    )


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"hash": ""}


def save_state(h):
    STATE_FILE.write_text(json.dumps({"hash": h}))


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def post_discord(webhook_url, content):
    requests.post(webhook_url, json={"content": content})


def main():
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        raise RuntimeError("Missing DISCORD_WEBHOOK_URL")

    risers, fallers = fetch_summary()
    content = format_message(risers, fallers)
    current_hash = sha(content)

    state = load_state()
    if state.get("hash") == current_hash:
        print("No change.")
        return

    post_discord(webhook, content)
    save_state(current_hash)
    print("Posted update.")


if __name__ == "__main__":
    main()
