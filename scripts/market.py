"""
72 Central - Market map (runs right after news.py in news.yml, no Claude, no paid services).

Builds market.json for the News page's "Market map": the business of tennis country by country over the last 7 days
(sponsors, investors, broadcasters, federations, new or moved tournaments...), and, under them, each country's wider
business and investment news in the sectors in SECTORS (insurance, healthcare, food, banking, energy, sport, tech)
plus war and conflict.

Where the stories come from:
  - news.json's business and tournament stories (news.py), and
  - Google News searches (free, public RSS), two per country in PLACES (tennis business; then sector business and
    war news, SECTOR_QUERY), a few countries each run (SEARCH_PER_RUN), so every country is searched a few times a
    day and smaller markets are covered too. A sector story must name the country searched in its headline, be a
    money / business move (W_MONEY; war news needs no money word) and is labelled with its sector ("sec").
Each story is tagged with the countries it is about, without guessing: the country, its people ("Spanish"), its
cities, tournaments and federation named in the headline (or, for news.json stories, the summary). A search result
is kept for the country searched only if its headline names that country or no other country. Only business and
tournament stories (news.topic) are kept, the same story from several outlets is grouped (best-known outlet leads,
news.BEST), and the page shows each country's 10 most relevant: more outlets, the country in the headline,
business before tournament news, newer first.
"""
import json, os, re, sys
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

sys.path.insert(0, os.path.dirname(__file__))
import news
from news import norm, words, topic, rank, fetch, items, NOW, TODAY

OUT = "market.json"
POOL = "market_pool.json"  # every story seen in the last 7 days (the page never loads it)
KEEP_D = 7
SEARCH_PER_RUN = 8
# ISO code -> words that place a story there (matched as whole words, any accents, lower case). Words that are also
#   something else are left out on purpose: Georgia, Jordan, "Indian" (Indian Wells), Nice, Santiago, Austin, Florence.
PLACES = {
    "GB": "united kingdom|uk|u k|britain|british|england|scotland|scottish|wales|welsh|london|wimbledon|all england club|queen s club|eastbourne|nottingham|birmingham|manchester|edinburgh|glasgow|ilkley|lta",
    "US": "united states|usa|u s|america|american|americans|us open|usta|new york|flushing meadows|indian wells|miami|cincinnati|washington|atlanta|charleston|dallas|houston|delray beach|winston salem|los angeles|san diego|las vegas|chicago|boston|florida|california|texas",
    "FR": "france|french|paris|roland garros|fft|lyon|marseille|montpellier|metz",
    "ES": "spain|spanish|madrid|barcelona|valencia|mallorca|majorca|marbella|rfet",
    "IT": "italy|italian|rome|turin|milan|naples|bologna|fitp|internazionali",
    "DE": "germany|german|halle|hamburg|munich|stuttgart|berlin|bad homburg|dtb",
    "AU": "australia|australian|tennis australia|melbourne|sydney|brisbane|adelaide|perth|hobart|australian open",
    "CA": "canada|canadian|toronto|montreal|vancouver|tennis canada|national bank open",
    "MX": "mexico|mexican|acapulco|monterrey|guadalajara|merida|los cabos",
    "BR": "brazil|brazilian|rio de janeiro|sao paulo",
    "AR": "argentina|argentine|argentinian|buenos aires|cordoba",
    "CL": "chile|chilean",
    "CO": "colombia|colombian|bogota",
    "CN": "china|chinese|beijing|shanghai|wuhan|shenzhen|zhuhai|chengdu|guangzhou|ningbo|hangzhou|china open",
    "HK": "hong kong",
    "TW": "taiwan|taipei",
    "JP": "japan|japanese|tokyo|osaka",
    "KR": "south korea|korea|korean|seoul",
    "IN": "india|delhi|mumbai|pune|bengaluru|bangalore|chennai|aita",
    "SG": "singapore",
    "MY": "malaysia|malaysian|kuala lumpur",
    "TH": "thailand|thai|bangkok|hua hin",
    "ID": "indonesia|indonesian|jakarta|bali",
    "VN": "vietnam|vietnamese|hanoi",
    "PH": "philippines|philippine|filipino|filipina|manila",
    "KZ": "kazakhstan|kazakh|astana|almaty",
    "SA": "saudi|saudi arabia|riyadh|jeddah|six kings slam|pif",
    "AE": "uae|united arab emirates|emirati|dubai|abu dhabi",
    "QA": "qatar|qatari|doha",
    "BH": "bahrain|manama",
    "IL": "israel|israeli|tel aviv",
    "TR": "turkey|turkiye|turkish|istanbul|antalya",
    "EG": "egypt|egyptian|cairo|sharm el sheikh",
    "MA": "morocco|moroccan|marrakech|rabat",
    "ZA": "south africa|south african|cape town|johannesburg",
    "NZ": "new zealand|auckland",
    "CH": "switzerland|swiss|basel|gstaad|geneva|zurich|lausanne",
    "AT": "austria|austrian|vienna|kitzbuhel|linz",
    "NL": "netherlands|dutch|holland|rotterdam|s hertogenbosch|amsterdam",
    "BE": "belgium|belgian|antwerp|brussels",
    "SE": "sweden|swedish|stockholm|bastad",
    "NO": "norway|norwegian|oslo",
    "DK": "denmark|danish|copenhagen",
    "FI": "finland|finnish|helsinki",
    "IE": "ireland|irish|dublin",
    "PT": "portugal|portuguese|lisbon|estoril|porto",
    "GR": "greece|greek|athens",
    "PL": "poland|polish|warsaw|krakow",
    "CZ": "czech|czechia|czech republic|prague|ostrava",
    "SK": "slovakia|slovak|bratislava",
    "HU": "hungary|hungarian|budapest",
    "RO": "romania|romanian|bucharest|cluj",
    "RS": "serbia|serbian|belgrade",
    "HR": "croatia|croatian|zagreb|umag",
    "UA": "ukraine|ukrainian|kyiv",
    "RU": "russia|russian|moscow|st petersburg",
    "MC": "monaco|monte carlo|monegasque",
    "PE": "peru|peruvian|lima",
    "TN": "tunisia|tunisian|tunis",
    "BG": "bulgaria|bulgarian",
    "UZ": "uzbekistan|uzbek|tashkent",
}
PLACES = {cc: [" " + w + " " for w in v.split("|")] for cc, v in PLACES.items()}
# the searches: Google News, English (UK) edition; the country's own name is quoted in the search
NAME = {"GB": "United Kingdom", "US": "United States", "KR": "South Korea", "CZ": "Czech Republic", "AE": "UAE"}
QUERY = ("https://news.google.com/rss/search?hl=en-GB&gl=GB&ceid=GB:en&q=tennis+%22{c}%22+(sponsor+OR+sponsorship+OR+"
         "investment+OR+investor+OR+partnership+OR+deal+OR+broadcast+OR+%22media+rights%22+OR+CEO+OR+tournament+OR+"
         "academy+OR+acquisition+OR+venue)+when:7d")
# the wider business search: investment and business moves in the SECTORS below (incl. energy and banking), plus war news
SECTOR_QUERY = ("https://news.google.com/rss/search?hl=en-GB&gl=GB&ceid=GB:en&q=%22{c}%22+(investment+OR+invests+OR+"
                "investor+OR+acquisition+OR+acquires+OR+funding+OR+stake+OR+merger+OR+deal+OR+expansion+OR+war+OR+"
                "ceasefire+OR+sanctions)+(sport+OR+tech+OR+AI+OR+food+OR+insurance+OR+insurer+OR+healthcare+OR+"
                "hospital+OR+pharma+OR+energy+OR+oil+OR+gas+OR+bank+OR+banking+OR+military+OR+war)+when:7d")
# sector -> words (whole words in the headline); the first sector that matches is the label (war first: "drone
#   strikes on the energy grid" is war news; tech before energy: a phone's battery isn't energy). To add a sector
#   (retail, property...), add a line here and a word for it in SECTOR_QUERY.
SECTORS = {
    "War & conflict": "war wars invasion ceasefire truce missile missiles drone drones troops military defence defense "
                      "shelling airstrike airstrikes frontline offensive sanctions conflict army",
    "Insurance": "insurance insurer insurers reinsurance reinsurer insurtech underwriter",
    "Healthcare": "healthcare health hospital hospitals pharma pharmaceutical pharmaceuticals biotech medical clinic "
                  "clinics medtech drugmaker drugmakers vaccine vaccines",
    "Food": "food foods beverage beverages drinks restaurant restaurants grocery groceries supermarket supermarkets "
            "agriculture agri agritech dairy snack snacks brewer brewery coffee",
    "Banking": "bank banks banking banker bankers lender lenders fintech neobank mortgage mortgages",
    "Sport": "sport sports football soccer league stadium olympic olympics golf cricket rugby basketball nba nfl "
             "f1 athletics esports",
    "Tech": "tech technology ai software startup startups chip chips semiconductor semiconductors datacenter cloud "
            "fintech telecom telecoms 5g cyber cybersecurity digital robotics",
    "Energy": "energy oil gas lng petroleum refinery refineries pipeline pipelines power solar wind renewable renewables "
              "nuclear hydrogen battery batteries grid electricity utility utilities",
}
SECTORS = {k: set(v.split()) for k, v in SECTORS.items()}
W_MONEY = set("""invest invests invested investing investment investments investor investors stake stakes acquire
acquires acquired acquisition acquisitions buys bought buyout merger merge merges funding fund raises raised ipo
listing valuation deal deals partnership expansion expands expand launches opens plant factory billion million
contract contracts takeover""".split())
# share-price notes, crime and obituaries aren't market moves
W_NOISE = set("shares stock stocks analyst analysts dividend outperform overweight underweight downgrade obituary".split())
W_NOISE_PH = ["price target", "target price", "raises target", "cuts target"]


def sector(t):
    """A sector story's label, or "" if the headline isn't one (see SECTORS, W_MONEY)."""
    tn, tw = norm(t), set(norm(t).split())
    if tw & W_NOISE or any(f" {p} " in tn for p in W_NOISE_PH):
        return ""
    if " artificial intelligence " in tn or " data centre " in tn or " data center " in tn:
        tw = tw | {"ai"}
    for sec, ws in SECTORS.items():
        if tw & ws and (sec == "War & conflict" or tw & W_MONEY):
            return sec
    return ""


def places(t):
    """Countries named in a text (norm'd), as a set of codes."""
    return {cc for cc, ws in PLACES.items() if any(w in t for w in ws)}


def main():
    try:
        old = json.load(open(OUT))
    except Exception:
        old = {}
    wm = json.load(open("worldmap.json"))["c"]
    cut = NOW - timedelta(days=KEEP_D)
    try:
        pool = [x for x in json.load(open(POOL)) if x["at"] >= cut.strftime("%Y-%m-%dT%H:%M:%SZ")]
    except Exception:
        pool = []

    # 1) this run's searches: the countries searched longest ago. Our players' nations (the roster list brands.py saves)
    #    go first on a tie and count as due 4 hours sooner, so they are searched about twice as often
    done = old.get("searched") or {}
    try:
        ros = set(json.load(open("brands.json")).get("roster") or [])
    except Exception:
        ros = set()

    def due(c):
        t = done.get(c, "")
        if t and c in ros:
            t = (datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ") - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return (t, c not in ros)
    todo = sorted(PLACES, key=due)[:SEARCH_PER_RUN]
    errs = {}
    pros, fulls = set(), set()
    try:
        sq = json.load(open("scouting.json"))
        for t in ("atp", "wta"):
            for row in (sq.get(t) or {}).get("players") or []:
                w = norm(row[1]).split()
                if row[0] <= 500 and w and len(w[-1]) >= 4:
                    pros.add(w[-1])
                if row[0] <= 500 and len(w) > 1:
                    fulls.add(f" {w[0]} {w[-1]} ")
    except Exception:
        pass
    for cc in todo:
        name = NAME.get(cc) or wm.get(cc, {}).get("n") or cc
        try:
            its = items(fetch(QUERY.format(c=quote_plus(name))))
            its += items(fetch(SECTOR_QUERY.format(c=quote_plus(name))))
        except Exception as e:
            errs[cc] = str(e)[:200]
            print(f"{cc}: search failed ({e})")
            continue
        done[cc] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
        kept = ksec = 0
        for t, u, d, at, _img, src in its:
            if at < cut or at > NOW + timedelta(hours=1):
                continue
            if len(re.sub(r"[^A-Za-z]", "", t)) < 0.6 * len(t.replace(" ", "")):
                continue  # not English
            tn, tw = norm(t), set(norm(t).split())
            named = places(tn) | ({cc} if f" {norm(name).strip()} " in tn else set())
            row = {"t": t, "u": u, "s": src or "Google News", "at": at.strftime("%Y-%m-%dT%H:%M:%SZ")}
            k = topic(t, "")
            if k and (tw & news.TENNIS or news.pro_named(t, pros, fulls) or re.search(r"\b[A-Z][a-z]+ Open\b", t)):
                if named and cc not in named:
                    continue  # about somewhere else
                pool.append(dict(row, k=k, c=sorted(named | {cc}), h=sorted(named)))
                kept += 1
                continue
            # not tennis: a sector story, only if its headline names the country searched
            sec = sector(t)
            if sec and cc in named:
                pool.append(dict(row, k="mkt", sec=sec, c=sorted(named), h=sorted(named)))
                ksec += 1
        print(f"{cc} ({name}): {len(its)} results, {kept} tennis business stories, {ksec} sector stories")

    # 2) news.json's business and tournament stories (headline or summary names the country)
    try:
        nj = json.load(open("news.json"))
    except Exception:
        nj = {}
    for x in nj.get("items") or []:
        if not x.get("k") or x["at"] < cut.strftime("%Y-%m-%dT%H:%M:%SZ"):
            continue
        h = places(norm(x["t"]))
        c = h or places(norm(x.get("d") or ""))
        if not c:
            continue
        for y in [x] + (x.get("also") or []):
            pool.append({"t": x["t"], "u": y["u"], "s": y["s"], "at": x["at"], "k": x["k"], "c": sorted(c), "h": sorted(h)})

    # 3) one copy per link, then the same story from several outlets grouped (key words, as news.py does)
    seen, rows = set(), []
    for x in sorted(pool, key=lambda x: x["at"], reverse=True):
        if x["u"] in seen:
            continue
        seen.add(x["u"])
        rows.append(x)
    groups = []
    for x in rows:
        w = words(x["t"])
        for g in groups:
            c = len(w & g["w"])
            if c >= 3 and c >= 0.6 * min(len(w), len(g["w"])) and set(x["c"]) & set(g["c"]):
                g["x"].append(x)
                break
        else:
            groups.append({"w": w, "c": list(x["c"]), "x": [x]})
    stories = []
    for g in groups:
        xs = sorted(g["x"], key=lambda x: (rank(x["s"]), x["at"]))
        lead = xs[0]
        outlets = len({x["s"] for x in xs})
        age = (NOW - datetime.strptime(max(x["at"] for x in xs), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds() / 86400
        c = sorted({cc for x in xs for cc in x["c"]})
        h = sorted({cc for x in xs for cc in x["h"]})
        st = {"t": lead["t"], "u": lead["u"], "s": lead["s"], "at": max(x["at"] for x in xs), "k": lead["k"],
              "c": c, "h": h, "also": [{"s": x["s"], "u": x["u"]} for x in xs[1:]][:8],
              # tennis business first, then tournament news, then the sector stories
              "score": round(min(outlets, 6) + {"biz": 2, "ev": 1}.get(lead["k"], 0) - age * 0.6, 2)}
        if lead.get("sec"):
            st["sec"] = lead["sec"]
        stories.append(st)

    # 4) each country's top 10 tennis stories, then its top 10 sector stories (a headline naming the country counts 2
    #    more), and the world's top 10 tennis stories
    by = {}
    for i, x in enumerate(stories):
        for cc in x["c"]:
            by.setdefault(cc, []).append((x["score"] + (2 if cc in x["h"] else 0), i))
    keep_i = set()
    top = {}
    for cc, lst in by.items():
        lst = sorted(lst, key=lambda p: (-p[0], p[1]))
        top[cc] = [i for _, i in lst if not stories[i].get("sec")][:10] + [i for _, i in lst if stories[i].get("sec")][:10]
        keep_i |= set(top[cc])
    world = [i for i in sorted(range(len(stories)), key=lambda i: -stories[i]["score"]) if not stories[i].get("sec")][:10]
    keep_i |= set(world)
    idx = {i: n for n, i in enumerate(sorted(keep_i))}
    out_st = [{k: v for k, v in stories[i].items() if k != "h"} for i in sorted(keep_i)]
    new = {"updated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "stories": out_st,
           "top": {cc: [idx[i] for i in v] for cc, v in sorted(top.items())},
           "count": {cc: len(v) for cc, v in sorted(by.items())},
           "world": [idx[i] for i in world], "searched": done, "errors": errs}
    json.dump(sorted(rows, key=lambda x: (x["at"], x["u"]), reverse=True), open(POOL, "w"), ensure_ascii=False, indent=0)
    same = {k: v for k, v in new.items() if k != "updated"} == {k: v for k, v in old.items() if k != "updated"}
    if same:
        print("No new market stories")
        return
    json.dump(new, open(OUT, "w"), ensure_ascii=False, indent=0)
    print(f"Saved {len(out_st)} market stories across {len(top)} countries")


if __name__ == "__main__":
    main()
