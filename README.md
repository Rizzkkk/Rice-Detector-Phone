# Rice Detector

An Android app for a rice mill. You photograph rice and it tells you two things.

The first is the grade of the grain: Whole, Stained, Broken or Chalky. That is what a mill
prices on. The second is the disease on a rice leaf, for the farmers who supply the mill.

The phone runs no model. It takes the picture, shrinks it, uploads it, and shows what comes
back. Everything is decided on the server. That is why the app needs a connection and why
there is no offline mode.

How it works

There are three models, all YOLOv11 classifiers, all trained in Colab.

One grades the grain. One names the leaf disease. The third decides which of those two answers
applies to the photo you took, because the app only asks for one photo and neither of the other
two models can refuse an image it was not built for. A leaf sent to the grain model still comes
back with a confident grade. The router is what stops that wrong answer being shown as a real
one.

Held out test accuracy was 0.8427 for grain, 0.9675 for leaf and 1.0000 for the router. The
leaf number needs care. On photo sets the model had never seen it falls to between 0.44 and
0.60, so treat it as a screening aid and not as a reason to spray a crop.

ARCHITECTURE.md has diagrams of the flow, from the camera through to the answer on screen.

What is in here

backend is a FastAPI service with two endpoints. POST /analyze takes one image and returns
both results. GET /health says whether the models are loaded.

app is the Flutter client, Android only.

notebooks holds the training work. train_mill.ipynb is the current one. The other two are
earlier versions kept for reference and they train the wrong models for a mill.

deploy holds the systemd unit and the Caddy config for a single small VPS.

Running the backend

The models themselves are not in this repo. They are a few megabytes each and they are the
result of several hours of GPU time, so they are kept outside version control.

There is a mock mode that serves fixed responses in the right shape and imports no torch at
all, which is enough to build and test the client.

    cd backend
    python -m venv .venv
    .venv/bin/pip install -r requirements-mock.txt
    RICE_MOCK=1 .venv/bin/python -m uvicorn app.main:app --port 8000

For the real thing, put grain_grade.pt, leaf_disease.pt and router.pt in models, then install
requirements.txt instead. Take torch from the CPU index, not the default one, or pip will pull
about 2.5 GB of CUDA that a small server has no card to use.

    .venv/bin/pip install torch==2.11.0 torchvision==0.26.0 \
        --index-url https://download.pytorch.org/whl/cpu
    .venv/bin/pip install -r requirements.txt

The versions are pinned to the ones the models were trained with. A .pt file stores the module
paths of the classes that built it, so the wrong torch or ultralytics fails on load with an
error about a missing attribute rather than anything that mentions versions.

The models load once when the process starts and stay in memory. Replacing a file on disk does
nothing until you restart the service.

Tests

    cd backend
    .venv/bin/python test_contract.py    # 78 checks, mock mode, no weights needed
    .venv/bin/python smoke_real.py       # 27 checks, needs the real weights

    cd app
    flutter test

test_contract.py pins the shape of every response the client depends on. It runs in mock mode,
so it can tell you the wiring is right but not whether a model is. smoke_real.py is the one
that loads the weights and puts real photographs through them.

What it cannot do

Both result models only know the classes they were trained on and neither can say it does not
recognise something. Anything outside those lists gets sorted into the nearest match.

No recognised disease means none of the four it knows about, not that the plant is healthy.
The healthy class scored zero recall on every photo set the model had not trained on, so the
app is not allowed to report a plant as healthy at all.

The grain model was trained on Peruvian rice photographed at a mill in Lambayeque, and it has
only that one source, so there is no held out source to measure it against.

The variety is probably not the main problem. Those training photos are single grains on a
plain black background, evenly lit. A phone at a working mill sees grains on a tray under
whatever light is in the room. The four classes are defects and not varietal traits, a break is
a break and chalk is chalk, so some of it should carry over. But that is reasoning and not a
measurement, and nobody has taken the measurement yet.

The next step is photographing the mill's own rice on the actual phone and retraining on it.
The classes and the filename do not change, so that is a new weights file and a restart, not a
code change.

Neither model has been checked by an agronomist.
