"""
Draw a predicted-class annotation onto a document image → PNG bytes.

Called by the inference worker after every successful classification.
Input can be any image format PIL supports (TIFF, PNG, JPEG).
Output is always PNG.

Annotation layout:
  ┌─────────────────────────────────────────┐
  │  invoice  92.4%               (banner)  │  40 px dark semi-transparent bar
  ├══════════════════════════════           │   6 px green confidence bar (scaled)
  │                                         │
  │            document body                │
  │                                         │
  └─────────────────────────────────────────┘
"""
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont


# Candidate font paths in the container (installed by fonts-dejavu-core).
# Falls back to PIL's built-in bitmap font if none are found.
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]
_FONT_SIZE   = 20
_BANNER_H    = 40   # px — text area height
_BAR_H       = 6    # px — confidence bar height
_BANNER_FILL = (0, 0, 0, 160)    # RGBA: black, 63% opacity
_BAR_FILL    = (0, 200, 80, 220) # RGBA: green


def _load_font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, _FONT_SIZE)
        except OSError:
            continue
    # PIL built-in — always available, but very small
    return ImageFont.load_default()


def draw_overlay(image_bytes: bytes, label: str, confidence: float) -> bytes:
    """
    Composite a text banner + confidence bar onto the document image.

    Args:
        image_bytes: Raw bytes of the source image (TIFF / PNG / JPEG).
        label:       Predicted class label string, e.g. "invoice".
        confidence:  Softmax probability in [0, 1].

    Returns:
        PNG bytes of the annotated image.
    """
    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h  = image.size

    # Build a transparent overlay the same size as the image
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)

    # Dark banner strip at the top
    draw.rectangle([(0, 0), (w, _BANNER_H)], fill=_BANNER_FILL)

    # Confidence bar directly below the banner (width proportional to confidence)
    bar_w = max(1, int(w * confidence))
    draw  = ImageDraw.Draw(overlay)
    draw.rectangle([(0, _BANNER_H), (bar_w, _BANNER_H + _BAR_H)], fill=_BAR_FILL)

    # Alpha-composite the overlay onto the image
    combined = Image.alpha_composite(image, overlay)

    # Draw text on top of the composited image
    draw2 = ImageDraw.Draw(combined)
    font  = _load_font()
    text  = f"{label}  {confidence:.1%}"
    draw2.text((10, (_BANNER_H - _FONT_SIZE) // 2), text, fill=(255, 255, 255, 255), font=font)

    out = io.BytesIO()
    combined.convert("RGB").save(out, format="PNG")
    return out.getvalue()
