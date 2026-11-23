"""Black-Scholes pricing, delta, a simple volatility skew, and strike selection."""
import math

import config as C

_SQRT2 = math.sqrt(2.0)


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def intrinsic(S: float, K: float, cp: str) -> float:
    return max(0.0, S - K) if cp == "C" else max(0.0, K - S)


def bs_price(S, K, T, sigma, cp, r=C.RISK_FREE, q=C.DIV_YIELD):
    """European option price. T in years. cp = 'C' or 'P'."""
    if T <= 0 or sigma <= 0:
        return intrinsic(S, K, cp)
    vt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vt
    d2 = d1 - vt
    if cp == "C":
        return S * math.exp(-q * T) * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2)
    return K * math.exp(-r * T) * _ncdf(-d2) - S * math.exp(-q * T) * _ncdf(-d1)


def bs_delta(S, K, T, sigma, cp, r=C.RISK_FREE, q=C.DIV_YIELD):
    if T <= 0 or sigma <= 0:
        itm = (S > K) if cp == "C" else (S < K)
        return (1.0 if cp == "C" else -1.0) if itm else 0.0
    vt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vt
    if cp == "C":
        return math.exp(-q * T) * _ncdf(d1)
    return -math.exp(-q * T) * _ncdf(-d1)


def skewed_iv(S, K, T, atm_iv):
    """IV for strike K given at-the-money IV (India VIX / 100)."""
    if T <= 0:
        return atm_iv
    z = math.log(K / S) / (atm_iv * math.sqrt(T))
    z = max(-4.0, min(4.0, z))
    iv = atm_iv * (1.0 - C.SKEW_SLOPE * z + C.SKEW_CURVE * z * z)
    return max(0.5 * atm_iv, iv)


def price(S, K, T, atm_iv, cp):
    return bs_price(S, K, T, skewed_iv(S, K, T, atm_iv), cp)


def delta(S, K, T, atm_iv, cp):
    return bs_delta(S, K, T, skewed_iv(S, K, T, atm_iv), cp)


def round_strike(x: float) -> float:
    return float(round(x / C.STRIKE_STEP) * C.STRIKE_STEP)


def strike_for_delta(S, T, atm_iv, cp, target_abs_delta):
    """Strike on the 50-point grid whose |delta| is closest to the target."""
    atm = round_strike(S)
    best_k, best_err = atm, 9.9
    for i in range(0, 80):  # up to 4,000 points away
        k = atm + i * C.STRIKE_STEP if cp == "C" else atm - i * C.STRIKE_STEP
        d = abs(delta(S, k, T, atm_iv, cp))
        err = abs(d - target_abs_delta)
        if err < best_err:
            best_k, best_err = k, err
        if d < target_abs_delta - 0.05:
            break
    return best_k


def expected_move(S, atm_iv, T):
    """1-standard-deviation move in points: S * IV * sqrt(T)."""
    return S * atm_iv * math.sqrt(max(T, 0.0))
