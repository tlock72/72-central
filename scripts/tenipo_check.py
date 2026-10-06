"""One-off test: could a live-score site (Tenipo, tennislive.net...) give us live Challenger scores?
The site is set with the SITE environment variable.

Read-only, a handful of requests, nothing saved. It answers three questions:
  1) Can its live feed be read at all (from GitHub)?
  2) Would a browser on our site be allowed to read it (Access-Control-Allow-Origin)?
  3) What do its robots.txt and terms say?
"""
import os
import re
import urllib.error
import urllib.parse
import urllib.request

SITE = os.environ.get("SITE", "https://tenipo.com").rstrip("/")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
OUR_SITE = "https://tlock72.github.io"

# roster surnames, to see whether 72 players appear in the feed
src = open("scripts/update.py", encoding="utf-8").read()
SURNAMES = sorted({n.split()[-1] for n in re.findall(r'\("([^"]+)", "(?:atp|wta)"\)', src) if len(n.split()[-1]) >= 4})


def get(url, origin=False):
    h = {"User-Agent": UA, "Accept": "*/*", "Referer": SITE + "/"}
    if origin:
        h["Origin"] = OUR_SITE
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=20) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), ""
    except Exception as e:
        return None, {}, f"ERROR {e}"


def hdr(h, name):
    return next((v for k, v in h.items() if k.lower() == name), "")


def show(label, url, origin=False):
    st, h, body = get(url, origin)
    print(f"\n--- {label}: {url}")
    print(f"status {st} | type {hdr(h, 'content-type')} | size {len(body)} | "
          f"allow-origin: {hdr(h, 'access-control-allow-origin') or '(none)'}")
    return st, h, body


print("=" * 70, "\n1) robots.txt")
st, h, robots = show("robots", SITE + "/robots.txt")
print(robots[:1500])

print("=" * 70, "\n2) Home page")
st, h, home = show("home", SITE + "/", origin=True)
t = re.search(r"<title>(.*?)</title>", home, re.S | re.I)
print("title:", t.group(1).strip() if t else "-")
print("mentions 'Challenger':", "challenger" in home.lower())
low = home.lower()
print("72 players named on the page:", [s for s in SURNAMES if re.search(r"\b" + re.escape(s.lower()) + r"\b", low)])
print("score-like text on the page itself:", re.findall(r"\b[0-7]-[0-7]\b", home)[:15])

print("=" * 70, "\n3) Terms / legal pages")
links = set(re.findall(r'href="([^"]+)"', home))
legal = [l for l in links if re.search(r"term|condition|legal|privacy|about|disclaimer|copyright", l, re.I)]
for l in sorted(legal)[:5]:
    u = urllib.parse.urljoin(SITE + "/", l)
    st, h, body = show("legal", u)
    text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"\s+", " ", text)
    for kw in ("scrap", "automat", "robot", "reproduc", "copy", "commercial", "permission", "data", "accuracy"):
        for m in re.finditer(kw, text, re.I):
            print(f"  [{kw}] ...{text[max(0, m.start() - 150):m.end() + 150]}...")
            break

print("=" * 70, "\n4) Looking for the live-score feed")
scripts = re.findall(r'<script[^>]+src="([^"]+)"', home, re.I)
print("scripts:", scripts[:20])
js = home
for s in scripts:
    u = urllib.parse.urljoin(SITE + "/", s)
    if urllib.parse.urlparse(SITE).netloc.replace("www.", "") in urllib.parse.urlparse(u).netloc:
        st, h, body = get(u)
        js += "\n" + body
DOM = urllib.parse.urlparse(SITE).netloc.replace("www.", "")
cands = set()
for m in re.findall(r'["\']((?:https?://[^"\'\s/]+)?/[^"\'\s<>]*\.(?:xml|json|php|txt)[^"\'\s<>]*)["\']', js, re.I):
    cands.add(m)
for m in re.findall(r'["\']((?:https?://[^"\'\s/]+)?/[^"\'\s<>]*(?:live|feed|ajax|xml|api|score)[^"\'\s<>]*)["\']', js, re.I):
    if not re.search(r"\.(css|png|jpg|svg|gif|webp|ico|woff2?)(\?|$)", m, re.I):
        cands.add(m)
cands = {c for c in cands if c.startswith("/") or DOM in urllib.parse.urlparse(c).netloc}
for g in ("/live", "/livescore", "/live-scores", "/challenger", "/atp-challenger/", "/scores", "/scores/", "/live-scores/"):
    cands.add(g)
print(f"{len(cands)} candidate URLs:", sorted(cands)[:40])

best = []
for c in sorted(cands)[:25]:
    u = urllib.parse.urljoin(SITE + "/", c)
    st, h, body = show("candidate", u, origin=True)
    low = body.lower()
    found = [s for s in SURNAMES if re.search(r"\b" + re.escape(s.lower()) + r"\b", low)]
    print(f"  contains 'challenger': {'challenger' in low} | score-like: {bool(re.search(r'[0-7]-[0-7]|[0-7]:[0-7]', body))} "
          f"| 72 players: {found[:10]}")
    print("  start:", re.sub(r"\s+", " ", body[:300]))
    if st == 200 and ("challenger" in low or found):
        best.append((u, hdr(h, "access-control-allow-origin")))

print("=" * 70, "\nSUMMARY")
print("robots.txt read:", bool(robots), "| blocks ordinary visitors (User-agent: *):",
      bool(re.search(r"User-agent:\s*\*\s*\n(?:(?!User-agent).*\n)*?\s*Disallow:\s*/\s*$", robots + "\n", re.M | re.I)))
print("home page readable:", bool(home))
print("feeds with Challenger / 72 data:", best or "none found")
print("browser on our site allowed:", any(a in ("*", OUR_SITE) for _, a in best))
