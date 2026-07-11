# BOPTEST reference environment — local setup

[BOPTEST](https://ibpsa.github.io/project1-boptest/) serves as the independent benchmark
environment for this project (test case `multizone_residential_hydronic`: 6-zone
residential dwelling, gas boiler, one radiator with thermostatic valve per zone,
standardized KPIs). Verified working on this machine 2026-07-11.

## Setup

```powershell
# long paths needed on Windows, repo exceeds 260-char limit
git clone -c core.longpaths=true https://github.com/ibpsa/project1-boptest.git
cd project1-boptest
```

If port 8000 is occupied locally (e.g. a uvicorn/FastAPI dev server), remap the API port
with a `docker-compose.override.yml` in the repo root:

```yaml
services:
  web:
    ports: !override
      - "8081:8000"
```

Then start the stack (first build takes ~10 min):

```powershell
docker compose up -d web worker provision
```

## Smoke test (REST API)

```powershell
# list test cases
Invoke-RestMethod "http://127.0.0.1:8081/testcases" | % { $_.testcaseid }

# select a test case -> returns testid
$sel = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8081/testcases/multizone_residential_hydronic/select" `
  -ContentType "application/json" -Body "{}"

# measurement points (56 for this case), advance one step, stop
Invoke-RestMethod "http://127.0.0.1:8081/measurements/$($sel.testid)"
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8081/advance/$($sel.testid)" `
  -ContentType "application/json" -Body "{}"
Invoke-RestMethod -Method Put -Uri "http://127.0.0.1:8081/stop/$($sel.testid)"
```

Key endpoints: `/testcases`, `POST /testcases/{id}/select`, `/measurements/{testid}`,
`/inputs/{testid}`, `PUT /step/{testid}` (control step size), `POST /advance/{testid}`
(with control inputs in the body), `/kpi/{testid}`, `PUT /scenario/{testid}`
(predefined peak/typical heat days), `/forecast/{testid}`.

Shut down with `docker compose down` (or `docker compose -p boptest down` from anywhere).

## Role in this project

- Independent, validated multi-zone hydronic emulator to sanity-check our own
  parameterizable building model.
- Standardized KPIs (thermal discomfort, energy, cost, emissions) for comparing
  thermostat control strategies against published baselines.
- [BOPTEST-Gym](https://github.com/ibpsa/project1-boptest-gym) provides a Gymnasium
  wrapper if RL benchmarking is wanted later.
