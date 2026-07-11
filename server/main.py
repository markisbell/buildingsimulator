"""Run-store REST API for the dashboard.

Serves runs/<id>/ (manifest.json + series.csv) written by the SIL harness.

Run inside the container:
  docker run --rm -p 8010:8010 -v ${PWD}:/work -w /work buildingsimulator:dev \
      uvicorn server.main:app --host 0.0.0.0 --port 8010
"""

import csv
import json
import os
import re
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"

_children = []  # launched experiment processes (reaped on /api/runs)

app = FastAPI(title="buildingsimulator run store")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local research tool; tighten when deployed
    allow_methods=["*"],
    allow_headers=["*"],
)


def _manifest(run_id: str) -> dict:
    path = RUNS / run_id / "manifest.json"
    if not path.exists():
        raise HTTPException(404, f"run {run_id} not found")
    return json.loads(path.read_text())


class LaunchConfig(BaseModel):
    name: str = "experiment"
    controller: str = Field("realistic", pattern="^(realistic|ideal)$")
    durationDays: float = Field(7.0, ge=0.1, le=30.0)
    cloudiness: float = Field(0.4, ge=0.0, le=1.0)
    vacant: list[int] = [3]


@app.post("/api/launch")
def launch(config: LaunchConfig):
    running = sum(1 for m in list_runs() if m.get("status") == "running")
    if running >= 3:
        raise HTTPException(429, "already 3 runs in progress")
    proc = subprocess.Popen(
        [sys.executable, "run_experiment.py", config.model_dump_json()],
        cwd=ROOT / "sil", start_new_session=True)
    _children.append(proc)
    return {"launched": True, "pid": proc.pid}


@app.post("/api/runs/{run_id}/stop")
def stop_run(run_id: str):
    manifest = _manifest(run_id)
    if manifest.get("status") != "running":
        raise HTTPException(409, "run is not in progress")
    pid = manifest.get("pid")
    if not pid:
        raise HTTPException(409, "run has no recorded pid")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    manifest["status"] = "stopped"
    (RUNS / run_id / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return {"stopped": True}


@app.get("/api/runs")
def list_runs():
    for p in list(_children):  # reap finished children
        if p.poll() is not None:
            _children.remove(p)
    if not RUNS.exists():
        return []
    manifests = []
    for d in RUNS.iterdir():
        if (d / "manifest.json").exists():
            try:
                manifests.append(json.loads((d / "manifest.json").read_text()))
            except json.JSONDecodeError:
                continue  # mid-write during a live run; next poll catches it
    manifests.sort(key=lambda m: m.get("created", ""), reverse=True)
    return manifests


@app.get("/api/runs/{run_id}/manifest")
def get_manifest(run_id: str):
    return _manifest(run_id)


@app.get("/api/runs/{run_id}/rows")
def get_rows(run_id: str, stride: int = Query(5, ge=1, le=100)):
    """Row-oriented series for Grafana (Infinity datasource): a flat list of
    records with sanitized column names (TRoom[1] -> TRoom_1) and 'ts' as
    epoch milliseconds anchored at the scenario start date."""
    path = RUNS / run_id / "series.csv"
    if not path.exists():
        raise HTTPException(404, f"run {run_id} has no series yet")
    manifest = _manifest(run_id)
    start = manifest.get("scenario", {}).get("startDate") or manifest["created"][:10]
    t0 = datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp()

    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        names = {n: re.sub(r"\[(\d+)\]", r"_\1", n) for n in reader.fieldnames or []}
        for k, row in enumerate(reader):
            if k % stride:
                continue
            rec = {}
            for raw, clean in names.items():
                try:
                    v = float(row[raw])
                    # temperature columns (capital T prefix) as degC for Grafana
                    if raw.startswith("T"):
                        v = round(v - 273.15, 3)
                    rec[clean] = v
                except (TypeError, ValueError):
                    rec[clean] = None
            rec["ts"] = int((t0 + rec.get("time", 0.0)) * 1000)
            rows.append(rec)
    return rows


@app.get("/api/runs/{run_id}/series")
def get_series(run_id: str, stride: int = Query(1, ge=1, le=100)):
    """Columnar series {column: [values...]}, optionally downsampled."""
    path = RUNS / run_id / "series.csv"
    if not path.exists():
        raise HTTPException(404, f"run {run_id} has no series yet")
    columns = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        names = reader.fieldnames or []
        columns = {n: [] for n in names}
        for k, row in enumerate(reader):
            if k % stride:
                continue
            for n in names:
                v = row.get(n)
                try:
                    columns[n].append(float(v))
                except (TypeError, ValueError):
                    columns[n].append(None)
    return columns
