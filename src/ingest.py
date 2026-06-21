"""
ingest.py  —  the data-intake layer. Accepts fresh violation records (file,
JSON, or a single map-pinned report), normalises them to the raw schema,
validates them, and appends them to a managed dataset. A rebuild then re-runs the
whole pipeline (including retraining the forecast model) on base + new data.

Design:
  * The original 105 MB file (config.BASE_RAW) is IMMUTABLE — we never touch it.
  * New records append to data/ingested.csv (small, append-only).
  * build_combined() concatenates BASE + ingested into data/combined.csv, which
    the rebuild points the pipeline at (via GRIDLOCK_RAW_CSV).
This keeps every ingest reversible (delete ingested.csv to reset) and the base safe.
"""
import sys, json, uuid
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import (BASE_RAW, DATA_DIR, CLEAN_PARQUET, BLR_LAT_MIN, BLR_LAT_MAX,
                    BLR_LON_MIN, BLR_LON_MAX, PARKING_VIOLATION_TYPES)

INGESTED_CSV = DATA_DIR / "ingested.csv"
COMBINED_CSV = DATA_DIR / "combined.csv"

_DEFAULT_DT = None


def _default_datetime():
    """Date new records to the dataset's most-recent day (not 'now') so the
    timeline stays continuous — otherwise a 2026 timestamp stretches the span and
    deflates every per-day rate. Read cheaply from the clean parquet; cached."""
    global _DEFAULT_DT
    if _DEFAULT_DT is None:
        try:
            mx = pd.read_parquet(CLEAN_PARQUET, columns=["ts_ist"])["ts_ist"].max()
            # one day inside the timeline so new records never extend the span
            # (which would deflate every per-day rate after UTC->IST conversion)
            _DEFAULT_DT = (pd.Timestamp(mx) - pd.Timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S+00")
        except Exception:
            _DEFAULT_DT = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00")
    return _DEFAULT_DT

# the columns pipeline.py reads (USECOLS)
SCHEMA = ["id", "latitude", "longitude", "location", "vehicle_type", "violation_type",
          "created_datetime", "police_station", "junction_name", "validation_status"]

# candidate source column names per schema field (canonical first)
CANDIDATES = {
    "latitude": ["latitude", "lat"],
    "longitude": ["longitude", "lng", "lon", "long"],
    "vehicle_type": ["vehicle_type", "vehicle", "type"],
    "violation_type": ["violation_type", "violation", "violations", "offence"],
    "created_datetime": ["created_datetime", "datetime", "timestamp", "time", "date"],
    "police_station": ["police_station", "station", "ps"],
    "junction_name": ["junction_name", "junction"],
    "location": ["location", "address", "place"],
    "validation_status": ["validation_status", "status"],
}


def _pick(df, field, default=None):
    """Coalesce the first present, non-null candidate column into one Series."""
    out = pd.Series([default] * len(df), index=df.index, dtype="object")
    for name in CANDIDATES[field]:
        if name in df.columns:
            col = df[name]
            if isinstance(col, pd.DataFrame):     # duplicate-named columns
                col = col.bfill(axis=1).iloc[:, 0]
            out = out.where(out.notna() & (out != default), col) if default is not None \
                else out.where(out.notna(), col)
    return out


def _as_violation_list(v):
    """Coerce any violation input into the JSON-list string the pipeline expects."""
    if isinstance(v, list):
        items = v
    elif isinstance(v, str):
        s = v.strip()
        if s.startswith("["):
            try:
                items = json.loads(s)
            except Exception:
                items = [s]
        else:
            items = [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]
    else:
        items = []
    items = [str(x).strip().upper() for x in items if str(x).strip()]
    return json.dumps(items or ["WRONG PARKING"])


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Map arbitrary incoming columns to the raw schema with sensible defaults."""
    df = df.rename(columns={c: str(c).strip().lower() for c in df.columns})
    now = _default_datetime()
    out = pd.DataFrame(index=df.index)
    out["latitude"] = pd.to_numeric(_pick(df, "latitude"), errors="coerce")
    out["longitude"] = pd.to_numeric(_pick(df, "longitude"), errors="coerce")
    out["vehicle_type"] = _pick(df, "vehicle_type", "CAR").fillna("CAR").astype(str).str.upper()
    out["violation_type"] = _pick(df, "violation_type", "WRONG PARKING").map(_as_violation_list)
    out["created_datetime"] = _pick(df, "created_datetime", now).fillna(now).astype(str)
    out["police_station"] = _pick(df, "police_station", "INGESTED").fillna("INGESTED").astype(str)
    out["junction_name"] = _pick(df, "junction_name", "No Junction").fillna("No Junction").astype(str)
    out["location"] = _pick(df, "location", "User-ingested record").fillna("User-ingested record").astype(str)
    out["validation_status"] = _pick(df, "validation_status", "approved").fillna("approved").astype(str)
    out["id"] = [f"ING{uuid.uuid4().hex[:10].upper()}" for _ in range(len(out))]
    return out[SCHEMA].reset_index(drop=True)


def validate(df: pd.DataFrame):
    """Return (good_rows, report). Drops bad geometry / non-parking offences."""
    n0 = len(df)
    geo = (df["latitude"].between(BLR_LAT_MIN, BLR_LAT_MAX)
           & df["longitude"].between(BLR_LON_MIN, BLR_LON_MAX))
    def is_parking(s):
        try:
            return any(v in PARKING_VIOLATION_TYPES for v in json.loads(s))
        except Exception:
            return False
    park = df["violation_type"].map(is_parking)
    good = df[geo & park].copy()
    report = {"received": int(n0), "accepted": int(len(good)),
              "rejected_geo": int((~geo).sum()),
              "rejected_nonparking": int((geo & ~park).sum())}
    return good, report


def read_any(filename: str, raw: bytes) -> pd.DataFrame:
    """Parse an uploaded file by extension: csv / xlsx / json."""
    import io
    name = filename.lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(raw))
    if name.endswith(".json"):
        data = json.loads(raw.decode("utf-8"))
        return pd.DataFrame(data if isinstance(data, list) else data.get("records", []))
    return pd.read_csv(io.BytesIO(raw))      # default: CSV


def append_ingested(good: pd.DataFrame):
    DATA_DIR.mkdir(exist_ok=True)
    header = not INGESTED_CSV.exists()
    good.to_csv(INGESTED_CSV, mode="a", header=header, index=False)


def ingest_frame(df: pd.DataFrame):
    """Full intake of an arbitrary frame: normalize -> validate -> append."""
    good, report = validate(normalize(df))
    if len(good):
        append_ingested(good)
    report["ingested_total"] = dataset_stats()["ingested"]
    return report


def dataset_stats():
    ingested = sum(1 for _ in open(INGESTED_CSV, encoding="utf-8")) - 1 if INGESTED_CSV.exists() else 0
    return {"ingested": max(0, ingested), "ingested_file": str(INGESTED_CSV)}


def build_combined() -> Path:
    """BASE (immutable) + ingested -> data/combined.csv for the rebuild."""
    if not INGESTED_CSV.exists():
        return BASE_RAW
    base = pd.read_csv(BASE_RAW, usecols=SCHEMA, low_memory=False)
    add = pd.read_csv(INGESTED_CSV)
    combined = pd.concat([base, add[SCHEMA]], ignore_index=True)
    combined.to_csv(COMBINED_CSV, index=False)
    return COMBINED_CSV


def reset_ingested():
    if INGESTED_CSV.exists():
        INGESTED_CSV.unlink()
    if COMBINED_CSV.exists():
        COMBINED_CSV.unlink()
