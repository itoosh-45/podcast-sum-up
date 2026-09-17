"""מדפיס את הפרקים האחרונים מפיד RSS של פודקאסט.

שימוש:  python latest.py חושבים-טוב
        python latest.py https://feeds.simplecast.com/w2pVTj5d 10
"""
import sys, urllib.request, xml.etree.ElementTree as ET

FEEDS = {
    "חושבים-טוב": "https://feeds.simplecast.com/w2pVTj5d",
    "ווינרים": "https://anchor.fm/s/10116a664/podcast/rss",
    "התשובה": "https://www.spreaker.com/show/4228834/episodes/feed",
    "לשבת-לקחת": "https://anchor.fm/s/fd1c3740/podcast/rss",
}
ITUNES = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}


def episodes(feed_url, limit=5):
    req = urllib.request.Request(feed_url, headers={"User-Agent": "podcast-sum-up"})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.parse(r).getroot()
    for item in root.find("channel").findall("item")[:limit]:
        text = lambda tag, ns=None: (
            item.find(tag, ns).text if item.find(tag, ns) is not None else ""
        )
        enc = item.find("enclosure")
        yield {
            "title": text("title"),
            "date": text("pubDate"),
            "duration": text("itunes:duration", ITUNES),
            "guid": text("guid"),
            "mp3": enc.get("url") if enc is not None else "",
            "mb": round(int(enc.get("length") or 0) / 1048576, 1) if enc is not None else 0,
        }


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "חושבים-טוב"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    url = FEEDS.get(name, name)
    for ep in episodes(url, limit):
        print(f"{ep['title']}\n  {ep['date']}  |  {ep['duration']}  |  {ep['mb']} MB")
        print(f"  {ep['mp3']}\n")


if __name__ == "__main__":
    main()
