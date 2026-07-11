within BuildingSimulator;
model ApartmentBranch
  "One apartment: radiator valve + EN 442 radiator + single-capacity zone.
   The valve position is an external input (electronic thermostat in the loop)."

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

  Modelica.Fluid.Interfaces.FluidPort_a port_a(redeclare package Medium = Medium)
    "Supply connection (from riser)";
  Modelica.Fluid.Interfaces.FluidPort_b port_b(redeclare package Medium = Medium)
    "Return connection (to riser)";

  Modelica.Blocks.Interfaces.RealInput yVal(min=0, max=1)
    "Valve position from external thermostat";
  Modelica.Blocks.Interfaces.RealOutput TRoom(unit="K") "Zone temperature";
  Modelica.Blocks.Interfaces.RealOutput m_flow(unit="kg/s") "Radiator mass flow";

  Modelica.Thermal.HeatTransfer.Interfaces.HeatPort_a heaPorZon
    "Zone node, for coupling to neighbouring apartments";
  Modelica.Thermal.HeatTransfer.Interfaces.HeatPort_a heaPorAmb
    "Ambient node (connect to outdoor temperature source)";

  Buildings.Fluid.Actuators.Valves.TwoWayEqualPercentage val(
    redeclare final package Medium = Medium,
    final m_flow_nominal=m_flow_nominal,
    dpValve_nominal=10000,
    dpFixed_nominal=2000,
    l=0.01,
    from_dp=true,
    use_strokeTime=true,
    strokeTime=120) "Radiator valve";

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
end ApartmentBranch;
