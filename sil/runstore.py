"""File-based run store: every simulation persists to runs/<id>/.

Layout (the contract the UI and the API server rely on):
  runs/<id>/manifest.json   metadata, config, progress, KPIs, device diagnostics
  runs/<id>/series.csv      recorded time series (one column per signal)

The manifest is rewritten periodically during a run so a UI can poll live.
"""

import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "runs"


def _git_commit():
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=Path(__file__).parent).stdout.strip() or None
    except Exception:
        return None


class RunWriter:
    def __init__(self, run_dir: Path, manifest: dict):
        self.dir = run_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.manifest = manifest
        self._file = None
        self._writer = None
        self._n = 0
        self._write_manifest()

    def _write_manifest(self):
        tmp = self.dir / "manifest.json.tmp"
        tmp.write_text(json.dumps(self.manifest, indent=1))
        tmp.replace(self.dir / "manifest.json")

    def append(self, record: dict):
        if self._writer is None:
            self._file = open(self.dir / "series.csv", "w", newline="")
            self._writer = csv.DictWriter(self._file, fieldnames=list(record))
            self._writer.writeheader()
        self._writer.writerow(record)
        self._n += 1
        if self._n % 120 == 0:  # periodic flush + progress for live polling
            self._file.flush()
            self.manifest["progressDays"] = round(record.get("time", 0.0) / 86400, 2)
            self._write_manifest()

    def finish(self, kpis=None, devices=None, status="finished"):
        if self._file:
            self._file.close()
        self.manifest["status"] = status
        self.manifest["progressDays"] = self.manifest.get("durationDays")
        if kpis is not None:
            self.manifest["kpis"] = kpis
        if devices is not None:
            self.manifest["devices"] = devices
        self._write_manifest()


def create_run(name: str, manifest: dict, root: Path = None) -> RunWriter:
    root = root or DEFAULT_ROOT
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_id = f"{stamp}-{name}"
    manifest = {
        "id": run_id,
        "name": name,
        "status": "running",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "progressDays": 0.0,
        "git": _git_commit(),
        **manifest,
    }
    return RunWriter(root / run_id, manifest)
