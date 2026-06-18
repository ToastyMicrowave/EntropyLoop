#!/usr/bin/env bash
#
# run_analysis.sh - Run NIST STS and dieharder against a raw binary stream.
#
# Usage:
#   tests/run_analysis.sh <file.bin> [outdir]
#
# Produces, under <outdir> (default: tests/results/<basename>/):
#   nist_finalAnalysisReport.txt   - NIST STS 2.1.2 summary table
#   dieharder.txt                  - dieharder -a full battery output
#   summary.txt                    - quick pass/fail tally from both
#
# NIST STS is well suited to MB-scale samples. dieharder really wants GBs; on a
# small file it rewinds and re-reads the data, which inflates correlations - so
# treat the dieharder column as indicative only unless you feed it a large file.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STS_DIR="$HERE/tools/sts-2.1.2/sts-2.1.2"
ASSESS="$STS_DIR/assess"
DIEHARDER="$HERE/tools/dieharder-install/bin/dieharder"
export DYLD_LIBRARY_PATH="$HERE/tools/dieharder-install/lib:${DYLD_LIBRARY_PATH:-}"

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <file.bin> [outdir]" >&2
    exit 1
fi

BIN="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"   # absolute path
[[ -f "$BIN" ]] || { echo "no such file: $BIN" >&2; exit 1; }

BASE="$(basename "$BIN")"
OUTDIR="${2:-$HERE/results/${BASE%.*}}"
mkdir -p "$OUTDIR"

BYTES=$(wc -c < "$BIN" | tr -d ' ')
BITS=$(( BYTES * 8 ))

echo "============================================================"
echo " Analysing : $BIN"
echo " Size      : $BYTES bytes ($BITS bits)"
echo " Output    : $OUTDIR"
echo "============================================================"

# ---------------------------------------------------------------------------
# NIST STS
# ---------------------------------------------------------------------------
# Pick a stream length and stream count that fit the data. NIST recommends
# 1,000,000 bits/stream; fall back to the whole file as one stream if smaller.
STREAM_LEN=1000000
if (( BITS < STREAM_LEN )); then
    STREAM_LEN=$BITS
fi
NSTREAMS=$(( BITS / STREAM_LEN ))
(( NSTREAMS < 1 )) && NSTREAMS=1
(( NSTREAMS > 200 )) && NSTREAMS=200   # cap; 200 is plenty for the proportion test

echo
echo ">>> NIST STS: ${NSTREAMS} stream(s) x ${STREAM_LEN} bits"
if (( STREAM_LEN < 1000000 )); then
    echo "    NOTE: stream length < 1,000,000 bits; some tests (Universal,"
    echo "    Random Excursions, etc.) may be skipped or report as not applicable."
fi

# Drive the interactive menu:
#   0           -> Input File
#   <path>      -> the binary file
#   1           -> apply ALL statistical tests
#   0           -> accept default parameter adjustments
#   <nstreams>  -> number of bitstreams
#   1           -> Binary input format (8 bits per byte)
(
    cd "$STS_DIR"
    printf '0\n%s\n1\n0\n%d\n1\n' "$BIN" "$NSTREAMS" | ./assess "$STREAM_LEN" >/dev/null 2>&1 || true
    REPORT="experiments/AlgorithmTesting/finalAnalysisReport.txt"
    if [[ -s "$REPORT" ]]; then
        cp "$REPORT" "$OUTDIR/nist_finalAnalysisReport.txt"
    else
        echo "(NIST STS produced no report - check stream sizing)" > "$OUTDIR/nist_finalAnalysisReport.txt"
    fi
)
echo "    -> $OUTDIR/nist_finalAnalysisReport.txt"

# ---------------------------------------------------------------------------
# dieharder
# ---------------------------------------------------------------------------
echo
echo ">>> dieharder -a (raw file, generator 201)"
if (( BYTES < 100000000 )); then
    echo "    NOTE: file is < 100 MB; dieharder will rewind/re-read it. Results"
    echo "    are indicative only. For a real run, capture a multi-GB sample."
fi
"$DIEHARDER" -a -g 201 -f "$BIN" 2>&1 | tee "$OUTDIR/dieharder.txt" | tail -40 || true
echo "    -> $OUTDIR/dieharder.txt"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
{
    echo "Summary for $BASE  ($BYTES bytes / $BITS bits)"
    echo "Generated: $(date '+%Y-%m-%d %H:%M:%S')"
    echo
    echo "--- NIST STS (proportion of passing sequences per test) ---"
    if grep -q PROPORTION "$OUTDIR/nist_finalAnalysisReport.txt" 2>/dev/null; then
        # A test line starts with the C1..C10 counts; NIST flags a failed
        # proportion/uniformity with a '*' somewhere in that line (after the
        # p-value and/or after the proportion, before the test name).
        nist_total=$(grep -cE '^[ ]*[0-9]+ ' "$OUTDIR/nist_finalAnalysisReport.txt" || true)
        nist_star=$(grep -E '^[ ]*[0-9]+ ' "$OUTDIR/nist_finalAnalysisReport.txt" | grep -c '\*' || true)
        echo "  test lines : $nist_total"
        echo "  flagged (*) : $nist_star   (a '*' marks a failed proportion/uniformity)"
    else
        echo "  (no NIST report parsed)"
    fi
    echo
    echo "--- dieharder assessment tally ---"
    for verdict in PASSED WEAK FAILED; do
        n=$(grep -c "$verdict" "$OUTDIR/dieharder.txt" 2>/dev/null || true)
        printf "  %-7s : %s\n" "$verdict" "$n"
    done
} | tee "$OUTDIR/summary.txt"

echo
echo "Done. Full results in: $OUTDIR"
