"""
forecast.py  —  Predict NEXT WEEK's parking-violation load per zone, so
enforcement can be planned before the congestion happens (proactive, not
reactive).

FRAMING
  We build a zone x day panel (one row per zone per calendar day, zeros filled)
  and train a gradient-boosted regressor to predict a zone's ticket count 7 days
  ahead. Every feature is computed from history that is >= 7 days old, so the
  same model can forecast all 7 future days at once with no leakage and no
  iterative error build-up.

WHY gradient boosting + this validation
  Counts are non-linear in weekday/seasonality/recent-trend; HistGradientBoosting
  handles that with no scaling. We hold out the LAST 21 days as a time-based test
  set and compare against a strong seasonal baseline (same weekday last week).
  Beating that baseline is the bar a forecasting model must clear.

OUTPUT
  outputs/forecast_next_week.csv   - zone x date predicted tickets
  outputs/forecast_hotspots.csv    - zones ranked by predicted next-week load
  outputs/forecast_accuracy.png    - predicted vs actual on the holdout
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import OUT_DIR

LABELLED = OUT_DIR / "violations_labelled.parquet"
HORIZON = 7          # forecast 7 days ahead
TEST_DAYS = 21       # time-based holdout


def build_panel(df):
    """zone x day counts, zero-filled across each zone's active span."""
    df = df[df["zone"] != "__noise__"].copy()
    df["date"] = pd.to_datetime(df["date"])
    daily = df.groupby(["zone", "date"]).size().rename("y").reset_index()

    full_dates = pd.date_range(df["date"].min(), df["date"].max(), freq="D")
    zones = daily["zone"].unique()
    idx = pd.MultiIndex.from_product([zones, full_dates], names=["zone", "date"])
    panel = daily.set_index(["zone", "date"]).reindex(idx, fill_value=0).reset_index()

    # static zone attributes (mean severity, junction share, vehicle blocking)
    zattr = (df.groupby("zone")
               .agg(sev=("severity", "mean"),
                    jn=("at_junction", "mean"),
                    veh=("vehicle_block", "mean"),
                    lat=("latitude", "mean"),
                    lon=("longitude", "mean"),
                    junction_name=("junction_name", lambda s: s.mode().iloc[0]),
                    police_station=("police_station", lambda s: s.mode().iloc[0]))
               .reset_index())
    panel = panel.merge(zattr, on="zone", how="left")
    return panel


def add_features(panel):
    """All lag/rolling features use data >= HORIZON days old (leakage-safe)."""
    panel = panel.sort_values(["zone", "date"]).copy()
    g = panel.groupby("zone")["y"]
    panel["dow"] = panel["date"].dt.dayofweek
    panel["is_weekend"] = (panel["dow"] >= 5).astype(int)
    panel["doy"] = panel["date"].dt.dayofyear

    panel["lag7"]  = g.shift(7)
    panel["lag14"] = g.shift(14)
    panel["lag21"] = g.shift(21)
    # rolling stats computed on the series shifted by HORIZON (only past info)
    sh = g.shift(HORIZON)
    panel["roll7"]  = sh.rolling(7,  min_periods=1).mean().reset_index(level=0, drop=True)
    panel["roll14"] = sh.rolling(14, min_periods=1).mean().reset_index(level=0, drop=True)
    panel["roll28"] = sh.rolling(28, min_periods=1).mean().reset_index(level=0, drop=True)
    panel["dow_mean"] = (panel.groupby(["zone", "dow"])["lag7"]
                              .transform(lambda s: s.expanding().mean()))
    return panel


FEATURES = ["dow", "is_weekend", "doy", "sev", "jn", "veh",
            "lag7", "lag14", "lag21", "roll7", "roll14", "roll28", "dow_mean"]


def main():
    df = pd.read_parquet(LABELLED)
    print(f"Loaded {len(df):,} labelled violations.")

    panel = add_features(build_panel(df))
    panel = panel.dropna(subset=["lag21"])          # need >=21 days of history
    print(f"Panel: {len(panel):,} zone-day rows, {panel['zone'].nunique():,} zones, "
          f"{panel['date'].min().date()} -> {panel['date'].max().date()}")

    # ---- time-based train/test split ------------------------------------
    cutoff = panel["date"].max() - pd.Timedelta(days=TEST_DAYS)
    train = panel[panel["date"] <= cutoff]
    test  = panel[panel["date"] > cutoff]

    model = HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.05, max_depth=7,
        l2_regularization=1.0, random_state=0)
    model.fit(train[FEATURES], train["y"])

    pred = np.clip(model.predict(test[FEATURES]), 0, None)
    mae = mean_absolute_error(test["y"], pred)
    base = test["lag7"].fillna(test["roll7"]).clip(lower=0)   # seasonal baseline
    mae_base = mean_absolute_error(test["y"], base)
    skill = (1 - mae / mae_base) * 100
    print(f"\nHoldout ({TEST_DAYS} d):  model MAE={mae:.3f}  "
          f"baseline(lag7) MAE={mae_base:.3f}  ->  {skill:+.1f}% better than baseline")

    # zone-level holdout accuracy (what ops cares about: weekly totals)
    tz = test.assign(pred=pred).groupby("zone").agg(
        actual=("y", "sum"), pred=("pred", "sum"))
    corr = tz["actual"].corr(tz["pred"])
    print(f"Zone weekly-total correlation (actual vs pred): r={corr:.3f}")

    # ---- accuracy plot ---------------------------------------------------
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
    daily_a = test.groupby("date")["y"].sum()
    daily_p = test.assign(p=pred).groupby("date")["p"].sum()
    ax[0].plot(daily_a.index, daily_a.values, "o-", label="actual", color="#111")
    ax[0].plot(daily_p.index, daily_p.values, "s--", label="forecast", color="#f03b20")
    ax[0].set_title("Citywide daily tickets — holdout", weight="bold", fontsize=11)
    ax[0].legend(); ax[0].tick_params(axis="x", rotation=45, labelsize=8)
    ax[1].scatter(tz["actual"], tz["pred"], s=12, alpha=.5, color="#3182bd")
    lim = max(tz["actual"].max(), tz["pred"].max())
    ax[1].plot([0, lim], [0, lim], "k--", lw=1)
    ax[1].set_xlabel("actual weekly tickets"); ax[1].set_ylabel("predicted")
    ax[1].set_title(f"Per-zone weekly total (r={corr:.2f})", weight="bold", fontsize=11)
    fig.tight_layout(); fig.savefig(OUT_DIR / "forecast_accuracy.png", dpi=130)
    plt.close(fig)

    # ---- refit on ALL data, forecast the next 7 days --------------------
    model.fit(panel[FEATURES], panel["y"])
    last = panel["date"].max()
    future_dates = pd.date_range(last + pd.Timedelta(days=1), periods=HORIZON, freq="D")

    # for a 7-day-ahead horizon, future-day features come from the last known
    # week's lags/rollings — reuse each zone's most recent feature row.
    recent = panel.sort_values("date").groupby("zone").tail(1).set_index("zone")
    zmeta = recent[["lat", "lon", "sev", "jn", "veh",
                    "junction_name", "police_station",
                    "lag7", "lag14", "lag21", "roll7", "roll14", "roll28", "dow_mean"]]

    rows = []
    for d in future_dates:
        fd = zmeta.copy()
        fd["zone"] = fd.index
        fd["date"] = d
        fd["dow"] = d.dayofweek
        fd["is_weekend"] = int(d.dayofweek >= 5)
        fd["doy"] = d.dayofyear
        fd["pred"] = np.clip(model.predict(fd[FEATURES]), 0, None)
        rows.append(fd[["zone", "date", "pred", "lat", "lon",
                        "junction_name", "police_station"]])
    fc = pd.concat(rows, ignore_index=True)
    fc["pred"] = fc["pred"].round(2)
    fc.to_csv(OUT_DIR / "forecast_next_week.csv", index=False)

    ranked = (fc.groupby(["zone", "junction_name", "police_station", "lat", "lon"])
                ["pred"].sum().rename("pred_week").reset_index()
                .sort_values("pred_week", ascending=False).reset_index(drop=True))
    ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
    ranked["pred_week"] = ranked["pred_week"].round(1)
    ranked.to_csv(OUT_DIR / "forecast_hotspots.csv", index=False)

    print(f"\nForecast window: {future_dates[0].date()} -> {future_dates[-1].date()}")
    print(f"Predicted total tickets next week: {fc['pred'].sum():,.0f}")
    print("\nTOP 10 PREDICTED HOTSPOTS NEXT WEEK:")
    show = ranked.head(10)[["rank", "pred_week", "junction_name", "police_station"]]
    print(show.to_string(index=False))
    print("\nWrote forecast_next_week.csv, forecast_hotspots.csv, forecast_accuracy.png")


if __name__ == "__main__":
    main()
