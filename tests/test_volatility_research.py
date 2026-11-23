import numpy as np
import pandas as pd
import pytest

from research.indian_volatility import observations, folds, fit_ridge, predict, block_interval


def fixture(days=36):
    rng=np.random.default_rng(12)
    ts=pd.DatetimeIndex([t for day in pd.bdate_range('2026-01-01',periods=days)
                        for t in pd.date_range(str(day.date())+' 09:20',periods=75,freq='5min',tz='Asia/Kolkata')])
    close=25000*np.exp(np.cumsum(rng.normal(0,.0004,len(ts))))
    return pd.DataFrame({'timestamp':ts,'Open':close,'Close':close,'High':close*1.001,'Low':close*.999,'VIX':15.})


def test_features_do_not_change_when_future_prices_change():
    data=fixture();split=1200
    before=observations(data)
    data.loc[split:,['Open','Close','High','Low']]*=1.5
    after=observations(data)
    cutoff=pd.Timestamp(data.timestamp.iloc[split])
    cols=['timestamp','log_rv_6','log_rv_24','log_rv_75','log_vix_variance','log_range_variance']
    pd.testing.assert_frame_equal(before.loc[before.timestamp<cutoff,cols].reset_index(drop=True),
                                  after.loc[after.timestamp<cutoff,cols].reset_index(drop=True))


def test_forward_labels_never_cross_sessions_or_get_padded():
    data=fixture();rows=observations(data)
    assert (rows.target_end-rows.timestamp==pd.Timedelta(minutes=30)).all()
    assert (rows.target_end.dt.date==rows.timestamp.dt.date).all()
    assert rows.target_end.max()<data.timestamp.max()
    assert (rows.target_variance>0).all()
    for tr,va,te in folds(rows):
        assert rows.target_end.iloc[tr].max()<rows.timestamp.iloc[va].min()
        assert rows.target_end.iloc[va].max()<rows.timestamp.iloc[te].min()
        assert set(rows.session.iloc[tr]).isdisjoint(rows.session.iloc[te])


def test_training_scaler_and_forecast_ignore_unseen_values():
    rng=np.random.default_rng(3);x=rng.normal(size=(30,5));y=np.exp(rng.normal(size=30))
    model=fit_ridge(x[:20],y[:20],1.)
    pred=predict(model,x[20:25]);x[25:]=1e8
    assert np.isfinite(pred).all() and (pred>0).all()
    np.testing.assert_array_equal(pred,predict(model,x[20:25]))
    assert block_interval([.1,.2,.3],iterations=100,seed=1)==block_interval([.1,.2,.3],iterations=100,seed=1)


def test_duplicate_and_invalid_prices_fail_closed():
    data=fixture();data.loc[3,'timestamp']=data.timestamp.iloc[2]
    with pytest.raises(ValueError):observations(data)
    data=fixture();data.loc[3,'High']=1
    with pytest.raises(ValueError):observations(data)
