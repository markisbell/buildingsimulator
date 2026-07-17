model VDI6007ZoneTest
  "VDI 6007-1 test rig: the ApartmentBranch 2R2C zone network, extracted
   verbatim (air node + structural mass node, conductances G_win/G_wall/
   G_int, convective heat to air, radiative to mass), under the guideline's
   test-case boundary conditions. Parameters are set per case from
   data/vdi6007/cases.json via the documented VDI-network mapping.

   Heater/cooler: same construct as the AixLib test cases — PI(k=0.1, Ti=4)
   on the air temperature, output scaled by heaterQ (0 disables; 500 W for
   the power-capped case 7; large value approximates case 6's ideal
   air-clamping heater)."

  parameter Modelica.Units.SI.HeatCapacity C_air = 0.70e6
    "Fast node: production convention 40 kJ/(m2 K) x 17.5 m2 VDI room";
  parameter Modelica.Units.SI.HeatCapacity C_mass = 16.44e6
    "Structural mass: CInt + CExt of the VDI network";
  parameter Modelica.Units.SI.ThermalConductance G_int = 178.9
    "Air <-> mass: both VDI air-to-storage series paths in parallel";
  parameter Modelica.Units.SI.ThermalConductance G_wall = 23.38
    "Mass <-> outdoor: RExtRem in series with the outdoor film";
  parameter Modelica.Units.SI.ThermalConductance G_win = 0
    "Air <-> outdoor direct: no window conduction in cases 1-7";
  parameter Modelica.Units.SI.Temperature T_start = 295.15;
  parameter Real heaterQ(unit="W") = 0 "Heater/cooler scale, 0 = off";

  Modelica.Blocks.Interfaces.RealInput TOut(unit="K")
    "Outdoor air temperature";
  Modelica.Blocks.Interfaces.RealInput QConv(unit="W")
    "Convective gains -> air node";
  Modelica.Blocks.Interfaces.RealInput QRadGain(unit="W")
    "Radiative gains -> mass node (surfaces)";
  Modelica.Blocks.Interfaces.RealInput TSetHeat(unit="K")
    "Heater/cooler setpoint";
  Modelica.Blocks.Interfaces.RealOutput TAir(unit="K") "Air temperature";
  Modelica.Blocks.Interfaces.RealOutput TMass(unit="K") "Mass temperature";
  Modelica.Blocks.Interfaces.RealOutput QHeat(unit="W")
    "Heater/cooler heat flow (positive = heating)";

  Modelica.Thermal.HeatTransfer.Components.HeatCapacitor capAir(
    final C=C_air, T(start=T_start, fixed=true)) "Air node";
  Modelica.Thermal.HeatTransfer.Components.HeatCapacitor capMass(
    final C=C_mass, T(start=T_start, fixed=true)) "Structural mass node";
  Modelica.Thermal.HeatTransfer.Components.ThermalConductor conWin(
    final G=G_win) "Windows + infiltration (air -> out)";
  Modelica.Thermal.HeatTransfer.Components.ThermalConductor conWall(
    final G=G_wall) "Opaque envelope (mass -> out)";
  Modelica.Thermal.HeatTransfer.Components.ThermalConductor conInt(
    final G=G_int) "Air <-> internal surfaces";
  Modelica.Thermal.HeatTransfer.Sources.PrescribedTemperature preTOut;
  Modelica.Thermal.HeatTransfer.Sources.PrescribedHeatFlow preConv;
  Modelica.Thermal.HeatTransfer.Sources.PrescribedHeatFlow preRad;
  Modelica.Thermal.HeatTransfer.Sources.PrescribedHeatFlow preHeat;
  Modelica.Thermal.HeatTransfer.Sensors.TemperatureSensor senTAir;
  Modelica.Thermal.HeatTransfer.Sensors.TemperatureSensor senTMass;
  Modelica.Blocks.Continuous.LimPID pid(
    controllerType=Modelica.Blocks.Types.SimpleController.PI,
    k=0.1, Ti=4, yMax=1, yMin=-1) "AixLib test-case heater controller";
  Modelica.Blocks.Math.Gain heaScale(final k=heaterQ);

equation
  connect(TOut, preTOut.T);
  connect(conWin.port_a, capAir.port);
  connect(conWin.port_b, preTOut.port);
  connect(conWall.port_a, capMass.port);
  connect(conWall.port_b, preTOut.port);
  connect(conInt.port_a, capAir.port);
  connect(conInt.port_b, capMass.port);

  connect(QConv, preConv.Q_flow);
  connect(preConv.port, capAir.port);
  connect(QRadGain, preRad.Q_flow);
  connect(preRad.port, capMass.port);

  connect(senTAir.port, capAir.port);
  connect(senTMass.port, capMass.port);
  connect(TSetHeat, pid.u_s);
  connect(senTAir.T, pid.u_m);
  connect(pid.y, heaScale.u);
  connect(heaScale.y, preHeat.Q_flow);
  connect(preHeat.port, capAir.port);

  TAir = senTAir.T;
  TMass = senTMass.T;
  QHeat = heaScale.y;
end VDI6007ZoneTest;
