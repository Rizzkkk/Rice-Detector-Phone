"""the response shapes. the flutter app reads these field by field, so changing anything here
breaks the app."""
from typing import Dict, Optional

from pydantic import BaseModel, Field


class Subject(BaseModel):
    # which answer actually fits this photo. a trained router decides, not the app. nothing in
    # what the two models return tells a good answer apart from a confident wrong one.
    kind: str
    # how sure the router is. under 0.70 it says unclear. this is not how accurate the grain or
    # leaf answer is and must never be shown as if it were.
    confidence: float


class Grain(BaseModel):
    assessed: bool
    # false when the photo looks like a leaf. the grade below is still filled in because the
    # model always returns one, but it means nothing and must not be shown as a result.
    applicable: bool
    grade: Optional[str] = None
    confidence: Optional[float] = None
    # all the classes and not just the winner, so the app can show a close call instead of
    # hiding it. chalky and whole are the two that actually get mixed up.
    probabilities: Dict[str, float] = Field(default_factory=dict)
    low_confidence: bool = False


class Leaf(BaseModel):
    assessed: bool
    applicable: bool
    disease: Optional[str] = None
    confidence: Optional[float] = None
    probabilities: Dict[str, float] = Field(default_factory=dict)
    low_confidence: bool = False
    # always filled in when assessed, never depending on confidence. on a source the model has
    # not trained on it scores 0.44 to 0.60, and a photo from a mill is a new source, so every
    # leaf answer is provisional no matter how sure it looks.
    caveat: Optional[str] = None


class ImageMeta(BaseModel):
    width: int
    height: int


class AnalyzeResponse(BaseModel):
    subject: Subject
    grain: Grain
    leaf: Leaf
    report: str
    # size of the image the models actually saw, after shrinking
    image: ImageMeta


class HealthResponse(BaseModel):
    # anyone can call this, so no versions, paths or config in here
    status: str
    models_loaded: bool


class ErrorResponse(BaseModel):
    error: str
