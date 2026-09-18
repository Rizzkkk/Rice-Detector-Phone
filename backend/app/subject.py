"""stand in router for mock mode.

the real routing is a trained model, predict_subject in inference.py. this colour rule is here
so mock mode can still route with no torch installed, which is what let the flutter app get
built and demoed with no weights on the machine.

this is not the production rule. we tried colour first, measured it on the real data, and it
failed in a way worth writing down:

    grain, every percentile        0.000
    leaf, p05                      0.085
    leaf per source, median        philippines 0.721, sethy 0.654, dedeikhsan 0.102

added up it looks like a clean split. dedeikhsan is not, because a badly diseased leaf is
brown and not green, so the greenest leaves are the healthy ones. a colour rule would have been
worst on exactly the photos the app is for. the trained router got 1.0000 on all four sources,
every dedeikhsan leaf included.
"""
from typing import Tuple

from PIL import Image

# everything gets shrunk to this first so the cost does not depend on how big the upload was
PROBE = 128

# green band on pillow's 0-255 hue scale, about 63 to 162 degrees. the saturation and value
# floors matter more than the hue range. a white grain has a hue too, it just means nothing.
HUE_LO, HUE_HI = 45, 115
SAT_FLOOR = 60
VAL_FLOOR = 40

# wide unclear gap on purpose, this rule is only good enough for fixtures
GRAIN_BELOW = 0.05
LEAF_ABOVE = 0.30


def green_fraction(im: Image.Image, probe: int = PROBE) -> float:
    """how much of the image is properly green."""
    small = im.convert("RGB").resize((probe, probe), Image.BILINEAR).convert("HSV")
    green = 0
    for h, s, v in small.getdata():
        if HUE_LO <= h <= HUE_HI and s >= SAT_FLOOR and v >= VAL_FLOOR:
            green += 1
    return green / float(probe * probe)


def classify(im: Image.Image) -> Tuple[str, float]:
    """returns (kind, confidence) so it matches the real router and main.py only needs one code
    path. the confidence is made up from how far past the threshold it landed. it is a fixture
    number, not a measurement."""
    fraction = green_fraction(im)
    if fraction < GRAIN_BELOW:
        return "grain", round(min(1.0, 0.90 + (GRAIN_BELOW - fraction)), 4)
    if fraction > LEAF_ABOVE:
        return "leaf", round(min(1.0, 0.90 + (fraction - LEAF_ABOVE)), 4)
    return "unclear", 0.5
