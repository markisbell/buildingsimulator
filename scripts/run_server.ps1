# Serve the run store to the dashboard on http://localhost:8010
$root = Resolve-Path "$PSScriptRoot\.."
docker run --rm -p 8010:8010 -v "${root}:/work" -w /work buildingsimulator:dev `
    uvicorn server.main:app --host 0.0.0.0 --port 8010
