#!/bin/bash
# Docker-free simulation toolchain inside WSL (Ubuntu 24.04), run as root:
#   wsl -d Ubuntu-24.04 -u root -- bash -c "tr -d '\r' < /mnt/c/.../scripts/wsl_toolchain_setup.sh | bash"
#
# Installs OpenModelica (stable apt channel) + Modelica Buildings 13.0.0 +
# the Python SIL dependencies, and links the repo at /work so the existing
# build .mos scripts work unchanged. Idempotent. Created when the Docker
# Desktop service became unstartable without admin rights; WSL runs the
# same toolchain per-user.
set -e

REPO="/mnt/c/Users/bell/Documents/Forschungsprojekte_Drittmittel/Forschung_Gebaeudemodelle/buildingsimulator"

echo "--- base packages"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    ca-certificates curl gnupg python3-pip python3-venv >/dev/null

echo "--- openmodelica apt repo"
curl -fsSL https://build.openmodelica.org/apt/openmodelica.asc \
    -o /usr/share/keyrings/openmodelica.asc
echo "deb [signed-by=/usr/share/keyrings/openmodelica.asc arch=amd64] https://build.openmodelica.org/apt noble stable" \
    > /etc/apt/sources.list.d/openmodelica.list
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq omc >/dev/null
omc --version

echo "--- python deps (dedicated venv, avoids debian-owned packages)"
python3 -m venv /opt/silenv
/opt/silenv/bin/pip install -q --upgrade pip
/opt/silenv/bin/pip install -q fmpy numpy pandas matplotlib pvlib gymnasium
/opt/silenv/bin/python3 -c "import fmpy, pvlib, pandas; print('python deps ok, fmpy', fmpy.__version__)"

echo "--- Modelica Buildings 13.0.0 (package manager)"
cat > /tmp/install_libs.mos <<'EOF'
updatePackageIndex(); getErrorString();
installPackage(Modelica); getErrorString();
installPackage(Buildings, "13.0.0", exactMatch=true); getErrorString();
EOF
omc /tmp/install_libs.mos
ls "$HOME/.openmodelica/libraries" || true

echo "--- /work symlink (build .mos scripts reference /work/...)"
ln -sfn "$REPO" /work
ls /work/modelica >/dev/null && echo "/work -> repo ok"

echo "--- SETUP COMPLETE"
