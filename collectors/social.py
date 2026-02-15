import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import List

from collectors.base import BudgetManager, request_json, request_text


@dataclass
class FearGreedSnapshot:
    value: int
    label: str
    healthy: bool = True


def fetch_fear_greed(budget: BudgetManager) -> FearGreedSnapshot:
    if not budget.can_call("alternative_me"):
        return FearGreedSnapshot(50, "Neutral", False)
    try:
        budget.record_call("alternative_me")
        payload = request_json("https://api.alternative.me/fng/?limit=1&format=json", timeout=10)
        entry = payload["data"][0]
        return FearGreedSnapshot(int(entry["value"]), entry["value_classification"])
    except (KeyError, ValueError, TypeError):
        return FearGreedSnapshot(50, "Neutral", False)
    except Exception:
        return FearGreedSnapshot(50, "Neutral", False)


@dataclass
class Headline:
    title: str
    source: str


def fetch_news(budget: BudgetManager) -> List[Headline]:
    if not budget.can_call("rss"):
        return []
    budget.record_call("rss")
    feeds = ["https://cointelegraph.com/rss", "https://www.coindesk.com/arc/outboundfeeds/rss/"]

    def _fetch_feed(url: str):
        try:
            text = request_text(url, timeout=10)
            root = ET.fromstring(text)
            return [Headline(item.find("title").text or "", url.split("/")[2]) for item in root.iter("item") if item.find("title") is not None]
        except Exception:
            return []

    results: List[Headline] = []
    with ThreadPoolExecutor(max_workers=len(feeds)) as executor:
        for feed_results in executor.map(_fetch_feed, feeds):
            results.extend(feed_results)
            if len(results) >= 40:
                break

    return results[:20]
