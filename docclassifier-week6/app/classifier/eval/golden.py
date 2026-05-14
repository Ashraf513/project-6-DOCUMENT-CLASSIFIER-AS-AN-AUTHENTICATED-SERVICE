"""
Golden‑set replay test.

This script:
  1. Loads the classifier model (calling verify_model_integrity internally).
  2. Iterates over every TIFF in app/classifier/eval/golden_images/.
  3. Predicts the label and confidence.
  4. Compares the prediction against golden_expected.json.
  5. Exits with code 1 if any mismatch is found.

Mismatch criteria:
  - Predicted label ≠ expected label.
  - Absolute difference in confidence > 1e-6.

Passing this test is required to proceed past CI.
"""

import json
import sys
from pathlib import Path

from app.classifier.model import load_model, predict

GOLDEN_DIR     = Path(__file__).parent / "golden_images"
EXPECTED_JSON  = Path(__file__).parent / "golden_expected.json"


def main():
    # 1. Load expected data
    if not EXPECTED_JSON.exists():
        print(f"❌ Missing {EXPECTED_JSON}")
        sys.exit(1)

    with open(EXPECTED_JSON) as fh:
        expected = json.load(fh)

    # 2. List golden images
    tiff_files = sorted(GOLDEN_DIR.glob("*.tif")) + sorted(GOLDEN_DIR.glob("*.tiff"))
    if not tiff_files:
        print("❌ No golden images found in", GOLDEN_DIR)
        sys.exit(1)

    # 3. Load the model once (this also verifies SHA‑256 and top‑1 threshold)
    try:
        model = load_model()
    except Exception as exc:
        print(f"❌ Model loading failed: {exc}")
        sys.exit(1)

    failures = 0
    total    = len(tiff_files)

    for image_path in tiff_files:
        filename = image_path.name

        # Skip files not listed in expected JSON (allows extra images during dev)
        if filename not in expected:
            print(f"⚠️  Skipping {filename} (not in golden_expected.json)")
            continue

        exp = expected[filename]
        exp_label      = exp["class"]          # ← your JSON uses "class"
        exp_confidence = float(exp["confidence"])

        # Read image bytes and predict
        with open(image_path, "rb") as fh:
            image_bytes = fh.read()

        pred_label, pred_conf, _ = predict(model, image_bytes)

        label_match = (pred_label == exp_label)
        conf_match  = abs(pred_conf - exp_confidence) <= 1e-6

        if not label_match or not conf_match:
            print(
                f"❌ MISMATCH {filename}: "
                f"expected {exp_label} / {exp_confidence:.6f}, "
                f"got {pred_label} / {pred_conf:.6f}"
            )
            failures += 1
        else:
            print(f"✅ {filename}: {pred_label} {pred_conf:.4f}")

    if failures:
        print(f"\n❌ {failures}/{total} golden images failed.")
        sys.exit(1)

    print(f"\n✅ All {total} golden images passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()