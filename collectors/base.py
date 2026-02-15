import json
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import httpx

from config import HTTP_RETRY

from typing import Dict, List


@dataclass
class _SourceBucket:
    max_calls: int
    window_seconds: float
    timestamps: List[float] = field(default_factory=list)

    def _prune(self):
        cutoff = time.time() - self.window_seconds
        self.timestamps = [t for t in self.timestamps if t > cutoff]

    def can_call(self) -> bool:
        self._prune()
        return len(self.timestamps) < self.max_calls

    def record(self):
        self.timestamps.append(time.time())


class BudgetManager:
    LIMITS = {
        "kraken": (24, 60.0),
        "coingecko": (10, 60.0),
        "alternative_me": (5, 300.0),
        "rss": (20, 300.0),
        "llm": (5, 300.0),
        "yahoo": (24, 60.0),
        "bybit": (24, 60.0),
        "okx": (24, 60.0),
    }

    def __init__(self, path: str = ".budget.json"):
        self.path = Path(path)
        self._buckets = {k: _SourceBucket(v[0], v[1]) for k, v in self.LIMITS.items()}
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                data: Dict[str, List[float]] = json.loads(self.path.read_text())
                for k, ts in data.items():
                    if k in self._buckets:
                        self._buckets[k].timestamps = ts
            except Exception:
                return

    def _save(self):
        try:
            self.path.write_text(json.dumps({k: b.timestamps for k, b in self._buckets.items()}))
        except Exception:
            return

    def can_call(self, source: str) -> bool:
        with self._lock:
            return self._buckets.get(source, _SourceBucket(5, 60)).can_call()

    def record_call(self, source: str):
        with self._lock:
            if source in self._buckets:
                self._buckets[source].record()
                self._save()


def _is_retriable_status(code: int) -> bool:
    return code == 429 or code >= 500


def _request(url: str, params: Optional[dict], timeout: float) -> httpx.Response:
def request_json(url: str, params: Optional[dict] = None, timeout: float = 10.0) -> dict:
    last_exc: Optional[Exception] = None
    for attempt in range(HTTP_RETRY["attempts"]):
        try:
            resp = httpx.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            code = exc.response.status_code
            if not _is_retriable_status(code) or attempt == HTTP_RETRY["attempts"] - 1:
                raise
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt == HTTP_RETRY["attempts"] - 1:
                raise
        sleep_s = HTTP_RETRY["backoff_seconds"] * (2**attempt) + random.uniform(0, HTTP_RETRY["jitter_seconds"])
        time.sleep(sleep_s)
    raise last_exc if last_exc else RuntimeError("request failed")


def request_json(url: str, params: Optional[dict] = None, timeout: float = 10.0) -> dict:
    return _request(url, params, timeout).json()


def request_text(url: str, params: Optional[dict] = None, timeout: float = 10.0) -> str:
    return _request(url, params, timeout).text
            return resp.json()
        except Exception as exc:  # pragma: no cover - exercised via callers
            last_exc = exc
            if attempt < HTTP_RETRY["attempts"] - 1:
                sleep_s = HTTP_RETRY["backoff_seconds"] * (2**attempt) + random.uniform(0, HTTP_RETRY["jitter_seconds"])
                time.sleep(sleep_s)
    raise last_exc if last_exc else RuntimeError("request_json failed")
