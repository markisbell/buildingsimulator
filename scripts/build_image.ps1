# Build the simulator toolchain image (OpenModelica + Buildings library + FMPy)
docker build -t buildingsimulator:dev -f "$PSScriptRoot\..\docker\Dockerfile" "$PSScriptRoot\..\docker"
