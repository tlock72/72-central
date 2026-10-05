"""One-off: Spazio's Shanghai entry-list post, raw."""
import sys, json, re
sys.path.insert(0, "scripts")
import schedule as S
S.PAUSE["other"] = 0
c = json.loads(S.get(S.SP_API + "/posts/142467?_fields=content"))["content"]["rendered"]
i = c.find("ENTRY LIST ATP MASTERS")
print(len(c)); print(c[i - 200: i + 2500]); j = c.find("ALTERNATE"); print("ALT:", c[j - 300: j + 600] if j > 0 else "none")
cat = json.loads(S.get(S.SP_API + "/categories?slug=ent&_fields=id"))
after = "2026-08-24T00:00:00"
posts = json.loads(S.get(f"{S.SP_API}/posts?categories={cat[0]['id']}&per_page=100&after={after}&_fields=id,date"))
print("posts:", len(posts), "has 142467:", any(p["id"] == 142467 for p in posts), posts[-1])
