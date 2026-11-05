import time
import os
import math
import socket
from flask import Flask, request, jsonify

app = Flask(__name__)
HOSTNAME = socket.gethostname()

# In-memory metrics tracking
stats = {
    "requests": 0,
    "total_latency_ms": 0.0,
    "latencies": []
}

@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "healthy",
        "service": "k8s-cost-autoscaler-workload",
        "pod": HOSTNAME
    })

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

@app.route("/work", methods=["GET", "POST"])
def work():
    start_time = time.time()
    
    # Optional artificial CPU burn (in milliseconds)
    cpu_ms = float(request.args.get("cpu_ms", 10.0))
    # Optional artificial I/O sleep (in milliseconds)
    io_ms = float(request.args.get("io_ms", 5.0))
    
    # 1. Simulate CPU load with math computation
    if cpu_ms > 0:
        burn_end = time.time() + (cpu_ms / 1000.0)
        x = 0.0001
        while time.time() < burn_end:
            x = math.sin(x) + math.cos(x)
            
    # 2. Simulate I/O or network delay
    if io_ms > 0:
        time.sleep(io_ms / 1000.0)
        
    duration_ms = (time.time() - start_time) * 1000.0
    
    # Track stats
    stats["requests"] += 1
    stats["total_latency_ms"] += duration_ms
    stats["latencies"].append(duration_ms)
    # Keep window of last 1000 requests to compute percentiles
    if len(stats["latencies"]) > 1000:
        stats["latencies"].pop(0)

    return jsonify({
        "pod": HOSTNAME,
        "duration_ms": round(duration_ms, 2),
        "requests_processed": stats["requests"]
    })

@app.route("/stats", methods=["GET"])
def get_stats():
    latencies = sorted(stats["latencies"])
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0.0
    avg = (stats["total_latency_ms"] / stats["requests"]) if stats["requests"] > 0 else 0.0
    
    return jsonify({
        "pod": HOSTNAME,
        "total_requests": stats["requests"],
        "avg_latency_ms": round(avg, 2),
        "p95_latency_ms": round(p95, 2),
        "p99_latency_ms": round(p99, 2),
        "sample_size": len(latencies)
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

