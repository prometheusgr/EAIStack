"""Retrieval evaluation: metrics for measuring whether retrieval changes
(prefixing, chunking, hybrid search, reranking) actually improve results.

This package holds pure, deterministic logic only. The harness that seeds a
fixture corpus into real Postgres and runs it through the actual retrieval
path lives in tests/eval/ — a measurement tool run on demand, not a
CI-gating test suite, since its numbers move as content changes.
"""
