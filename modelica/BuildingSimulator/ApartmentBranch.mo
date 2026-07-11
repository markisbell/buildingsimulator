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
    "Radiator heat output at 60/40/20";
  parameter Modelica.Units.SI.MassFlowRate m_flow_nominal = Q_flow_nominal/4186/20
    "Design mass flow";
  parameter Modelica.Units.SI.ThermalConductance UA = 120
    "Envelope conductance to outdoor";
  parameter Modelica.Units.SI.HeatCapacity C = 15e6
    "Effective zone heat capacity";
  parameter Modelica.Units.SI.Temperature T_start = 293.15
    "Initial zone temperature";

  parameter Real yCha[:] = {0, 0.03, 0.06, 0.10, 0.15, 0.22, 0.30, 0.45, 0.65, 1.0}
    "Valve characteristic: normalized pin lift (1.0 = 1.5 mm stroke)";
  parameter Real phiCha[:] = {4e-4, 6e-4, 1.2e-3, 0.12, 0.35, 0.60, 0.78, 0.88, 0.94, 1.0}
    "Valve characteristic: Kv/Kvs, quick-opening (RA-N-like: 80 % flow at 30 % stroke)";

  Modelica.Fluid.Interfaces.FluidPort_a port_a(redeclare package Medium = Medium)
    "Supply connection (from riser)";
  Modelica.Fluid.Interfaces.FluidPort_b port_b(redeclare package Medium = Medium)
    "Return connection (to riser)";

  Modelica.Blocks.Interfaces.RealInput yVal(min=0, max=1)
    "Valve position from external thermostat";
  Modelica.Blocks.Interfaces.RealOutput TRoom(unit="K") "Zone temperature";
  Modelica.Blocks.Interfaces.RealOutput m_flow(unit="kg/s") "Radiator mass flow";
  Modelica.Blocks.Interfaces.RealOutput QRad(unit="W")
    "Radiator heat output (for valve-mounted sensor models)";
  Modelica.Blocks.Interfaces.RealOutput dpVal(unit="Pa")
    "Pressure drop across the valve (for actuator force models)";

  Modelica.Thermal.HeatTransfer.Interfaces.HeatPort_a heaPorZon
    "Zone node, for coupling to neighbouring apartments";
  Modelica.Thermal.HeatTransfer.Interfaces.HeatPort_a heaPorAmb
    "Ambient node (connect to outdoor temperature source)";

  Buildings.Fluid.Actuators.Valves.TwoWayTable val(
    redeclare final package Medium = Medium,
    final m_flow_nominal=m_flow_nominal,
    dpValve_nominal=10000,
    dpFixed_nominal=2000,
    from_dp=true,
    use_strokeTime=true,
    strokeTime=60,
    flowCharacteristics(y=yCha, phi=phiCha))
    "TRV insert (1.5 mm stroke, sealing dead zone; 60 s full stroke by eTRV motor)";

  Buildings.Fluid.HeatExchangers.Radiators.RadiatorEN442_2 rad(
    redeclare final package Medium = Medium,
    final Q_flow_nominal=Q_flow_nominal,
    T_a_nominal=333.15,
    T_b_nominal=313.15,
    TAir_nominal=293.15,
    dp_nominal=0) "Radiator (EN 442-2)";

  Buildings.Fluid.Sensors.MassFlowRate senM(redeclare final package Medium = Medium);

  Modelica.Thermal.HeatTransfer.Components.HeatCapacitor cap(
    final C=C, T(start=T_start, fixed=true)) "Zone thermal mass";
  Modelica.Thermal.HeatTransfer.Components.ThermalConductor conExt(final G=UA)
    "Envelope conductance";
  Modelica.Thermal.HeatTransfer.Sensors.TemperatureSensor senT;

equation
  connect(port_a, val.port_a);
  connect(val.port_b, rad.port_a);
  connect(rad.port_b, senM.port_a);
  connect(senM.port_b, port_b);

  connect(rad.heatPortCon, cap.port);
  connect(rad.heatPortRad, cap.port);
  connect(conExt.port_a, cap.port);
  connect(conExt.port_b, heaPorAmb);
  connect(cap.port, heaPorZon);
  connect(senT.port, cap.port);

  connect(yVal, val.y);
  connect(senT.T, TRoom);
  connect(senM.m_flow, m_flow);

  // heat delivered by the radiator to the zone (port convention: positive into radiator)
  QRad = -(rad.heatPortCon.Q_flow + rad.heatPortRad.Q_flow);
  dpVal = val.dp;
end ApartmentBranch;
