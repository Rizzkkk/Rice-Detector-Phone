"""loading the models and running them. three yolo11 classifiers, no detector. one grades a
grain, one names a leaf disease, one says which of those two answers fits the photo. the exact
wording in format_report is part of the api contract so it only lives here."""
import sys
from typing import Dict, Optional, Tuple

from . import config

_grain_model = None
_leaf_model = None
_router_model = None
_load_error: Optional[str] = None

# goes on every leaf answer, not just the shaky ones. held back images from the training sets
# score 0.97 but a set the model has never seen scores 0.44 to 0.60, and a photo from a mill is
# a new set. healthy scored 0.000 on unseen sets, so we never report a plant as healthy at all.
# see format_leaf.
LEAF_CAVEAT = (
    "Recognises four rice diseases only. Cannot confirm a plant is healthy, and has not "
    "been reviewed by an agronomist. Use as a screening aid, not as grounds for spraying."
)


def load_models() -> None:
    """runs once at startup. the models stay in memory after that, so dropping a new file on
    disk does nothing until you restart."""
    global _grain_model, _leaf_model, _router_model, _load_error

    if config.MOCK:
        return

    try:
        # imported here and not at the top so mock mode works with no torch installed
        from ultralytics import YOLO

        for path in (config.GRAIN_MODEL_PATH, config.LEAF_MODEL_PATH,
                     config.ROUTER_MODEL_PATH):
            if not path.exists():
                raise FileNotFoundError("missing %s" % path.name)

        _grain_model = YOLO(str(config.GRAIN_MODEL_PATH))
        _leaf_model = YOLO(str(config.LEAF_MODEL_PATH))
        _router_model = YOLO(str(config.ROUTER_MODEL_PATH))
        _load_error = None
    except Exception as exc:
        # saved instead of raised so the app still starts and /health can say what went wrong.
        # also printed, because /health only returns a bool and the reason is the whole point
        # when you are on a server wondering why models_loaded is false.
        _load_error = "%s: %s" % (type(exc).__name__, exc)
        print("model load failed: %s" % _load_error, file=sys.stderr, flush=True)
        _grain_model = None
        _leaf_model = None
        _router_model = None


def models_loaded() -> bool:
    if config.MOCK:
        return True
    return (_grain_model is not None and _leaf_model is not None
            and _router_model is not None)


def load_error() -> Optional[str]:
    return _load_error


def _classify(model, image_path: str) -> Tuple[str, float, Dict[str, float]]:
    """best class plus all the scores. the second place one matters, chalky and whole get mixed
    up often enough that showing only the winner makes the answer look more certain than it is."""
    result = model.predict(image_path, imgsz=config.CLS_IMGSZ, verbose=False)[0]
    probs = {name: float(result.probs.data[i]) for i, name in result.names.items()}
    label = result.names[int(result.probs.top1)]
    return label, float(result.probs.top1conf), probs


def predict_grain(image_path: str) -> Tuple[str, float, Dict[str, float]]:
    return _classify(_grain_model, image_path)


def predict_leaf(image_path: str) -> Tuple[str, float, Dict[str, float]]:
    return _classify(_leaf_model, image_path)


def predict_subject(image_path: str) -> Tuple[str, float]:
    """says which of the two answers fits this photo.

    we tried a colour rule first and it failed on dedeikhsan, where the leaves are brown and not
    green. see app/subject.py. this model got 1.0000 on all four sources.

    it only picks between grain and leaf. it cannot tell you a photo is neither. like every
    model here it only knows its own classes, so a photo of something else lands on whichever
    one it looks closer to."""
    kind, confidence, _ = _classify(_router_model, image_path)
    if confidence < config.ROUTER_UNCERTAIN_BELOW:
        return "unclear", confidence
    return kind, confidence


def is_low_confidence(confidence: Optional[float]) -> bool:
    if confidence is None:
        return False
    return confidence < config.LOW_CONFIDENCE_BELOW


# --- report ---
# one line for the app to show above the detail. the wording is part of the contract.

def _title(label: str) -> str:
    return label.replace("_", " ").title()


def format_leaf(disease: Optional[str]) -> str:
    """healthy never comes out as healthy. that class got 0.000 on every source the model had
    not trained on, so the most we can say is that nothing it knows about is there."""
    if disease is None:
        return "not assessed"
    if disease == "healthy":
        return "No recognised disease"
    return _title(disease)


def format_report(grain: Optional[Tuple[str, float]], leaf: Optional[Tuple[str, float]],
                  grain_applicable: bool = True, leaf_applicable: bool = True) -> str:
    """one line, the answer that applies goes first. the other model still returned a number but
    printing it here would put a meaningless grade next to a real one."""
    def part(name: str, value: Optional[Tuple[str, float]], text: str, applicable: bool) -> str:
        if not applicable:
            return "%s: not applicable to this photo" % name
        if value is None:
            return "%s: not assessed" % name
        line = "%s: %s, %d%% confident" % (name, text, round(value[1] * 100))
        if is_low_confidence(value[1]):
            line += " (low)"
        return line

    parts = [
        (grain_applicable, part("Grain", grain, _title(grain[0]) if grain else "", grain_applicable)),
        (leaf_applicable, part("Leaf", leaf, format_leaf(leaf[0]) if leaf else "", leaf_applicable)),
    ]
    # the one that applies goes first. sorted is stable so grain still leads when both apply
    parts.sort(key=lambda p: not p[0])
    return "%s | %s" % (parts[0][1], parts[1][1])


# --- mock ---
# fixed values so the flutter app sees the same response every time while its screens get
# built. the grain answer is a near tie between chalky and whole on purpose, because that is
# the case the results screen has to handle without overclaiming.

MOCK_GRAIN = ("chalky", 0.5412, {
    "broken": 0.0181, "chalky": 0.5412, "stained": 0.0119, "whole": 0.4288,
})
MOCK_LEAF = ("brown_spot", 0.9134, {
    "bacterial_leaf_blight": 0.0402, "brown_spot": 0.9134, "healthy": 0.0090,
    "rice_blast": 0.0301, "tungro": 0.0073,
})


def mock_analyze(with_grain: bool, with_leaf: bool):
    return (MOCK_GRAIN if with_grain else None), (MOCK_LEAF if with_leaf else None)
