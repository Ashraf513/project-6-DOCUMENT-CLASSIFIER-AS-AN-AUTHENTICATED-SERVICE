"""
Regenerate golden_expected.json using the current model weights.

Run this script to create a new golden expected output file that exactly
matches the model you have in app/classifier/models/classifier.pt.

Usage (from project root):
    uv run python -m app.classifier.eval.regenerate_golden
"""

import json
from pathlib import Path

from app.classifier.model import load_model, predict

GOLDEN_DIR = Path(__file__).parent / "golden_images"
OUTPUT_JSON = Path(__file__).parent / "golden_expected.json"


def main():
    # Load the model (this also verifies integrity)
    print("Loading model...")
    model = load_model()

    # Get all TIFF files in the golden directory
    image_files = sorted(
        list(GOLDEN_DIR.glob("*.tif")) + list(GOLDEN_DIR.glob("*.tiff"))
    )
    if not image_files:
        print("❌ No TIFF files found in", GOLDEN_DIR)
        return

    result = {}
    for image_path in image_files:
        filename = image_path.name
        print(f"Processing {filename}...")
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        label, confidence, all_scores = predict(model, image_bytes)

        # Build the expected structure (matching your existing JSON format)
        result[filename] = {
            "class": label,
            "confidence": confidence,
            "all_scores": {
                cls: score for cls, score in zip(
                    # We need the class names in the same order as the model's output.
                    # The predict function returns all_scores in the order of CLASSES.
                    [*__import__("app.classifier.classes", fromlist=["CLASSES"]).CLASSES],
                    all_scores,
                )
            },
        }

    # Write the JSON with nice formatting
    with open(OUTPUT_JSON, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n✅ New golden_expected.json written with {len(result)} entries.")


if __name__ == "__main__":
    main()