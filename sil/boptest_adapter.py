"""Adapter between the project's controller stack and the BOPTEST REST API.

Test case `multizone_residential_hydronic` exposes exactly the surface our
device models need, so the SAME firmware objects run unmodified:

    valve command   -> conHea<Zone>_oveActHea_u (+ _activate)
    true zone temp  <- conHea<Zone>_reaTZon_y
    delivered heat  <- reaHea<Zone>_y      (drives the sensor-bias model)
    comfort bounds  <- forecast points LowerSetp[<zone>] / UpperSetp[<zone>]

Five radiator zones (the hall has no valve — like our halls).
"""

import json
import time
import urllib.error
import urllib.request

ZONES = ["Liv", "Ro1", "Ro2", "Ro3", "Bth"]


class BoptestClient:
    def __init__(self, base="http://localhost:8081", testid=None,
                 timeout_s=120.0, retries=3):
        self.base = base
        self.testid = testid
        self.timeout_s = timeout_s
        self.retries = retries

    # -- plumbing -----------------------------------------------------
    def _req(self, method, path, data=None):
        # long advance loops (4000+ requests over an hour) hit transient
        # socket timeouts; retry with backoff instead of dying mid-run
        last = None
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(
                f"{self.base}{path}", method=method,
                data=None if data is None else json.dumps(data).encode(),
                headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    out = json.load(resp)
                return out.get("payload", out)
            except (urllib.error.URLError, TimeoutError) as exc:
                last = exc
                time.sleep(5.0 * (attempt + 1))
        raise last

    def stop(self, testid=None):
        try:
            return self._req("PUT", f"/stop/{testid or self.testid}")
        except Exception:
            return None

    # -- lifecycle ----------------------------------------------------
    def select(self, testcase="multizone_residential_hydronic"):
        p = self._req("POST", f"/testcases/{testcase}/select")
        self.testid = p.get("testid", p)
        return self.testid

    def set_scenario(self, time_period="peak_heat_day",
                     electricity_price="dynamic"):
        return self._req("PUT", f"/scenario/{self.testid}",
                         {"time_period": time_period,
                          "electricity_price": electricity_price})

    def set_step(self, step_s=300):
        return self._req("PUT", f"/step/{self.testid}", {"step": step_s})

    def advance(self, inputs=None):
        """One control step; returns the measurement payload or None when
        the scenario period is over."""
        return self._req("POST", f"/advance/{self.testid}", inputs or {})

    def kpis(self):
        return self._req("GET", f"/kpi/{self.testid}")

    def forecast(self, points, horizon_s, interval_s=300):
        return self._req("PUT", f"/forecast/{self.testid}",
                         {"point_names": points, "horizon": horizon_s,
                          "interval": interval_s})

    # -- zone helpers ---------------------------------------------------
    @staticmethod
    def valve_inputs(commands):
        """commands: dict zone -> opening [0..1] -> overwrite payload."""
        out = {}
        for z, u in commands.items():
            out[f"conHea{z}_oveActHea_u"] = float(u)
            out[f"conHea{z}_oveActHea_activate"] = 1
        return out

    @staticmethod
    def zone_temp(payload, zone):
        return payload[f"conHea{zone}_reaTZon_y"]

    @staticmethod
    def zone_heat(payload, zone):
        return payload[f"reaHea{zone}_y"]

    def lower_setpoints(self, horizon_s, interval_s=300):
        """Comfort lower bounds per zone over the horizon (the heating
        setpoint schedule our controllers must track)."""
        pts = [f"LowerSetp[{z}]" for z in ZONES]
        f = self.forecast(pts, horizon_s, interval_s)
        return f
