"""One-off: layout of Spazio Tennis entry-list posts (WordPress API)."""
import re, json, urllib.request
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
get = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=40).read().decode("utf-8", "replace")
posts = json.loads(get("https://www.spaziotennis.com/wp-json/wp/v2/posts?categories=5103&per_page=40&_fields=id,date,modified,link,title"))
for p in posts:
    print(p["date"][:10], p["modified"][:10], p["title"]["rendered"], p["link"])
for want in ["week-41", "vienna-2026", "basilea-2026"]:
    p = next((p for p in posts if want in p["link"]), None)
    if not p: print("no post", want); continue
    c = json.loads(get(f"https://www.spaziotennis.com/wp-json/wp/v2/posts/{p['id']}?_fields=content"))["content"]["rendered"]
    i = c.find("ENTRY LIST ATP") if "week" in want else c.find("<table")
    print("\n#####", want, len(c)); print(c[max(0, i - 500): i + 5000])
    j = c.find("ALTERNATE")
    print("\n--- alternates:", c[j - 300: j + 1500] if j > 0 else "none")
