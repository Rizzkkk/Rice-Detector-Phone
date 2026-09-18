"""Real-mode smoke check. Loads the three .pt files and puts real photographs through them.

Deliberately separate from test_contract.py, which sets RICE_MOCK=1 at import and pins the
wire format against fixed values. That suite passes with no weights, no torch and no models
directory at all - which is what it is for, and why it cannot answer the question here: does a
real photograph through a real model come back with the right answer.

The photographs come out of the training zip rather than app/test/fixtures/. Those fixtures are
solid colour rectangles built for the mock-mode colour heuristic, and a closed-set classifier
puts a beige rectangle somewhere confident and arbitrary. They are correct for what they test
and useless here.

This is a smoke check, not a measurement. The images are from the validation split, which the
model saw during training for early stopping, so passing says the plumbing and the weights
agree - not that the model is accurate. The held-out numbers in models/model_facts.json are
the only figures worth quoting.

Run from backend/:  .venv/Scripts/python smoke_real.py
Override the zip location with RICE_MODELS_ZIP if it is not in Downloads.
"""
import io
import os
import sys
import zipfile
from pathlib import Path

os.environ.pop("RICE_MOCK", None)

from PIL import Image  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config, inference  # noqa: E402
from app.main import app  # noqa: E402

DEFAULT_ZIP = Path.home() / "Downloads" / "rice_models (4).zip"
MODELS_ZIP = Path(os.getenv("RICE_MODELS_ZIP", DEFAULT_ZIP))

# Ultralytics writes val_batch0_labels.jpg as a 4x4 grid of 224px tiles, each with its
# ground-truth label printed across the top ~24px. Cropping the top-left tile below that banner
# gives one real photograph whose correct answer is known.
TILE = (0, 24, 224, 224)

# Read off the printed labels in that top-left tile. Retraining regenerates the mosaic, so if
# these stop matching, re-read the labels rather than loosening the assertion - a wrong answer
# and a reshuffled grid look identical from here.
GRAIN_TRUTH = "whole"
LEAF_TRUTH = "brown_spot"

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           "" if cond else "  <- " + str(detail)))


def tile_from(zf, member):
    with zf.open(member) as f:
        im = Image.open(io.BytesIO(f.read())).convert("RGB").crop(TILE)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=95)
    return buf.getvalue()


def analyze(client, data):
    return client.post("/analyze", files={"image": ("p.jpg", data, "image/jpeg")})


print("weights on disk")
for path in (config.GRAIN_MODEL_PATH, config.LEAF_MODEL_PATH, config.ROUTER_MODEL_PATH):
    check(path.name, path.exists(), path)

if not all(results):
    print("\nno weights, nothing else can run")
    raise SystemExit(1)

if not MODELS_ZIP.exists():
    print("\nno training zip at %s" % MODELS_ZIP)
    print("set RICE_MODELS_ZIP. the model-loading checks above passed; the photograph checks "
          "did not run and nothing here should be read as proof they would.")
    raise SystemExit(1)

with zipfile.ZipFile(MODELS_ZIP) as zf:
    grain_photo = tile_from(zf, "grain_grade_run/val_batch0_labels.jpg")
    leaf_photo = tile_from(zf, "leaf_disease_run/val_batch0_labels.jpg")

# context manager, not a bare TestClient: starlette only fires the lifespan inside one, and
# load_models is the thing this file exists to exercise
with TestClient(app) as client:
    print("\nmodels load")
    check("no load error", inference.load_error() is None, inference.load_error())
    check("models_loaded true", inference.models_loaded())

    r = client.get("/health")
    check("health is 200", r.status_code == 200, r.status_code)
    check("health reports loaded", r.json().get("models_loaded") is True, r.json())

    if not all(results):
        print("\nmodels did not load, skipping inference")
        raise SystemExit(1)

    print("\nclass names match what the notebook recorded")
    grain_names = set(inference._grain_model.names.values())
    leaf_names = set(inference._leaf_model.names.values())
    router_names = set(inference._router_model.names.values())
    check("grain classes", grain_names == {"broken", "chalky", "stained", "whole"}, grain_names)
    check("leaf classes", leaf_names == {"bacterial_leaf_blight", "brown_spot", "healthy",
                                         "rice_blast", "tungro"}, leaf_names)
    check("router classes", router_names == {"grain", "leaf"}, router_names)

    print("\na real grain photograph")
    r = analyze(client, grain_photo)
    check("200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        b = r.json()
        check("routed to grain", b["subject"]["kind"] == "grain", b["subject"])
        check("grain applicable", b["grain"]["applicable"] is True)
        check("leaf muted", b["leaf"]["applicable"] is False)
        check("graded %s" % GRAIN_TRUTH, b["grain"]["grade"] == GRAIN_TRUTH, b["grain"]["grade"])
        # a softmax sums to 1 whatever the answer is. a set that does not means the wrong head
        # or the wrong imgsz, which costs accuracy silently rather than raising
        check("probs sum to 1", abs(sum(b["grain"]["probabilities"].values()) - 1.0) < 0.01,
              sum(b["grain"]["probabilities"].values()))
        check("report leads with grain", b["report"].startswith("Grain:"), b["report"])
        print("      -> %s" % b["report"])

    print("\na real leaf photograph")
    r = analyze(client, leaf_photo)
    check("200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        b = r.json()
        check("routed to leaf", b["subject"]["kind"] == "leaf", b["subject"])
        check("leaf applicable", b["leaf"]["applicable"] is True)
        check("grain muted", b["grain"]["applicable"] is False)
        check("named %s" % LEAF_TRUTH, b["leaf"]["disease"] == LEAF_TRUTH, b["leaf"]["disease"])
        check("caveat present", bool(b["leaf"].get("caveat")), b["leaf"].get("caveat"))
        check("report leads with leaf", b["report"].startswith("Leaf:"), b["report"])
        check("never says Healthy", "Healthy" not in b["report"], b["report"])
        print("      -> %s" % b["report"])

        # The measured reason `applicable` exists and cannot be replaced by a confidence
        # threshold. On this leaf photograph the grain model returns a grade at ~0.9998 - a
        # nonsense answer more confident than the correct one it gives on real grain. Anything
        # that decides what to show from confidence alone would show this.
        muted = b["grain"]["confidence"]
        check("inapplicable answer arrives highly confident", muted is not None and muted > 0.9,
              muted)
        check("and is still marked inapplicable", b["grain"]["applicable"] is False)
        print("      -> grain model on a leaf: %s at %.4f, muted" % (b["grain"]["grade"], muted))

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
