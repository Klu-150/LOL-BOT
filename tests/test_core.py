"""Sanity tests:  python -m pytest -q"""
import math
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import config as C
import pricing
import regime
import strategies as ST
from data import weekly_expiries


def test_put_call_parity():
    S, K, T, s = 25000, 25200, 7 / 365, 0.15
    c = pricing.bs_price(S, K, T, s, "C")
    p = pricing.bs_price(S, K, T, s, "P")
    rhs = S * math.exp(-C.DIV_YIELD * T) - K * math.exp(-C.RISK_FREE * T)
    assert abs((c - p) - rhs) < 1e-6


def test_expiry_value_is_intrinsic():
    assert pricing.bs_price(25000, 24800, 0, 0.15, "C") == 200
    assert pricing.bs_price(25000, 24800, 0, 0.15, "P") == 0


def test_delta_strike_selection():
    k = pricing.strike_for_delta(25000, 7 / 365, 0.14, "P", 0.25)
    assert k < 25000 and k % C.STRIKE_STEP == 0
    assert abs(abs(pricing.delta(25000, k, 7 / 365, 0.14, "P")) - 0.25) < 0.06


def test_skew_puts_richer_than_calls():
    S, T, atm = 25000, 7 / 365, 0.14
    assert pricing.skewed_iv(S, 24500, T, atm) > atm > pricing.skewed_iv(S, 25500, T, atm)


def test_credit_spread_is_a_credit():
    legs = ST.build("bull_put_spread", 25000, 7 / 365, 0.14)
    net = sum(l.qty * pricing.price(25000, l.K, 7 / 365, 0.14, l.cp) for l in legs)
    assert net < 0  # we receive premium


def test_expiry_calendar_switch():
    days = pd.bdate_range("2025-08-18", "2025-09-12")
    ex = weekly_expiries(days)
    assert date(2025, 8, 28) in ex      # Thursday before switch
    assert date(2025, 9, 2) in ex       # first Tuesday expiry
    assert date(2025, 9, 4) not in ex


def test_regime_rules():
    assert regime.classify_trend(110, 105, 100, 30) == "strong_up"
    assert regime.classify_trend(90, 95, 100, 30) == "strong_down"
    assert regime.classify_trend(100, 100, 100, 15) == "range"
    assert regime.classify_iv(70) == "high" and regime.classify_iv(10) == "low"
    assert regime.choose_strategy("range", "high", False, False) == "iron_condor"
    assert regime.choose_strategy("range", "high", True, False) is None
