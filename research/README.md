# Dissertation-inspired Indian-market research

These modules run offline. They never import the paper order worker, modify its
account, or send broker orders. The submitted FX notebook and PDF remain unchanged.

## Why volatility research, rather than deploying the FX graph

The dissertation reports no useful directional benefit from its graph: headline
accuracies are about 50%, and the full graph does not beat the isolated LSTM. Its
volatility control task is stronger (about 68% accuracy), but does not establish a
significant graph benefit or options profitability. FX daily results cannot be
transferred directly to Nifty intraday options.

The supplied code also needs several qualifications before reuse:

- The minimum-move pipeline filters existing test predictions using subsequently
  realized returns. It does not retrain on a filtered training set, despite the
  report's wording in section 4.10. That mask cannot select live entries.
- Walk-forward calls reuse globally standardized features and a graph estimated
  at the original split. Earlier folds can therefore use preprocessing informed
  by later dates. Refit all learned preprocessing and any graph inside each fold.
- The five-day volatility labels overlap partition boundaries and pad the last
  outcomes. Purge unresolved labels and drop incomplete future windows.
- The paired bootstrap resamples whole days, preserving cross-pair dependence,
  but not serial dependence. The new experiment uses five-session blocks.
- Selecting the median random seed using test-set accuracy is an ex-post choice.
  Select seeds/model settings without consulting held-out outcomes.

## Nifty experiment

```
.venv/bin/python -m research.indian_volatility
```

Predict the variance of the next six completed five-minute returns using past
6/24/75-bar variance, India VIX and the current OHLC range. The small ridge model
is inspired by multi-horizon volatility models, not an implementation or validation
of a full GNN or the canonical daily/weekly/monthly HAR-RV specification.

Each expanding fold has at least 20 training sessions, five validation sessions,
and five test sessions. Scaling and ridge coefficients are fitted on training only;
regularization and the simple reference model are selected on validation only.
Future labels must exist, remain in the same session and precede the next partition.
Overnight gaps are not treated as five-minute returns. Entry timestamps are limited
to 09:45–14:30 IST using the clock, not subsequent realized moves.

Results: `results/research/indian-volatility.json`. Lower QLIKE is better. A positive
baseline-minus-model QLIKE difference supports better variance forecasting on these
observations only. The 35 held-out sessions remain short and the block interval is
an exploratory uncertainty estimate. No options P&L, margin or execution advantage
has been demonstrated. **No automatic promotion to the paper strategy is enabled.**

The current dataset provides Nifty and VIX, not the synchronized multi-instrument
history needed to evaluate a useful sector/index GNN against matched non-graph
baselines. That remains a future, separately validated experiment.

## Observed option quotes

`research.option_quotes.research_fill` accepts explicit broker/exchange-export
provenance, timezone-aware quotes, actual lot sizes and total fees. It buys at ask,
sells at bid, checks quoted size, rejects quotes older than 30 seconds or later than
the decision, and requires spread-leg observations within five seconds.

This is a research adapter, not a live feed or a broker connector. It does not prove
that a multi-leg order could fill simultaneously or calculate a margin/risk limit.
No real option quote export was supplied, so observed-price options validation is
still pending. Synthetic prices are explicitly rejected by this adapter.

## Sources

- User-supplied dissertation PDF, sections 4.4, 4.9–4.11 and 6.5, and notebook modules
  `data_pipeline`, `targets`, `validation`, `significance` and the final pipeline.
- [Corsi's original multi-horizon realized-volatility paper](https://statmath.wu.ac.at/~hauser/LVs/FinEtricsQF/References/Corsi2009JFinEtrics_LMmodelRealizedVola.pdf).
- [Time-ordered validation and a gap](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).
- [Fit preprocessing on training data](https://scikit-learn.org/stable/common_pitfalls.html).
- [NSE's option-chain fields](https://www.nseindia.com/option-chain): observed bid/ask,
  liquidity, expiry and contract information are distinct from modelled premiums.

The latest isolated cloud run used 65 source sessions and 40 held-out sessions; its QLIKE was 0.392 versus 0.711 for the reference. `results/research/cloud-volatility-shadow.json` contains the detailed fold evidence. The original local result remains preserved separately. Daily cloud re-evaluation is scheduled at 16:00 IST on weekdays in a container with no network or paper-account mount.
