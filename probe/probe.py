import sys, re
sys.path.insert(0, "scripts")
import news
C = """https://www.sportbusiness.com/feed/
https://www.sportspromedia.com/feed/
https://www.sportico.com/feed/
https://frontofficesports.com/feed/
https://www.racquetsportsindustry.com/feed/
https://www.thetennisgazette.com/feed/
https://www.theracket.news/feed
https://www.tennishead.net/feed/
https://www.dailymail.co.uk/sport/tennis/index.rss
https://rss.nytimes.com/services/xml/rss/nyt/Tennis.xml
https://www.tennis.com/rss
https://www.tennisworldusa.org/rss/news.xml
https://www.sportsbusinessjournal.com/RSS/News.aspx
https://www.insidethegames.biz/rss
https://www.reuters.com/arc/outboundfeeds/rss/category/sports/tennis/?outputType=xml
https://api.wtatennis.com/content/wta/text/EN/?page=0&pageSize=20
https://www.itftennis.com/en/news-and-media/rss/
https://www.lta.org.uk/rss/news
https://news.google.com/rss/search?q=tennis+(sponsorship+OR+investment+OR+investor+OR+%22prize+money%22+OR+broadcast+OR+CEO)+when:3d&hl=en-GB&gl=GB&ceid=GB:en
https://news.google.com/rss/search?q=(ATP+OR+WTA+OR+ITF+OR+%22Tennis+Europe%22)+(tournament+OR+calendar+OR+sanction+OR+licence+OR+deal)+when:3d&hl=en-GB&gl=GB&ceid=GB:en
https://www.bing.com/news/search?q=tennis+sponsorship+OR+investment&format=rss
""".split()
for u in C:
    try:
        raw = news.fetch(u)
        try:
            its = news.items(raw)
        except Exception as e:
            print("OK-RAW", u, len(raw), raw[:300]); continue
        print(f"OK {len(its)} {u}")
        for it in its[:8]:
            print("    ", it[3].date(), "|", it[0][:110])
    except Exception as e:
        print("FAIL", u, str(e)[:150])
