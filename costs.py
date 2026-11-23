"""Zerodha brokerage + statutory charges + slippage for one option order."""
import config as C


def slippage(theo_price: float) -> float:
    """Points lost to the bid-ask spread on one leg, one side."""
    return C.SLIPPAGE_FIXED + C.SLIPPAGE_PCT * theo_price


def order_charges(fill_price: float, side: str, lots: int = 1) -> float:
    """
    Rupee charges for one executed option order.
    side = "buy" or "sell". fill_price in points (premium per unit).
    """
    turnover = fill_price * C.LOT_SIZE * lots
    brokerage = C.BROKERAGE_PER_ORDER
    txn = C.EXCHANGE_TXN * turnover
    sebi = C.SEBI_FEE * turnover
    gst = C.GST * (brokerage + txn + sebi)
    stt = C.STT_SELL_PREMIUM * turnover if side == "sell" else 0.0
    stamp = C.STAMP_BUY * turnover if side == "buy" else 0.0
    return brokerage + txn + sebi + gst + stt + stamp


def exercise_stt(intrinsic_value: float, lots: int = 1) -> float:
    """STT on a long option that expires in the money (cash settled)."""
    return C.STT_EXERCISE * intrinsic_value * C.LOT_SIZE * lots
