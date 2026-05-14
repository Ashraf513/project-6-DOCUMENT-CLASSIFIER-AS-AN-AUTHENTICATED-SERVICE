# Location: app/classifier/model.py
# Stub for local development – skips model integrity check.
# Replace with real verification when classifier.pt is available.

def verify_model_integrity() -> None:
    """Temporarily a no‑op – will verify SHA‑256 and top‑1 threshold later."""
    # Real implementation:
    #   - check app/classifier/models/classifier.pt exists
    #   - compute SHA-256 and compare with model_card.json
    #   - assert test top-1 >= threshold from README
    pass