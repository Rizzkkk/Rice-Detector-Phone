"""Contract tests. Pins the wire format the Flutter client depends on."""
import io, os
os.environ["RICE_MOCK"] = "1"

from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app import main as _m

# context manager, not a bare TestClient: without it starlette skips lifespan, load_models
# never runs, and an earlier version of this suite passed while reporting no load error at all
client_cm = TestClient(app)

GREEN = (60, 140, 50)        # foliage
PALE = (235, 230, 215)       # grain on a plain tray


def solid(colour, w=1600, h=1200, fmt="JPEG"):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(buf, fmt)
    return buf.getvalue()


def mixed(green_rows=240, w=1600, h=1200):
    """Part foliage, part plain, so neither rule fires. The unclear case."""
    im = Image.new("RGB", (w, h), PALE)
    im.paste(Image.new("RGB", (w, green_rows), GREEN), (0, 0))
    buf = io.BytesIO()
    im.save(buf, "JPEG")
    return buf.getvalue()


def post(data, name="p.jpg", mime="image/jpeg"):
    _m._hits.clear()
    return client.post("/analyze", files={"image": (name, data, mime)})


results = []
def check(name, cond, detail=""):
    results.append(cond)
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, "" if cond else "  <- " + str(detail)))


with client_cm as client:
    print("health")
    r = client.get("/health")
    check("200", r.status_code == 200, r.status_code)
    check("exact body shape", r.json() == {"status": "ok", "models_loaded": True}, r.json())

    print("subject routing")
    d_grain = post(solid(PALE, 800, 800)).json()
    check("pale photo routes to grain", d_grain["subject"]["kind"] == "grain", d_grain["subject"])
    d_leaf = post(solid(GREEN)).json()
    check("green photo routes to leaf", d_leaf["subject"]["kind"] == "leaf", d_leaf["subject"])
    d_mix = post(mixed()).json()
    check("part-green photo is unclear", d_mix["subject"]["kind"] == "unclear", d_mix["subject"])
    check("subject confidence in [0,1]",
          all(0 <= d["subject"]["confidence"] <= 1 for d in (d_grain, d_leaf, d_mix)))
    check("a decided subject is more confident than an unclear one",
          d_mix["subject"]["confidence"] < d_grain["subject"]["confidence"]
          and d_mix["subject"]["confidence"] < d_leaf["subject"]["confidence"],
          [d["subject"]["confidence"] for d in (d_grain, d_mix, d_leaf)])

    print("applicability")
    check("grain photo: grain applies, leaf does not",
          d_grain["grain"]["applicable"] is True and d_grain["leaf"]["applicable"] is False,
          (d_grain["grain"]["applicable"], d_grain["leaf"]["applicable"]))
    check("leaf photo: leaf applies, grain does not",
          d_leaf["leaf"]["applicable"] is True and d_leaf["grain"]["applicable"] is False,
          (d_leaf["grain"]["applicable"], d_leaf["leaf"]["applicable"]))
    check("unclear: both apply",
          d_mix["grain"]["applicable"] is True and d_mix["leaf"]["applicable"] is True, d_mix)
    for tag, d in (("grain", d_grain), ("leaf", d_leaf), ("unclear", d_mix)):
        check("never both inapplicable (%s)" % tag,
              d["grain"]["applicable"] or d["leaf"]["applicable"], d)
    check("both applicable only when unclear",
          not (d_grain["grain"]["applicable"] and d_grain["leaf"]["applicable"])
          and not (d_leaf["grain"]["applicable"] and d_leaf["leaf"]["applicable"]))

    print("both models still run regardless of applicability")
    check("inapplicable leaf still assessed", d_grain["leaf"]["assessed"] is True, d_grain["leaf"])
    check("inapplicable grain still assessed", d_leaf["grain"]["assessed"] is True, d_leaf["grain"])

    print("model payloads")
    check("grain has 4 classes", len(d_grain["grain"]["probabilities"]) == 4, d_grain["grain"])
    check("leaf has 5 classes", len(d_leaf["leaf"]["probabilities"]) == 5, d_leaf["leaf"])
    check("grain probabilities sum to 1",
          abs(sum(d_grain["grain"]["probabilities"].values()) - 1) < 0.01)
    check("leaf probabilities sum to 1",
          abs(sum(d_leaf["leaf"]["probabilities"].values()) - 1) < 0.01)
    check("grain winner matches top probability",
          max(d_grain["grain"]["probabilities"], key=d_grain["grain"]["probabilities"].get)
          == d_grain["grain"]["grade"], d_grain["grain"])
    check("leaf winner matches top probability",
          max(d_leaf["leaf"]["probabilities"], key=d_leaf["leaf"]["probabilities"].get)
          == d_leaf["leaf"]["disease"], d_leaf["leaf"])
    check("confidence in [0,1]", 0 <= d_grain["grain"]["confidence"] <= 1)

    print("confidence floor")
    check("near-tie flagged low", d_grain["grain"]["low_confidence"] is True, d_grain["grain"])
    check("confident answer not flagged", d_leaf["leaf"]["low_confidence"] is False, d_leaf["leaf"])
    check("report marks it low", "(low)" in d_grain["report"], d_grain["report"])

    print("report leads with the applicable result")
    check("grain photo leads with Grain", d_grain["report"].startswith("Grain:"), d_grain["report"])
    check("grain photo marks leaf inapplicable",
          "Leaf: not applicable to this photo" in d_grain["report"], d_grain["report"])
    check("leaf photo leads with Leaf", d_leaf["report"].startswith("Leaf:"), d_leaf["report"])
    check("leaf photo marks grain inapplicable",
          "Grain: not applicable to this photo" in d_leaf["report"], d_leaf["report"])
    check("unclear shows both, grain first",
          d_mix["report"].startswith("Grain:") and "not applicable" not in d_mix["report"],
          d_mix["report"])

    print("caveat")
    check("caveat present on the leaf answer", bool(d_leaf["leaf"]["caveat"]), d_leaf["leaf"])
    check("caveat present even when leaf is inapplicable", bool(d_grain["leaf"]["caveat"]))
    check("caveat refuses to confirm healthy",
          "cannot confirm" in d_leaf["leaf"]["caveat"].lower(), d_leaf["leaf"]["caveat"])

    print("image meta")
    check("downscaled to long edge 1280",
          max(d_leaf["image"]["width"], d_leaf["image"]["height"]) == 1280, d_leaf["image"])
    check("aspect preserved 4:3", d_leaf["image"] == {"width": 1280, "height": 960}, d_leaf["image"])
    check("small image left alone", d_grain["image"] == {"width": 800, "height": 800},
          d_grain["image"])

    print("errors")
    _m._hits.clear()
    r = client.post("/analyze", files={})
    check("missing image -> 400", r.status_code == 400, r.status_code)
    check("message names the field", r.json() == {"error": "image is required"}, r.json())

    r = post(b"not an image at all")
    check("undecodable -> 400", r.status_code == 400, r.status_code)
    check("error shape", set(r.json().keys()) == {"error"}, r.json())

    r = post(b"\xff\xd8" + b"\x00" * (11 * 1024 * 1024), name="big.jpg")
    check("oversized -> 413", r.status_code == 413, r.status_code)

    r = post(solid(GREEN, fmt="GIF"), name="a.gif", mime="image/gif")
    check("gif -> 415", r.status_code == 415, r.status_code)

    _m._hits.clear()
    r = client.post("/analyze", files={"image": ("", b"", "application/octet-stream")})
    check("empty part counts as missing -> 400", r.status_code == 400, r.status_code)

    print("rate limit")
    _m._hits.clear()
    small = solid(GREEN, 200, 200)
    codes = [client.post("/analyze", files={"image": ("l.jpg", small, "image/jpeg")}).status_code
             for _ in range(30)]
    check("429 eventually", 429 in codes, codes[-5:])
    check("429 body shape",
          client.post("/analyze", files={"image": ("l.jpg", small, "image/jpeg")}).json()
          == {"error": "too many requests, slow down"})

    print("multipart bomb")
    _m._hits.clear()
    many = {("f%d" % i): ("f%d.jpg" % i, solid(GREEN, 60, 60), "image/jpeg") for i in range(6)}
    many["image"] = ("p.jpg", solid(GREEN, 60, 60), "image/jpeg")
    r = client.post("/analyze", files=many)
    check("rejected", r.status_code != 200, r.status_code)
    check("as 4xx not 500", 400 <= r.status_code < 500, r.status_code)
    check("error shape", set(r.json().keys()) == {"error"}, r.json())

    print("api key")
    # config is read at request time, not import time, so the key can be switched on here.
    # restored in a finally: leaving it set would fail every check written before this one.
    from app import config as _cfg
    _previous_key = _cfg.API_KEY
    try:
        _cfg.API_KEY = "test-key-value"
        img = ("p.jpg", solid(PALE, 200, 200), "image/jpeg")

        _m._hits.clear()
        r = client.post("/analyze", files={"image": img})
        check("no header rejected", r.status_code == 401, r.status_code)
        check("401 error shape", set(r.json().keys()) == {"error"}, r.json())

        _m._hits.clear()
        r = client.post("/analyze", files={"image": img}, headers={"x-api-key": "wrong"})
        check("wrong key rejected", r.status_code == 401, r.status_code)

        _m._hits.clear()
        r = client.post("/analyze", files={"image": img},
                        headers={"x-api-key": "test-key-value"})
        check("right key accepted", r.status_code == 200, r.status_code)

        # a prefix of the real key must not pass, or compare_digest is not being reached
        _m._hits.clear()
        r = client.post("/analyze", files={"image": img}, headers={"x-api-key": "test-key"})
        check("prefix of key rejected", r.status_code == 401, r.status_code)

        # caddy and any uptime probe hit this unauthenticated
        check("health needs no key", client.get("/health").status_code == 200)

        # the rate limit runs before the key check, so an unauthenticated flood is throttled
        # rather than being cheap to repeat. documented in 02-api-contract.md; asserted here
        # because swapping the two lines in analyze() would silently reverse it.
        _m._hits.clear()
        codes = [client.post("/analyze", files={"image": img}).status_code
                 for _ in range(30)]
        check("unauthenticated flood is rate limited", 429 in codes, set(codes))
        check("and 401 came first", codes[0] == 401, codes[0])
    finally:
        _cfg.API_KEY = _previous_key

    _m._hits.clear()
    check("unset key leaves endpoint open",
          client.post("/analyze", files={"image": ("p.jpg", solid(PALE, 200, 200),
                                                   "image/jpeg")}).status_code == 200)

print("subject helper, directly")
from app import subject

check("solid foliage is leaf", subject.classify(Image.new("RGB", (300, 300), GREEN))[0] == "leaf")
check("plain tray is grain", subject.classify(Image.new("RGB", (300, 300), PALE))[0] == "grain")
check("grey is grain", subject.classify(Image.new("RGB", (300, 300), (128, 128, 128)))[0] == "grain")
check("near black is grain", subject.classify(Image.new("RGB", (300, 300), (8, 8, 8)))[0] == "grain")
check("dark shaded leaf still leaf",
      subject.classify(Image.new("RGB", (300, 300), (25, 55, 20)))[0] == "leaf")
check("thresholds ordered", subject.GRAIN_BELOW < subject.LEAF_ABOVE)

print("report formatting")
from app.inference import format_report, format_leaf, LEAF_CAVEAT

check("both applicable",
      format_report(("chalky", 0.91), ("brown_spot", 0.88))
      == "Grain: Chalky, 91% confident | Leaf: Brown Spot, 88% confident")
check("leaf inapplicable",
      format_report(("whole", 0.95), ("tungro", 0.99), True, False)
      == "Grain: Whole, 95% confident | Leaf: not applicable to this photo")
check("grain inapplicable leads with leaf",
      format_report(("whole", 0.95), ("tungro", 0.99), False, True)
      == "Leaf: Tungro, 99% confident | Grain: not applicable to this photo")
check("low confidence marked",
      format_report(("chalky", 0.52), None, True, False)
      == "Grain: Chalky, 52% confident (low) | Leaf: not applicable to this photo",
      format_report(("chalky", 0.52), None, True, False))
check("confident answer not marked low", "(low)" not in format_report(("chalky", 0.91), None))
check("multi-word disease titled",
      "Bacterial Leaf Blight" in format_report(None, ("bacterial_leaf_blight", 0.7)))

print("healthy is never reported as healthy")
check("healthy becomes no recognised disease", format_leaf("healthy") == "No recognised disease")
check("report never says Healthy", "Healthy" not in format_report(None, ("healthy", 0.97)))
check("other diseases unaffected", format_leaf("rice_blast") == "Rice Blast")
check("absent stays not assessed", format_leaf(None) == "not assessed")

print("hardening")
import time as _t

_m._hits.clear(); _m._last_prune = 0.0
for i in range(500):
    _m._hits["10.0.0.%d" % (i % 250)].append(_t.monotonic() - 999)
_m._last_prune = 0.0
_m._prune(_t.monotonic())
check("stale rate-limit entries pruned", len(_m._hits) == 0, len(_m._hits))

_m._hits.clear(); _m._last_prune = 0.0
_m._hits["1.2.3.4"].append(_t.monotonic())
_m._prune(_t.monotonic())
check("fresh entries kept", len(_m._hits) == 1, len(_m._hits))

check("inference semaphore is 1", _m._inference_slot._value == 1, _m._inference_slot._value)
check("caveat is not empty", len(LEAF_CAVEAT) > 40, LEAF_CAVEAT)

print("\n%d/%d passed" % (sum(results), len(results)))
raise SystemExit(0 if all(results) else 1)
