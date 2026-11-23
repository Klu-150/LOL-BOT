"""
All tunable settings in one place.

Change values here, re-run `python run_backtest.py`, and compare reports.
Nothing else in the project needs editing for normal experiments.
"""
from datetime import date
BOT_NAME = "Last of Our League"

# ----------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------
NIFTY_CSV = "data/nifty50.csv"
VIX_CSV = "data/indiavix.csv"
EVENTS_CSV = "events.csv"

# Raw CSV URLs (NSE end-of-day data mirrored on GitHub by the EOD2 project,
# updated weekly). update_data.py downloads these.
NIFTY_URL = "https://raw.githubusercontent.com/BennyThadikaran/eod2_data/main/daily/nifty%2050.csv"
VIX_URL = "https://raw.githubusercontent.com/BennyThadikaran/eod2_data/main/daily/india%20vix.csv"

# Nifty weekly options launched Feb 2019 -> start there so every simulated
# week used a contract that actually existed.
BACKTEST_START = date(2019, 2, 11)
BACKTEST_END = None  # None = up to the latest date in the data

# NSE moved Nifty weekly expiry from Thursday to Tuesday from 1 Sep 2025.
EXPIRY_SWITCH_DATE = date(2025, 9, 1)

# ----------------------------------------------------------------------------
# Contract
# ----------------------------------------------------------------------------
LOT_SIZE = 65          # current Nifty lot size (2026). Kept constant so results
                       # are comparable across years. Verify on NSE before live.
STRIKE_STEP = 50       # Nifty strike interval

# ----------------------------------------------------------------------------
# Pricing model (Black-Scholes with India VIX as the at-the-money IV)
# ----------------------------------------------------------------------------
RISK_FREE = 0.065      # annual
DIV_YIELD = 0.012      # Nifty dividend yield, approx
# Volatility skew: iv(K) = atm * (1 - SKEW_SLOPE*z + SKEW_CURVE*z^2),
# z = ln(K/S) / (atm*sqrt(T)). Puts below spot get higher IV, calls above lower.
SKEW_SLOPE = 0.10
SKEW_CURVE = 0.03

# ----------------------------------------------------------------------------
# Regime classifier thresholds
# ----------------------------------------------------------------------------
EMA_FAST = 20
EMA_SLOW = 50
ADX_LEN = 14
ADX_TREND = 25         # ADX >= this = trending
ADX_RANGE = 20         # ADX <  this = range-bound
IVR_LOOKBACK = 252     # trading days for IV Rank
IVR_HIGH = 50          # IV Rank >= this = "high" IV
IVR_LOW = 30           # IV Rank <  this = "low" IV
VIX_SHOCK = 30         # India VIX >= this = crisis, stand aside

# ----------------------------------------------------------------------------
# Strategy construction
# ----------------------------------------------------------------------------
SPREAD_WIDTH = 100     # fixed for the new research run; 2 Nifty strike intervals
CREDIT_SHORT_DELTA = 0.25   # short strike for bull-put / bear-call spreads
CONDOR_SHORT_DELTA = 0.16   # short strikes for iron condor

# ----------------------------------------------------------------------------
# Exit rules (checked on each daily close)
# ----------------------------------------------------------------------------
MANAGE_EXITS = True
CREDIT_TAKE_PROFIT = 0.50   # close when 50% of credit is captured
CREDIT_STOP_MULT = 2.0      # close when loss = 2 x credit
DEBIT_TAKE_PROFIT = 0.50    # close at 50% of max profit (debit spreads)
DEBIT_STOP = 0.50           # close when loss = 50% of debit paid
STRADDLE_TAKE_PROFIT = 0.30
STRADDLE_STOP = 0.40
CALENDAR_TAKE_PROFIT = 0.25
CALENDAR_STOP = 0.40

# ----------------------------------------------------------------------------
# Trading costs (Zerodha + statutory, 2026 rates)
# ----------------------------------------------------------------------------
BROKERAGE_PER_ORDER = 20.0      # Rs per executed order (each leg, each side)
STT_SELL_PREMIUM = 0.0015       # 0.15% of premium on the sell side (from 1 Apr 2026)
STT_EXERCISE = 0.0015           # 0.15% of intrinsic value, ITM long at expiry
EXCHANGE_TXN = 0.0003553        # NSE options transaction charge, on premium
SEBI_FEE = 0.000001             # Rs 10 per crore
STAMP_BUY = 0.00003             # 0.003% on buy-side premium
GST = 0.18                      # on brokerage + exchange + SEBI fee
# Slippage per leg per side, in index points: fixed + % of option price
SLIPPAGE_FIXED = 0.5
SLIPPAGE_PCT = 0.01

# ----------------------------------------------------------------------------
# Account simulation
# ----------------------------------------------------------------------------
START_CAPITAL = 20_000

# Fixed condition router; prior credit-only and textbook maps remain benchmarks.
ALGORITHM = "adaptive_regime"
REALIZED_VOL_WINDOW = 20
MIN_IV_RANK = 30.0
MIN_IV_RV_RATIO = 1.10  # India VIX / trailing annualised realised volatility
MIN_CREDIT_WIDTH_RATIO = 0.15  # net entry credit after entry slippage / wing width
MAX_CHEAP_IV_RV_RATIO = 1.00   # low-IV directional debit entries only
MIN_DEBIT_REWARD_RISK = 0.50   # estimated maximum reward / full reserved loss
RISK_PER_TRADE = 0.02   # fraction of current equity, never round up to one lot
MAX_LOTS = 5
MAX_ACCOUNT_DRAWDOWN = 0.15  # halt new entries until an explicit new simulation
RISK_COST_BUFFER_RS = 500.0  # per lot, additional reserve; not a guaranteed fee cap
EVALUATION_SPLIT = date(2023, 1, 1)  # diagnostic split, not untouched test data
PAPER_DB = "paper/adaptive_500k.sqlite3"
PAPER_CAPITAL = 500_000  # user-selected virtual capital; no real money

# Automatic intraday paper mode: 15-minute bias, closed 5-minute triggers.
INTRADAY_CSV = "data/intraday_nifty.csv"
INTRADAY_DB = "paper/intraday_500k.sqlite3"
INTRADAY_ENTRY_START = "09:45"
INTRADAY_ENTRY_END = "14:30"
INTRADAY_EXIT_TIME = "15:15"  # our earlier square-off target, not an exchange close claim
INTRADAY_MAX_TRADES = 3
INTRADAY_DAILY_LOSS_LIMIT = 0.03
INTRADAY_COOLDOWN_MINUTES = 15
INTRADAY_MAX_BAR_AGE_MINUTES = 10
INTRADAY_POLL_SECONDS = 60

# ----------------------------------------------------------------------------
# Legacy playbook: (trend, iv_level) -> strategy. None = no trade.
# ----------------------------------------------------------------------------
PLAYBOOK = {
    ("strong_up", "low"): "bull_call_spread",
    ("strong_up", "mid"): "bull_call_spread",
    ("strong_up", "high"): "bull_put_spread",
    ("mild_up", "low"): "bull_call_spread",
    ("mild_up", "mid"): "bull_put_spread",
    ("mild_up", "high"): "bull_put_spread",
    ("strong_down", "low"): "bear_put_spread",
    ("strong_down", "mid"): "bear_put_spread",
    ("strong_down", "high"): "bear_call_spread",
    ("mild_down", "low"): "bear_put_spread",
    ("mild_down", "mid"): "bear_call_spread",
    ("mild_down", "high"): "bear_call_spread",
    ("range", "low"): "calendar",
    ("range", "mid"): "iron_condor",
    ("range", "high"): "iron_condor",
}
# Scheduled event inside the holding week (budget, election result, RBI...):
EVENT_PLAYBOOK = {"low": "long_straddle", "mid": "long_straddle", "high": None}
# India VIX >= VIX_SHOCK:
SHOCK_STRATEGY = None
