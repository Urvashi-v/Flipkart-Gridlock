"""
test_core.py  —  trust checks for the Gridlock product.

    pytest -q

Covers config sanity, the integrity of the built artifacts, the core scoring/
cost maths, the optimiser's monotonicity, and a live smoke test of every API
endpoint via FastAPI's TestClient. Run `python run_all.py` first so the
artifacts exist.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
from config import (CIS_WEIGHTS, VIOLATION_SEVERITY, VEHICLE_BLOCKING, OUT_DIR)

OUT = OUT_DIR


# ---------------------------------------------------------------- config
def test_cis_weights_sum_to_one():
    assert abs(sum(CIS_WEIGHTS.values()) - 1.0) < 1e-9


def test_severity_and_vehicle_in_unit_range():
    assert all(0 <= v <= 1 for v in VIOLATION_SEVERITY.values())
    assert all(0 <= v <= 1 for v in VEHICLE_BLOCKING.values())


# ---------------------------------------------------------------- artifacts
@pytest.fixture(scope="module")
def hotspots():
    p = OUT / "hotspots.csv"
    if not p.exists():
        pytest.skip("artifacts not built — run python run_all.py")
    return pd.read_csv(p)


def test_hotspots_have_required_columns(hotspots):
    need = {"zone", "rank", "CIS", "tier", "n_tickets",
            "c_volume", "c_severity", "c_junction", "c_vehicle", "c_persistence"}
    assert need.issubset(hotspots.columns)


def test_cis_in_range_and_sorted(hotspots):
    assert hotspots["CIS"].between(0, 100).all()
    assert hotspots["rank"].is_monotonic_increasing
    assert hotspots["CIS"].is_monotonic_decreasing


def test_cis_recomputes_from_components(hotspots):
    w = CIS_WEIGHTS
    recomputed = 100 * (
        w["volume"] * hotspots["c_volume"] + w["severity"] * hotspots["c_severity"] +
        w["junction"] * hotspots["c_junction"] + w["vehicle"] * hotspots["c_vehicle"] +
        w["persistence"] * hotspots["c_persistence"])
    assert np.allclose(recomputed, hotspots["CIS"], atol=0.5)


def test_violations_concentrated(hotspots):
    # violations should be concentrated: top 20% of zones hold > 40% of tickets
    top20 = hotspots.sort_values("n_tickets", ascending=False) \
                    .head(max(1, int(0.2 * len(hotspots))))["n_tickets"].sum()
    assert top20 / hotspots["n_tickets"].sum() > 0.40


def test_deployment_coverage_monotonic():
    p = OUT / "deployment_plan.csv"
    if not p.exists():
        pytest.skip("deployment not built")
    plan = pd.read_csv(p)
    assert plan["cum_located_%"].is_monotonic_increasing
    assert plan["cum_captured_%"].is_monotonic_increasing
    assert plan["cum_located_%"].iloc[-1] <= 100.01


# ---------------------------------------------------------------- API
@pytest.fixture(scope="module")
def client():
    if not (OUT / "hotspots.csv").exists():
        pytest.skip("artifacts not built")
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app)


def test_api_summary(client):
    r = client.get("/summary")
    assert r.status_code == 200
    assert r.json()["zones"] > 0


def test_api_hotspots_filter(client):
    r = client.get("/hotspots?limit=5&tier=Critical")
    assert r.status_code == 200
    body = r.json()
    assert len(body) <= 5
    assert all(z["tier"] == "Critical" for z in body)


def test_api_score_reranks(client):
    # severity-heavy weighting should change the #1 zone vs volume-heavy
    a = client.post("/score", json={"volume": 1, "severity": 0, "junction": 0,
                                    "vehicle": 0, "persistence": 0, "limit": 1}).json()
    b = client.post("/score", json={"volume": 0, "severity": 1, "junction": 0,
                                    "vehicle": 0, "persistence": 0, "limit": 1}).json()
    assert a["zones"][0]["zone"] != b["zones"][0]["zone"]


def test_api_deployment_roi(client):
    r = client.get("/deployment?patrols=10")
    assert r.status_code == 200
    body = r.json()
    assert 0 <= body["violations_captured_pct"] <= 100
    assert len(body["roster"]) == 10


# ---------------------------------------------------------------- chatbot
def test_chat_rules_are_quantitative():
    import re as _re
    from src import chat as chatmod
    ctx = chatmod.build_context()
    if not ctx:
        pytest.skip("artifacts not built")
    for q in ["worst hotspots", "busiest police station", "how many violations"]:
        a = chatmod.answer_rules(q, ctx)
        assert isinstance(a, str) and len(a) > 0
        assert _re.search(r"\d", a)          # answers cite numbers


def test_api_chat(client):
    r = client.post("/chat", json={"question": "worst hotspots"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] in ("ai", "rules") and len(body["answer"]) > 0


# ---------------------------------------------------------------- auth / roles
def test_auth_login_roles(client):
    v = client.post("/auth/login", json={"username": "viewer", "password": "viewer@gridlock"})
    a = client.post("/auth/login", json={"username": "admin", "password": "admin@gridlock"})
    assert v.status_code == 200 and v.json()["can_ingest"] is False
    assert a.status_code == 200 and a.json()["can_ingest"] is True
    assert client.post("/auth/login", json={"username": "admin", "password": "x"}).status_code == 401


def test_ingest_requires_admin(client):
    rec = {"lat": 12.97, "lng": 77.59, "vehicle": "CAR", "violation": "NO PARKING"}
    # anonymous + viewer are blocked
    assert client.post("/ingest/record", json=rec).status_code == 401
    vtok = client.post("/auth/login", json={"username": "viewer", "password": "viewer@gridlock"}).json()["token"]
    assert client.post("/ingest/record", json=rec,
                       headers={"Authorization": f"Bearer {vtok}"}).status_code == 401
    # admin is allowed
    atok = client.post("/auth/login", json={"username": "admin", "password": "admin@gridlock"}).json()["token"]
    h = {"Authorization": f"Bearer {atok}"}
    assert client.post("/ingest/record", json=rec, headers=h).status_code == 200
    client.post("/dataset/reset", headers=h)        # clean up the test record
