import threading
import http.client
import time
import statistics

HOST = "127.0.0.1"
PORT = 8888

def send_request(results, errors):
    try:
        conn = http.client.HTTPConnection(HOST, PORT, timeout=10)
        start = time.perf_counter()
        conn.request("GET", "/slow") # / for base route
        response = conn.getresponse()
        response.read()
        elapsed = time.perf_counter() - start
        results.append(elapsed)
        conn.close()
    except Exception as e:
        errors.append(str(e))

def run_benchmark(label, num_requests, concurrency):
    results = []
    errors = []
    threads = []

    print(f"\n{'='*50}")
    print(f"{label}")
    print(f"Requests: {num_requests} | Concurrency: {concurrency}")
    print(f"{'='*50}")

    total_start = time.perf_counter()

    for i in range(0, num_requests, concurrency):
        batch = min(concurrency, num_requests - i)
        batch_threads = []
        for _ in range(batch):
            t = threading.Thread(target=send_request, args=(results, errors))
            batch_threads.append(t)
        for t in batch_threads:
            t.start()
        for t in batch_threads:
            t.join()
        threads.extend(batch_threads)

    total_elapsed = time.perf_counter() - total_start

    if results:
        print(f"Completed:    {len(results)}/{num_requests} requests")
        print(f"Errors:       {len(errors)}")
        print(f"Total time:   {total_elapsed:.3f}s")
        print(f"Req/sec:      {len(results) / total_elapsed:.1f}")
        print(f"Latency mean: {statistics.mean(results)*1000:.1f}ms")
        print(f"Latency p50:  {statistics.median(results)*1000:.1f}ms")
        print(f"Latency p99:  {sorted(results)[int(len(results)*0.99)-1]*1000:.1f}ms")
        print(f"Latency max:  {max(results)*1000:.1f}ms")
    else:
        print("All requests failed.")
        for e in errors[:5]:
            print(f"  Error: {e}")

if __name__ == "__main__":
    # Low concurrency 
    run_benchmark("LOW CONCURRENCY", num_requests=100, concurrency=1)

    # Medium concurrency
    run_benchmark("MEDIUM CONCURRENCY", num_requests=100, concurrency=10)

    # High concurrency 
    run_benchmark("HIGH CONCURRENCY", num_requests=200, concurrency=50)