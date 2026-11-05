#!/usr/bin/env python3
"""
loadgen.py - Multi-pattern synthetic HTTP load generator.
Supports patterns: steady, ramp, spike, sawtooth, sustained.
Pings the NodePort service endpoint with configurable concurrency.
"""
import time
import sys
import math
import argparse
import requests
import concurrent.futures

class LoadGenerator:
    def __init__(self, target_url="http://localhost:30080/work", duration_sec=120):
        self.target_url = target_url
        self.duration_sec = duration_sec
        self.session = requests.Session()

    def send_request(self, cpu_ms=15, io_ms=5):
        try:
            resp = self.session.get(f"{self.target_url}?cpu_ms={cpu_ms}&io_ms={io_ms}", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    def run_pattern(self, pattern="steady", base_rps=30, peak_rps=120):
        print(f"[*] Starting LoadGen -> Pattern: {pattern.upper()}, Target: {self.target_url}, Duration: {self.duration_sec}s")
        start_time = time.time()
        
        while time.time() - start_time < self.duration_sec:
            elapsed = time.time() - start_time
            progress = elapsed / self.duration_sec

            if pattern == "steady":
                current_rps = base_rps
            elif pattern == "ramp":
                current_rps = int(base_rps + (peak_rps - base_rps) * progress)
            elif pattern == "spike":
                # Spike between 30% and 70% of the duration
                if 0.3 <= progress <= 0.7:
                    current_rps = peak_rps
                else:
                    current_rps = base_rps
            elif pattern == "sawtooth":
                # Oscillating wave every 30 seconds
                cycle = (elapsed % 30) / 30.0
                current_rps = int(base_rps + (peak_rps - base_rps) * cycle)
            else:
                current_rps = base_rps

            # Dispatch requests for this 1-second window
            sec_start = time.time()
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(50, max(5, current_rps))) as executor:
                futures = [executor.submit(self.send_request) for _ in range(current_rps)]
                concurrent.futures.wait(futures)

            time_spent = time.time() - sec_start
            print(f"[{int(elapsed)}s/{self.duration_sec}s] Pattern={pattern} Target RPS={current_rps} | Took: {time_spent:.2f}s")
            
            # Sleep remainder of the 1-second window
            if time_spent < 1.0:
                time.sleep(1.0 - time_spent)

        print("[+] Load generation completed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kubernetes Scaler Load Generator")
    parser.add_argument("--url", default="http://localhost:30080/work", help="Target URL")
    parser.add_argument("--pattern", choices=["steady", "ramp", "spike", "sawtooth"], default="steady")
    parser.add_argument("--duration", type=int, default=120, help="Duration in seconds")
    parser.add_argument("--base-rps", type=int, default=20, help="Base RPS")
    parser.add_argument("--peak-rps", type=int, default=100, help="Peak RPS")

    args = parser.parse_args()
    lg = LoadGenerator(target_url=args.url, duration_sec=args.duration)
    lg.run_pattern(pattern=args.pattern, base_rps=args.base_rps, peak_rps=args.peak_rps)

