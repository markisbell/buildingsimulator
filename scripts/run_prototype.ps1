# Run both prototype SIL scenarios; results land in results/
$root = Resolve-Path "$PSScriptRoot\.."
docker run --rm -v "${root}:/work" -w /work/sil buildingsimulator:dev python3 run_prototype.py
