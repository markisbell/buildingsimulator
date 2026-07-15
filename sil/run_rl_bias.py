"""Can an RL agent learn the sensor-bias compensation from reward alone?

The simplest honest RL formulation the FMU sample budget allows (an
episode costs ~10 min of wall time, so deep RL is out): derivative-free
episodic policy search over a STRUCTURED policy —

    per occupied zone: PI on  T_comp = T_sensed - theta * u_filt
    u_filt = 600 s lag filter of the zone's own commanded-opening heat
             proxy (y/0.3)^0.5  — the same feature the engineered
             firmware uses; the GAIN theta is the learned parameter.

The agent observes only the device-realistic sensed temperatures
(BuildingEnv observation_mode="device"); the reward is the env's
standard mix (true comfort + energy + travel). Two-stage search
(coarse grid, then refinement around the best) with common random
numbers across candidates; evaluations run in parallel workers.

Questions answered:
1. Does the reward landscape over theta have its optimum near the
   engineered compensation gain (k_hat ~ 1.5-2.5 on this building)?
2. Does the energy term punish over-compensation (the trap the
   engineered estimator fell into) without any explicit overheat
   penalty?
3. How close does the learned policy come to the plant-observation
   upper bound in true comfort?

  wsl -d Ubuntu-24.04 -u root -- bash -c \
      "cd /work/sil && /opt/silenv/bin/python3 run_rl_bias.py"
"""

from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FMU = str(ROOT / "build" / "MultiTenantBuilding.fmu")
RESULTS = ROOT / "results"

SEARCH_DAYS = 2          # episode length during the search
FINAL_DAYS = 3           # final comparison episodes
N_WORKERS = 4
PROXY_TAU = 600.0


def run_episode(theta, days, observation_mode):
    """One episode with the structured compensation policy; returns the
    episodic return and true-comfort diagnostics."""
    from controllers import PIThermostat
    from gym_env import BuildingEnv
    from scenario_common import SCHEDULES, day_night_setpoint

    env = BuildingEnv(FMU, episode_days=days,
                      observation_mode=observation_mode, sensor_seed=0)
    pis = {i: PIThermostat(f"T[{i}]", day_night_setpoint(*s),
                           dt=env.control_dt)
           for i, s in SCHEDULES.items() if s is not None}
    obs, _ = env.reset(seed=0)
    u_filt = np.zeros(env.n)
    y_prev = np.zeros(env.n)
    ret = comfort = energy = travel = 0.0
    day_errs = []
    trunc = False
    while not trunc:
        # compensated readings from the policy's own state
        action = np.zeros(env.n)
        for i, pi in pis.items():
            t_comp = obs[i - 1] - theta * u_filt[i - 1]
            action[i - 1] = pi.step(env._t, {f"T[{i}]": t_comp})
        obs, r, _, trunc, info = env.step(action)
        proxy = np.clip((y_prev / 0.30), 0.0, None) ** 0.5
        u_filt += (np.minimum(proxy, 1.0) - u_filt) * min(
            1.0, env.control_dt / PROXY_TAU)
        y_prev = action
        ret += r
        comfort += info["comfort_kh"]
        energy += info["energy_kwh"]
        travel += info["travel"]
        hour = (info["t"] % 86400.0) / 3600.0
        if info["t"] > 86400.0 and 8 <= hour < 22:
            sp = day_night_setpoint(*SCHEDULES[1])(info["t"])
            day_errs.append(info["TRoom_true"][0] - sp)
    env.close()
    return {"theta": theta, "return": ret, "comfort_kh": comfort,
            "energy_kwh": energy, "travel": travel,
            "mean_dev_K": float(np.mean(day_errs)),
            "mean_abs_dev_K": float(np.mean(np.abs(day_errs)))}


def _search_eval(theta):
    return run_episode(theta, SEARCH_DAYS, "device")


def main():
    # ---- stage 1: coarse grid (parallel, common random numbers) ----
    grid = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    with Pool(N_WORKERS) as pool:
        results = pool.map(_search_eval, grid)
    print("stage 1 (coarse):")
    for r in results:
        print(f"  theta={r['theta']:.2f}  return={r['return']:8.1f}  "
              f"comfort={r['comfort_kh']:6.1f}  energy={r['energy_kwh']:6.1f}"
              f"  dev={r['mean_dev_K']:+.2f} K")
    best = max(results, key=lambda r: r["return"])

    # ---- stage 2: refine around the best ----
    step = 0.25
    refine = [round(best["theta"] + d, 2) for d in (-step, step)
              if 0.0 <= best["theta"] + d <= 3.0]
    with Pool(min(N_WORKERS, len(refine))) as pool:
        results += pool.map(_search_eval, refine)
    results.sort(key=lambda r: r["theta"])
    best = max(results, key=lambda r: r["return"])
    print(f"\nstage 2 best: theta = {best['theta']:.2f} "
          f"(return {best['return']:.1f})")

    # ---- final 3-day comparison: learned vs uncompensated vs plant ----
    finals = {}
    with Pool(3) as pool:
        futs = {
            "learned (device obs)": pool.apply_async(
                run_episode, (best["theta"], FINAL_DAYS, "device")),
            "uncompensated (device obs)": pool.apply_async(
                run_episode, (0.0, FINAL_DAYS, "device")),
            "plant obs (upper bound)": pool.apply_async(
                run_episode, (0.0, FINAL_DAYS, "plant")),
        }
        for name, f in futs.items():
            finals[name] = f.get()

    print(f"\n{'final 3-day episodes':30s} {'return':>9s} {'comfort':>8s} "
          f"{'energy':>7s} {'dev K':>7s}")
    for name, r in finals.items():
        print(f"{name:30s} {r['return']:9.1f} {r['comfort_kh']:8.1f} "
              f"{r['energy_kwh']:7.1f} {r['mean_dev_K']:+7.2f}")

    # ---- figure ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.6))
    th = [r["theta"] for r in results]
    ax1.plot(th, [r["return"] for r in results], "o-", color="#2E5E8C")
    ax1.axvline(best["theta"], color="#B8432F", ls="--", lw=1.0,
                label=f"learned θ = {best['theta']:.2f}")
    ax1.axvspan(1.5, 2.5, color="gray", alpha=0.12,
                label="engineered k̂ range (night-anchor)")
    ax1.set_xlabel("compensation gain θ")
    ax1.set_ylabel("episodic return")
    ax1.set_title("Reward landscape over the policy parameter\n"
                  "(device observations, common random numbers)")
    ax1.legend(fontsize=8)

    names = list(finals)
    devs = [finals[n]["mean_dev_K"] for n in names]
    ax2.bar(range(3), devs, color=["#2E5E8C", "#B8432F", "gray"])
    ax2.axhline(0, color="black", lw=0.8)
    ax2.set_xticks(range(3))
    ax2.set_xticklabels(["learned θ\n(device obs)", "θ = 0\n(device obs)",
                         "plant obs\n(upper bound)"], fontsize=8)
    ax2.set_ylabel("mean daytime T_true − sp / K")
    ax2.set_title("True-temperature tracking, apartment 1 (day 2+)")

    fig.tight_layout()
    fig.savefig(RESULTS / "rl_bias.png", dpi=150)
    print("\nwrote results/rl_bias.png")


if __name__ == "__main__":
    main()
