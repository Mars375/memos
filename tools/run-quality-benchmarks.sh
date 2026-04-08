#!/usr/bin/env bash
# run-quality-benchmarks.sh — CI-ready recall quality benchmarks for MemOS
# Usage:
#   ./tools/run-quality-benchmarks.sh          # default run
#   ./tools/run-quality-benchmarks.sh --json   # JSON output for CI
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

echo "=== MemOS Recall Quality Benchmarks ==="
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

# Run quality benchmark
memos benchmark-quality \
    --noise 50 \
    --top 5 \
    --seed 42 \
    "$@"

echo ""
echo "=== Benchmark complete ==="
