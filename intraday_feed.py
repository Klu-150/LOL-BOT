"""Public 5-minute research data. Timestamps in the CSV denote bar END times."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import os
from pathlib import Path
import urllib.parse

import numpy as np
import pandas as pd

import config as C
from data import ROOT
from feed_transport import transport

ZONE = "Asia/Kolkata"


def validate_prices(frame):
    values = frame[["Open", "High", "Low", "Close"]]
    if not np.isfinite(values.to_numpy()).all() or (values <= 0).any().any():
        raise ValueError("Intraday OHLC must be finite positive prices")
    if ((frame.High < frame[["Open", "Close", "Low"]].max(axis=1)) |
            (frame.Low > frame[["Open", "Close", "High"]].min(axis=1))).any():
        raise ValueError("Intraday OHLC high/low must contain the open and close")


def chart(symbol, interval="5m", period="1mo"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe='')}?range={period}&interval={interval}"
    body = transport.fetch(url, symbol)
    if body["chart"].get("error") or not body["chart"].get("result"):
        raise ValueError(f"Data provider could not return {symbol}: {body['chart'].get('error')}")
    result = body["chart"]["result"][0]
    if result["meta"]["symbol"] != symbol:
        raise ValueError("Unexpected instrument returned by data provider")
    quotes = result["indicators"]["quote"][0]
    frame = pd.DataFrame(quotes, index=pd.to_datetime(result["timestamp"], unit="s", utc=True).tz_convert(ZONE))
    frame = frame.rename(columns=str.title).dropna(subset=["Open", "High", "Low", "Close"])
    validate_prices(frame)
    if interval == "5m":
        # Yahoo can append a live tick stamped at the last trade time. Only rows on
        # the 5-minute grid are bars; an off-grid tick must never become a "completed" bar.
        frame = frame.loc[(frame.index.second == 0) & (frame.index.minute % 5 == 0)]
        frame = frame[~frame.index.duplicated(keep="last")]
        frame.index += pd.Timedelta(minutes=5)
    frame.index.name = "timestamp"
    return frame


def refresh(path=None, period="1mo"):
    """Fetch Nifty and, when available, same-bar VIX. No orders or credentials."""
    path = Path(path or ROOT / C.INTRADAY_CSV)
    with ThreadPoolExecutor(max_workers=2) as pool:
        nifty_job = pool.submit(chart, "^NSEI", "5m", period)
        vix_job = pool.submit(chart, "^INDIAVIX", "5m", period)
        nifty = nifty_job.result()
        warning = None
        try:
            vix = vix_job.result()
            nifty["VIX"] = vix["Close"].reindex(nifty.index)
        except Exception as exc:
            nifty["VIX"] = float("nan")
            warning = f"Intraday VIX unavailable; completed prior-day VIX will be labelled as a pricing proxy: {exc}"
    now = pd.Timestamp.now(tz=ZONE)
    nifty = nifty.loc[(nifty.index <= now) & (nifty.index.strftime("%H:%M") >= "09:20") &
                      (nifty.index.strftime("%H:%M") <= "15:30")]
    nifty["source"] = "Yahoo public 5m; model options"
    if path.exists():
        existing = load(path)
        nifty = pd.concat([existing, nifty]).sort_index()
        nifty = nifty[~nifty.index.duplicated(keep="last")]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    nifty.to_csv(temporary)
    os.replace(temporary, path)
    return {"bars": len(nifty), "latest_bar": nifty.index[-1].isoformat() if len(nifty) else None,
            "source": "Yahoo public research feed", "warning": warning}


def load(path=None):
    path = Path(path or ROOT / C.INTRADAY_CSV)
    if not path.exists():
        raise ValueError("No intraday data. Refresh the 5-minute feed or provide data/intraday_nifty.csv.")
    frame = pd.read_csv(path)
    if "timestamp" not in frame or any(k not in frame for k in ["Open", "High", "Low", "Close"]):
        raise ValueError("Intraday CSV needs timestamp, Open, High, Low, Close; timestamps are 5-minute bar ends")
    index = pd.to_datetime(frame.pop("timestamp"), utc=True).dt.tz_convert(ZONE)
    frame.index = pd.DatetimeIndex(index, name="timestamp")
    if frame.index.has_duplicates:
        raise ValueError("Intraday timestamps must be unique")
    if frame.empty or not frame.index.is_monotonic_increasing:
        raise ValueError("Intraday data must be nonempty and chronological")
    if any(frame.index.minute % 5) or any(frame.index.second) or any(frame.index.microsecond):
        raise ValueError("Intraday timestamps must be on a 5-minute bar-end boundary")
    for key in ["Open", "High", "Low", "Close"]:
        frame[key] = pd.to_numeric(frame[key], errors="raise")
    validate_prices(frame)
    if "VIX" not in frame:
        frame["VIX"] = float("nan")
    return frame


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", choices=["1mo", "60d"], default="1mo")
    args = parser.parse_args()
    print(json.dumps(refresh(period=args.period), indent=2))
