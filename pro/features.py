"""Causal daily features and market regime.

Every value on day t uses data up to and including day t's close only.
Signals computed on day t are executed at day t+1's open by the engine.
"""
import numpy as np
import pandas as pd

from data import load_events, load_market
import regime as legacy_regime


def rsi(close: pd.Series, n: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df.Close.shift(1)
    tr = pd.concat([df.High - df.Low, (df.High - prev).abs(), (df.Low - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c = out.Close
    for n in (5, 20, 50, 200):
        out[f"ema{n}"] = c.ewm(span=n, adjust=False, min_periods=n).mean()
    out["sma20"] = c.rolling(20).mean()
    sd = c.rolling(20).std()
    out["bb_up"], out["bb_dn"] = out.sma20 + 2 * sd, out.sma20 - 2 * sd
    out["rsi2"], out["rsi14"] = rsi(c, 2), rsi(c, 14)
    out["atr"] = atr(out)
    out["atr_pct"] = 100 * out.atr / c
    out["adx"] = legacy_regime.adx(out)
    # Channels exclude today so "today broke the prior 55-day high" is well defined.
    out["hi55"], out["lo55"] = out.High.rolling(55).max().shift(1), out.Low.rolling(55).min().shift(1)
    out["hi20"], out["lo20"] = out.High.rolling(20).max().shift(1), out.Low.rolling(20).min().shift(1)
    lo, hi = out.VIX.rolling(252, min_periods=126).min(), out.VIX.rolling(252, min_periods=126).max()
    out["vix_rank"] = 100 * (out.VIX - lo) / (hi - lo).replace(0, np.nan)
    out["vix_chg5"] = out.VIX / out.VIX.shift(5) - 1
    out["ret20"] = c / c.shift(20) - 1
    out["regime"] = classify(out)
    events = set(load_events())
    # "News" veto: do not open a new position on the session before a scheduled event.
    nxt = pd.Series(out.index, index=out.index).shift(-1)
    out["event_next"] = [(d.date() in events) or (pd.notna(n) and n.date() in events)
                         for d, n in zip(out.index, nxt)]
    return out


def classify(f: pd.DataFrame) -> pd.Series:
    stress = (f.VIX >= 25) | (f.vix_rank >= 85)
    up = (f.Close > f.ema200) & (f.ema50 > f.ema200)
    down = (f.Close < f.ema200) & (f.ema50 < f.ema200)
    reg = np.select(
        [f.ema200.isna(), stress, up & (f.adx >= 20), down & (f.adx >= 20), f.adx < 20],
        ["warmup", "stress", "uptrend", "downtrend", "range"], default="transition")
    return pd.Series(reg, index=f.index)


def load(extra: pd.DataFrame | None = None) -> pd.DataFrame:
    df = load_market()
    if extra is not None and len(extra):
        df = pd.concat([df, extra.loc[extra.index > df.index[-1]]])
    return add_features(df)
