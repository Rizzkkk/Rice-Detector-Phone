"""the api. two endpoints, GET /health and POST /analyze, which takes one image field.

one photo goes in, both models run on it, and a router says which of the two answers fits."""
import asyncio
import hmac
import io
import os
import tempfile
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Deque, Dict, Optional

from fastapi import FastAPI, Request
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from PIL import Image, ImageOps

from . import config, inference, subject
from .schemas import AnalyzeResponse, HealthResponse

RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_WINDOW_S = 60


@asynccontextmanager
async def lifespan(app: FastAPI):
    inference.load_models()
    yield


app = FastAPI(title="Rice Detector API", lifespan=lifespan, docs_url=None, redoc_url=None)


# --- errors ---
# same shape every time, {"error": "..."}. never a traceback, a path or a version.

def _err(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message})


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


@app.exception_handler(ApiError)
async def _api_error(request: Request, exc: ApiError):
    return _err(exc.status, exc.message)


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    # /analyze parses its own form so this only catches broken requests. 400 and not 422 so the
    # app only has one error shape to deal with.
    return _err(400, "invalid request")


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    # without this starlette's own 404s come back as {"detail": ...} and break the shape
    detail = exc.detail if isinstance(exc.detail, str) else "request rejected"
    return _err(exc.status_code, detail)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    return _err(500, "internal error")


# --- rate limiting ---
# public endpoint and every request burns real cpu. keeping the counts in memory only works
# because uvicorn runs as one long lived process under systemd.

_hits: Dict[str, Deque[float]] = defaultdict(deque)
_last_prune = 0.0

# without this anyio would run 40 inferences at once on 2 cores
_inference_slot = asyncio.Semaphore(config.INFERENCE_CONCURRENCY)


def _prune(now: float) -> None:
    """without this _hits keeps one entry per ip forever on a process meant to run for weeks.
    anyone rotating ips fills it up without trying."""
    global _last_prune
    if now - _last_prune < RATE_LIMIT_WINDOW_S:
        return
    _last_prune = now
    stale = [ip for ip, q in _hits.items() if not q or now - q[-1] > RATE_LIMIT_WINDOW_S]
    for ip in stale:
        del _hits[ip]


def _client_ip(request: Request) -> str:
    # last entry and not the first. a client can fake the header, caddy adds the real ip at the
    # end
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _rate_limit(request: Request) -> None:
    now = time.monotonic()
    _prune(now)
    q = _hits[_client_ip(request)]
    while q and now - q[0] > RATE_LIMIT_WINDOW_S:
        q.popleft()
    if len(q) >= RATE_LIMIT_REQUESTS:
        raise ApiError(429, "too many requests, slow down")
    q.append(now)


# --- api key ---

def _check_api_key(request: Request) -> None:
    """no key set means no check. compare_digest and not == because == stops at the first wrong
    byte, and the time that takes gives the key away one character at a time."""
    if not config.API_KEY:
        return
    supplied = request.headers.get(config.API_KEY_HEADER, "")
    if not hmac.compare_digest(supplied, config.API_KEY):
        raise ApiError(401, "invalid or missing api key")


# --- images ---

async def _read_capped(upload: UploadFile, field: str) -> bytes:
    """a backstop, nothing more. starlette 0.41 has no max_part_size so the upload is already
    buffered by the time this runs. caddy's 12mb cap is the real limit."""
    chunks, total = [], 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > config.MAX_UPLOAD_BYTES:
            raise ApiError(413, f"{field} exceeds the 10 MB limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _decode(data: bytes, field: str) -> Image.Image:
    try:
        im = Image.open(io.BytesIO(data))
        fmt = im.format
        im.load()  # forces a real decode so a cut off or fake file fails right here
    except Exception:
        raise ApiError(400, f"{field} could not be read as an image")

    if fmt not in config.ALLOWED_FORMATS:
        raise ApiError(415, "only JPEG and PNG images are accepted")

    # apply exif rotation before the models see it. a sideways grain is a different shape to
    # the model, and that looks like a bad prediction instead of a bad upload.
    im = ImageOps.exif_transpose(im)
    return im.convert("RGB")


def _downscale(im: Image.Image) -> Image.Image:
    long_edge = max(im.size)
    if long_edge <= config.MAX_LONG_EDGE:
        return im
    scale = config.MAX_LONG_EDGE / long_edge
    return im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)


def _run_inference(path: str):
    """blocking c code. it has to stay behind run_in_threadpool or it freezes the event loop for
    everyone else.

    all three share one semaphore slot instead of three, so a waiting request only queues once.
    both models run even though only one answer applies, because the screen shows the other one
    greyed out and an unclear photo needs both anyway."""
    kind, confidence = inference.predict_subject(path)
    return kind, confidence, inference.predict_grain(path), inference.predict_leaf(path)


# --- endpoints ---

@app.get("/health", response_model=HealthResponse)
async def health():
    loaded = inference.models_loaded()
    body = {"status": "ok" if loaded else "unavailable", "models_loaded": loaded}
    return JSONResponse(status_code=200 if loaded else 503, content=body)


def _form_file(form, field: str) -> Optional[UploadFile]:
    """an empty part comes through as a str, so treat it as missing. the contract says leave the
    field out but being loose about it costs nothing."""
    value = form.get(field)
    if isinstance(value, UploadFile) and value.filename:
        return value
    return None


def _section(result, applicable: bool, caveat: Optional[str] = None) -> dict:
    """one model's answer, ready to send. an answer that does not apply still goes back in full
    so the screen can show it greyed out, but applicable is what decides whether it is allowed to
    be shown as a result."""
    if result is None:
        body = {"assessed": False, "applicable": applicable, "confidence": None,
                "probabilities": {}, "low_confidence": False}
    else:
        label, confidence, probabilities = result
        body = {
            "assessed": True,
            "applicable": applicable,
            "confidence": round(confidence, 4),
            "probabilities": {k: round(v, 4) for k, v in probabilities.items()},
            "low_confidence": inference.is_low_confidence(confidence),
        }
    if caveat is not None:
        body["caveat"] = caveat if result is not None else None
    return body


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: Request):
    # the form is parsed by hand. declaring the image as an optional file made fastapi turn a
    # real upload into a str, and doing it here gives the exact error messages the contract wants.
    _rate_limit(request)
    _check_api_key(request)

    if not inference.models_loaded():
        raise ApiError(503, "service unavailable")

    form = await request.form(
        max_files=config.MAX_FORM_FILES, max_fields=config.MAX_FORM_FIELDS
    )

    upload = _form_file(form, "image")
    if upload is None:
        raise ApiError(400, "image is required")

    im = _downscale(_decode(await _read_capped(upload, "image"), "image"))

    if config.MOCK:
        # colour stand in so the app still sees real routing with no torch installed
        kind, subject_confidence = subject.classify(im)
        grain, leaf = inference.mock_analyze(with_grain=True, with_leaf=True)
    else:
        tmp = []
        try:
            async with _inference_slot:
                kind, subject_confidence, grain, leaf = await run_in_threadpool(
                    _run_inference, _to_temp(im, tmp)
                )
        finally:
            for p in tmp:
                try:
                    os.unlink(p)
                except OSError:
                    pass

    # when it is unclear both apply. the server does not know which, and picking one would put a
    # meaningless number at the top of the screen
    grain_applicable = kind in ("grain", "unclear")
    leaf_applicable = kind in ("leaf", "unclear")

    grain_body = _section(grain, grain_applicable)
    grain_body["grade"] = grain[0] if grain else None

    leaf_body = _section(leaf, leaf_applicable, caveat=inference.LEAF_CAVEAT)
    leaf_body["disease"] = leaf[0] if leaf else None

    return {
        "subject": {"kind": kind, "confidence": round(subject_confidence, 4)},
        "grain": grain_body,
        "leaf": leaf_body,
        "report": inference.format_report(
            (grain[0], grain[1]) if grain else None,
            (leaf[0], leaf[1]) if leaf else None,
            grain_applicable, leaf_applicable,
        ),
        "image": {"width": im.width, "height": im.height},
    }


def _to_temp(im: Image.Image, registry: list) -> str:
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    im.save(path, "JPEG", quality=95)
    registry.append(path)
    return path
