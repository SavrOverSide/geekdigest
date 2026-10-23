"""Tells Yandex and Bing that the sites changed (IndexNow). Run on the server after a site update:
python3 /opt/tenge/geekdigest/tools/indexnow.py wordlore ideaforgegen
"""
import json
import re
import sys
import urllib.error
import urllib.request

KEY = "650eec11b63dea1dca12d533e35333ca"   # the same key file sits at the root of each site
HOST = "savroverside.github.io"

for site in sys.argv[1:] or ["wordlore", "ideaforgegen"]:
    xml = urllib.request.urlopen(f"https://{HOST}/{site}/sitemap.xml", timeout=20).read().decode()
    urls = re.findall(r"<loc>(.*?)</loc>", xml)
    body = json.dumps({"host": HOST, "key": KEY, "keyLocation": f"https://{HOST}/{site}/{KEY}.txt", "urlList": urls}).encode()
    for ep in ("https://yandex.com/indexnow", "https://api.indexnow.org/indexnow"):
        try:
            r = urllib.request.urlopen(urllib.request.Request(ep, data=body, headers={"Content-Type": "application/json; charset=utf-8"}), timeout=30)
            print(site, ep, r.status, len(urls), "urls")
        except urllib.error.HTTPError as e:
            print(site, ep, "HTTP", e.code, e.read()[:120])
