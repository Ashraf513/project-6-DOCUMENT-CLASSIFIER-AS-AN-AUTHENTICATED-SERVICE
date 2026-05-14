"""
ConvNeXt-Tiny document classifier — model loading and inference.

Training happens on Colab; this module only loads and runs the weights.
Weights file: app/classifier/models/classifier.pt  (tracked via git LFS)
Model card:   app/classifier/models/model_card.json (SHA-256, test_top1, backbone)

DEV_SKIP_MODEL_CHECK=1 skips the integrity guard and returns an untrained
model so the pipeline can be exercised end-to-end without weights.
Never set this flag in production.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import pathlib
from typing import Any

MODEL_PATH = pathlib.Path("app/classifier/models/classifier.pt")
CARD_PATH  = pathlib.Path("app/classifier/models/model_card.json")
MIN_TOP1 = 0.60   # minimum acceptable test top-1; commit threshold lives in README too
# ImageNet normalisation — ConvNeXt was pre-trained on ImageNet
_MEAN = [0.485, 0.456, 0.406]
_STD  = [0.229, 0.224, 0.225]


def verify_model_integrity() -> None:
    """Abort startup if weights are missing, SHA-256 mismatches, or accuracy is too low."""
    if os.getenv("DEV_SKIP_MODEL_CHECK") == "1":
        return  # local dev without trained weights — never set in production

    if not MODEL_PATH.exists():
        raise RuntimeError(f"Classifier weights missing: {MODEL_PATH}")
    if not CARD_PATH.exists():
        raise RuntimeError(f"Model card missing: {CARD_PATH}")

    card = json.loads(CARD_PATH.read_text())

    sha = hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()
    if sha != card.get("sha256", ""):
        raise RuntimeError(
            f"SHA-256 mismatch — got {sha[:16]}…, card has {card.get('sha256','<none>')[:16]}…"
        )

    # test_top1 is nested under metrics in the actual card structure
    metrics = card.get("metrics", {})
    # Read threshold from model card if present; fallback to MIN_TOP1 constant
    min_top1 = card.get("min_top1_threshold", MIN_TOP1)
    top1 = metrics.get("test_top1", 0.0)
    if top1 < min_top1:
        raise RuntimeError(
            f"Model top-1 accuracy {top1:.3f} is below the required threshold {min_top1}"
        )


def load_model() -> Any:
    """
    Load the ConvNeXt-Tiny classifier from disk.

    In dev mode (DEV_SKIP_MODEL_CHECK=1) returns the architecture with random
    weights so the pipeline can be tested without trained weights.
    In production raises if the integrity check fails.

    Returns a torch.nn.Module in eval() mode.
    """
    import torch
    from torchvision import models

    from app.classifier.classes import CLASSES

    verify_model_integrity()

    model = models.convnext_tiny(weights=None)
    # Replace the classifier head to match our 16-class RVL-CDIP vocabulary
    in_features = model.classifier[2].in_features
    model.classifier[2] = torch.nn.Linear(in_features, len(CLASSES))

    if os.getenv("DEV_SKIP_MODEL_CHECK") != "1":
        state = torch.load(MODEL_PATH, map_location="cpu", weights_only=True)
        model.load_state_dict(state)

    model.eval()
    return model


def predict(model: Any, image_bytes: bytes) -> tuple[str, float, list[float]]:
    """
    Run inference on raw image bytes (any format PIL can read: TIFF, PNG, JPEG).

    Returns:
        (predicted_label, confidence_float, all_class_probabilities_list)

    The caller is responsible for acquiring the model via load_model() once
    at process startup and reusing it for the lifetime of the worker.
    """
    import torch
    from torchvision import transforms
    from PIL import Image

    from app.classifier.classes import CLASSES

    transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(mean=_MEAN, std=_STD),
    ])

    image  = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    tensor = transform(image).unsqueeze(0)  # (1, 3, 224, 224)

    with torch.no_grad():
        logits = model(tensor)
        probs  = torch.softmax(logits, dim=1)[0]

    idx        = int(probs.argmax())
    confidence = float(probs[idx])
    label      = CLASSES[idx]
    all_scores = probs.tolist()

    return label, confidence, all_scores
