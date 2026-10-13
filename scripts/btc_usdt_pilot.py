from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import websockets

STREAM_URL = "wss://stream.binance.com:9443/ws/btcusdt@bookTicker"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def event_timestamp_ms(payload: dict[str, Any]) -> int | None:
    for field in ("E", "T", "ts"):
        value = payload.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
    return None


async def collect(duration_seconds: float, output: Path | None) -> dict[str, Any]:
    started_at = utc_now()
    monotonic_start = time.monotonic()
    message_count = 0
    reconnect_count = 0
    invalid_count = 0
    out_of_order_count = 0
    sequence_gap_count = 0
    event_timestamp_count = 0
    delays_ms: list[int] = []
    payload_bytes = 0
    sequence_ids: list[int] = []
    message_types: Counter[str] = Counter()
    output_handle = output.open("w", encoding="utf-8") if output else None

    try:
        while time.monotonic() - monotonic_start < duration_seconds:
            try:
                async with websockets.connect(
                    STREAM_URL,
                    open_timeout=10,
                    close_timeout=2,
                    ping_interval=20,
                ) as socket:
                    while time.monotonic() - monotonic_start < duration_seconds:
                        raw = await asyncio.wait_for(socket.recv(), timeout=10)
                        received_at = utc_now()
                        if isinstance(raw, bytes):
                            payload_bytes += len(raw)
                            raw_text = raw.decode("utf-8")
                        else:
                            raw_text = raw
                            payload_bytes += len(raw.encode("utf-8"))
                        payload = json.loads(raw_text)
                        if not isinstance(payload, dict):
                            invalid_count += 1
                            continue

                        message_count += 1
                        message_types[str(payload.get("e", "bookTicker"))] += 1
                        update_id = payload.get("u")
                        if isinstance(update_id, int) and not isinstance(
                            update_id, bool
                        ):
                            if sequence_ids:
                                previous = sequence_ids[-1]
                                if update_id <= previous:
                                    out_of_order_count += 1
                                elif update_id > previous + 1:
                                    sequence_gap_count += update_id - previous - 1
                            sequence_ids.append(update_id)

                        event_ms = event_timestamp_ms(payload)
                        if event_ms is not None:
                            event_timestamp_count += 1
                            delays_ms.append(
                                int(received_at.timestamp() * 1000) - event_ms
                            )

                        if output_handle:
                            output_handle.write(
                                json.dumps(
                                    {
                                        "exchange": "binance",
                                        "symbol": "BTC/USDT",
                                        "event_timestamp": (
                                            datetime.fromtimestamp(
                                                event_ms / 1000, timezone.utc
                                            ).isoformat()
                                            if event_ms is not None
                                            else None
                                        ),
                                        "received_timestamp": received_at.isoformat(),
                                        "sequence_id": update_id,
                                        "payload": payload,
                                    },
                                    separators=(",", ":"),
                                )
                                + "\n"
                            )
            except (OSError, asyncio.TimeoutError, json.JSONDecodeError):
                if time.monotonic() - monotonic_start >= duration_seconds:
                    break
                reconnect_count += 1
                await asyncio.sleep(min(2**reconnect_count, 10))
    finally:
        if output_handle:
            output_handle.close()

    elapsed = time.monotonic() - monotonic_start
    result: dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "ended_at": utc_now().isoformat(),
        "duration_seconds": round(elapsed, 3),
        "stream": STREAM_URL,
        "message_count": message_count,
        "messages_per_second": round(message_count / elapsed, 3) if elapsed else 0,
        "reconnect_count": reconnect_count,
        "invalid_count": invalid_count,
        "sequence_gap_count": sequence_gap_count,
        "out_of_order_count": out_of_order_count,
        "event_timestamp_count": event_timestamp_count,
        "event_timestamp_coverage": (
            round(event_timestamp_count / message_count, 4) if message_count else 0
        ),
        "local_receive_timestamp_coverage": 1 if message_count else 0,
        "payload_bytes": payload_bytes,
        "estimated_raw_bytes_per_day": (
            round(payload_bytes / elapsed * 86400) if elapsed else 0
        ),
        "message_types": dict(message_types),
    }
    if delays_ms:
        result["event_to_receive_delay_ms"] = {
            "min": min(delays_ms),
            "max": max(delays_ms),
            "avg": round(sum(delays_ms) / len(delays_ms), 3),
        }
    if output:
        result["output"] = str(output)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a Binance BTC/USDT collection pilot"
    )
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(collect(args.duration, args.output))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
