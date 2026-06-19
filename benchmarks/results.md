# HTTP Server Benchmarks

## 1. Thread Pool Architecture (Synchronous + ThreadPoolExecutor)
* **OS/Hardware:** WSL2 (Ubuntu), 12-Core Host CPU
* **Configuration:** `max_workers=24`
* **Command:** `ab -n 1000 -c 50 http://localhost:8888/`

### Metrics
* **Requests per Second (RPS):** 1748.21 [#/sec] (mean)
* **Failed Requests:** 0
* **Time per Request (mean):** 28.601 ms
* **99% Tail Latency:** 65 ms
* **100% Max Latency:** 87 ms