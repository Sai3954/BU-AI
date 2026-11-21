"""Build public/journey.html from journey.src.html + recorded runs (evals/journey_runs.json)."""
import json, pathlib
here = pathlib.Path(__file__).parent
runs = json.loads((here.parent / "backend/evals/journey_runs.json").read_text())
src = (here / "public/journey.src.html").read_text()
out = src.replace("/*RECORDED_DATA*/[]", json.dumps(runs, ensure_ascii=False).replace("</", "<\\/"))
(here / "public/journey.html").write_text(out)
print("journey.html", len(out) // 1024, "KB,", len(runs), "recorded runs")
