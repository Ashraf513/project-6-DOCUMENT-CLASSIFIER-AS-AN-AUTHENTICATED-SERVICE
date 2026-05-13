"""
RVL-CDIP class labels.

Ordered so the list index matches the integer class id produced by the
classifier model.  Stored here so that domain validators and the inference
worker share a single source of truth.
"""

CLASSES: list[str] = [
    "letter",                  # 0
    "form",                    # 1
    "email",                   # 2
    "handwritten",             # 3
    "advertisement",           # 4
    "scientific report",       # 5
    "scientific publication",  # 6
    "specification",           # 7
    "file folder",             # 8
    "news article",            # 9
    "budget",                  # 10
    "invoice",                 # 11
    "presentation",            # 12
    "questionnaire",           # 13
    "resume",                  # 14
    "memo",                    # 15
]
