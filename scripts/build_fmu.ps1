# Compile modelica/PrototypeTwoRooms.mo to build/PrototypeTwoRooms.fmu
$root = Resolve-Path "$PSScriptRoot\.."
New-Item -ItemType Directory -Force "$root\build" | Out-Null
docker run --rm -v "${root}:/work" -w /work/build buildingsimulator:dev omc /work/modelica/build_fmu.mos
