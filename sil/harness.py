"""Software-in-the-loop harness: fixed-step co-simulation of a building FMU.

The FMU is the plant (building + hydronic system); all control intelligence
lives outside, in Python controller objects (see controllers.py).
"""

import os

from fmpy import read_model_description, extract
from fmpy.fmi2 import FMU2Slave


class BuildingFMU:
    """Thin wrapper around an FMI 2.0 co-simulation FMU with named I/O."""

    def __init__(self, fmu_path: str, start_time: float = 0.0, parameters=None):
        """parameters: dict of FMU parameter start values (e.g. balancing
        presets), applied after instantiation, before initialization."""
        self._md = read_model_description(fmu_path)
        self._vrs = {v.name: v.valueReference for v in self._md.modelVariables}
        self._unzipdir = extract(fmu_path)
        self._fmu = FMU2Slave(
            guid=self._md.guid,
            unzipDirectory=self._unzipdir,
            modelIdentifier=self._md.coSimulation.modelIdentifier,
            instanceName="buildingsim",
        )
        self.time = start_time
        # BUILDINGSIM_FMU_DEBUG=logNonlinearSystems[,logEvents,...] enables
        # FMI debug categories (needed to surface LOG_NLS & friends from the
        # OpenModelica runtime when diagnosing solver failures)
        debug_cats = os.environ.get("BUILDINGSIM_FMU_DEBUG", "")
        self._fmu.instantiate(loggingOn=bool(debug_cats))
        if debug_cats:
            self._fmu.setDebugLogging(True, debug_cats.split(","))
        if parameters:
            self.set_inputs(parameters)
        self._fmu.setupExperiment(startTime=start_time)
        self._initialized = False

    @property
    def variable_names(self):
        return list(self._vrs)

    def set_inputs(self, values: dict) -> None:
        # dict-based (not kwargs): FMU names like "yVal[1]" are not identifiers
        vrs = [self._vrs[name] for name in values]
        self._fmu.setReal(vrs, list(values.values()))

    def initialize(self, start_inputs: dict = None) -> None:
        self._fmu.enterInitializationMode()
        if start_inputs:
            self.set_inputs(start_inputs)
        self._fmu.exitInitializationMode()
        self._initialized = True

    def step(self, dt: float) -> None:
        if not self._initialized:
            raise RuntimeError("call initialize() before step()")
        self._fmu.doStep(currentCommunicationPoint=self.time, communicationStepSize=dt)
        self.time += dt

    def get_outputs(self, names) -> dict:
        vrs = [self._vrs[name] for name in names]
        vals = self._fmu.getReal(vrs)
        return dict(zip(names, vals))

    def close(self) -> None:
        if self._initialized:
            self._fmu.terminate()
        self._fmu.freeInstance()


STROKE_TIME = 60.0
"""Full-stroke travel time of the eTRV motor in seconds. Valve commands
(yVal*) are rate-limited to this speed harness-side: the FMU valve applies
positions instantly since the in-FMU actuator filter had to go (its states
get entangled with the branch pressure drops by dynamic state selection
once the radiators carry water states — see ApartmentBranch.mo)."""


def run_simulation(fmu_path, controllers, scenario, duration, control_dt,
                   output_names, record_dt=None, on_record=None,
                   parameters=None):
    """Run a closed-loop SIL simulation.

    controllers: dict mapping FMU input name -> controller object with
                 .step(t, measurements: dict) -> float
    scenario:    callable t -> dict of exogenous FMU inputs
                 (weather, setpoints for supervisory inputs)
    on_record:   optional callback invoked with each recorded row
                 (e.g. runstore.RunWriter.append for live persistence)
    Returns a list of per-step records (dicts).
    """
    fmu = BuildingFMU(fmu_path, parameters=parameters)
    exo0 = scenario(0.0)
    # controllers may declare a sensible initial output (e.g. a supply-
    # temperature controller starting hot instead of at valve mid-position)
    act0 = {name: getattr(ctrl, "initial_output", 0.5)
            for name, ctrl in controllers.items()}
    fmu.initialize({**exo0, **act0})

    records = []
    record_dt = record_dt or control_dt
    next_record = 0.0
    t = 0.0
    actions = dict(act0)

    max_dy = control_dt / STROKE_TIME  # motor speed limit per control step

    while t < duration:
        meas = fmu.get_outputs(output_names)
        # controllers observe, then act (sampled control like a real thermostat)
        wanted = {name: ctrl.step(t, meas) for name, ctrl in controllers.items()}
        actions = {
            name: (min(max(y, actions[name] - max_dy), actions[name] + max_dy)
                   if name.startswith("yVal") else y)
            for name, y in wanted.items()
        }
        exo = scenario(t)
        fmu.set_inputs({**exo, **actions})

        if t >= next_record:
            record = {"time": t, **meas, **actions, **exo}
            records.append(record)
            if on_record:
                on_record(record)
            next_record += record_dt

        fmu.step(control_dt)
        t = fmu.time

    fmu.close()
    return records
