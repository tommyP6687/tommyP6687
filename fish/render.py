#!/usr/bin/env python3
"""Render fish.svg whose mood follows your GitHub contribution activity.

Moods, from best to worst: happy -> tired1 -> tired2 -> sleep

Usage
  python fish/render.py                 # fetch your contributions, write fish.svg
  python fish/render.py --state tired2  # force a mood (for previews)

Env
  GH_LOGIN  GitHub username to read (default: tommyP6687)
  GH_TOKEN  token for the GraphQL API (the workflow passes one in)
"""
import argparse
import base64
import datetime as dt
import json
import os
import pathlib
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
STATES = ["happy", "tired1", "tired2", "sleep"]

# ---------------------------------------------------------------- mood logic

# Days since your last contribution -> mood level (0 happy .. 3 sleep)
IDLE_LEVELS = [(1, 0), (3, 1), (6, 2)]          # <=1 happy, <=3 tired1, <=6 tired2, else sleep
# Active days in the last 14 -> mood level
ACTIVE_LEVELS = [(8, 0), (4, 1), (1, 2)]        # >=8 happy, >=4 tired1, >=1 tired2, 0 sleep


def fetch_days(login, token):
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
    }"""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        raise SystemExit(f"GraphQL error: {data['errors']}")
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [(dt.date.fromisoformat(d["date"]), d["contributionCount"])
            for w in weeks for d in w["contributionDays"]]
    return sorted(days)


def pick_state(days):
    today = days[-1][0]
    active = [d for d, c in days if c > 0]
    idle = (today - active[-1]).days if active else 999
    active14 = sum(1 for d, c in days if c > 0 and (today - d).days < 14)

    idle_lvl = next((lvl for limit, lvl in IDLE_LEVELS if idle <= limit), 3)
    act_lvl = next((lvl for limit, lvl in ACTIVE_LEVELS if active14 >= limit), 3)
    level = max(idle_lvl, act_lvl)                # the worse of the two wins
    print(f"idle_days={idle} active_last_14={active14} -> {STATES[level]}")
    return STATES[level]

# ---------------------------------------------------------------- rendering

# Per-mood animation settings
#   swim   seconds for one lap across the tank (0 = stay in place)
#   bob    seconds for one up/down bob, amp = bob height in px
#   blink  (seconds between blinks, fraction of time eyes stay closed)
#   y      vertical position of the fish, tilt = nose-down degrees
STYLE = {
    "happy":  dict(swim=9,  bob=1.4, amp=8, blink=(4.0, 0.04), y=60,  tilt=0),
    "tired1": dict(swim=18, bob=2.6, amp=6, blink=(3.0, 0.12), y=80,  tilt=3),
    "tired2": dict(swim=0,  bob=4.0, amp=4, blink=(2.5, 0.35), y=110, tilt=6),
    "sleep":  dict(swim=0,  bob=6.0, amp=3, blink=None,        y=150, tilt=9),
}

W, H = 800, 340          # canvas
FW, FH = 300, 126        # drawn fish size (art is 1520x640)


def data_uri(name):
    b64 = base64.b64encode((HERE / f"{name}.gif").read_bytes()).decode()
    return f"data:image/gif;base64,{b64}"


def render(state):
    s = STYLE[state]
    closed = "sleep"
    css = []

    # Swimming lap: right, turn, left, turn
    travel = W - FW - 60
    if s["swim"]:
        css.append(f"""
.swim {{ animation: swim {s['swim']}s ease-in-out infinite; }}
@keyframes swim {{
  0%   {{ transform: translateX(0px); }}
  45%  {{ transform: translateX({travel}px); }}
  50%  {{ transform: translateX({travel}px); }}
  95%  {{ transform: translateX(0px); }}
  100% {{ transform: translateX(0px); }}
}}
.flip {{ animation: flip {s['swim']}s linear infinite; transform-box: fill-box; transform-origin: center; }}
@keyframes flip {{
  0%, 45%   {{ transform: scaleX(1); }}
  50%, 95%  {{ transform: scaleX(-1); }}
  100%      {{ transform: scaleX(1); }}
}}""")
        x0 = 30
    else:
        x0 = (W - FW) // 2

    css.append(f"""
.bob {{ animation: bob {s['bob']}s ease-in-out infinite; }}
@keyframes bob {{
  0%, 100% {{ transform: translateY(0px); }}
  50%      {{ transform: translateY({s['amp']}px); }}
}}""")

    # Blink by fading the closed-eye frame in and out
    if s["blink"]:
        period, frac = s["blink"]
        on = 100 - frac * 100
        css.append(f"""
.closed {{ opacity: 0; animation: blink {period}s steps(1) infinite; }}
@keyframes blink {{
  0%, {on:.1f}% {{ opacity: 0; }}
  {on:.1f}%, 100% {{ opacity: 1; }}
}}""")

    # Bubbles (happy/tired) or Zs (sleep)
    floaters = ""
    if state == "sleep":
        css.append("""
.z { font: bold 28px monospace; fill: #4a6a8a; opacity: 0; animation: z 6s ease-out infinite; }
.z2 { animation-delay: 2s; } .z3 { animation-delay: 4s; }
@keyframes z {
  0%   { opacity: 0; transform: translate(0px, 0px); }
  20%  { opacity: 1; }
  100% { opacity: 0; transform: translate(40px, -90px); }
}""")
        zx, zy = x0 + FW - 40, s["y"] + 10
        floaters = "".join(
            f'<text class="z {c}" x="{zx}" y="{zy}">{t}</text>'
            for c, t in [("z1", "z"), ("z2", "Z"), ("z3", "z")])
    else:
        n = {"happy": 6, "tired1": 3, "tired2": 1}[state]
        css.append("""
.bubble { fill: none; stroke: #ffffffcc; stroke-width: 2; animation: rise 5s linear infinite; }
@keyframes rise {
  0%   { transform: translateY(0px); opacity: 0; }
  10%  { opacity: 1; }
  100% { transform: translateY(-300px); opacity: 0; }
}""")
        for i in range(n):
            bx = 80 + i * (W - 160) // max(n, 1)
            floaters += (f'<circle class="bubble" cx="{bx}" cy="{H - 30}" r="{5 + i % 3 * 2}" '
                         f'style="animation-delay:{i * 0.9:.1f}s"/>')

    fish = (f'<image href="{data_uri(state)}" width="{FW}" height="{FH}" '
            f'style="image-rendering: pixelated"/>')
    if s["blink"]:
        fish += (f'<image class="closed" href="{data_uri(closed)}" width="{FW}" height="{FH}" '
                 f'style="image-rendering: pixelated"/>')

    fish_group = (f'<g transform="rotate({s["tilt"]} {FW // 2} {FH // 2})">{fish}</g>')
    if s["swim"]:
        fish_group = f'<g class="flip">{fish_group}</g>'
    fish_group = f'<g class="bob">{fish_group}</g>'
    if s["swim"]:
        fish_group = f'<g class="swim">{fish_group}</g>'

    label = {"happy": "happy", "tired1": "a little tired", "tired2": "very tired",
             "sleep": "asleep"}[state]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<title>Pufferfish is {label}</title>
<style>{''.join(css)}</style>
<defs>
  <linearGradient id="water" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#bfe6f5"/><stop offset="1" stop-color="#5fa8c9"/>
  </linearGradient>
</defs>
<rect width="{W}" height="{H}" rx="18" fill="url(#water)"/>
<path d="M0 {H - 28} Q {W // 4} {H - 44} {W // 2} {H - 30} T {W} {H - 32} V {H} H 0 Z" fill="#e8d8a8"/>
{floaters}
<g transform="translate({x0} {s['y']})">{fish_group}</g>
<text x="{W - 16}" y="28" text-anchor="end" font-family="monospace" font-size="16" fill="#1d3b4f">mood: {label}</text>
</svg>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", choices=STATES)
    ap.add_argument("--out", default=str(ROOT / "fish.svg"))
    args = ap.parse_args()

    state = args.state
    if not state:
        days = fetch_days(os.environ.get("GH_LOGIN", "tommyP6687"), os.environ["GH_TOKEN"])
        state = pick_state(days)
    pathlib.Path(args.out).write_text(render(state))
    print(f"wrote {args.out} ({state})")


if __name__ == "__main__":
    main()
