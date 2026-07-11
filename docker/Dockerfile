FROM openmodelica/openmodelica:v1.27.0-ompython

# Modelica Buildings library via the OpenModelica package manager
RUN echo 'updatePackageIndex(); getErrorString(); installPackage(Buildings); getErrorString();' > /tmp/install_buildings.mos \
 && omc /tmp/install_buildings.mos \
 && rm /tmp/install_buildings.mos

# Python packages for the SIL harness (fall back for pre-PEP668 images)
RUN pip3 install --no-cache-dir --break-system-packages fmpy matplotlib pandas pvlib \
 || pip3 install --no-cache-dir fmpy matplotlib pandas pvlib

WORKDIR /work
