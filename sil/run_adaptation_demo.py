"""Adaptation run demo — motor-current-based zero referencing.

Panel 1: current trace of one adaptation sweep with the firmware's stall
         detection against the true seal contact and hard stop (the seal
         force is visible in the trace as plant physics; the firmware only
         uses the stall).
Panel 2: zero-estimation error across a population of devices (different
         noise seeds and mounting tolerances) — the residual calibration
         uncertainty an adaptive control strategy has to live with.

Pure device-model demo, no FMU needed:
  docker run --rm -v ${PWD}:/work -w /work/sil buildingsimulator:dev python3 run_adaptation_demo.py
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from thermostat import ElectronicThermostat, SampledPI

RESULTS = Path(__file__).resolve().parents[1] / "results"
RESULTS.mkdir(exist_ok=True)


def make_device(seed):
    return ElectronicThermostat("T", "Q", SampledPI(294.15),
                                auto_adapt=False, seed=seed)


def main():
    # ---- one detailed trace ----
    dev = make_device(seed=7)
    act = dev.actuator
    info = dev.adaptation_run(t=0.0)
    trace = np.array(info["trace"])
    print(f"true zero:      {act.true_zero_mm:.3f} mm (motor coordinate)")
    print(f"estimated zero: {act.zero_est_mm:.3f} mm "
          f"-> error {info['zero_error_mm']*1000:+.0f} um")
    print(f"sweep duration: {info['duration_s']:.0f} s, "
          f"travel {act.travel_mm:.2f} mm")

    # ---- population statistics ----
    errors = []
    for seed in range(60):
        d = make_device(seed=seed)
        a = d.adaptation_run(t=0.0)
        errors.append(a["zero_error_mm"] * 1000)  # um
    errors = np.array(errors)
    print(f"\npopulation (n=60): zero error {errors.mean():+.0f} um mean, "
          f"{errors.std():.0f} um std")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))

    ax1.plot(trace[:, 0], trace[:, 1], lw=1.0)
    # during closing the pin lags the motor by the play width, so pin events
    # appear shifted by -backlash on the motor axis
    lag = act.backlash_mm
    ax1.axvline(act.true_zero_mm + act.seal_zone_mm - lag, color="#1baf7a",
                lw=0.9, ls=":", label="true seal contact (pin)")
    ax1.axvline(act.true_zero_mm - lag, color="#e34948", lw=0.9, ls=":",
                label="true hard stop (pin)")
    ax1.plot(info["stall_mm"], trace[-1, 1], "s", ms=6, mfc="none",
             label="stall -> zero ref")
    ax1.invert_xaxis()  # motor travels toward smaller coordinates
    ax1.set_xlabel("motor position / mm (closing ->)")
    ax1.set_ylabel("measured motor current / mA")
    ax1.set_title("Adaptation sweep: stall-based zero referencing")
    ax1.legend(fontsize=8, loc="upper left")

    ax2.hist(errors, bins=15, edgecolor="white")
    ax2.axvline(0, color="gray", lw=0.8, ls="--")
    ax2.set_xlabel("zero-estimate error / µm")
    ax2.set_ylabel("devices")
    ax2.set_title(f"60 devices: {errors.mean():+.0f} µm bias, "
                  f"{errors.std():.0f} µm spread")

    fig.tight_layout()
    fig.savefig(RESULTS / "adaptation_run.png", dpi=150)
    print("done — plot in results/adaptation_run.png")


if __name__ == "__main__":
    main()
