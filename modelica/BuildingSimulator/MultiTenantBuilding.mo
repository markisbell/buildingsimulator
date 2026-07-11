within BuildingSimulator;
model MultiTenantBuilding
  "Multi-tenant building: boiler -> pump -> vertical riser -> nFlo x nApeFlo apartments.
   Apartment i = (floor-1)*nApeFlo + positionOnFloor, floor 1 at the bottom.
   All radiator valves are external inputs (electronic thermostats in the loop).
   Stacked apartments exchange heat through floor/ceiling conductances."

  package MediumW = Buildings.Media.Water "Water medium";

  parameter Integer nFlo = 3 "Number of floors";
  parameter Integer nApeFlo = 2 "Apartments per floor";
  final parameter Integer nApt = nFlo*nApeFlo "Total apartments";

  parameter Modelica.Units.SI.Power QRad_nominal = 4500
    "Radiator size per apartment at 60/40/20 (UA_apt*30 K design load + margin)";
  final parameter Modelica.Units.SI.MassFlowRate m_flow_nominal_rad =
    QRad_nominal/4186/20 "Design flow per apartment";
  final parameter Modelica.Units.SI.MassFlowRate m_flow_nominal_tot =
    nApt*m_flow_nominal_rad "Design total flow";

  parameter Modelica.Units.SI.ThermalConductance UA_apt = 120
    "Envelope conductance per apartment";
  parameter Modelica.Units.SI.HeatCapacity C_apt = 15e6
    "Effective heat capacity per apartment";
  parameter Modelica.Units.SI.ThermalConductance G_vert = 150
    "Floor/ceiling conductance between stacked apartments";
  parameter Modelica.Units.SI.PressureDifference dpPipe_nominal = 500
    "Pressure drop per riser segment (each, supply and return)";

  final parameter Modelica.Units.SI.PressureDifference dpDesign =
    10000 + 2000 + 3000 + 2*nFlo*dpPipe_nominal
    "Network design pressure drop (branch + boiler + riser)";

  // ---------- SIL interface ----------
  Modelica.Blocks.Interfaces.RealInput yVal[nApt](each min=0, each max=1)
    "Valve position per apartment (external thermostats)";
  Modelica.Blocks.Interfaces.RealInput TOut(unit="K") "Outdoor air temperature";
  Modelica.Blocks.Interfaces.RealInput TSupSet(unit="K") "Supply temperature setpoint";

  Modelica.Blocks.Interfaces.RealOutput TRoom[nApt](each unit="K")
    "Zone temperature per apartment";
  Modelica.Blocks.Interfaces.RealOutput mFlow[nApt](each unit="kg/s")
    "Radiator mass flow per apartment";
  Modelica.Blocks.Interfaces.RealOutput TSup(unit="K") "Supply water temperature";
  Modelica.Blocks.Interfaces.RealOutput TRet(unit="K") "Return water temperature";
  Modelica.Blocks.Interfaces.RealOutput QBoi(unit="W") "Boiler heat flow";
  Modelica.Blocks.Interfaces.RealOutput PPum(unit="W") "Pump electrical power";

  // ---------- Apartments ----------
  BuildingSimulator.ApartmentBranch apt[nApt](
    redeclare each final package Medium = MediumW,
    each Q_flow_nominal=QRad_nominal,
    each UA=UA_apt,
    each C=C_apt) "Apartment branches";

  Modelica.Thermal.HeatTransfer.Components.ThermalConductor conVer[nApt - nApeFlo](
    each G=G_vert) "Vertical coupling between stacked apartments";

  Modelica.Thermal.HeatTransfer.Sources.PrescribedTemperature preTOut
    "Outdoor temperature boundary";

  // ---------- Riser ----------
  Buildings.Fluid.FixedResistances.PressureDrop pipSup[nFlo](
    redeclare each package Medium = MediumW,
    m_flow_nominal={(nFlo - f + 1)*nApeFlo*m_flow_nominal_rad for f in 1:nFlo},
    each dp_nominal=dpPipe_nominal) "Supply riser segments (bottom to top)";

  Buildings.Fluid.FixedResistances.PressureDrop pipRet[nFlo](
    redeclare each package Medium = MediumW,
    m_flow_nominal={(nFlo - f + 1)*nApeFlo*m_flow_nominal_rad for f in 1:nFlo},
    each dp_nominal=dpPipe_nominal) "Return riser segments (bottom to top)";

  // ---------- Plant ----------
  Buildings.Fluid.Movers.SpeedControlled_y pum(
    redeclare package Medium = MediumW,
    per(pressure(V_flow={0, 0.5, 1.0, 1.5}*(m_flow_nominal_tot/1000),
                 dp={1.5, 1.3, 1.0, 0.4}*dpDesign)))
    "Constant-speed circulation pump";

  Modelica.Blocks.Sources.Constant conPumY(k=1) "Pump at full speed";

  Buildings.Fluid.HeatExchangers.Heater_T boi(
    redeclare package Medium = MediumW,
    m_flow_nominal=m_flow_nominal_tot,
    dp_nominal=3000,
    QMax_flow=nApt*QRad_nominal)
    "Ideal boiler tracking the supply temperature setpoint";

  Buildings.Fluid.Sensors.TemperatureTwoPort senTSup(
    redeclare package Medium = MediumW,
    m_flow_nominal=m_flow_nominal_tot) "Supply temperature sensor";

  Buildings.Fluid.Sensors.TemperatureTwoPort senTRet(
    redeclare package Medium = MediumW,
    m_flow_nominal=m_flow_nominal_tot) "Return temperature sensor";

  Buildings.Fluid.FixedResistances.PressureDrop byp(
    redeclare package Medium = MediumW,
    m_flow_nominal=0.1*m_flow_nominal_tot,
    dp_nominal=1.2*dpDesign,
    linearized=true)
    "Differential-pressure bypass (protects pump when all valves close)";

  Buildings.Fluid.Sources.Boundary_pT expVes(
    redeclare package Medium = MediumW,
    p=300000,
    T=313.15,
    nPorts=1) "Expansion vessel / pressure reference";

equation
  // Plant loop
  connect(pum.port_b, boi.port_a);
  connect(boi.port_b, senTSup.port_a);
  connect(senTSup.port_b, pipSup[1].port_a);
  connect(pipRet[1].port_b, senTRet.port_a);
  connect(senTRet.port_b, pum.port_a);
  connect(expVes.ports[1], pum.port_a);

  // Bypass across the riser base
  connect(senTSup.port_b, byp.port_a);
  connect(byp.port_b, senTRet.port_a);

  // Riser: stack the segments
  for f in 1:nFlo - 1 loop
    connect(pipSup[f].port_b, pipSup[f + 1].port_a);
    connect(pipRet[f + 1].port_b, pipRet[f].port_a);
  end for;

  // Apartments tap off at their floor level
  for f in 1:nFlo loop
    for a in 1:nApeFlo loop
      connect(pipSup[f].port_b, apt[(f - 1)*nApeFlo + a].port_a);
      connect(apt[(f - 1)*nApeFlo + a].port_b, pipRet[f].port_a);
    end for;
  end for;

  // Thermal: envelope to outdoor, vertical coupling between stacked apartments
  for i in 1:nApt loop
    connect(apt[i].heaPorAmb, preTOut.port);
  end for;
  for i in 1:nApt - nApeFlo loop
    connect(conVer[i].port_a, apt[i].heaPorZon);
    connect(conVer[i].port_b, apt[i + nApeFlo].heaPorZon);
  end for;

  // SIL interface wiring
  connect(conPumY.y, pum.y);
  connect(TSupSet, boi.TSet);
  connect(TOut, preTOut.T);
  for i in 1:nApt loop
    connect(yVal[i], apt[i].yVal);
    connect(apt[i].TRoom, TRoom[i]);
    connect(apt[i].m_flow, mFlow[i]);
  end for;
  connect(senTSup.T, TSup);
  connect(senTRet.T, TRet);
  connect(boi.Q_flow, QBoi);
  connect(pum.P, PPum);

  annotation (
    experiment(StopTime=604800, Tolerance=1e-6),
    Documentation(info="<html>
<p>Parameterizable multi-tenant building for thermostat SIL research. A gas
boiler (ideal, setpoint-tracking) and a constant-speed pump feed a vertical
two-pipe riser; on every floor <code>nApeFlo</code> apartment branches tap
off. Each branch holds an EN 442-2 radiator behind an equal-percentage valve
whose position is an FMU input. Upper floors see less differential pressure
(riser segment losses), and stacked apartments exchange heat through
floor/ceiling conductances &mdash; both effects that building-wide
distributed thermostat control has to deal with.</p>
</html>"));
end MultiTenantBuilding;
