#!/usr/bin/env python3
"""
capture.py - Read the Entropy Loop's serial output and log it to a readable .txt file.

Each batch from the firmware looks like:

    H_min: 6.4000 | R: 1918 | Data:
    <128 hex chars>   (SHA-512 of the raw samples  -> the usable randomness)
    <128 hex chars>   (SHA-512 of that hash         -> derived, no extra entropy)

This parses those blocks and writes one tidy, aligned record per batch.

The firmware also prints a fourth line per batch:

    RAW: <4096 hex chars>   (the exact 2048 bytes fed into SHA-512 -> raw input)

We collect those into a separate JSON file mapping the post-hash hex to its
pre-hash raw bitstream, so you can run randomness tests on both:

    { "<128-hex SHA-512>": "<4096-hex raw input>", ... }

Usage:
    python3 capture.py                       # logs until Ctrl+C, default port/file
    python3 capture.py --port /dev/tty.usbmodem3101 --out run.txt
    python3 capture.py --count 100           # stop after 100 good batches
    python3 capture.py --min-hmin 6.0        # only keep batches at/above this H_min
    python3 capture.py --raw-mb 10           # stop after ~10 MB of raw bits collected
    python3 capture.py --raw-out raw.json    # where to write the hash->raw JSON map
"""

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime

import serial  # pyserial

DEFAULT_PORT = "/dev/tty.usbmodem3101"
DEFAULT_BAUD = 115200


def parse_args():
    p = argparse.ArgumentParser(description="Capture Entropy Loop output to a readable text file.")
    p.add_argument("--port", default=DEFAULT_PORT, help=f"Serial port (default: {DEFAULT_PORT})")
    p.add_argument("--baud", type=int, default=DEFAULT_BAUD, help=f"Baud rate (default: {DEFAULT_BAUD})")
    p.add_argument("--out", default=None, help="Output .txt file (default: entropy_capture_<timestamp>.txt)")
    p.add_argument("--count", type=int, default=0, help="Stop after N kept batches (0 = run until Ctrl+C)")
    p.add_argument("--min-hmin", type=float, default=0.0,
                   help="Only keep batches with H_min >= this value (default 0 = keep all)")
    p.add_argument("--raw-out", default=None,
                   help="JSON file mapping post-hash hex -> raw pre-hash bitstream "
                        "(default: entropy_raw_<timestamp>.json)")
    p.add_argument("--raw-mb", type=float, default=10.0,
                   help="Stop after collecting ~this many MB of raw bits (default 10; 0 = no limit)")
    return p.parse_args()


def parse_header(line):
    """Parse 'H_min: 6.4000 | R: 1918 | Data:' -> (h_min, r). Returns None if it doesn't match."""
    try:
        parts = line.split("|")
        h_min = float(parts[0].split(":")[1])
        r = int(parts[1].split(":")[1])
        return h_min, r
    except (IndexError, ValueError):
        return None


def is_hex_line(line):
    return len(line) >= 64 and all(c in "0123456789abcdefABCDEF" for c in line)


def main():
    args = parse_args()
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    out_path = args.out or f"entropy_capture_{stamp}.txt"
    raw_path = args.raw_out or f"entropy_raw_{stamp}.json"
    raw_target = int(args.raw_mb * 1024 * 1024)  # bytes; 0 = unlimited

    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
    except serial.SerialException as e:
        print(f"ERROR: could not open {args.port}: {e}", file=sys.stderr)
        print("Is the Pico plugged in? Check the port with: ls /dev/tty.usbmodem*", file=sys.stderr)
        sys.exit(1)

    kept = 0
    skipped = 0
    total = 0                      # every valid batch seen, pre-filter
    hmin_counts = Counter()        # how many batches at each H_min value
    r_counts = Counter()           # how many batches at each R (range/max) value
    raw_map = {}                   # post-hash hex -> raw pre-hash bitstream (hex)
    raw_bytes = 0                  # running total of raw bits collected, in bytes
    pending_hash = None            # hash awaiting its matching "RAW:" line
    started = datetime.now()

    print(f"Connected to {args.port} @ {args.baud} baud")
    print(f"Writing to {out_path}  (Ctrl+C to stop)")
    print(f"Raw bits -> {raw_path}"
          + (f"  (target ~{args.raw_mb:g} MB)" if raw_target else "  (no limit)") + "\n")

    with open(out_path, "w") as f:
        f.write("Entropy Loop Capture\n")
        f.write(f"Started : {started:%Y-%m-%d %H:%M:%S}\n")
        f.write(f"Port    : {args.port} @ {args.baud} baud\n")
        if args.min_hmin > 0:
            f.write(f"Filter  : keeping batches with H_min >= {args.min_hmin}\n")
        f.write("=" * 78 + "\n\n")
        f.flush()

        try:
            header = None
            while True:
                raw = ser.readline().decode(errors="ignore").strip()
                if not raw:
                    continue

                if raw.startswith("H_min"):
                    header = parse_header(raw)
                    continue

                # The raw pre-hash bitstream line, paired with the last kept hash.
                if raw.startswith("RAW:"):
                    raw_hex = raw[4:].strip().lower()
                    if pending_hash is not None and is_hex_line(raw_hex):
                        raw_map[pending_hash] = raw_hex
                        raw_bytes += len(raw_hex) // 2
                        pending_hash = None
                        if raw_target and raw_bytes >= raw_target:
                            break
                    pending_hash = None
                    continue

                # A hex line only counts if it directly followed a valid header.
                if header is not None and is_hex_line(raw):
                    h_min, r = header
                    header = None  # the firmware prints a second hash line; ignore it

                    # Tally EVERY valid batch, regardless of the H_min filter.
                    # Round H_min so near-duplicate floats bucket together.
                    total += 1
                    hmin_counts[round(h_min, 4)] += 1
                    r_counts[r] += 1

                    quality = "OK" if (r >= 200 and h_min > 0) else "UNSAFE (squelch)"
                    if h_min < args.min_hmin:
                        skipped += 1
                        continue

                    kept += 1
                    ts = datetime.now()
                    f.write(f"#{kept:06d}  {ts:%H:%M:%S}  "
                            f"H_min={h_min:6.4f}  R={r:5d}  [{quality}]\n")
                    f.write(f"        random(512-bit): {raw.lower()}\n\n")
                    f.flush()

                    # Remember this hash so the upcoming "RAW:" line gets paired
                    # with it in the hash->raw JSON map.
                    pending_hash = raw.lower()

                    print(f"\r#{kept} kept ({skipped} skipped)  "
                          f"raw={raw_bytes/1024/1024:.2f} MB  "
                          f"last H_min={h_min:.4f} R={r}",
                          end="", flush=True)

                    if args.count and kept >= args.count:
                        break
        except KeyboardInterrupt:
            pass
        finally:
            ser.close()
            ended = datetime.now()

            # Dump the post-hash -> raw pre-hash map for offline randomness tests.
            with open(raw_path, "w") as rf:
                json.dump(raw_map, rf)

            f.write("\n" + "=" * 78 + "\n")
            f.write(f"Ended   : {ended:%Y-%m-%d %H:%M:%S}\n")
            f.write(f"Duration: {ended - started}\n")
            f.write(f"Total   : {total} batches seen (all, pre-filter)\n")
            f.write(f"Kept    : {kept} batches  ({kept * 64} bytes / {kept * 512} bits of randomness)\n")
            f.write(f"Skipped : {skipped} batches (below H_min filter)\n")
            f.write(f"Raw     : {len(raw_map)} batches  "
                    f"({raw_bytes} bytes / {raw_bytes * 8} bits) -> {raw_path}\n")

            # --- Distribution tables over ALL batches ---
            f.write("\n" + "-" * 78 + "\n")
            f.write("H_min distribution (all batches)\n")
            f.write(f"{'H_min':>10}  {'count':>8}  {'percent':>8}\n")
            for value, count in sorted(hmin_counts.items()):
                pct = (count / total * 100) if total else 0.0
                f.write(f"{value:>10.4f}  {count:>8d}  {pct:>7.2f}%\n")

            f.write("\n" + "-" * 78 + "\n")
            f.write("R (range / max) distribution (all batches)\n")
            f.write(f"{'R':>10}  {'count':>8}  {'percent':>8}\n")
            for value, count in sorted(r_counts.items()):
                pct = (count / total * 100) if total else 0.0
                f.write(f"{value:>10d}  {count:>8d}  {pct:>7.2f}%\n")

    print(f"\n\nDone. {kept} batches written to {out_path}")
    print(f"      {len(raw_map)} raw blocks ({raw_bytes/1024/1024:.2f} MB) written to {raw_path}")


if __name__ == "__main__":
    main()
