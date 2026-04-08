# ACTIVE.md — Chantier memos

## Status
**ACTIVE** — v0.31.2

## Last Action
- 2026-04-08 19:22: P14 Benchmark Suite completed
  - benchmark_quality.py: Recall@K, MRR, NDCG@K, zero-result rate, decay impact, scalability
  - CLI: memos benchmark-quality --noise N --top K --seed S [--no-decay] [--scalability] [--json]
  - Synthetic dataset generator (5 categories, 10 templates each, configurable noise)
  - 34 new tests, all passing
  - CI script: tools/run-quality-benchmarks.sh
  - Results: Recall@5=85%, MRR=0.57, NDCG@5=0.62, latency p50=105ms

## Next
- P12 — Memory Conflict Resolution (Multi-instance Sync)
- Quality improvements: publish benchmark results in README
- GitHub issues if any
