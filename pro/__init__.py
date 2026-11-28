"""Adaptive multi-strategy research engine (paper only, no broker access).

Pipeline: causal daily features -> market regime -> strategy library signals ->
walk-forward selector that learns, from completed past trades only, which
strategy works in the current regime -> one position at a time.
"""
