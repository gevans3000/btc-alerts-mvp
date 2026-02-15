## 2026-02-14 - Thread-safe Rate Limiting
**Learning:** Parallelizing network I/O in Python with `ThreadPoolExecutor` provides massive speedups for data-heavy applications, but requires explicit thread-safety for shared state management. In this app, the `BudgetManager` shared a JSON file for rate-limit persistence, which would have suffered from race conditions without a `threading.Lock`.
**Action:** Always audit shared managers or persistence layers for thread-safety before introducing concurrency.
