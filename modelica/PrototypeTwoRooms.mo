model PrototypeTwoRooms
  "Prototype: boiler -> pump -> two parallel radiator branches with externally controlled valves -> two rooms.
   All thermostat intelligence lives outside the FMU (software in the loop)."

  package MediumW = Buildings.Media.Water "Water medium";

  // Nominal design values (60/40 radiator system, 20 degC room)
  parameter Modelica.Units.SI.Power Q_flow_nominal_rad = 2000
    "Nominal heat output per radiator at 60/40/20";
  parameter Modelica.Units.SI.MassFlowRate m_flow_nominal_rad = Q_flow_nominal_rad/4186/20
    "Nominal mass flow per radiator branch";
  parameter Modelica.Units.SI.MassFlowRate m_flow_nominal_tot = 2*m_flow_nominal_rad
    "Nominal total mass flow";

  // ---------- SIL interface: inputs ----------
  Modelica.Blocks.Interfaces.RealInput yVal1(min=0, max=1)
    "Valve position radiator 1 (0=closed, 1=open)";
  Modelica.Blocks.Interfaces.RealInput yVal2(min=0, max=1)
    "Valve position radiator 2 (0=closed, 1=open)";
  Modelica.Blocks.Interfaces.RealInput TOut(unit="K")
    "Outdoor air temperature";
  Modelica.Blocks.Interfaces.RealInput TSupSet(unit="K")
    "Boiler supply temperature setpoint";

  // ---------- SIL interface: outputs ----------
  Modelica.Blocks.Interfaces.RealOutput TRoom1(unit="K") "Room 1 air temperature";
  Modelica.Blocks.Interfaces.RealOutput TRoom2(unit="K") "Room 2 air temperature";
  Modelica.Blocks.Interfaces.RealOutput TSup(unit="K") "Supply water temperature";
  Modelica.Blocks.Interfaces.RealOutput TRet(unit="K") "Return water temperature";
  Modelica.Blocks.Interfaces.RealOutput mFlow1(unit="kg/s") "Mass flow radiator 1";
  Modelica.Blocks.Interfaces.RealOutput mFlow2(unit="kg/s") "Mass flow radiator 2";
  Modelica.Blocks.Interfaces.RealOutput QBoi(unit="W") "Boiler heat flow";

  // ---------- Hydronic plant ----------
  Buildings.Fluid.Movers.SpeedControlled_y pum(
    redeclare package Medium = MediumW,
    per(pressure(V_flow={0, 2.5e-5, 5e-5, 7.5e-5, 1e-4},
                 dp={30000, 26000, 20000, 12000, 2000})))
    "Constant-speed circulation pump (head follows pump curve -> hydraulic coupling)";

  Modelica.Blocks.Sources.Constant conPumY(k=1) "Pump at full speed";

  Buildings.Fluid.HeatExchangers.Heater_T boi(
    redeclare package Medium = MediumW,
    m_flow_nominal=m_flow_nominal_tot,
    dp_nominal=3000,
    QMax_flow=10000)
    "Ideal boiler tracking the supply temperature setpoint";

  Buildings.Fluid.Sensors.TemperatureTwoPort senTSup(
    redeclare package Medium = MediumW,
    m_flow_nominal=m_flow_nominal_tot) "Supply temperature sensor";

  Buildings.Fluid.Sensors.TemperatureTwoPort senTRet(
    redeclare package Medium = MediumW,
    m_flow_nominal=m_flow_nominal_tot) "Return temperature sensor";

  Buildings.Fluid.FixedResistances.PressureDrop resSup(
    redeclare package Medium = MediumW,
    m_flow_nominal=m_flow_nominal_tot,
    dp_nominal=3000) "Common supply header/riser resistance";

  Buildings.Fluid.FixedResistances.PressureDrop resRet(
    redeclare package Medium = MediumW,
    m_flow_nominal=m_flow_nominal_tot,
    dp_nominal=3000) "Common return header/riser resistance";

  Buildings.Fluid.Sources.Boundary_pT expVes(
    redeclare package Medium = MediumW,
    p=300000,
    T=313.15,
    nPorts=1) "Expansion vessel / pressure reference";

  Buildings.Fluid.FixedResistances.PressureDrop byp(
    redeclare package Medium = MediumW,
    m_flow_nominal=0.005,
    dp_nominal=20000)
    "Differential-pressure bypass (protects pump when all valves close)";

  // ---------- Radiator branch 1 ----------
  Buildings.Fluid.Actuators.Valves.TwoWayEqualPercentage val1(
    redeclare package Medium = MediumW,
    m_flow_nominal=m_flow_nominal_rad,
    dpValve_nominal=10000,
    dpFixed_nominal=2000,
    l=0.01) "Radiator valve 1 (actuated by external thermostat)";

  Buildings.Fluid.HeatExchangers.Radiators.RadiatorEN442_2 rad1(
    redeclare package Medium = MediumW,
    Q_flow_nominal=Q_flow_nominal_rad,
    T_a_nominal=333.15,
    T_b_nominal=313.15,
    TAir_nominal=293.15,
    dp_nominal=0) "Radiator 1 (EN 442-2)";

  Buildings.Fluid.Sensors.MassFlowRate senM1(redeclare package Medium = MediumW);

  // ---------- Radiator branch 2 ----------
  Buildings.Fluid.Actuators.Valves.TwoWayEqualPercentage val2(
    redeclare package Medium = MediumW,
    m_flow_nominal=m_flow_nominal_rad,
    dpValve_nominal=10000,
    dpFixed_nominal=2000,
    l=0.01) "Radiator valve 2 (actuated by external thermostat)";

  Buildings.Fluid.HeatExchangers.Radiators.RadiatorEN442_2 rad2(
    redeclare package Medium = MediumW,
    Q_flow_nominal=Q_flow_nominal_rad,
    T_a_nominal=333.15,
    T_b_nominal=313.15,
    TAir_nominal=293.15,
    dp_nominal=0) "Radiator 2 (EN 442-2)";

  Buildings.Fluid.Sensors.MassFlowRate senM2(redeclare package Medium = MediumW);

  // ---------- Rooms: simple RC zones (UA sized so 2 kW covers dT = 25 K) ----------
  Modelica.Thermal.HeatTransfer.Components.HeatCapacitor cap1(
    C=10e6, T(start=293.15, fixed=true)) "Thermal mass room 1";
  Modelica.Thermal.HeatTransfer.Components.ThermalConductor con1(G=80)
    "Envelope conductance room 1";
  Modelica.Thermal.HeatTransfer.Sensors.TemperatureSensor senTRoom1;

  Modelica.Thermal.HeatTransfer.Components.HeatCapacitor cap2(
    C=10e6, T(start=293.15, fixed=true)) "Thermal mass room 2";
  Modelica.Thermal.HeatTransfer.Components.ThermalConductor con2(G=80)
    "Envelope conductance room 2";
  Modelica.Thermal.HeatTransfer.Sensors.TemperatureSensor senTRoom2;

  Modelica.Thermal.HeatTransfer.Sources.PrescribedTemperature preTOut
    "Outdoor temperature boundary";

equation
  // Plant loop: pump -> boiler -> supply sensor -> supply header
  connect(pum.port_b, boi.port_a);
  connect(boi.port_b, senTSup.port_a);
  connect(senTSup.port_b, resSup.port_a);

  // Parallel branches off the supply header (+ dp bypass)
  connect(resSup.port_b, val1.port_a);
  connect(resSup.port_b, val2.port_a);
  connect(resSup.port_b, byp.port_a);
  connect(byp.port_b, resRet.port_a);
  connect(val1.port_b, rad1.port_a);
  connect(val2.port_b, rad2.port_a);
  connect(rad1.port_b, senM1.port_a);
  connect(rad2.port_b, senM2.port_a);

  // Return header -> return sensor -> pump suction (+ pressure reference)
  connect(senM1.port_b, resRet.port_a);
  connect(senM2.port_b, resRet.port_a);
  connect(resRet.port_b, senTRet.port_a);
  connect(senTRet.port_b, pum.port_a);
  connect(expVes.ports[1], pum.port_a);

  // Rooms
  connect(rad1.heatPortCon, cap1.port);
  connect(rad1.heatPortRad, cap1.port);
  connect(con1.port_a, cap1.port);
  connect(con1.port_b, preTOut.port);
  connect(senTRoom1.port, cap1.port);

  connect(rad2.heatPortCon, cap2.port);
  connect(rad2.heatPortRad, cap2.port);
  connect(con2.port_a, cap2.port);
  connect(con2.port_b, preTOut.port);
  connect(senTRoom2.port, cap2.port);

  // SIL interface wiring
  connect(conPumY.y, pum.y);
  connect(yVal1, val1.y);
  connect(yVal2, val2.y);
  connect(TSupSet, boi.TSet);
  connect(TOut, preTOut.T);
  connect(senTRoom1.T, TRoom1);
  connect(senTRoom2.T, TRoom2);
  connect(senTSup.T, TSup);
  connect(senTRet.T, TRet);
  connect(senM1.m_flow, mFlow1);
  connect(senM2.m_flow, mFlow2);
  connect(boi.Q_flow, QBoi);

  annotation (
    experiment(StopTime=604800, Tolerance=1e-6),
    Documentation(info="<html>
<p>Minimal hydronic prototype for the building simulator SIL toolchain.
Two parallel radiator branches share a constant-speed pump and common
supply/return resistances, so closing one valve shifts flow to the other
branch (hydraulic coupling). Valve positions, outdoor temperature and the
supply temperature setpoint are FMU inputs; room/water temperatures, branch
mass flows and boiler power are FMU outputs.</p>
</html>"));
end PrototypeTwoRooms;
