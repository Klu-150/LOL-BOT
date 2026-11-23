"""Dissertation-inspired Nifty volatility research. No account or broker access.

Predict the variance of the next six completed 5-minute returns, using only
observations available at the decision bar. This is not a return/P&L backtest.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = ['log_rv_6', 'log_rv_24', 'log_rv_75', 'log_vix_variance', 'log_range_variance']
SCALE = 252 * 75
EPS = 1e-10


def observations(frame, horizon=6):
    frame = frame.copy()
    if not {'timestamp', 'Open', 'High', 'Low', 'Close', 'VIX'} <= set(frame):
        raise ValueError('Require timestamp, OHLC and VIX columns')
    ts = pd.to_datetime(frame.timestamp, utc=True, errors='raise').dt.tz_convert('Asia/Kolkata')
    if ts.duplicated().any() or not ts.is_monotonic_increasing:
        raise ValueError('Bars must be ordered with unique timestamps')
    prices = frame[['Open', 'High', 'Low', 'Close', 'VIX']].apply(pd.to_numeric, errors='raise')
    if not np.isfinite(prices).all().all() or (prices <= 0).any().any():
        raise ValueError('Prices and VIX must be finite and positive')
    if ((prices.High < prices[['Open', 'Close', 'Low']].max(axis=1)) |
            (prices.Low > prices[['Open', 'Close', 'High']].min(axis=1))).any():
        raise ValueError('Invalid OHLC range')
    result = pd.DataFrame({'timestamp': ts, 'session': ts.dt.strftime('%Y-%m-%d')})
    ret = np.log(prices.Close / prices.Close.shift())
    contiguous = ts.diff() == pd.Timedelta(minutes=5)
    ret = ret.where(contiguous)  # Never treat an overnight gap as a 5-minute move.
    square = ret.pow(2) * SCALE
    for window in (6, 24, 75):
        # The 75-bar context can span sessions, excluding overnight returns.
        variance = square.rolling(window, min_periods=max(6, window-2)).mean()
        result[f'log_rv_{window}'] = np.log(variance.clip(lower=EPS))
    result['log_vix_variance'] = np.log((prices.VIX / 100).pow(2))
    result['log_range_variance'] = np.log(((np.log(prices.High/prices.Low).pow(2) / (4*np.log(2))) * SCALE).clip(lower=EPS))
    future = pd.concat([square.shift(-step) for step in range(1, horizon+1)], axis=1)
    result['target_variance'] = future.mean(axis=1, skipna=False)
    result['target_end'] = ts.shift(-horizon)
    result['persistence'] = np.exp(result.log_rv_6)
    result['vix_reference'] = np.exp(result.log_vix_variance)
    # Require the full future label window to exist, within the same session.
    complete = (result.target_end - ts == pd.Timedelta(minutes=5*horizon)) & (result.target_end.dt.date == ts.dt.date)
    clock = ts.dt.strftime('%H:%M')
    eligible = clock.between('09:45', '14:30')
    valid = complete & eligible & np.isfinite(result[FEATURES + ['target_variance']]).all(axis=1)
    return result.loc[valid].reset_index(drop=True)


def folds(rows, min_train=20, validation_days=5, test_days=5):
    days = sorted(rows.session.unique())
    for start in range(min_train + validation_days, len(days), test_days):
        test = days[start:start+test_days]
        if len(test) < test_days:
            break
        train_days = days[:start-validation_days]
        validation = days[start-validation_days:start]
        tr = np.flatnonzero(rows.session.isin(train_days))
        va = np.flatnonzero(rows.session.isin(validation))
        te = np.flatnonzero(rows.session.isin(test))
        # Explicit purging: every training/validation outcome must already exist
        # before the next fitting/evaluation partition begins.
        tr = tr[(rows.target_end.iloc[tr] < rows.timestamp.iloc[va[0]]).to_numpy()]
        va = va[(rows.target_end.iloc[va] < rows.timestamp.iloc[te[0]]).to_numpy()]
        yield tr, va, te


def fit_ridge(x, y, alpha):
    mu, sd = x.mean(axis=0), x.std(axis=0)
    sd = np.where(sd > 1e-8, sd, 1.)
    design = np.column_stack([np.ones(len(x)), (x-mu)/sd])
    penalty = np.eye(design.shape[1])*alpha
    penalty[0, 0] = 0
    beta = np.linalg.solve(design.T@design+penalty, design.T@np.log(np.maximum(y, EPS)))
    return mu, sd, beta


def predict(model, x):
    mu, sd, beta = model
    return np.exp(np.clip(np.column_stack([np.ones(len(x)), (x-mu)/sd])@beta, np.log(EPS), np.log(25.)))


def qlike(actual, forecast):
    ratio = np.maximum(actual, EPS)/np.maximum(forecast, EPS)
    return ratio - np.log(ratio) - 1


def block_interval(day_differences, block=5, iterations=2000, seed=42):
    values = np.asarray(day_differences, dtype=float)
    if len(values) < 2:
        return None
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(iterations):
        starts = rng.integers(0, len(values), int(np.ceil(len(values)/block)))
        indices = np.concatenate([(np.arange(block)+s) % len(values) for s in starts])[:len(values)]
        samples.append(float(values[indices].mean()))
    return dict(zip(['low', 'high'], map(float, np.quantile(samples, [.025, .975]))))


def evaluate(frame):
    rows = observations(frame)
    x = rows[FEATURES].to_numpy(dtype=float)
    y = rows.target_variance.to_numpy(dtype=float)
    records, fold_results = [], []
    for number, (tr, va, te) in enumerate(folds(rows), 1):
        models = [(alpha, fit_ridge(x[tr], y[tr], alpha)) for alpha in (.1, 1., 10., 100.)]
        alpha, model = min(models, key=lambda item: qlike(y[va], predict(item[1], x[va])).mean())
        # Baseline selection also uses validation only; never the held-out test.
        baseline = min(('persistence', 'vix_reference'), key=lambda name: qlike(y[va], rows[name].iloc[va].to_numpy()).mean())
        forecasts = predict(model, x[te])
        ref = rows[baseline].iloc[te].to_numpy()
        for i, pred, base in zip(te, forecasts, ref):
            records.append({'session': rows.session.iloc[i], 'timestamp': rows.timestamp.iloc[i].isoformat(),
                            'actual_variance': float(y[i]), 'forecast_variance': float(pred),
                            'baseline_variance': float(base), 'qlike_difference': float(qlike(y[i], base)-qlike(y[i], pred))})
        fold_results.append({'fold': number, 'train_sessions': int(rows.session.iloc[tr].nunique()),
                             'validation_sessions': int(rows.session.iloc[va].nunique()), 'test_sessions': int(rows.session.iloc[te].nunique()),
                             'train_last_label': rows.target_end.iloc[tr].max().isoformat(),
                             'validation_first_bar': rows.timestamp.iloc[va].min().isoformat(),
                             'validation_last_label': rows.target_end.iloc[va].max().isoformat(),
                             'test_first_bar': rows.timestamp.iloc[te].min().isoformat(), 'test_last_bar': rows.timestamp.iloc[te].max().isoformat(),
                             'alpha_selected_on_validation': alpha, 'baseline_selected_on_validation': baseline,
                             'forecast_qlike': float(qlike(y[te], forecasts).mean()), 'baseline_qlike': float(qlike(y[te], ref).mean())})
    if not records:
        raise ValueError('Need at least 30 complete sessions for a 20/5/5 walk-forward evaluation')
    predictions = pd.DataFrame(records)
    days = predictions.groupby('session').qlike_difference.mean()
    ci = block_interval(days.to_numpy())
    return {'scope': 'Offline Nifty 30-minute variance forecasting; no option trade simulation or execution',
            'source_sessions': int(rows.session.nunique()), 'first_bar': rows.timestamp.iloc[0].isoformat(),
            'last_bar': rows.timestamp.iloc[-1].isoformat(), 'features': FEATURES, 'folds': fold_results,
            'test_observations': len(predictions), 'test_sessions': len(days),
            'forecast_qlike': float(qlike(predictions.actual_variance, predictions.forecast_variance).mean()),
            'baseline_qlike': float(qlike(predictions.actual_variance, predictions.baseline_variance).mean()),
            'mean_daily_qlike_improvement': float(days.mean()), 'five_session_block_bootstrap_95_ci': ci,
            'demonstrated_volatility_improvement': bool(ci and ci['low'] > 0),
            'promotion': 'research_only', 'automatically_deployable': False,
            'limitations': ['Short public-feed history; held-out sessions are too few for production evidence',
                            'Overlapping 30-minute targets; inference uses session aggregation and five-session blocks',
                            'India VIX is a longer-horizon implied-volatility reference, not a 30-minute fair-value forecast',
                            'Forecast accuracy is not evidence of profitable options trading; no observed option quotes supplied',
                            'No multi-instrument GNN trained; available data do not support the dissertation FX graph directly']}, records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path(__file__).resolve().parents[1]/'data/intraday_nifty.csv')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1]/'results/research/indian-volatility.json')
    args = parser.parse_args()
    result, records = evaluate(pd.read_csv(args.data))
    result.update(at=datetime.now(timezone.utc).isoformat(), source_sha256=hashlib.sha256(args.data.read_bytes()).hexdigest())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    args.output.with_suffix('.predictions.json').write_text(json.dumps(records, allow_nan=False)+'\n')
    print(json.dumps({k: result[k] for k in ['source_sessions', 'test_sessions', 'forecast_qlike', 'baseline_qlike', 'five_session_block_bootstrap_95_ci', 'promotion']}, indent=2))


if __name__ == '__main__':
    main()
