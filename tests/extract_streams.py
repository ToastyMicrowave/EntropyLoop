#!/usr/bin/env python3
"""
extract_streams.py - Turn a capture JSON map into raw binary streams for testing.

capture.py writes a JSON file shaped like:

    { "<128-hex SHA-512>": "<4096-hex raw pre-hash input>", ... }

This splits that into two raw binary files so you can run the SAME randomness
test suites (NIST STS, dieharder) on both sides of the hash:

    post.bin  - all SHA-512 outputs concatenated   (post-hash / conditioned)
    pre.bin   - all raw ADC inputs concatenated     (pre-hash  / source)

Note the size asymmetry: each batch yields 64 post-hash bytes but 2048 pre-hash
bytes, so pre.bin is ~32x larger than post.bin. That is expected - the raw
samples are the bytes that were fed into the hash.

Usage:
    python3 extract_streams.py entropy_raw_20260618-110000.json
    python3 extract_streams.py raw.json --outdir tests/streams --prefix run1
"""

import argparse
import json
import os
import sys


def parse_args():
    p = argparse.ArgumentParser(description="Split a capture JSON map into pre/post binary streams.")
    p.add_argument("json", help="capture JSON file (hash hex -> raw hex)")
    p.add_argument("--outdir", default=".", help="directory to write the .bin files into (default: .)")
    p.add_argument("--prefix", default="", help="optional filename prefix, e.g. 'run1' -> run1_pre.bin")
    p.add_argument("--pack12", action="store_true",
                   help="pack the pre-hash stream as dense 12-bit samples (drop the 4 "
                        "zero-pad bits each 16-bit word carries) so randomness tests see "
                        "the analog source, not the storage format")
    return p.parse_args()


def pack12(raw_bytes):
    """Pack little-endian 16-bit ADC words (12 valid bits each) into a dense bitstream.

    Each batch is 1024 samples * 12 bits = 12288 bits = exactly 1536 bytes, so the
    stream stays byte-aligned across batches. Bits are emitted MSB-first per sample.
    """
    out = bytearray()
    acc = 0
    nbits = 0
    for i in range(0, len(raw_bytes), 2):
        val = (raw_bytes[i] | (raw_bytes[i + 1] << 8)) & 0xFFF
        acc = (acc << 12) | val
        nbits += 12
        while nbits >= 8:
            nbits -= 8
            out.append((acc >> nbits) & 0xFF)
    return bytes(out)


def main():
    args = parse_args()

    with open(args.json) as f:
        raw_map = json.load(f)

    if not raw_map:
        print("ERROR: the JSON map is empty - capture some data first.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.outdir, exist_ok=True)
    tag = f"{args.prefix}_" if args.prefix else ""
    post_path = os.path.join(args.outdir, f"{tag}post.bin")
    pre_path = os.path.join(args.outdir, f"{tag}pre.bin")

    post_bytes = 0
    pre_bytes = 0
    with open(post_path, "wb") as pf, open(pre_path, "wb") as rf:
        for hash_hex, raw_hex in raw_map.items():
            hb = bytes.fromhex(hash_hex)
            rb = bytes.fromhex(raw_hex)
            if args.pack12:
                rb = pack12(rb)
            pf.write(hb)
            rf.write(rb)
            post_bytes += len(hb)
            pre_bytes += len(rb)

    def fmt(n):
        return f"{n:,} bytes ({n / 1024 / 1024:.2f} MB, {n * 8:,} bits)"

    print(f"Batches      : {len(raw_map)}")
    print(f"pre-hash mode: {'packed 12-bit (zero-pad stripped)' if args.pack12 else 'raw 16-bit words'}")
    print(f"post-hash -> {post_path}")
    print(f"             {fmt(post_bytes)}")
    print(f"pre-hash  -> {pre_path}")
    print(f"             {fmt(pre_bytes)}")
    print()
    print("Next: run the suites with")
    print(f"    tests/run_analysis.sh {pre_path}")
    print(f"    tests/run_analysis.sh {post_path}")


if __name__ == "__main__":
    main()
