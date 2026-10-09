"""Builds worldmap.json (country shapes for the News market map) from world-atlas (Natural Earth, public domain).
A one-off (the file is kept in the repo, nothing runs this on a schedule). To rebuild: download the npm packages
world-atlas 2.0.2 and i18n-iso-countries 7.11.0 into one folder (each unpacked as <name>-<version>/package), then
python3 scripts/build_worldmap.py <that folder> worldmap.json"""
import json, math, sys
G = sys.argv[1]
t110 = json.load(open(f"{G}/world-atlas-2.0.2/package/countries-110m.json"))
t50 = json.load(open(f"{G}/world-atlas-2.0.2/package/countries-50m.json"))
num2a2 = {c[2]: c[0] for c in json.load(open(f"{G}/i18n-iso-countries-7.11.0/package/codes.json"))}
NAMES = json.load(open(f"{G}/i18n-iso-countries-7.11.0/package/langs/en.json"))["countries"]
W = 2000

def proj(lon, lat):
    l, p = math.radians(lon), math.radians(lat)
    p2 = p * p; p4 = p2 * p2
    x = l * (0.870700 - 0.131979 * p2 - 0.013791 * p4 + 0.003971 * p4 * p4 * p2 - 0.001529 * p4 * p4 * p4)
    y = p * (1.007226 + 0.015085 * p2 - 0.044475 * p4 * p2 + 0.028874 * p4 * p4 - 0.005916 * p4 * p4 * p2)
    return x, y
XM = proj(180, 0)[0]; YT, YB = proj(0, 84)[1], proj(0, -58)[1]
S = W / (2 * XM)
H = round((YT - YB) * S)
def xy(lon, lat):
    x, y = proj(max(-200, min(200, lon)), max(-58, min(84, lat)))
    return (x + XM) * S, (YT - y) * S

def arcs_of(topo):
    tr = topo["transform"]; sx, sy = tr["scale"]; tx, ty = tr["translate"]
    out = []
    for a in topo["arcs"]:
        x = y = 0; pts = []
        for dx, dy in a:
            x += dx; y += dy
            pts.append((x * sx + tx, y * sy + ty))
        out.append(pts)
    return out

def ring(arcs, idx):
    pts = []
    for i in idx:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts += a[1:] if pts else a
    return pts

def side(r):
    """A ring at 180° (Russia, Fiji) can list its edge as +180 and -180, or run across it: keep it all on its own side."""
    n = [lon for lon, _ in r if abs(lon) < 179.9]
    s = 1 if sum(1 if lon > 0 else -1 for lon in n) >= 0 else -1
    if any(abs(a[0] - b[0]) > 180 for a, b in zip(r, r[1:])):  # the ring itself crosses 180°: carry it on past the edge
        return [(lon + 360 * s if lon * s < 0 else lon, lat) for lon, lat in r]
    return [(180 * s if abs(lon) >= 179.9 else lon, lat) for lon, lat in r]


def polys(arcs, g):
    if g["type"] == "Polygon":
        return [[side(ring(arcs, r)) for r in g["arcs"]]]
    if g["type"] == "MultiPolygon":
        return [[side(ring(arcs, r)) for r in p] for p in g["arcs"]]
    return []

def area(r):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]))) / 2

def code(g):
    if g.get("id") in num2a2:
        return num2a2[g["id"]]
    return {"Kosovo": "XK", "N. Cyprus": "CY", "Somaliland": "SO"}.get(g["properties"]["name"])

out = {}
a110 = arcs_of(t110)
for g in t110["objects"]["countries"]["geometries"]:
    cc = code(g)
    if not cc or cc == "AQ":
        continue
    d, best = [], None
    for p in polys(a110, g):
        for k, r in enumerate(p):
            q = [xy(*pt) for pt in r]
            if k == 0 and (best is None or area(q) > area(best)):
                best = q
            seg, px, py = [], None, None
            for x, y in q:
                ix, iy = round(x), round(y)
                if px is None:
                    seg.append(f"M{ix} {iy}")
                elif (ix, iy) != (px, py):
                    seg.append(f"l{ix - px} {iy - py}")
                px, py = ix, iy
            if len(seg) > 2:
                d.append("".join(seg) + "z")
    if not d:
        continue
    if max(p[0] for p in best) - min(p[0] for p in best) > W / 2:  # crosses 180° (Russia, Fiji): the bigger side
        l, r = [p for p in best if p[0] < W / 2], [p for p in best if p[0] >= W / 2]
        best = l if len(l) > len(r) else r
    xs, ys = [p[0] for p in best], [p[1] for p in best]
    e = out.setdefault(cc, {"n": NAMES.get(cc, g["properties"]["name"]), "d": ""})
    if isinstance(e["n"], list):
        e["n"] = e["n"][0]
    e["d"] += "".join(d)
    if "b" not in e:  # the main landmass (Alaska, overseas territories left out of the zoom)
        e["b"] = [round(min(xs)), round(min(ys)), round(max(xs) - min(xs)), round(max(ys) - min(ys))]
# small countries the 110m map leaves out (Singapore, Monaco, Hong Kong...): a dot at their centre
a50 = arcs_of(t50)
for g in t50["objects"]["countries"]["geometries"]:
    cc = code(g)
    if not cc or cc in out or cc == "AQ":
        continue
    rings = [p[0] for p in polys(a50, g)]
    if not rings:
        continue
    r = max(rings, key=area)
    lon = sum(p[0] for p in r) / len(r); lat = sum(p[1] for p in r) / len(r)
    x, y = xy(lon, lat)
    n = NAMES.get(cc, g["properties"]["name"])
    out[cc] = {"n": n[0] if isinstance(n, list) else n, "p": [round(x), round(y)]}
SHORT = {"US": "United States", "RU": "Russia", "KR": "South Korea", "KP": "North Korea", "GB": "United Kingdom",
         "IR": "Iran", "SY": "Syria", "VN": "Vietnam", "LA": "Laos", "BO": "Bolivia", "VE": "Venezuela", "TZ": "Tanzania",
         "MD": "Moldova", "CZ": "Czechia", "TW": "Taiwan", "XK": "Kosovo", "CD": "DR Congo", "CG": "Congo", "CN": "China", "MK": "North Macedonia", "VA": "Vatican City", "FK": "Falkland Islands", "FM": "Micronesia"}
for cc, n in SHORT.items():
    if cc in out:
        out[cc]["n"] = n
json.dump({"w": W, "h": H, "c": out}, open(sys.argv[2], "w"), separators=(",", ":"), ensure_ascii=False)
print(len(out), "countries", W, H)
