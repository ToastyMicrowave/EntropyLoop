#!/usr/bin/env python3
"""
visualize.py - Quick matplotlib view of a capture.py .txt file.

Usage:
    python3 visualize.py                      # auto-picks newest capture in repo root
    python3 visualize.py path/to/capture.txt
"""
import sys
import re
import glob
import os
import numpy as np
import matplotlib.pyplot as plt


def find_capture():
    if len(sys.argv) > 1:
        return sys.argv[1]
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
    files = sorted(glob.glob(os.path.join(here, "entropy_capture_*.txt")), key=os.path.getmtime)
    if not files:
        sys.exit("No capture file found. Run capture.py first, or pass a path.")
    return files[-1]


def parse(path):
    h_min, r, hexes = [], [], []
    hdr = re.compile(r"H_min=([\d.]+)\s+R=\s*(\d+)")
    with open(path) as f:
        pending = None
        for line in f:
            m = hdr.search(line)
            if m:
                pending = (float(m.group(1)), int(m.group(2)))
            elif "random(512-bit):" in line and pending:
                h_min.append(pending[0]); r.append(pending[1])
                hexes.append(line.split(":")[1].strip())
                pending = None
    return np.array(h_min), np.array(r), hexes


def main():
    path = find_capture()
    h_min, r, hexes = parse(path)
    if not hexes:
        sys.exit(f"No batches parsed from {path}")

    data = np.frombuffer(b"".join(bytes.fromhex(h) for h in hexes), dtype=np.uint8)
    bits = np.unpackbits(data)
    print(f"{os.path.basename(path)}: {len(hexes)} batches, {len(data)} random bytes, {len(bits)} bits")

    fig, ax = plt.subplots(2, 2, figsize=(13, 8))
    fig.suptitle(f"Entropy Loop - {os.path.basename(path)}  ({len(hexes)} batches)", fontsize=13)

    # 1. H_min and R over time (health signals)
    a = ax[0, 0]
    a.plot(h_min, color="tab:blue", lw=1, label="H_min")
    a.set_ylabel("H_min", color="tab:blue"); a.set_xlabel("batch #")
    a.set_title("Quality over time (H_min & R)")
    a2 = a.twinx()
    a2.plot(r, color="tab:orange", lw=1, alpha=0.6, label="R")
    a2.set_ylabel("R (range)", color="tab:orange")

    # 2. Byte-value histogram of the whitened output (should be flat ~uniform)
    a = ax[0, 1]
    a.hist(data, bins=256, range=(0, 256), color="tab:green")
    a.axhline(len(data) / 256, color="red", ls="--", lw=1, label="ideal uniform")
    a.set_title("Byte histogram (flat = uniform)")
    a.set_xlabel("byte value 0-255"); a.set_ylabel("count"); a.legend()

    # 3. Bitmap of the raw bitstream (look for any visible pattern)
    a = ax[1, 0]
    w = 256
    rows = len(bits) // w
    img = bits[: rows * w].reshape(rows, w)
    a.imshow(img, cmap="binary", aspect="auto", interpolation="nearest")
    a.set_title("Bitstream bitmap (should look like TV static)")
    a.set_xlabel(f"bit (width={w})"); a.set_ylabel("row")

    # 4. Lag-1 scatter of byte values (structure shows as lines/clusters)
    a = ax[1, 1]
    a.scatter(data[:-1], data[1:], s=2, alpha=0.25, color="tab:purple")
    a.set_title("Lag-1 scatter (byte[n] vs byte[n+1])")
    a.set_xlabel("byte[n]"); a.set_ylabel("byte[n+1]")
    a.set_xlim(0, 255); a.set_ylim(0, 255)

    plt.tight_layout(rect=(0, 0, 1, 0.97))
    out = os.path.splitext(path)[0] + "_plot.png"
    plt.savefig(out, dpi=110)
    print(f"Saved {out}")
    plt.show()


if __name__ == "__main__":
    main()
