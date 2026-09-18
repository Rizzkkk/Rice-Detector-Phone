"""settings. most of these change what the api returns, so they are not free to tweak."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = Path(os.getenv("RICE_MODELS_DIR", BASE_DIR / "models"))

GRAIN_MODEL_PATH = MODELS_DIR / "grain_grade.pt"
LEAF_MODEL_PATH = MODELS_DIR / "leaf_disease.pt"
# picks which of the two answers applies. app/subject.py says why this is a model and not the
# colour rule we tried first.
ROUTER_MODEL_PATH = MODELS_DIR / "router.pt"

# same size the notebook trained at. a different size just loses accuracy, it does not error,
# so it is easy to get wrong and never notice.
CLS_IMGSZ = 224

# neither model can say "i don't know", it always picks a class. so this flag is the only way
# a response can hold back. 0.60 is under the average confidence of both models (grain 0.84,
# leaf 0.97), so a sure answer is not touched.
LOW_CONFIDENCE_BELOW = 0.60

# under this the router says "unclear" and the app shows both results. the router scored
# 900/900 on its test split at 0.9999 average, so a real grain or leaf photo is never close to
# this line.
ROUTER_UNCERTAIN_BELOW = 0.70

# a speed bump, not real auth. anyone with the apk can pull this key out of it. it stops
# random scanners and nothing more. leave it unset and the check is skipped, which is what lets
# mock mode and the tests run with no env var.
API_KEY = os.getenv("RICE_API_KEY", "")
API_KEY_HEADER = "x-api-key"

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# both models only see a 224px crop, so anything bigger than this is wasted upload time
MAX_LONG_EDGE = 1280

# fixed responses, no models and no torch import. this is what let the flutter app get built
# before training was done. env var and not a flag because uvicorn owns argv.
MOCK = os.getenv("RICE_MOCK", "").lower() in ("1", "true", "yes")

# without this anyio runs 40 inferences at once on 2 cores, which thrashes instead of queuing.
# keeping the queue short is the rate limiter's job, not this one.
INFERENCE_CONCURRENCY = int(os.getenv("RICE_INFERENCE_CONCURRENCY", "1"))

# stops someone posting thousands of tiny fields just to make us parse them
MAX_FORM_FILES = 2
MAX_FORM_FIELDS = 4

ALLOWED_FORMATS = {"JPEG", "PNG"}
