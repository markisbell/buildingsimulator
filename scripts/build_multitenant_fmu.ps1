# Compile the multi-tenant building to build/MultiTenantBuilding.fmu
# Usage: .\build_multitenant_fmu.ps1 [-Floors 3] [-ApartmentsPerFloor 2]
param(
    [int]$Floors = 3,
    [int]$ApartmentsPerFloor = 2
)
$root = Resolve-Path "$PSScriptRoot\.."
New-Item -ItemType Directory -Force "$root\build" | Out-Null
docker run --rm -v "${root}:/work" -w /work/build `
    -e NFLOORS=$Floors -e NAPTSPERFLOOR=$ApartmentsPerFloor `
    buildingsimulator:dev omc /work/modelica/build_multitenant.mos
