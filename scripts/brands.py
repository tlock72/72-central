"""
72 Central - Brands on the move (runs after news.py and market.py in news.yml, no Claude, no paid services).

Builds brands.json for the News page's Market map "Brands" view: for each market (every nation on the pro roster,
plus the big markets in MARKETS), which companies are making moves this week, so 72 knows who to approach.

How (no guessing, no AI):
  - Google News searches (free, public RSS), two per market: sponsorship news, and business moves (new marketing
    bosses, expansion, launches, funding, results). Roster nations are searched about every 5 hours, the other
    markets about every 10; SEARCHES_PER_RUN a run.
  - A headline is placed in the market searched unless it names only other countries (market.places).
  - Known brands (BRANDS: about 450, by sector) are found by name in the headline (exact capitals, any accents;
    names that are also everyday words or surnames only in a longer form, e.g. "Wilson Sporting Goods").
  - What the brand is doing comes from the headline's words (SIGNALS): a sports sponsor, a new marketing boss,
    expanding, funding / results, or cooling (cuts, losses, a sponsorship dropped).
  - Each market keeps its top brands (one card per brand with its headlines) and its top "other business moves"
    (headlines with a signal but no known brand). Nothing is kept beyond 7 days.
"""
import json, os, re, sys, unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

sys.path.insert(0, os.path.dirname(__file__))
import news
from news import norm, rank, fetch, items, NOW
from market import places

OUT = "brands.json"
POOL = "brands_pool.json"   # every headline kept this week (the page never loads it)
KEEP_D = 7
SEARCHES_PER_RUN = 10
# roster nations (ROSTER in index.html / update.py) first, then the big markets; ISO codes
ROSTER_NATS = "AU RU PE DE FR UA CZ TH GB TN HR AT CH US BG HK CN ES NL IT HU UZ RO RS IN JP".split()
BIG = "CA BR MX AR SA AE QA KR SG SE".split()
MARKETS = ROSTER_NATS + [c for c in BIG if c not in ROSTER_NATS]
EVERY_H = {"roster": 5, "big": 10}
NAME = {"GB": "United Kingdom", "US": "United States", "KR": "South Korea", "CZ": "Czech Republic", "AE": "UAE",
        "HK": "Hong Kong", "RU": "Russia"}
GN = "https://news.google.com/rss/search?hl=en-GB&gl=GB&ceid=GB:en&q="
QUERIES = [
    "%22{c}%22+(sponsorship+OR+sponsor+OR+%22official+partner%22+OR+%22naming+rights%22+OR+%22brand+ambassador%22)+when:7d",
    "%22{c}%22+(brand+OR+company)+(%22chief+marketing+officer%22+OR+CMO+OR+%22marketing+director%22+OR+expands+OR+"
    "expansion+OR+launches+OR+opens+OR+raises+OR+funding+OR+acquisition+OR+%22record+profit%22)+when:7d",
]

# ---- known brands: "Sector: Name, Name/Alias, ..." (an alias is any other way the headline may write it) ----
BRANDS_TXT = """
Sportswear: Nike, Adidas/adidas, Puma/PUMA, Asics/ASICS, New Balance, Under Armour, Lacoste, Fila/FILA, Yonex, Wilson Sporting Goods/Wilson Sports, Babolat, Le Coq Sportif, Diadora, Hoka/HOKA, On Running/On Holding, Anta/ANTA, Li-Ning/Li Ning, Mizuno, Joma, Kappa, Umbro, Skechers, Lululemon/lululemon, Ellesse, Sergio Tacchini, Castore, Decathlon, JD Sports, Tecnifibre, Dunlop Sport, Slazenger, Fanatics, Canada Goose
Watches & luxury: Rolex, Omega, TAG Heuer, Richard Mille, Hublot, Longines, Audemars Piguet, Patek Philippe, Cartier, Breitling, IWC Schaffhausen/IWC, Swatch, Tissot, Seiko, Casio, Louis Vuitton, LVMH, Gucci, Chanel, Hermès/Hermes, Dior, Prada, Burberry, Ralph Lauren, Hugo Boss, Armani, Moncler, Kering, Richemont, Tiffany, Bulgari/Bvlgari, Montblanc, Ray-Ban, EssilorLuxottica, Oakley, Swarovski
Fashion & retail: Zara, Inditex, H&M, Uniqlo, Fast Retailing, Primark, Marks & Spencer/M&S, El Corte Inglés/El Corte Ingles, Tesco, Sainsbury's, Walmart, Costco, Carrefour, Lidl, Aldi, IKEA, Amazon, Alibaba, JD.com, Shein, Temu, Mercado Libre, Coupang, Woolworths, Wesfarmers, Albert Heijn, Rozetka, Central Group, Majid Al Futtaim, Al-Futtaim, Dubai Duty Free, Pop Mart
Beauty & consumer goods: L'Oréal/L'Oreal, Estée Lauder/Estee Lauder, Sephora, Unilever, Procter & Gamble/P&G, Nivea, Beiersdorf, Gillette, Colgate, Henkel, Shiseido, Clarins, Lancôme/Lancome, Natura, Amorepacific, Godrej, Hindustan Unilever, Haier, Midea, Dyson, Philips, Electrolux, Havaianas
Cars & motoring: Mercedes-Benz/Mercedes, BMW, Audi, Porsche, Volkswagen/VW, Kia, Hyundai, Toyota, Lexus, Honda, Nissan, Peugeot, Renault, Stellantis, Ford Motor, Tesla, BYD, Volvo, Polestar, Jaguar Land Rover/JLR, Land Rover, Range Rover, Ferrari, Lamborghini, Maserati, Bentley, Rolls-Royce, Aston Martin, McLaren, Škoda/Skoda, Cupra, NIO, Xpeng/XPeng, Geely, Chery, Great Wall Motor, Mahindra, Tata Motors, Suzuki, Maruti Suzuki, Mazda, Subaru, Lucid Motors/Lucid Group, Rivian, General Motors, Chevrolet, Cadillac, Fiat, Dacia, KTM, Rimac, Royal Enfield, Hero MotoCorp, Bajaj, Pirelli, Michelin, Bridgestone
Banking & finance: BNP Paribas, HSBC, Barclays, Lloyds, NatWest, Santander, BBVA, CaixaBank, ING, ABN Amro/ABN AMRO, Rabobank, UBS, Julius Baer, JPMorgan/J.P. Morgan, Goldman Sachs, Morgan Stanley, Citigroup/Citibank/Citi, Bank of America, Wells Fargo, Deutsche Bank, Commerzbank, UniCredit, Intesa Sanpaolo, Société Générale/Societe Generale, Crédit Agricole/Credit Agricole, Standard Chartered, Emirates NBD, First Abu Dhabi Bank, QNB/Qatar National Bank, Doha Bank, Al Rajhi, Raiffeisen, Erste, OTP Bank, Banca Transilvania, Revolut, Monzo, Klarna, Kotak, HDFC, ICICI, ANZ, Westpac, Commonwealth Bank, NAB, Macquarie, Nomura, Mizuho, MUFG, Bank of China, ICBC, Itaú/Itau, Bradesco, BTG Pactual, Nubank, Banco do Brasil, Banorte, DBS, OCBC, UOB, Shinhan, KB Financial, Kasikornbank, Bangkok Bank, Credicorp, Interbank, Kapitalbank, Sberbank/Sber, VTB, Tinkoff/T-Bank, Monobank, PrivatBank, RBC/Royal Bank of Canada, TD Bank, Scotiabank, BMO, CIBC
Investors & funds: PIF, Mubadala, Temasek, BlackRock, Blackstone, KKR, CVC Capital/CVC, Carlyle Group, SoftBank, Abu Dhabi Investment Authority, ADQ, QIA/Qatar Investment Authority, Silver Lake, Bain Capital, Fosun, Tata Group, Reliance, Adani, Aditya Birla, JSW, Vedanta, Wanda Group/Dalian Wanda, Swire, Jardine, Lotte, Hanwha, SK Group, CP Group/Charoen Pokphand, ThaiBev
Payments & crypto: Visa, Mastercard, American Express/Amex, PayPal, Adyen, Coinbase, Binance, Crypto.com, Paytm, Afterpay
Insurance: Allianz, AXA, Generali, Zurich Insurance, Aviva, Prudential, MetLife, AIG, Mapfre/MAPFRE, Mutua Madrileña/Mutua Madrilena, Chubb, Swiss Re, Munich Re, Legal & General, Manulife, Sun Life, Ping An, AIA
Airlines & travel: Emirates, Qatar Airways, Etihad, flydubai, Saudia, Riyadh Air, British Airways, Lufthansa, Air France, KLM, Iberia, Ryanair, easyJet, Wizz Air, Singapore Airlines, Cathay Pacific, Qantas, Virgin Atlantic, Virgin Australia, Delta Air Lines, United Airlines, American Airlines, Turkish Airlines, Japan Airlines, Air India, IndiGo, Air Canada, WestJet, Korean Air, Asiana, Thai Airways, Tunisair, Uzbekistan Airways, Aeroflot, Booking.com, Booking Holdings, Expedia, Airbnb, Uber, Marriott, Hilton, Accor, Hyatt, IHG, Four Seasons, Mandarin Oriental, Jumeirah, Meliá/Melia, Visit Saudi, Visit Qatar
Tech: Apple, Google, Alphabet, Microsoft, Meta, Samsung, LG Electronics, Sony, Huawei, Xiaomi, Oppo/OPPO, Lenovo, Dell, HP, Intel, Nvidia/NVIDIA, AMD, Qualcomm, IBM, Oracle, SAP, Salesforce, Infosys, Wipro, Tencent, ByteDance, TikTok, Spotify, OpenAI, Anthropic, Canon, Panasonic, Nintendo, Garmin, WHOOP/Whoop, Oura, Peloton, Cisco, Siemens, Bosch, Logitech, Rakuten, Shopify, Canva, Atlassian, ASML, Ericsson, Naver, Kakao, Grab Holdings, Shopee, Yandex, Bitdefender, UiPath, Infobip, Avast, Uzum, Meituan, Zomato, Swiggy, Dream11, Byju's
Telecoms: Vodafone, Telefónica/Telefonica, Movistar, Deutsche Telekom, T-Mobile, BT, Verizon, AT&T, Telstra, Optus, Etisalat, Ooredoo, Airtel, Jio/Reliance Jio, Swisscom, KPN, Telenor, Telia, SK Telecom, NTT, China Mobile, Rogers Communications, Bell Canada, Telus, Singtel, Kyivstar, MegaFon, Magyar Telekom, Telekom Srbija, Telcel, América Movil/América Móvil
Energy & industry: Shell, BP, TotalEnergies, ExxonMobil/Exxon, Chevron, Aramco/Saudi Aramco, ADNOC, QatarEnergy, Equinor, Eni, Repsol, Iberdrola, EDF, Enel, Engie, Petrobras, Petronas, Pemex, YPF, Gazprom, Lukoil, Rosneft, Naftogaz, OMV, OMV Petrom, MOL, ČEZ/CEZ, BHP, Rio Tinto, Fortescue, Vale SA, Nornickel, AGL, Origin Energy, ABB, Airbus, Boeing, Hitachi, Mitsubishi, Toshiba, Kubota, Komatsu, Daikin, Sumitomo, Cemex, Strabag, SCG, Saab, Scania, Northvolt, BASF, Bayer
Logistics: DHL, FedEx, UPS, Maersk, DP World, Kuehne+Nagel, Nova Poshta
Property & destinations: Emaar, Aldar, NEOM, Red Sea Global, ROSHN, Qiddiya, Diriyah, Damac/DAMAC, Sobha, CapitaLand, Sun Hung Kai, Hong Kong Jockey Club
Food & drink: Coca-Cola, Pepsi/PepsiCo, Red Bull, Monster Energy, Nestlé/Nestle, Danone, Evian, San Pellegrino/S.Pellegrino, Perrier, Lavazza, Nespresso, Starbucks, McDonald's, KFC, Burger King, Mondelez, Cadbury, Ferrero, Barilla, Kellogg's, Lindt, Haribo, Gatorade, Powerade, Lipton, Kraft Heinz, Tim Hortons, Luckin Coffee, Grupo Bimbo/Bimbo, Inca Kola, Kofola, Podravka, Amul, Fever-Tree
Drinks (alcohol): Heineken, AB InBev/Anheuser-Busch, Budweiser, Michelob Ultra, Stella Artois, Moët & Chandon/Moët/Moet, Diageo, Pernod Ricard, Grey Goose, Aperol, Campari, Peroni, Carlsberg, Asahi, Kirin, Suntory, Tsingtao, Mahou, Estrella Damm, Estrella Galicia, Bacardi, Johnnie Walker, Hennessy, Lanson, Absolut, Ambev, Singha, Pilsner Urquell, Kweichow Moutai/Moutai
Betting: Bet365/bet365, Betway, William Hill, Ladbrokes, Paddy Power, Flutter Entertainment, Entain, DraftKings, FanDuel, Betfair, Unibet, Kindred Group, bwin, Codere, 1xBet, Sportsbet, Tabcorp, Stake.com
Media & streaming: DAZN, ESPN, TNT Sports, Eurosport, Warner Bros. Discovery, Disney, Paramount Global/Paramount+/Paramount Pictures, Comcast, NBCUniversal, beIN, Netflix, Prime Video, Tennis Channel, Fox Sports, Sky Sports
Health & pharma: Novartis, Roche, Pfizer, AstraZeneca, GSK, Sanofi, Johnson & Johnson, Novo Nordisk, Abbott Laboratories, Gedeon Richter
"""
# names that would also catch everyday words or people, matched with their own pattern instead
SPECIAL = {
    "Visa": r"(?<!Golden )(?<!golden )(?<!Student )(?<!student )(?<!Work )(?<!work )(?<!Tourist )(?<!tourist )(?<!Travel )(?<!travel )\bVisa\b(?![- ](?:[Rr]ules?|[Aa]pplications?|[Hh]olders?|[Ff]ees?|[Pp]olic(?:y|ies)|[Bb]ans?|[Ff]ree|[Ww]aivers?|[Cc]aps?|[Ss]cheme))",
    "Emirates": r"(?<!Arab )(?<!United )\bEmirates\b(?! NBD)",
    "Mercedes-Benz": r"\bMercedes(?:-Benz|-AMG)?\b",
    "Amazon": r"\bAmazon\b(?! [Rr]ainforest| [Rr]iver| [Bb]asin)",
    "Shell": r"\bShell\b(?![- ][Ss]hock)",
    "Meta": r"\bMeta\b(?![- ][Aa]nalys)",
    "Citigroup": r"\bCiti(?:group|bank)?\b",
    "Reliance": r"\bReliance (?:Industries|Retail|Group)\b",
    "BT": r"\bBT\b(?= (?:Group|Sport|chief|boss|Openreach)|'s)",
    "Omega": r"\bOmega\b(?!-?\d| fatty)",
    "Hilton": r"(?<!Paris )\bHilton\b",
    "Zara": r"(?<!Princess )\bZara\b(?! (?:Tindall|Larsson|McDermott|Phillips|Holland))",
    "Bayer": r"\bBayer\b(?! (?:Leverkusen|04))",
    "Intel": r"\bIntel\b(?! (?:on|suggests?|reports?|officials|agencies|community))",
}
SIGNALS = [
    # (key, label shown, weight). A headline can carry several.
    ("sponsor", "Sports sponsor", 3.0),
    ("people", "New marketing boss", 2.5),
    ("expand", "Expanding", 2.0),
    ("money", "Funding / results", 1.5),
    ("cool", "Cooling", 0.5),
]
SPORT = set("""sport sports football soccer club fc f1 formula golf tennis cricket rugby olympic olympics league team cup
marathon nba nfl nhl mlb racing esports athlete athletes stadium arena championship championships tour cycling sailing
padel boxing ufc motogp premier serie bundesliga laliga liga fifa uefa ioc open wimbledon prix nascar indycar
paralympic paralympics athletics swimming""".split())
W_SPONSOR = set("sponsor sponsors sponsored sponsorship sponsorships".split())
W_STRONG = ["official partner", "naming rights", "kit deal", "shirt deal", "kit supplier", "title partner",
            "title partnership", "title sponsor", "presenting partner", "official supplier"]  # sponsorship on their own
W_PARTNER = ["partner of", "partners with", "ambassador", "partnership with", "signs partnership", "renews partnership",
             "extends partnership", "multi year partnership", "multi year deal", "partnership", "deal with"]  # with a sport word
W_ROLE = ["chief marketing officer", "cmo", "marketing director", "head of marketing", "director of marketing",
          "brand director", "head of brand", "head of sponsorship", "chief commercial officer", "commercial director",
          "chief executive", "ceo", "managing director", "country manager"]
W_HIRE = set("appoints appointed appointment names named hires hired joins promotes promoted taps new".split())
W_EXPAND = set("""expands expand expansion enters entering launches launch launched opens opening unveils debut debuts
rollout flagship arrives arrival invests""".split())
W_EXPAND_PH = ["new store", "first store", "new market", "new plant", "new factory", "new hub", "new headquarters"]
W_MONEY = set("""raises raised funding investment invest investor investors ipo listing acquires acquired acquisition
acquisitions buys bought merger merge stake valuation profit profits revenue revenues sales earnings""".split())
W_COOL = set("""layoffs layoff cuts cutting losses loss slump plunge plunges falls bankruptcy insolvency
administration recall scandal fined exits exit withdraws closes closure closing shuts""".split())
W_COOL_PH = ["ends sponsorship", "ends partnership", "drops sponsorship", "pulls out", "job cuts", "profit warning"]


def deacc(s):
    s = re.sub(r"[\u2019\u2018`]", "'", s or "")  # McDonald’s -> McDonald's
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()


def load_brands():
    out = []  # (name, sector, compiled pattern)
    for line in BRANDS_TXT.strip().splitlines():
        sec, names = line.split(":", 1)
        for entry in names.split(","):
            alts = [a.strip() for a in entry.split("/") if a.strip()]
            if not alts:
                continue
            name = alts[0]
            if name in SPECIAL:
                pat = SPECIAL[name]
            else:
                pat = "|".join(r"(?<![\w&])" + re.escape(deacc(a)) + r"(?![\w&])" for a in alts)
            out.append((name, sec.strip(), re.compile(pat)))
    return out


def signals(t):
    """The signal keys a headline carries."""
    n = norm(t)
    w = set(n.split())
    out = []
    if w & W_SPONSOR or any(f" {p} " in n for p in W_STRONG) or ((w & SPORT) and any(f" {p} " in n for p in W_PARTNER)):
        out.append("sponsor")
    if w & W_HIRE and any(f" {p} " in n for p in W_ROLE):
        out.append("people")
    if w & W_EXPAND or any(f" {p} " in n for p in W_EXPAND_PH):
        out.append("expand")
    if w & W_MONEY:
        out.append("money")
    if w & W_COOL or any(f" {p} " in n for p in W_COOL_PH):
        out.append("cool")
    return out


def english(t):
    return len(re.sub(r"[^A-Za-z]", "", t)) >= 0.6 * len(t.replace(" ", ""))


def main():
    try:
        old = json.load(open(OUT))
    except Exception:
        old = {}
    try:
        names = {cc: c["n"] for cc, c in json.load(open("worldmap.json"))["c"].items()}
    except Exception:
        names = {}
    brands = load_brands()
    cut = (NOW - timedelta(days=KEEP_D)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        pool = [x for x in json.load(open(POOL)) if x["at"] >= cut]
    except Exception:
        pool = []

    # 1) this run's searches: the most overdue (roster nations every EVERY_H["roster"] hours, the rest less often)
    done = old.get("searched") or {}
    def overdue(key):
        cc = key.split(":")[0]
        last = done.get(key)
        h = EVERY_H["roster" if cc in ROSTER_NATS else "big"]
        if not last:
            return 1e9 - MARKETS.index(cc)
        return (NOW - datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds() / 3600 / h
    keys = [f"{cc}:{i}" for cc in MARKETS for i in range(len(QUERIES))]
    todo = [k for k in sorted(keys, key=overdue, reverse=True) if overdue(k) >= 1][:SEARCHES_PER_RUN]
    errs = {k: v for k, v in (old.get("errors") or {}).items() if k in keys and k not in todo}
    for key in todo:
        cc, qi = key.split(":")
        nm = NAME.get(cc) or names.get(cc) or cc
        try:
            its = items(fetch(GN + QUERIES[int(qi)].format(c=quote_plus(nm))))
        except Exception as e:
            errs[key] = str(e)[:200]
            print(f"{key} ({nm}): search failed ({e})")
            continue
        errs.pop(key, None)
        done[key] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
        kept = 0
        for t, u, _d, at, _img, src in its:
            a = at.strftime("%Y-%m-%dT%H:%M:%SZ")
            if a < cut or at > NOW + timedelta(hours=1) or not english(t):
                continue
            named = places(norm(t))
            if named and cc not in named:
                continue  # about somewhere else
            sig = signals(t)
            if not sig:
                continue
            pool.append({"t": t, "u": u, "s": src or "Google News", "at": a, "cc": cc, "sig": sig, "local": cc in named})
            kept += 1
        print(f"{key} ({nm}): {len(its)} results, {kept} with a business signal")

    # 2) one copy per link and market; brands found in each headline (done again every run, so a brand added to
    #    BRANDS also shows on older headlines)
    seen, rows = set(), []
    for x in sorted(pool, key=lambda x: x["at"], reverse=True):
        if (x["u"], x["cc"]) in seen or (x["t"], x["cc"]) in seen:
            continue
        seen |= {(x["u"], x["cc"]), (x["t"], x["cc"])}
        rows.append(x)
    json.dump(rows, open(POOL, "w"), ensure_ascii=False, indent=0)

    wt = {k: w for k, _, w in SIGNALS}
    markets = {}
    for cc in MARKETS:
        mine = [x for x in rows if x["cc"] == cc]
        cards, other = {}, []
        for x in mine:
            plain = deacc(x["t"])
            hit = [(b, sec) for b, sec, pat in brands if pat.search(plain)]
            age = (NOW - datetime.strptime(x["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds() / 86400
            pts = sum(wt[s] for s in x["sig"] if s != "cool") + (1.5 if x["local"] else 0) - age * 0.3
            h = {"t": x["t"], "u": x["u"], "s": x["s"], "at": x["at"], "sig": x["sig"]}
            if not hit:
                other.append((pts, h))
                continue
            for b, sec in hit:
                c = cards.setdefault(b, {"b": b, "sec": sec, "sig": [], "h": [], "pts": 0.0, "local": False})
                c["h"].append(h)
                c["pts"] += max(pts, 0.5)
                c["local"] = c["local"] or x["local"]
                for s in x["sig"]:
                    if s not in c["sig"]:
                        c["sig"].append(s)
        # brands named in exactly the same headlines (a group and its brand: "Inditex: Zara opens...") share one card
        same = {}
        for c in list(cards.values()):
            k = tuple(sorted(h["u"] for h in c["h"]))
            if k in same:
                o = same[k]
                o["b"] += " / " + c["b"]
                del cards[c["b"]]
            else:
                same[k] = c
        out = []
        for c in cards.values():
            c["more"] = max(0, len(c["h"]) - 3)
            c["h"] = sorted(c["h"], key=lambda h: (h["at"], -rank(h["s"])), reverse=True)[:3]  # the newest 3
            c["sig"] = [k for k, _, _ in SIGNALS if k in c["sig"]]
            c["cool"] = c["sig"] == ["cool"]  # only bad news: shown greyed, at the end
            c["score"] = round(c.pop("pts"), 2)
            out.append(c)
        out.sort(key=lambda c: (c["cool"], -c["score"], c["b"]))
        other.sort(key=lambda p: (-p[0], p[1]["at"]))
        o, seen_t = [], set()
        for _, h in other:
            k = frozenset(news.words(h["t"]))
            if any(len(k & s) >= 3 and len(k & s) >= 0.6 * min(len(k), len(s)) for s in seen_t):
                continue  # the same story from another outlet
            seen_t.add(k)
            o.append(h)
            if len(o) == 10:
                break
        markets[cc] = {"brands": out[:20], "other": o, "n": sum(1 for c in out if not c["cool"])}

    new = {"updated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "markets": markets, "roster": ROSTER_NATS,
           "signals": {k: lab for k, lab, _ in SIGNALS}, "searched": done, "errors": errs}
    if {k: v for k, v in new.items() if k not in ("updated", "searched")} == {k: v for k, v in old.items() if k not in ("updated", "searched")}:
        json.dump({**old, "searched": done}, open(OUT, "w"), ensure_ascii=False, indent=0)
        print("No new brand moves")
        return
    json.dump(new, open(OUT, "w"), ensure_ascii=False, indent=0)
    print(f"Saved brand moves for {sum(1 for m in markets.values() if m['brands'])} markets")


if __name__ == "__main__":
    main()
