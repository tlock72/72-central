"""One-off: how the Tennis Europe acceptance list switches age group (read-only)."""
import re, sys
sys.path.insert(0, "scripts")
import schedule as S

TE = S.te_session()
url = S.TE_SITE + "/sport/acceptancelist.aspx?id=E21AD649-4BBF-42D8-9E7A-204CE395FD27"
b = S.get(url, "te", opener=TE.opener)
for m in re.finditer(r"selectevent_IndexChanged", b):
    print("JS:", b[max(0, m.start() - 300):m.start() + 900].replace("\n", " "))
    print("----")
for m in re.finditer(r"<form[^>]*>", b):
    print("FORM:", m.group(0))
print("hidden:", re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]*)"', b)[:20])
print("scripts:", re.findall(r'<script[^>]*src="([^"]*)"', b))
for cand in ("&event=5786549", "&e=5786549", "&eventid=5786549", "&draw=5786549", "&ev=5786549"):
    p = S.get(url + cand, "te", opener=TE.opener)
    h = re.search(r"<h3>\s*(\S+)\s+(?:Acceptance|Entry) list", p)
    print(cand, "->", h.group(1) if h else None)
