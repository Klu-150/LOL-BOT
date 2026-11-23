"""
Market regime classifier.

Every value on day t uses only data up to and including day t's close,
so there is no look-ahead when the backtest trades at that close.

Output per day:
    trend : strong_up | mild_up | range | mild_down | strong_down
    iv    : low | mid | high          (from India VIX IV Rank)
    shock : True when India VIX >= VIX_SHOCK
"""
import numpy as np
import pandas as pd

import config as C


def adx(df: pd.DataFrame, n: int = C.ADX_LEN) -> pd.Series:
    """Wilder's Average Directional Index."""
    h, l, c = df["High"], df["Low"], df["Close"]
    up = h.diff()
    dn = -l.diff()
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    a = 1.0 / n
    atr = tr.ewm(alpha=a, adjust=False).mean()
    pdi = 100 * plus_dm.ewm(alpha=a, adjust=False).mean() / atr
    mdi = 100 * minus_dm.ewm(alpha=a, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=a, adjust=False).mean()


def iv_rank(vix: pd.Series, lookback: int = C.IVR_LOOKBACK) -> pd.Series:
    """IV Rank = (IV now - lowest IV) / (highest IV - lowest IV) * 100."""
    lo = vix.rolling(lookback, min_periods=lookback // 2).min()
    hi = vix.rolling(lookback, min_periods=lookback // 2).max()
    return 100 * (vix - lo) / (hi - lo).replace(0, np.nan)


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = out["Close"].ewm(span=C.EMA_FAST, adjust=False).mean()
    out["ema_slow"] = out["Close"].ewm(span=C.EMA_SLOW, adjust=False).mean()
    out["adx"] = adx(out)
    out["ivr"] = iv_rank(out["VIX"])
    returns = np.log(out["Close"] / out["Close"].shift(1))
    out["realized_vol"] = returns.rolling(C.REALIZED_VOL_WINDOW).std() * np.sqrt(252) * 100
    out["iv_rv_ratio"] = out["VIX"] / out["realized_vol"].replace(0, np.nan)
    return out


def classify_trend(close, ema_f, ema_s, adx_v) -> str:
    if adx_v >= C.ADX_TREND and close > ema_f > ema_s:
        return "strong_up"
    if adx_v >= C.ADX_TREND and close < ema_f < ema_s:
        return "strong_down"
    if adx_v < C.ADX_RANGE:
        return "range"
    return "mild_up" if close >= ema_s else "mild_down"


def classify_iv(ivr_v) -> str:
    if ivr_v >= C.IVR_HIGH:
        return "high"
    if ivr_v < C.IVR_LOW:
        return "low"
    return "mid"


def classify_row(row) -> dict:
    return {
        "trend": classify_trend(row["Close"], row["ema_fast"], row["ema_slow"], row["adx"]),
        "iv": classify_iv(row["ivr"]),
        "shock": bool(row["VIX"] >= C.VIX_SHOCK),
    }


def classify(df_feat: pd.DataFrame) -> pd.DataFrame:
    """Vectorised version for the whole history."""
    rows = [classify_row(r) for _, r in df_feat.iterrows()]
    lab = pd.DataFrame(rows, index=df_feat.index)
    return df_feat.join(lab)


def choose_strategy(trend: str, iv: str, shock: bool, event_ahead: bool):
    """The playbook. Returns a strategy name or None (stay flat)."""
    if shock:
        return C.SHOCK_STRATEGY
    if event_ahead:
        return C.EVENT_PLAYBOOK.get(iv)
    return C.PLAYBOOK.get((trend, iv))
