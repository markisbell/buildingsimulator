within BuildingSimulator;
model Building80s
  "German 1979-1983 multi-family building (IWU class MFH_G), room-resolved.

   nFlo floors x 2 apartments x 4 rooms (living S, bedroom S, kitchen N,
   bath N) + an unheated hall per apartment. Envelope from IWU typology
   U-values (wall 0.80, window 2.57, roof 0.44, cellar ceiling 0.67 with
   b = 0.5), +10 % thermal bridges, n = 0.7 1/h infiltration. Radiators
   rated 90/70/20 and sized 1.15 x room design load at -12 degC. Two-pipe
   distribution with one riser per room stack (8 risers).
   See docs/building80s-parameters.md for the derivation.

   Zone index k = (floor-1)*8 + stack, stacks 1..8 =
   [apt1: living, bedroom, kitchen, bath | apt2: living, bedroom, kitchen, bath]."

  package MediumW = Buildings.Media.Water "Water medium";

  parameter Integer nFlo = 3 "Number of floors";
  final parameter Integer nSta = 8 "Room stacks (2 apartments x 4 rooms)";
  final parameter Integer nZon = nFlo*nSta "Total rooms";

  // ---------- room parameter tables (per stack, see docs) ----------
  final parameter Modelica.Units.SI.Area ARoo[nSta] =
    {24, 16, 10, 6, 24, 16, 10, 6} "Room floor areas";
  final parameter Modelica.Units.SI.ThermalConductance GWin[nSta] =
    {26.1, 16.7, 10.6, 5.6, 26.1, 16.7, 10.6, 5.6}
    "Window + infiltration conductance (air node)";
  final parameter Modelica.Units.SI.ThermalConductance GWalMid[nSta] =
    {15.3, 11.6, 5.0, 3.7, 15.3, 11.6, 5.0, 3.7}
    "Opaque envelope conductance, mid floor (incl. gable share, +10 % bridges)";
  final parameter Modelica.Units.SI.ThermalConductance GGnd[nSta] =
    {8.8, 5.9, 3.7, 2.2, 8.8, 5.9, 3.7, 2.2}
    "Ground-floor extra: cellar ceiling, b = 0.5";
  final parameter Modelica.Units.SI.ThermalConductance GTop[nSta] =
    {11.6, 7.7, 4.8, 2.9, 11.6, 7.7, 4.8, 2.9} "Top-floor extra: flat roof";
  final parameter Modelica.Units.SI.Temperature TSetDes[nSta] =
    {293.15, 293.15, 293.15, 297.15, 293.15, 293.15, 293.15, 297.15}
    "Design room temperatures (bath 24 degC)";

  final parameter Modelica.Units.SI.ThermalConductance GWal[nFlo, nSta] =
    {{GWalMid[s] + (if f == 1 then GGnd[s] else 0)
              + (if f == nFlo then GTop[s] else 0) for s in 1:nSta} for f in 1:nFlo};

  parameter Modelica.Units.SI.Temperature TOutDes = 261.15
    "Design outdoor temperature (-12 degC)";

  // manual balancing hardware as inputs (set once per run, like a
  // technician's setting; OpenModelica exports bound parameters as
  // calculatedParameter, so inputs are the reliable tunable channel)
  Modelica.Blocks.Interfaces.RealInput yPreset[nZon](each min=0, each max=1)
    "Radiator presetting rings (Voreinstellung), 1 = fully open";
  Modelica.Blocks.Interfaces.RealInput yBalance[nSta](each min=0, each max=1)
    "Riser balancing valves (Strangregulierventile), 1 = fully open";
  parameter Real overSize = 1.15 "Radiator oversizing vs design load";
  final parameter Modelica.Units.SI.Power QRadNom[nFlo, nSta] =
    {{overSize*((GWin[s] + GWal[f, s])*(TSetDes[s] - TOutDes)
                + 15*(TSetDes[s] - 292.15))
      for s in 1:nSta} for f in 1:nFlo}
    "Room design load incl. door loss to the ~19 degC hall, x oversizing";

  final parameter Modelica.Units.SI.MassFlowRate mSta_nominal[nSta] =
    {sum(QRadNom[f, s] for f in 1:nFlo)/4186/20 for s in 1:nSta}
    "Design flow per riser stack (90/70)";
  final parameter Modelica.Units.SI.MassFlowRate m_flow_nominal_tot =
    sum(mSta_nominal);

  final parameter Modelica.Units.SI.PressureDifference dpDesign =
    10000 + 2000 + 5000 + 2000 + 3000 + 2*nFlo*300
    "TRV + branch + preset ring + riser balancing + boiler + riser drops";

  // ---------- SIL interface (flattened: k = (floor-1)*nSta + stack) ----------
  Modelica.Blocks.Interfaces.RealInput yVal[nZon](each min=0, each max=1)
    "Valve position per room (external thermostats)";
  Modelica.Blocks.Interfaces.RealInput QGain[nZon](each unit="W")
    "Solar + internal gains per room";
  Modelica.Blocks.Interfaces.RealInput TOut(unit="K") "Outdoor air temperature";
  Modelica.Blocks.Interfaces.RealInput TSupSet(unit="K") "Supply setpoint";

  Modelica.Blocks.Interfaces.RealOutput TRoom[nZon](each unit="K");
  Modelica.Blocks.Interfaces.RealOutput mFlow[nZon](each unit="kg/s");
  Modelica.Blocks.Interfaces.RealOutput QRad[nZon](each unit="W");
  Modelica.Blocks.Interfaces.RealOutput dpVal[nZon](each unit="Pa");
  Modelica.Blocks.Interfaces.RealOutput THall[nFlo, 2](each unit="K")
    "Hall temperatures per floor and apartment";
  Modelica.Blocks.Interfaces.RealOutput TSup(unit="K");
  Modelica.Blocks.Interfaces.RealOutput TRet(unit="K");
  Modelica.Blocks.Interfaces.RealOutput QBoi(unit="W");
  Modelica.Blocks.Interfaces.RealOutput PPum(unit="W");

  // ---------- rooms ----------
  BuildingSimulator.ApartmentBranch roo[nFlo, nSta](
    redeclare each final package Medium = MediumW,
    Q_flow_nominal=QRadNom,
    each TRadSup_nominal=363.15,
    each TRadRet_nominal=343.15,
    TAirRad_nominal={{TSetDes[s] for s in 1:nSta} for f in 1:nFlo},
    G_win={{GWin[s] for s in 1:nSta} for f in 1:nFlo},
    G_wall=GWal,
    G_int={{9.0*ARoo[s] for s in 1:nSta} for f in 1:nFlo},
    C_air={{15e3*ARoo[s] for s in 1:nSta} for f in 1:nFlo},
    C_mass={{260e3*ARoo[s] for s in 1:nSta} for f in 1:nFlo},
    each fraGainAir=0.3) "Rooms";

  // halls: small air node per apartment coupling its rooms, lossy to stairwell
  Modelica.Thermal.HeatTransfer.Components.HeatCapacitor hal[nFlo, 2](
    each C=0.5e6, each T(start=291.15, fixed=true)) "Hall air+mass";
  Modelica.Thermal.HeatTransfer.Components.ThermalConductor dooRoo[nFlo, nSta](
    each G=15) "Room <-> hall door coupling";
  Modelica.Thermal.HeatTransfer.Components.ThermalConductor halSta[nFlo, 2](
    each G=10) "Hall -> stairwell";
  Modelica.Thermal.HeatTransfer.Sources.FixedTemperature staWel(T=288.15)
    "Stairwell at 15 degC";
  Modelica.Thermal.HeatTransfer.Sensors.TemperatureSensor senHal[nFlo, 2];

  // vertical slab coupling per stack
  Modelica.Thermal.HeatTransfer.Components.ThermalConductor conVer[nFlo - 1, nSta](
    G={{1.7*ARoo[s] for s in 1:nSta} for f in 1:nFlo - 1});

  Modelica.Thermal.HeatTransfer.Sources.PrescribedTemperature preTOut;

  // ---------- hydronics: one riser per stack ----------
  Buildings.Fluid.Actuators.Valves.TwoWayLinear balRis[nSta](
    redeclare each package Medium = MediumW,
    m_flow_nominal=mSta_nominal,
    each dpValve_nominal=2000,
    each l=0.01,
    each linearized=true,
    each allowFlowReversal=false,
    each use_strokeTime=false)
    "Riser balancing valves at the riser bases (yBalance inputs)";

  Buildings.Fluid.FixedResistances.PressureDrop pipSup[nFlo, nSta](
    redeclare each package Medium = MediumW,
    m_flow_nominal={{mSta_nominal[s]*(nFlo - f + 1)/nFlo for s in 1:nSta} for f in 1:nFlo},
    each allowFlowReversal=false,
    each dp_nominal=300) "Supply riser segments";

  Buildings.Fluid.MixingVolumes.MixingVolume volSup[nSta](
    redeclare each package Medium = MediumW,
    m_flow_nominal=mSta_nominal,
    each V=0.006,
    each allowFlowReversal=false,
    each energyDynamics=Modelica.Fluid.Types.Dynamics.FixedInitial,
    each T_start=343.15,
    each nPorts=2)
    "Riser water column, lumped at the stack base: transport lag of the
     supply front. One volume per stack (mid-riser volumes between nearly
     closed segments destabilize the solver at night flows)";

  Modelica.Thermal.HeatTransfer.Components.ThermalConductor conRis[nSta](
    each G=6) "Riser heat loss to the shaft (weak 80s insulation)";

  Buildings.Fluid.MixingVolumes.MixingVolume volBoi(
    redeclare package Medium = MediumW,
    m_flow_nominal=m_flow_nominal_tot,
    V=0.08,
    energyDynamics=Modelica.Fluid.Types.Dynamics.FixedInitial,
    T_start=343.15,
    nPorts=2) "Boiler water content (cast-iron 30 kW class, ~80 l)";
  Buildings.Fluid.FixedResistances.PressureDrop pipRet[nFlo, nSta](
    redeclare each package Medium = MediumW,
    m_flow_nominal={{mSta_nominal[s]*(nFlo - f + 1)/nFlo for s in 1:nSta} for f in 1:nFlo},
    each allowFlowReversal=false,
    each dp_nominal=300) "Return riser segments";

  Buildings.Fluid.Movers.SpeedControlled_y pum(
    redeclare package Medium = MediumW,
    addPowerToMedium=false,
    energyDynamics=Modelica.Fluid.Types.Dynamics.SteadyState,
    per(pressure(V_flow={0, 0.5, 1.0, 1.5}*(m_flow_nominal_tot/1000),
                 dp={1.5, 1.3, 1.0, 0.4}*dpDesign)))
    "Circulation pump (steady-state volume: last unprotected water state)";
  Modelica.Blocks.Sources.Constant conPumY(k=1);

  Buildings.Fluid.HeatExchangers.Heater_T boi(
    redeclare package Medium = MediumW,
    m_flow_nominal=m_flow_nominal_tot,
    dp_nominal=3000,
    QMax_flow=1.3*sum(QRadNom)) "Boiler (90/70 era, setpoint tracking)";

  Buildings.Fluid.Sensors.TemperatureTwoPort senTSup(
    redeclare package Medium = MediumW, m_flow_nominal=m_flow_nominal_tot);
  Buildings.Fluid.Sensors.TemperatureTwoPort senTRet(
    redeclare package Medium = MediumW, m_flow_nominal=m_flow_nominal_tot);

  Buildings.Fluid.FixedResistances.PressureDrop byp(
    redeclare package Medium = MediumW,
    m_flow_nominal=0.1*m_flow_nominal_tot,
    dp_nominal=1.2*dpDesign,
    linearized=true) "dp bypass";

  Buildings.Fluid.Sources.Boundary_pT expVes(
    redeclare package Medium = MediumW, p=300000, T=343.15, nPorts=1);

equation
  // plant loop and bypass (boiler water mass shapes the cycling sawtooth)
  connect(pum.port_b, boi.port_a);
  connect(boi.port_b, volBoi.ports[1]);
  connect(volBoi.ports[2], senTSup.port_a);
  connect(senTSup.port_b, byp.port_a);
  connect(byp.port_b, senTRet.port_a);
  connect(senTRet.port_b, pum.port_a);
  connect(expVes.ports[1], pum.port_a);

  // risers: base connects to plant headers via balancing valves
  for s in 1:nSta loop
    connect(yBalance[s], balRis[s].y);
    connect(senTSup.port_b, balRis[s].port_a);
    connect(balRis[s].port_b, volSup[s].ports[1]);
    connect(volSup[s].ports[2], pipSup[1, s].port_a);
    connect(volSup[s].heatPort, conRis[s].port_a);
    connect(conRis[s].port_b, staWel.port);
    connect(pipRet[1, s].port_b, senTRet.port_a);
    for f in 1:nFlo - 1 loop
      connect(pipSup[f, s].port_b, pipSup[f + 1, s].port_a);
      connect(pipRet[f + 1, s].port_b, pipRet[f, s].port_a);
    end for;
    for f in 1:nFlo loop
      connect(pipSup[f, s].port_b, roo[f, s].port_a);
      connect(roo[f, s].port_b, pipRet[f, s].port_a);
    end for;
  end for;

  // thermal couplings
  for f in 1:nFlo loop
    for s in 1:nSta loop
      connect(roo[f, s].heaPorAmb, preTOut.port);
      connect(roo[f, s].heaPorAir, dooRoo[f, s].port_a);
      connect(dooRoo[f, s].port_b, hal[f, (if s <= 4 then 1 else 2)].port);
    end for;
    for a in 1:2 loop
      connect(hal[f, a].port, halSta[f, a].port_a);
      connect(halSta[f, a].port_b, staWel.port);
      connect(senHal[f, a].port, hal[f, a].port);
      connect(senHal[f, a].T, THall[f, a]);
    end for;
  end for;
  for f in 1:nFlo - 1 loop
    for s in 1:nSta loop
      connect(conVer[f, s].port_a, roo[f, s].heaPorZon);
      connect(conVer[f, s].port_b, roo[f + 1, s].heaPorZon);
    end for;
  end for;

  // SIL wiring (flattened indices)
  connect(conPumY.y, pum.y);
  connect(TSupSet, boi.TSet);
  connect(TOut, preTOut.T);
  for f in 1:nFlo loop
    for s in 1:nSta loop
      connect(yVal[(f - 1)*nSta + s], roo[f, s].yVal);
      connect(yPreset[(f - 1)*nSta + s], roo[f, s].yPreset);
      connect(QGain[(f - 1)*nSta + s], roo[f, s].QGain);
      connect(roo[f, s].TRoom, TRoom[(f - 1)*nSta + s]);
      connect(roo[f, s].m_flow, mFlow[(f - 1)*nSta + s]);
      connect(roo[f, s].QRad, QRad[(f - 1)*nSta + s]);
      connect(roo[f, s].dpVal, dpVal[(f - 1)*nSta + s]);
    end for;
  end for;
  connect(senTSup.T, TSup);
  connect(senTRet.T, TRet);
  connect(boi.Q_flow, QBoi);
  connect(pum.P, PPum);

  annotation (experiment(StopTime=259200, Tolerance=1e-6));
end Building80s;
