within BuildingSimulator;
model ApartmentBranch
  "One apartment: radiator valve + EN 442 radiator + single-capacity zone.
   The valve position is an external input (electronic thermostat in the loop).

   The valve models a German M30x1.5 TRV insert with 1.5 mm pin stroke:
   yVal = 0..1 maps to pin lift 0..1.5 mm. The flow characteristic is
   quick-opening, anchored to Danfoss RA-N 15 data: kv(xp=2K)/kvs =
   0.73/0.90 = 0.81 at ~0.44 mm lift (30 % stroke, head travel 0.22 mm/K).
   Sealing dead zone (elastomer seal) up to ~6 % stroke, then a steep rise
   to ~80 % flow at 30 % stroke, then saturation toward full lift. Seat
   leakage ~0.04 % of Kvs (rubber seals close tight; the nonzero floor
   keeps the flow inversion solvable). See docs/valve-modeling.md."

  replaceable package Medium = Modelica.Media.Interfaces.PartialMedium;

  parameter Modelica.Units.SI.Power Q_flow_nominal = 3000
    "Radiator heat output at rating conditions";
  parameter Modelica.Units.SI.Temperature TRadSup_nominal = 333.15
    "Radiator rating: supply temperature (333.15 = 60/40 modern, 363.15 = 90/70 original 80s)";
  parameter Modelica.Units.SI.Temperature TRadRet_nominal = 313.15
    "Radiator rating: return temperature";
  parameter Modelica.Units.SI.Temperature TAirRad_nominal = 293.15
    "Radiator rating: room temperature (set to the room design temperature)";
  parameter Modelica.Units.SI.PressureDifference dpPreset_nominal = 5000
    "Presetting ring: pressure drop fully open at design flow (sized so
     balancing lands at mid-opening, keeping the network well-conditioned)";
  parameter Modelica.Units.SI.MassFlowRate m_flow_nominal =
    Q_flow_nominal/4186/(TRadSup_nominal - TRadRet_nominal)
    "Design mass flow";
  // 2R2C zone: fast air node + slow structural mass node
  parameter Modelica.Units.SI.HeatCapacity C_air = 2.56e6
    "Fast-node capacity: air + furniture + interior surface layers,
     40 kJ/(m2K) x A_floor (64 m2 default). With the ISO-strength coupling
     the fast node includes what moves with the air; tau_fast ~ 40 min,
     matching grey-box identification of furnished rooms";
  parameter Modelica.Units.SI.HeatCapacity C_mass = 13.5e6
    "Structural mass capacity (slow node)";
  parameter Modelica.Units.SI.ThermalConductance G_win = 40
    "Air node to outdoor: windows + infiltration (fast losses)";
  parameter Modelica.Units.SI.ThermalConductance G_wall = 90
    "Mass node to outdoor: opaque envelope";
  parameter Modelica.Units.SI.ThermalConductance G_int = 990
    "Air to internal surfaces: ISO 13790 convention h_is*A_t =
     3.45 W/(m2K) x 4.5 x A_floor = 15.5 W/(m2K) x A_floor (64 m2 default)";
  parameter Real fraGainAir = 0.3
    "Fraction of QGain hitting the air node (rest absorbed by mass)";
  parameter Modelica.Units.SI.Temperature T_start = 293.15
    "Initial zone temperature";

  parameter Real yCha[:] = {0, 0.03, 0.06, 0.10, 0.15, 0.22, 0.30, 0.45, 0.65, 1.0}
    "Valve characteristic: normalized pin lift (1.0 = 1.5 mm stroke)";
  parameter Real phiCha[:] = {1.5e-3, 2e-3, 3e-3, 0.12, 0.35, 0.60, 0.78, 0.88, 0.94, 1.0}
    "Valve characteristic: Kv/Kvs, quick-opening (RA-N-like: 80 % flow at
     30 % stroke). Dead-zone floor 0.15-0.3 % keeps closed radiators
     hydraulically connected (a few-watt trickle) for solver robustness";

  Modelica.Fluid.Interfaces.FluidPort_a port_a(redeclare package Medium = Medium)
    "Supply connection (from riser)";
  Modelica.Fluid.Interfaces.FluidPort_b port_b(redeclare package Medium = Medium)
    "Return connection (to riser)";

  Modelica.Blocks.Interfaces.RealInput yVal(min=0, max=1)
    "Valve position from external thermostat";
  Modelica.Blocks.Interfaces.RealInput yPreset(min=0, max=1)
    "Manual presetting ring position (1 = fully open; set once, like a
     technician's Voreinstellung — FMU input so it is tunable per run)";
  Modelica.Blocks.Interfaces.RealInput QGain(unit="W")
    "Solar + internal heat gains into the zone";
  Modelica.Blocks.Interfaces.RealOutput TRoom(unit="K") "Zone temperature";
  Modelica.Blocks.Interfaces.RealOutput m_flow(unit="kg/s") "Radiator mass flow";
  Modelica.Blocks.Interfaces.RealOutput QRad(unit="W")
    "Radiator heat output (for valve-mounted sensor models)";
  Modelica.Blocks.Interfaces.RealOutput dpVal(unit="Pa")
    "Pressure drop across the valve (for actuator force models)";

  Modelica.Thermal.HeatTransfer.Interfaces.HeatPort_a heaPorZon
    "Mass node, for structural coupling to neighbouring zones";
  Modelica.Thermal.HeatTransfer.Interfaces.HeatPort_a heaPorAir
    "Air node, for door/air coupling (e.g. to a hall)";
  Modelica.Thermal.HeatTransfer.Interfaces.HeatPort_a heaPorAmb
    "Ambient node (connect to outdoor temperature source)";

  Buildings.Fluid.Actuators.Valves.TwoWayTable val(
    redeclare final package Medium = Medium,
    final m_flow_nominal=m_flow_nominal,
    dpValve_nominal=10000,
    dpFixed_nominal=2000,
    from_dp=true,
    allowFlowReversal=false,
    use_strokeTime=false,
    flowCharacteristics(y=yCha, phi=phiCha))
    "TRV insert (1.5 mm stroke, sealing dead zone). The 60 s motor stroke
     is rate-limited in the Python device model, not filtered here: the
     actuator filter states get entangled with the branch pressure drops
     by index reduction (dynamic state selection) once the radiators
     carry water states, and that state set breaks the solver when
     valves move at trickle flow (sil/probe_raddyn.py)";

  Buildings.Fluid.HeatExchangers.Radiators.RadiatorEN442_2 rad(
    redeclare final package Medium = Medium,
    final Q_flow_nominal=Q_flow_nominal,
    final T_a_nominal=TRadSup_nominal,
    final T_b_nominal=TRadRet_nominal,
    final TAir_nominal=TAirRad_nominal,
    T_start=TRadRet_nominal,
    allowFlowReversal=false,
    energyDynamics=Modelica.Fluid.Types.Dynamics.FixedInitial,
    VWat=8e-6*Q_flow_nominal,
    mDry=0.030*Q_flow_nominal,
    dp_nominal=500)
    "Radiator (EN 442-2) with dynamic energy balance: the water/steel
     storage (~8 l + 30 kg per kW, era steel/DIN radiators; library
     defaults 5.8 l + 26 kg are for modern panels) carries the emission
     lag that produces the field-typical setpoint overshoot after boost
     and cushions the first cooldown hour. dp_nominal 500 Pa: the real
     radiator+connection drop, and the smooth series resistance that
     keeps the branch flow system solvable when the valve moves off its
     seat at trickle flows (probe: sil/probe_raddyn.py)";

  Buildings.Fluid.Sensors.MassFlowRate senM(redeclare final package Medium = Medium);

  Buildings.Fluid.Actuators.Valves.TwoWayLinear preSet(
    redeclare final package Medium = Medium,
    final m_flow_nominal=m_flow_nominal,
    dpValve_nominal=dpPreset_nominal,
    l=0.01,
    linearized=true,
    allowFlowReversal=false,
    use_strokeTime=false)
    "Manual presetting ring (linear valve, linearized flow law: adequate for
     a static setting and keeps the 32-valve network solvable)";

  Modelica.Thermal.HeatTransfer.Components.HeatCapacitor capAir(
    final C=C_air, T(start=T_start, fixed=true)) "Air node";
  Modelica.Thermal.HeatTransfer.Components.HeatCapacitor capMass(
    final C=C_mass, T(start=T_start, fixed=true)) "Structural mass node";
  Modelica.Thermal.HeatTransfer.Components.ThermalConductor conWin(final G=G_win)
    "Windows + infiltration";
  Modelica.Thermal.HeatTransfer.Components.ThermalConductor conWall(final G=G_wall)
    "Opaque envelope";
  Modelica.Thermal.HeatTransfer.Components.ThermalConductor conInt(final G=G_int)
    "Air <-> internal surfaces";
  Modelica.Thermal.HeatTransfer.Sensors.TemperatureSensor senT;

  Modelica.Thermal.HeatTransfer.Sources.PrescribedHeatFlow preGainAir
    "Gain share to air node";
  Modelica.Thermal.HeatTransfer.Sources.PrescribedHeatFlow preGainMass
    "Gain share to mass node";
  Modelica.Blocks.Math.Gain gaiAir(final k=fraGainAir);
  Modelica.Blocks.Math.Gain gaiMass(final k=1 - fraGainAir);

equation
  connect(port_a, val.port_a);
  connect(val.port_b, preSet.port_a);
  connect(preSet.port_b, rad.port_a);
  connect(rad.port_b, senM.port_a);
  connect(senM.port_b, port_b);

  // 2R2C zone: convective heat to the air node, radiative to the surfaces
  connect(rad.heatPortCon, capAir.port);
  connect(rad.heatPortRad, capMass.port);
  connect(conWin.port_a, capAir.port);
  connect(conWin.port_b, heaPorAmb);
  connect(conWall.port_a, capMass.port);
  connect(conWall.port_b, heaPorAmb);
  connect(conInt.port_a, capAir.port);
  connect(conInt.port_b, capMass.port);
  connect(capMass.port, heaPorZon);
  connect(capAir.port, heaPorAir);
  connect(senT.port, capAir.port);

  // solar + internal gains, split between air and mass
  connect(QGain, gaiAir.u);
  connect(QGain, gaiMass.u);
  connect(gaiAir.y, preGainAir.Q_flow);
  connect(gaiMass.y, preGainMass.Q_flow);
  connect(preGainAir.port, capAir.port);
  connect(preGainMass.port, capMass.port);

  connect(yVal, val.y);
  connect(yPreset, preSet.y);
  connect(senT.T, TRoom);
  connect(senM.m_flow, m_flow);

  // heat delivered by the radiator to the zone (port convention: positive into radiator)
  QRad = -(rad.heatPortCon.Q_flow + rad.heatPortRad.Q_flow);
  dpVal = val.dp;
end ApartmentBranch;
