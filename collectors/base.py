import time, json, threading
from pathlib import Path
from dataclasses import dataclass, field
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
    LIMITS = {"kraken": (10, 60.0), "coingecko": (10, 60.0), "alternative_me": (5, 300.0), "rss": (20, 300.0), "llm": (5, 300.0), "yahoo": (20, 60.0), "binance": (20, 60.0), "bybit": (20, 60.0)}

    def __init__(self, path: str = ".budget.json"):
        self.path = Path(path)
        self._buckets = {k: _SourceBucket(v[0], v[1]) for k, v in self.LIMITS.items()}
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path, "r") as f:
                    data = json.load(f)
                    for k, ts in data.items():
                        if k in self._buckets: self._buckets[k].timestamps = ts
            except: pass

    def _save(self):
        try:
            with open(self.path, "w") as f:
                json.dump({k: b.timestamps for k, b in self._buckets.items()}, f)
        except: pass

    def can_call(self, source: str) -> bool:
        with self._lock:
            return self._buckets.get(source, _SourceBucket(5, 60)).can_call()

    def record_call(self, source: str):
        with self._lock:
            if source in self._buckets:
                self._buckets[source].record()
                self._save()
