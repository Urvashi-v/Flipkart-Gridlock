"""
Central configuration for the Gridlock parking-congestion intelligence project.
Keeping paths and tunable constants in one place so every script stays consistent.
"""
import os
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parent
# Raw CSV location is overridable via env var so the pipeline is portable
# (Docker / another machine): set GRIDLOCK_RAW_CSV=/path/to/file.csv
_DEFAULT_RAW = r"C:\Users\URVASHI VERMA\Downloads\jan to may police violation_anonymized791b166.csv"
RAW_CSV = Path(os.environ.get("GRIDLOCK_RAW_CSV", _DEFAULT_RAW))
# Immutable original base — ingestion appends ON TOP of this, never mutates it.
BASE_RAW = Path(_DEFAULT_RAW)
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "outputs"
DATA_DIR.mkdir(exist_ok=True)
OUT_DIR.mkdir(exist_ok=True)

# Cleaned/feature-engineered parquet produced by pipeline.py
CLEAN_PARQUET = DATA_DIR / "violations_clean.parquet"

# ---------------------------------------------------------------- geography
# Bengaluru bounding box (used to drop obviously bad GPS coordinates).
BLR_LAT_MIN, BLR_LAT_MAX = 12.7, 13.2
BLR_LON_MIN, BLR_LON_MAX = 77.3, 77.9

# ---------------------------------------------------------------- zoning
EARTH_RADIUS_M = 6_371_000.0
M_PER_DEG_LAT = 111_320.0   # ~constant

# Primary hotspot unit = a uniform grid cell ("enforcement zone").
# A ~150 m cell ≈ one city block: small enough to dispatch a patrol to, large
# enough to be statistically stable. Chosen over DBSCAN because density chaining
# merged whole commercial corridors (1.8 km blobs) into a single un-actionable
# hotspot. A grid gives bounded, comparable, patrol-able zones.
GRID_SIZE_M = 150
MIN_ZONE_TICKETS = 30       # a zone must have at least this many violations

# (kept for the optional DBSCAN comparison view)
HOTSPOT_EPS_M = 60
HOTSPOT_MIN_SAMPLES = 30

# ---------------------------------------------------------------- scoring weights
# Congestion Impact Score (CIS) component weights. Must sum to 1.0.
CIS_WEIGHTS = {
    "volume":      0.35,   # how many violations (log-scaled density)
    "severity":    0.25,   # weighted by how much each violation type blocks flow
    "junction":    0.20,   # share of violations at/near a junction
    "vehicle":     0.10,   # share of large/blocking vehicles
    "persistence": 0.10,   # spread across days/hours = chronic, not one-off
}

# How much each violation type blocks moving traffic (0-1).
# Higher = sits in the carriageway / chokes an intersection.
# Keys match the exact strings observed in the data (see profile_data.py output).
VIOLATION_SEVERITY = {
    "PARKING IN A MAIN ROAD": 1.00,
    "PARKING NEAR TRAFFIC LIGHT OR ZEBRA CROSS": 0.97,
    "PARKING NEAR ROAD CROSSING": 0.95,
    "DOUBLE PARKING": 0.90,
    "PARKING OPPOSITE TO ANOTHER PARKED VEHICLE": 0.80,
    "PARKING NEAR BUSTOP/SCHOOL/HOSPITAL ETC": 0.70,
    "PARKING OTHER THAN BUS STOP": 0.65,
    "WRONG PARKING": 0.55,
    "NO PARKING": 0.45,
    "PARKING ON FOOTPATH": 0.40,
}
DEFAULT_SEVERITY = 0.50  # any parking violation type not listed above

# Violation types that actually relate to parking/congestion. Everything else
# (defective number plate, refuse to hire, excess fare, seat belt, side mirror...)
# is enforcement noise for THIS problem and is dropped from the congestion model.
PARKING_VIOLATION_TYPES = set(VIOLATION_SEVERITY.keys())

# Relative road-footprint / blocking factor by vehicle type (0-1).
# Keys match exact strings in the data.
VEHICLE_BLOCKING = {
    "TANKER": 1.00, "BUS (BMTC/KSRTC)": 1.00, "PRIVATE BUS": 1.00,
    "HGV": 0.95, "LORRY/GOODS VEHICLE": 0.95, "TRUCK": 0.95,
    "LGV": 0.80, "TEMPO": 0.78, "MAXI-CAB": 0.75, "VAN": 0.72,
    "JEEP": 0.65, "CAR": 0.60, "GOODS AUTO": 0.58,
    "PASSENGER AUTO": 0.55, "AUTO": 0.55,
    "SCOOTER": 0.30, "MOTOR CYCLE": 0.30, "MOPED": 0.28, "BICYCLE": 0.15,
}
DEFAULT_VEHICLE_BLOCKING = 0.50

# ---------------------------------------------------------------- demand-generator context
# Ordered most-specific -> most-generic. First category whose keyword appears in a
# zone's address/junction text wins. Explains WHY a hotspot exists and ties it to
# the "commercial areas, metro stations, events" language in the problem statement.
CONTEXT_RULES = [
    ("Metro / Transit hub", ["metro", "railway", "bus stand", "bus station", "kbs",
                              "majestic", "satellite", "depot", "k.b.s"]),
    ("Wholesale market",     ["market", "mandi", "bazaar", "apmc"]),
    ("Mall / Shopping",      ["mall", "shopping", "plaza", "forum", "complex", "emporium"]),
    ("Hospital",             ["hospital", "clinic", "nursing home", "medical"]),
    ("Education",            ["school", "college", "university", "institute", "vidya", "campus"]),
    ("Religious",            ["temple", "church", "mosque", "masjid", "dargah", "math"]),
    ("Entertainment",        ["theatre", "theater", "cinema", "stadium", "club", "palace"]),
    ("Commercial street",    ["main road", "circle", "cross", "bazar", "street", "road junction"]),
    ("Residential",          ["layout", "nagar", "colony", "extension", "block", "ward"]),
]
DEFAULT_CONTEXT = "Mixed / Other"

# ---------------------------------------------------------------- enforcement optimiser
OPT = {
    # Fraction of a zone's window-impact a single patrol-shift actually captures
    # (deterrence isn't perfect).
    "capture_rate": 0.70,
    # Patrol-shift slots available per day to allocate across the city.
    "patrol_slots_per_day": 25,
}

# ---------------------------------------------------------------- AI event agent
# An internet-connected Claude agent that finds real-world demand drivers
# (festivals, scheduled events, rallies, mall sales) for the coming week and
# reasons about which hotspots they will overload — turning the statistical
# forecast into an explained, event-aware one. Live mode needs ANTHROPIC_API_KEY;
# without it the module falls back to a bundled sample so the demo still runs.
AI = {
    "model": "claude-opus-4-8",      # most capable; per Anthropic guidance
    "city": "Bengaluru",
    "horizon_days": 7,               # look this many days ahead
    "top_zones_for_ai": 30,          # only reason over the highest-value hotspots
    "max_events": 40,
}

# ---------------------------------------------------------------- live congestion / Google Maps
# District = a police jurisdiction. The command centre fuses our structural parking
# pressure with real-time road congestion from Google (travel-time index via the
# Distance Matrix API, key in GOOGLE_MAPS_API_KEY) — or a time-of-day simulation
# when no key is set. Each district blinks by live level and drills down to its
# hotspots ("areas of attention for police"). Google deep-links (traffic layer)
# work with no key at all.
CONGESTION = {
    "n_districts": 24,               # show the busiest N police jurisdictions
    "hotspots_per_district": 5,
    "structural_weight": 0.45,       # parking pressure vs live traffic in the blend
    "google_probe_pairs": 1,         # Distance-Matrix probes per district (live mode)
}

# ---------------------------------------------------------------- access control
# Two roles. ADMIN (the one head person) can ingest data + retrain the system;
# VIEWER can see every analytic but cannot write. The API enforces this with a
# signed token — hiding the tab is not the security boundary, the token is.
# Passwords are env-overridable; SECRET signs the tokens.
AUTH = {
    "admin":  {"password": os.environ.get("GRIDLOCK_ADMIN_PW", "admin@gridlock"),  "can_ingest": True},
    "viewer": {"password": os.environ.get("GRIDLOCK_VIEWER_PW", "viewer@gridlock"), "can_ingest": False},
}
AUTH_SECRET = os.environ.get("GRIDLOCK_SECRET", "gridlock-dev-secret-change-me")

