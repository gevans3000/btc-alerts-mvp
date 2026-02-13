import httpx, time, xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List
from collectors.base import BudgetManager

@dataclass
class FearGreedSnapshot:
    value: int
    label: str
    healthy: bool = True

def fetch_fear_greed(budget: BudgetManager) -> FearGreedSnapshot:
    if not budget.can_call("alternative_me"): return FearGreedSnapshot(50, "Neutral", False)
    try:
        budget.record_call("alternative_me")
        r = httpx.get("https://api.alternative.me/fng/?limit=1&format=json", timeout=10)
        entry = r.json()["data"][0]
        return FearGreedSnapshot(int(entry["value"]), entry["value_classification"])
    except: return FearGreedSnapshot(50, "Neutral", False)

@dataclass
class Headline:
    title: str
    source: str

def fetch_news(budget: BudgetManager) -> List[Headline]:
    if not budget.can_call("rss"): return []
    budget.record_call("rss")
    feeds = ["https://cointelegraph.com/rss", "https://www.coindesk.com/arc/outboundfeeds/rss/"]
    results = []
    for url in feeds:
        try:
            r = httpx.get(url, timeout=10)
            root = ET.fromstring(r.text)
            for item in root.iter("item"):
                results.append(Headline(item.find("title").text, url.split("/")[2]))
                if len(results) > 20: break
        except: pass
    return results
