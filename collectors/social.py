import os
import re
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
    feeds = [
        "https://cointelegraph.com/rss",
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://decrypt.co/feed",
        "https://bitcoinmagazine.com/.rss/full/",
        "https://www.reddit.com/r/Bitcoin/.rss",
        "https://www.reddit.com/r/CryptoCurrency/.rss",
    ]

    results: List[Headline] = []
    if budget.can_call("rss"):
        budget.record_call("rss")

        def _fetch_feed(url: str):
            try:
                text = request_text(url, timeout=10)
                root = ET.fromstring(text)
                return [
                    Headline(item.find("title").text or "", url.split("/")[2])
                    for item in root.iter("item")
                    if item.find("title") is not None
                ]
            except Exception:
                return []

        with ThreadPoolExecutor(max_workers=len(feeds)) as executor:
            for feed_results in executor.map(_fetch_feed, feeds):
                results.extend(feed_results)
                if len(results) >= 60:
                    break

    # Optional CryptoPanic free-tier backup
    cp_key = os.getenv("CRYPTOPANIC_API_KEY", "").strip()
    if cp_key and budget.can_call("cryptopanic"):
        try:
            budget.record_call("cryptopanic")
            payload = request_json(
                "https://cryptopanic.com/api/v1/posts/",
                params={"auth_token": cp_key, "currencies": "BTC", "kind": "news"},
                timeout=10,
            )
            for row in payload.get("results", [])[:20]:
                title = row.get("title") or ""
                if title:
                    results.append(Headline(title=title, source="cryptopanic.com"))
        except Exception:
            pass

    # Dedupe titles aggressively to avoid feed overlap
    deduped: List[Headline] = []
    seen = set()
    for h in results:
        key = re.sub(r"\s+", " ", h.title.strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(h)
        if len(deduped) >= 20:
            break

    return deduped
