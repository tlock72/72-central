"""
72 Central - Instagram follower counts for the pro roster, once a week (no Claude, free).

Uses Instagram's own Graph API ("Business Discovery"): an Instagram account we control looks up each
player's public account and reads its exact follower count. Free, no daily cost (19 calls a week).
It works for Business and Creator accounts, which almost every pro uses.

Needs two GitHub secrets (Settings > Secrets and variables > Actions):
  IG_TOKEN    a permanent "System User" token from Meta Business Settings
  IG_USER_ID  the Instagram ID (a long number) of the account doing the lookups. It can be any
              Business/Creator account linked to a Facebook Page we own (a spare one is fine), not the 72 account
Without them it does nothing and the player pages keep the typed numbers in index.html.

Writes social.json: players{id: {ig, followers, at}}. The player pages use it for the Instagram figure.
Accuracy: a player that can't be read keeps last week's number (or the typed one) and is alerted.
A new or changed handle is only used if its count is within half/double the typed number in
index.html, so a wrong handle can't put someone else's followers on a player page.
"""
import json, os, re, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")
NOW = datetime.now(timezone.utc)
TODAY = NOW.astimezone(UK).date().isoformat()
OUT = "social.json"
API = "https://graph.facebook.com/v23.0"

# Roster id -> Instagram handle (without the @). Leave "" if not known yet: the page then keeps the
# typed number. To change a handle, just edit it here; the next run checks it against the typed number.
HANDLES = {
    "deminaur": "alexdeminaur",
    "rublev": "andreyrublev",
    "svitolina": "elisvitolina",
    "kasatkina": "kasatkina",
    "buse": "ignaciobuse",
    "altmaier": "",
    "jabeur": "onsjabeur",
    "monfils": "gael_monfils",
    "bejlek": "sarabejlek",
    "starodubtseva": "",
    "coric": "borna_coric",
    "kym": "",
    "schwaerzler": "",
    "romero": "",
    "kuzuhara": "",
    "sawangkaew": "",
    "jones": "",
    "ristic": "",
}


def typed_counts():
    """The Instagram numbers typed into PROFILES in index.html (from the roster deck)."""
    try:
        src = open("index.html", encoding="utf-8").read()
        src = src[src.index("const PROFILES"):src.index("const JUNIOR_PROFILES")]
    except Exception:
        return {}
    out = {}
    for chunk in src.split('{ id:"')[1:]:
        pid = chunk.split('"', 1)[0]
        m = re.search(r"Instagram:([\d.]+)\*([KM])", chunk)
        if m:
            out[pid] = float(m.group(1)) * (1e3 if m.group(2) == "K" else 1e6)
    return out


def followers(handle, token, uid):
    q = urllib.parse.urlencode({"fields": f"business_discovery.username({handle}){{followers_count,username}}", "access_token": token})
    try:
        with urllib.request.urlopen(f"{API}/{uid}?{q}", timeout=30) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            d = json.load(e)
        except Exception:
            raise RuntimeError(f"HTTP {e.code}")
    if "error" in d:
        err = d["error"]
        raise RuntimeError(f"{err.get('message', 'error')} (code {err.get('code')})")
    n = (d.get("business_discovery") or {}).get("followers_count")
    if not isinstance(n, int):
        raise RuntimeError("no follower count returned")
    return n


def main():
    try:
        old = json.load(open(OUT))
    except Exception:
        old = {}
    players = old.get("players") or {}
    checks = []
    token, uid = os.environ.get("IG_TOKEN"), os.environ.get("IG_USER_ID")
    if not token or not uid:
        checks.append("Instagram followers aren't connected yet (the IG_TOKEN and IG_USER_ID secrets aren't set). "
                      "Player pages show the typed numbers.")
    else:
        typed = typed_counts()
        for pid, handle in HANDLES.items():
            if not handle:
                continue
            prev = players.get(pid) or {}
            try:
                n = followers(handle, token, uid)
            except Exception as e:
                msg = str(e)
                print(pid, handle, "failed:", msg)
                if "code 190" in msg:  # token expired or revoked: every lookup will fail the same way
                    checks.append(f"Instagram followers: the IG_TOKEN secret no longer works ({msg}). Nothing was updated on {TODAY}.")
                    break
                checks.append(f"Instagram followers: couldn't read @{handle} ({pid}) on {TODAY} ({msg}). "
                              "The page keeps the last number. If the handle is wrong, fix it in scripts/instagram.py.")
                continue
            if prev.get("ig") != handle:  # new or changed handle: make sure it's really the player
                t = typed.get(pid)
                if t and not (t / 2 <= n <= t * 2):
                    checks.append(f"Instagram followers: @{handle} has {n:,} followers but {pid}'s page says about {t:,.0f}, "
                                  "so it wasn't used. Check the handle in scripts/instagram.py.")
                    continue
            players[pid] = {"ig": handle, "followers": n, "at": TODAY}
            print(pid, handle, n)
    for pid in [p for p in players if not HANDLES.get(p)]:  # handle removed: stop showing its number
        del players[pid]
    json.dump({"updated": NOW.isoformat(timespec="seconds"), "players": players, "checks": checks},
              open(OUT, "w"), indent=1, ensure_ascii=False)
    for c in checks:
        print(c)


if __name__ == "__main__":
    sys.exit(main())
