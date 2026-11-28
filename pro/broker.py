"""Virtual broker: place and manage paper orders with live prices and virtual money.

A separate account from the bot's trial book (paper/pro_broker.json). Instruments:
  EQ:<SYMBOL>                       Nifty 50 stocks, products CNC (delivery) or MIS (intraday)
  OPT:NIFTY:<YYYY-MM-DD>:<K>:<CE|PE> Nifty index options (lot size from config), products NRML or MIS
Order types: MARKET, LIMIT, SL (trigger then limit), SL-M (trigger then market). Orders placed outside
market hours are queued (AMO) and handled at the next session. Prices: stocks use the latest public quote
(about 1 minute); options use the model price from Nifty and India VIX (no live option quotes) with a
bid/ask spread. Charges are estimates. No real orders are ever sent anywhere.
"""
from datetime import date, datetime, time, timedelta
import json
import math
import os
import threading
import uuid
from zoneinfo import ZoneInfo

import config as C
import costs
import pricing
from exchange_calendar import HOLIDAYS

ZONE = ZoneInfo("Asia/Kolkata")
LOT = C.LOT_SIZE
DEFAULT_CAPITAL = 500_000.0
EQ_SPREAD = 0.0005          # each side of LTP for stock bid/ask
MAX_QUOTE_AGE = 600         # seconds; never fill on a staler quote during the session
SHORT_OPTION_MARGIN = 0.12  # of underlying notional per unhedged short option (approximation of SPAN+exposure)
OPEN_STATES = ("OPEN", "AMO", "TRIGGER_PENDING")


# ------------------------------------------------------------------ helpers
def session_open(now):
    t = now.strftime("%H:%M:%S")
    return now.weekday() < 5 and now.date().isoformat() not in HOLIDAYS and "09:15:00" <= t < "15:30:00"


def expiry_close(d):
    return datetime.combine(d, time(15, 30), ZONE)


def expiries(now, weeks=4, months=2):
    """Next weekly (Tuesday) and monthly (last Tuesday) Nifty expiries; holidays not adjusted."""
    out, d = set(), now.date()
    while len(out) < weeks:
        if d.weekday() == 1 and expiry_close(d) > now:
            out.add(d)
        d += timedelta(days=1)
    m = now.date().replace(day=1)
    for _ in range(months + 1):
        nxt = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        last = nxt - timedelta(days=1)
        last -= timedelta(days=(last.weekday() - 1) % 7)
        if expiry_close(last) > now:
            out.add(last)
        m = nxt
    return sorted(out)[: weeks + months]


def parse(instrument):
    parts = instrument.split(":")
    if parts[0] == "EQ" and len(parts) == 2 and parts[1]:
        return {"kind": "EQ", "symbol": parts[1]}
    if parts[0] == "OPT" and len(parts) == 5 and parts[1] == "NIFTY" and parts[4] in ("CE", "PE"):
        k = float(parts[3])
        if k <= 0 or k % C.STRIKE_STEP:
            raise ValueError("Strike must be on the 50-point grid")
        return {"kind": "OPT", "expiry": date.fromisoformat(parts[2]), "strike": k, "cp": parts[4]}
    raise ValueError("Unknown instrument")


def option_id(expiry, strike, cp):
    return f"OPT:NIFTY:{expiry.isoformat()}:{int(strike)}:{cp}"


def label(instrument):
    p = parse(instrument)
    if p["kind"] == "EQ":
        return p["symbol"]
    return f"NIFTY {p['expiry']:%d %b} {int(p['strike'])} {p['cp']}"


def eq_charges(value, side, product):
    """Estimated Indian equity charges for one order (rupees)."""
    if product == "CNC":
        brokerage, stt = 0.0, 0.001 * value
        stamp = 0.00015 * value if side == "BUY" else 0.0
        dp = 15.34 if side == "SELL" else 0.0
    else:
        brokerage, stt = min(20.0, 0.0003 * value), (0.00025 * value if side == "SELL" else 0.0)
        stamp, dp = (0.00003 * value if side == "BUY" else 0.0), 0.0
    exch, sebi = 0.0000297 * value, 0.000001 * value
    return round(brokerage + stt + stamp + dp + exch + sebi + 0.18 * (brokerage + exch + sebi), 2)


def option_charges(price, qty, side):
    return round(costs.order_charges(price, "buy" if side == "BUY" else "sell", qty / LOT), 2)


# ----------------------------------------------------------------- quotes
class Quotes:
    """Bid/ask/last for any instrument from the engine's live market snapshots."""

    def __init__(self, stock_quote, index_quote, clock=None):
        self.stock_quote, self.index_quote = stock_quote, index_quote   # callables
        self.clock = clock or (lambda: datetime.now(ZONE))

    def get(self, instrument):
        p, now = parse(instrument), self.clock()
        if p["kind"] == "EQ":
            q = self.stock_quote(p["symbol"])
            if not q or not q.get("price"):
                return None
            ltp = float(q["price"])
            when = datetime.fromisoformat(q["time"]) if q.get("time") else None
            return {"ltp": round(ltp, 2), "bid": round(ltp * (1 - EQ_SPREAD), 2), "ask": round(ltp * (1 + EQ_SPREAD), 2),
                    "time": when, "model": False, "prev_close": q.get("prev_close")}
        idx = self.index_quote()
        if not idx or not idx.get("spot") or not idx.get("vix"):
            return None
        spot, vix = float(idx["spot"]), float(idx["vix"])
        years = max((expiry_close(p["expiry"]) - now).total_seconds(), 60) / (365 * 86400)
        if now >= expiry_close(p["expiry"]):
            mid = pricing.intrinsic(spot, p["strike"], "C" if p["cp"] == "CE" else "P")
            half = 0.0
        else:
            mid = pricing.price(spot, p["strike"], years, vix / 100, "C" if p["cp"] == "CE" else "P")
            half = costs.slippage(mid)
        return {"ltp": round(mid, 2), "bid": round(max(0.05, mid - half), 2), "ask": round(mid + half, 2),
                "time": idx.get("time"), "model": True, "spot": spot, "vix": vix,
                "delta": round(pricing.delta(spot, p["strike"], years, vix / 100, "C" if p["cp"] == "CE" else "P"), 3)}


# ------------------------------------------------------------------ broker
class Broker:
    def __init__(self, path, quotes, clock=None):
        self.path, self.quotes = path, quotes
        self.clock = clock or (lambda: datetime.now(ZONE))
        self._lock = threading.RLock()
        self.acct = self._load()

    # persistence
    def _new(self, capital=DEFAULT_CAPITAL):
        return {"capital": float(capital), "cash": float(capital), "created": self.clock().isoformat(),
                "orders": [], "trades": [], "positions": {}, "charges_total": 0.0, "last_day": None}

    def _load(self):
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return self._new()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.acct, default=str))
        os.replace(tmp, self.path)

    def reset(self, capital):
        capital = float(capital)
        if not 10_000 <= capital <= 100_000_000:
            raise ValueError("Capital must be between ₹10,000 and ₹10 crore")
        with self._lock:
            self.acct = self._new(capital)
            self._save()
        return self.snapshot()

    # margin and funds
    def _margin(self, positions):
        """Margin blocked for short positions. Long positions are paid in full from cash (no leverage)."""
        total, groups = 0.0, {}
        for key, pos in positions.items():
            if pos["qty"] >= 0:
                continue
            p = parse(pos["instrument"])
            if p["kind"] == "EQ":
                q = self.quotes.get(pos["instrument"])
                total += abs(pos["qty"]) * (q["ltp"] if q else pos["avg"])
            else:
                groups.setdefault((p["expiry"], p["cp"]), [])
        for (expiry, cp), _ in groups.items():
            legs = [(parse(pos["instrument"])["strike"], pos["qty"]) for pos in positions.values()
                    if pos["qty"] and parse(pos["instrument"])["kind"] == "OPT"
                    and parse(pos["instrument"])["expiry"] == expiry and parse(pos["instrument"])["cp"] == cp]
            shorts = sorted([[k, -q] for k, q in legs if q < 0], key=lambda x: x[0], reverse=(cp == "PE"))
            longs = sorted([[k, q] for k, q in legs if q > 0], key=lambda x: x[0], reverse=(cp == "PE"))
            idx = self.quotes.index_quote() or {}
            spot = float(idx.get("spot") or 0) or (shorts[0][0] if shorts else 0)
            for short in shorts:
                for lng in longs:
                    # A long further out of the money caps the loss of the short (vertical spread).
                    protective = lng[0] > short[0] if cp == "CE" else lng[0] < short[0]
                    if lng[1] <= 0 or short[1] <= 0 or not protective:
                        continue
                    n = min(short[1], lng[1])
                    total += abs(lng[0] - short[0]) * n
                    short[1] -= n
                    lng[1] -= n
                total += short[1] * spot * SHORT_OPTION_MARGIN
        return round(total, 2)

    def funds(self):
        with self._lock:
            pos = self.acct["positions"]
            value = unreal = 0.0
            for p in pos.values():
                q = self.quotes.get(p["instrument"])
                ltp = q["ltp"] if q else p["avg"]
                value += p["qty"] * ltp
                unreal += (ltp - p["avg"]) * p["qty"]
            margin = self._margin(pos)
            realised = sum(p["realised"] for p in pos.values())
            return {"capital": self.acct["capital"], "cash": round(self.acct["cash"], 2), "margin_used": margin,
                    "available": round(self.acct["cash"] - margin, 2), "positions_value": round(value, 2),
                    "account_value": round(self.acct["cash"] + value, 2), "unrealised": round(unreal, 2),
                    "realised": round(realised, 2), "charges": round(self.acct["charges_total"], 2),
                    "total_pnl": round(self.acct["cash"] + value - self.acct["capital"], 2)}

    # orders
    def place(self, instrument, side, product, order_type, qty, price=None, trigger=None):
        p = parse(instrument)
        side, product, order_type = str(side).upper(), str(product).upper(), str(order_type).upper()
        qty = int(qty)
        if side not in ("BUY", "SELL"):
            raise ValueError("Side must be BUY or SELL")
        if order_type not in ("MARKET", "LIMIT", "SL", "SL-M"):
            raise ValueError("Order type must be MARKET, LIMIT, SL or SL-M")
        allowed = ("CNC", "MIS") if p["kind"] == "EQ" else ("NRML", "MIS")
        if product not in allowed:
            raise ValueError(f"Product must be one of {', '.join(allowed)}")
        if qty <= 0 or qty > 100_000:
            raise ValueError("Quantity must be positive")
        if p["kind"] == "OPT" and qty % LOT:
            raise ValueError(f"Option quantity must be a multiple of the lot size ({LOT})")
        if p["kind"] == "OPT" and expiry_close(p["expiry"]) <= self.clock():
            raise ValueError("This option has expired")
        if order_type in ("LIMIT", "SL") and not (price and float(price) > 0):
            raise ValueError("Enter a limit price")
        if order_type in ("SL", "SL-M") and not (trigger and float(trigger) > 0):
            raise ValueError("Enter a trigger price")
        if self.quotes.get(instrument) is None:
            raise ValueError("No price available for this instrument yet")
        with self._lock:
            key = f"{instrument}|{product}"
            held = self.acct["positions"].get(key, {}).get("qty", 0)
            if product == "CNC" and side == "SELL" and qty > held:
                raise ValueError(f"You hold {held} shares in delivery; short selling needs the MIS product")
            now = self.clock()
            order = {"id": uuid.uuid4().hex[:10], "time": now.isoformat(), "instrument": instrument, "name": label(instrument),
                     "side": side, "product": product, "type": order_type, "qty": qty,
                     "price": round(float(price), 2) if price else None, "trigger": round(float(trigger), 2) if trigger else None,
                     "status": "TRIGGER_PENDING" if order_type in ("SL", "SL-M") else ("OPEN" if session_open(now) else "AMO"),
                     "fill_price": None, "filled_at": None, "charges": None, "message": None, "tag": None}
            if order["status"] == "TRIGGER_PENDING" and not session_open(now):
                order["message"] = "Queued: market closed, trigger is checked from the next open"
            self.acct["orders"].insert(0, order)
            del self.acct["orders"][500:]
            self._process_order(order, now)
            self._save()
            return order

    def cancel(self, order_id):
        with self._lock:
            for o in self.acct["orders"]:
                if o["id"] == order_id:
                    if o["status"] not in OPEN_STATES:
                        raise ValueError(f"Order is already {o['status'].lower()}")
                    o.update(status="CANCELLED", message="Cancelled by you")
                    self._save()
                    return o
        raise ValueError("Order not found")

    def _fresh(self, q, now):
        if q is None:
            return False
        t = q.get("time")
        if isinstance(t, str):
            t = datetime.fromisoformat(t)
        return t is not None and (now - t).total_seconds() <= MAX_QUOTE_AGE and t.date() == now.date()

    def _process_order(self, o, now):
        if o["status"] not in OPEN_STATES or not session_open(now):
            return
        q = self.quotes.get(o["instrument"])
        if not self._fresh(q, now):
            return
        if o["status"] == "AMO":
            o["status"] = "OPEN"
        if o["status"] == "TRIGGER_PENDING":
            hit = q["ltp"] >= o["trigger"] if o["side"] == "BUY" else q["ltp"] <= o["trigger"]
            if not hit:
                return
            o["status"], o["message"] = "OPEN", f"Triggered at {q['ltp']}"
        fill = q["ask"] if o["side"] == "BUY" else q["bid"]
        if o["type"] in ("LIMIT", "SL"):
            if (o["side"] == "BUY" and fill > o["price"]) or (o["side"] == "SELL" and fill < o["price"]):
                return
        self._execute(o, fill, now)

    def _execute(self, o, fill, now):
        p = parse(o["instrument"])
        qty = o["qty"] if o["side"] == "BUY" else -o["qty"]
        value = fill * o["qty"]
        charges = eq_charges(value, o["side"], o["product"]) if p["kind"] == "EQ" else option_charges(fill, o["qty"], o["side"])
        key = f"{o['instrument']}|{o['product']}"
        positions = json.loads(json.dumps(self.acct["positions"]))
        pos = positions.setdefault(key, {"instrument": o["instrument"], "name": o["name"], "product": o["product"],
                                         "qty": 0, "avg": 0.0, "realised": 0.0})
        old = pos["qty"]
        if old == 0 or (old > 0) == (qty > 0):
            pos["avg"] = (pos["avg"] * abs(old) + fill * abs(qty)) / (abs(old) + abs(qty))
        else:
            closed = min(abs(old), abs(qty))
            pos["realised"] += (fill - pos["avg"]) * closed * (1 if old > 0 else -1)
            if abs(qty) > abs(old):
                pos["avg"] = fill
        pos["qty"] = old + qty
        if pos["qty"] == 0:
            pos["avg"] = 0.0
        pos["realised"] -= charges
        cash_after = self.acct["cash"] - qty * fill - charges
        reducing = old != 0 and (old > 0) != (qty > 0) and abs(qty) <= abs(old)
        if not o.get("tag") and not reducing:
            # Rule: after the trade, cash minus margin blocked for shorts must not go negative (no leverage).
            short = cash_after - self._margin(positions)
            if short < 0:
                reason = "Insufficient funds" if o["side"] == "BUY" else "Insufficient margin"
                o.update(status="REJECTED", message=f"{reason}: short by ₹{-short:,.0f}")
                return
        self.acct["positions"] = positions
        self.acct["cash"] = cash_after
        self.acct["charges_total"] += charges
        o.update(status="COMPLETE", fill_price=round(fill, 2), filled_at=now.isoformat(), charges=charges,
                 message=(o.get("message") or "") + (" · model option price" if p["kind"] == "OPT" else ""))
        self.acct["trades"].insert(0, {"order_id": o["id"], "time": now.isoformat(), "instrument": o["instrument"],
                                       "name": o["name"], "side": o["side"], "product": o["product"], "qty": o["qty"],
                                       "price": round(fill, 2), "charges": charges, "tag": o.get("tag")})
        del self.acct["trades"][1000:]

    def _close_position(self, pos, now, price, tag, message):
        side = "SELL" if pos["qty"] > 0 else "BUY"
        o = {"id": uuid.uuid4().hex[:10], "time": now.isoformat(), "instrument": pos["instrument"], "name": pos["name"],
             "side": side, "product": pos["product"], "type": "MARKET", "qty": abs(pos["qty"]), "price": None,
             "trigger": None, "status": "OPEN", "fill_price": None, "filled_at": None, "charges": None,
             "message": message, "tag": tag}
        self.acct["orders"].insert(0, o)
        self._execute(o, price, now)

    # periodic processing
    def process(self, now=None):
        """Fill pending orders, square off intraday at 15:20, expire DAY orders at 15:30 and settle expiries."""
        now = now or self.clock()
        with self._lock:
            changed = False
            for o in list(self.acct["orders"]):
                if o["status"] in OPEN_STATES:
                    before = o["status"]
                    self._process_order(o, now)
                    changed |= o["status"] != before
            today = now.date().isoformat()
            if session_open(now) and now.strftime("%H:%M") >= "15:20":
                for pos in list(self.acct["positions"].values()):
                    if pos["product"] == "MIS" and pos["qty"]:
                        q = self.quotes.get(pos["instrument"])
                        if self._fresh(q, now):
                            self._close_position(pos, now, q["bid"] if pos["qty"] > 0 else q["ask"], "auto_square_off",
                                                 "Intraday (MIS) auto square-off at 15:20")
                            changed = True
            if now.strftime("%H:%M") >= "15:30" or now.weekday() >= 5:
                for o in self.acct["orders"]:
                    if o["status"] in ("OPEN", "TRIGGER_PENDING") and o["time"][:10] <= today and not o.get("tag"):
                        placed = datetime.fromisoformat(o["time"])
                        if placed.date() < now.date() or session_open(placed):
                            o.update(status="CANCELLED", message="Day order expired unfilled at the close")
                            changed = True
            idx = self.quotes.index_quote() or {}
            for pos in list(self.acct["positions"].values()):
                p = parse(pos["instrument"])
                if p["kind"] == "OPT" and pos["qty"] and now >= expiry_close(p["expiry"]) and idx.get("spot"):
                    value = pricing.intrinsic(float(idx["spot"]), p["strike"], "C" if p["cp"] == "CE" else "P")
                    self._close_position(pos, now, value, "expiry_settlement",
                                         f"Expired: settled at intrinsic value {value:.2f}")
                    changed = True
            self.acct["positions"] = {k: v for k, v in self.acct["positions"].items() if v["qty"] or v["realised"]}
            if changed:
                self._save()
            return changed

    # views
    def snapshot(self):
        with self._lock:
            positions = []
            for key, pos in self.acct["positions"].items():
                q = self.quotes.get(pos["instrument"])
                ltp = q["ltp"] if q else pos["avg"]
                pnl = (ltp - pos["avg"]) * pos["qty"] + pos["realised"]
                positions.append({**pos, "key": key, "ltp": ltp, "pnl": round(pnl, 2),
                                  "value": round(ltp * pos["qty"], 2), "model": bool(q and q.get("model")),
                                  "change_pct": round(100 * (ltp / q["prev_close"] - 1), 2) if q and q.get("prev_close") else None})
            return {"funds": self.funds(), "orders": self.acct["orders"][:200], "trades": self.acct["trades"][:200],
                    "positions": [p for p in positions if p["product"] != "CNC" or not p["qty"]],
                    "holdings": [p for p in positions if p["product"] == "CNC" and p["qty"]],
                    "created": self.acct["created"], "session_open": session_open(self.clock()), "lot_size": LOT}

    def chain(self, expiry=None, width=12):
        now = self.clock()
        exps = expiries(now)
        exp = date.fromisoformat(expiry) if expiry else exps[0]
        if exp not in exps:
            raise ValueError("Unknown expiry")
        idx = self.quotes.index_quote() or {}
        if not idx.get("spot"):
            raise ValueError("Nifty price unavailable")
        atm = pricing.round_strike(float(idx["spot"]))
        rows = []
        for k in [atm + i * C.STRIKE_STEP for i in range(-width, width + 1)]:
            row = {"strike": int(k)}
            for cp in ("CE", "PE"):
                inst = option_id(exp, k, cp)
                q = self.quotes.get(inst)
                row[cp] = {"instrument": inst, **{f: q[f] for f in ("ltp", "bid", "ask", "delta")}} if q else None
            rows.append(row)
        return {"expiry": exp.isoformat(), "expiries": [e.isoformat() for e in exps], "spot": idx["spot"],
                "vix": idx.get("vix"), "atm": int(atm), "rows": rows, "lot_size": LOT, "model": True}
