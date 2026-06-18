#!/usr/bin/env python3
"""
Lightweight chat load test — concurrent health + optional authenticated pings.

Usage:
  py scripts/load_test_chat.py --url http://127.0.0.1:8000 --users 20 --rounds 3
  py scripts/load_test_chat.py --url http://127.0.0.1:8000 --token YOUR_JWT
"""
from __future__ import annotations

import argparse
import concurrent.futures
import statistics
import time
import urllib.error
import urllib.request


def _get(url: str, headers: dict | None = None) -> tuple[int, float]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read(256)
            return resp.status, time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        return e.code, time.perf_counter() - t0
    except Exception:
        return 0, time.perf_counter() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--users", type=int, default=20)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--token", default="")
    args = ap.parse_args()
    base = args.url.rstrip("/")
    path = "/api/v1/health/live"
    headers = {}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"

    latencies: list[float] = []
    errors = 0

    def worker(_: int) -> None:
        nonlocal errors
        for _ in range(args.rounds):
            code, sec = _get(f"{base}{path}", headers)
            latencies.append(sec)
            if code != 200:
                errors += 1

    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.users) as ex:
        list(ex.map(worker, range(args.users)))
    elapsed = time.perf_counter() - t0
    total = args.users * args.rounds
    ok = total - errors
    print(f"Requests: {total}  OK: {ok}  Errors: {errors}")
    if latencies:
        latencies.sort()
        p95 = latencies[int(0.95 * len(latencies)) - 1]
        print(f"Latency avg={statistics.mean(latencies):.3f}s p95={p95:.3f}s max={max(latencies):.3f}s")
    print(f"Wall time: {elapsed:.2f}s  RPS: {total / max(elapsed, 0.001):.1f}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
