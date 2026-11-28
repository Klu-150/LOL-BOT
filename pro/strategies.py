"""Strategy library. Parameters are fixed textbook values, never fitted.

entry(row)  -> +1 long, -1 short, 0 nothing   (evaluated at day t close)
exit(row, side, held) -> True to exit at next open
stop_atr    -> protective stop distance in ATRs from the entry fill
"""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Strategy:
    name: str
    idea: str
    entry: Callable
    exit: Callable
    stop_atr: float
    max_hold: int
    trail: bool = False


def _pullback_entry(r):
    # Buy weakness inside an uptrend instead of chasing strength.
    if r.Close > r.ema200 and r.ema50 > r.ema200 and r.rsi2 < 10:
        return 1
    if r.Close < r.ema200 and r.ema50 < r.ema200 and r.rsi2 > 90:
        return -1
    return 0


def _pullback_exit(r, side, held):
    return (r.Close > r.ema5) if side > 0 else (r.Close < r.ema5)


def _breakout_entry(r):
    if r.adx >= 20 and r.Close > r.hi55:
        return 1
    if r.adx >= 20 and r.Close < r.lo55:
        return -1
    return 0


def _breakout_exit(r, side, held):
    return (r.Close < r.lo20) if side > 0 else (r.Close > r.hi20)


def _range_entry(r):
    if r.adx < 20 and r.Close < r.bb_dn:
        return 1
    if r.adx < 20 and r.Close > r.bb_up:
        return -1
    return 0


def _range_exit(r, side, held):
    return (r.Close >= r.sma20) if side > 0 else (r.Close <= r.sma20)


def _trend_entry(r):
    if r.adx >= 25 and r.Close > r.ema20 > r.ema50 and r.rsi14 < 70:
        return 1
    if r.adx >= 25 and r.Close < r.ema20 < r.ema50 and r.rsi14 > 30:
        return -1
    return 0


def _trend_exit(r, side, held):
    return (r.Close < r.ema50) if side > 0 else (r.Close > r.ema50)


def _panic_entry(r):
    # Fear spikes in a broad index tend to mean-revert; only buy, never short panic.
    if r.vix_rank >= 80 and r.vix_chg5 > 0.15 and r.Close < r.ema20 - 2 * r.atr:
        return 1
    return 0


def _panic_exit(r, side, held):
    return r.Close > r.ema20


LIBRARY = [
    Strategy("trend_pullback", "Uptrend + short-term oversold (RSI2<10): buy the dip, exit on bounce above EMA5",
             _pullback_entry, _pullback_exit, stop_atr=2.5, max_hold=10),
    Strategy("channel_breakout", "55-day channel breakout with ADX>=20, exit on 20-day opposite channel",
             _breakout_entry, _breakout_exit, stop_atr=3.0, max_hold=60, trail=True),
    Strategy("range_reversion", "ADX<20 sideways market: fade Bollinger(20,2) extremes back to the mean",
             _range_entry, _range_exit, stop_atr=2.0, max_hold=10),
    Strategy("trend_rider", "Strong trend (ADX>=25, price>EMA20>EMA50), ride until close crosses EMA50",
             _trend_entry, _trend_exit, stop_atr=3.0, max_hold=40, trail=True),
    Strategy("panic_reversal", "VIX spike + price stretched 2 ATR below EMA20: buy capitulation",
             _panic_entry, _panic_exit, stop_atr=3.0, max_hold=10),
]
BY_NAME = {s.name: s for s in LIBRARY}
