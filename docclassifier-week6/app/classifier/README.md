# Phase 1: Classifier — Training the AI Model

## What Is This Phase?

This phase is about **teaching the AI** to recognize document types. You do not write server code here — you train a neural network on Google Colab (a free cloud GPU environment), then save the trained model file and bring it back to this repo.

The local Docker stack **never trains** anything. It only loads the already-trained weights and runs them.

---

## Key Concept: What Is a Classifier?

A classifier is a neural network that takes an image as input and outputs a probability for each possible class.

```
Input: grayscale TIFF image (document scan)
         |
         v
   [ConvNeXt neural network]
         |
         v
Output: [letter: 0.02, form: 0.01, ..., invoice: 0.87, ..., memo: 0.01]
                                             ^
                                    highest = predicted class
```

The number next to each class (0–1.0) is the **confidence score**. A score of 0.87 means the model is 87% sure it is an invoice.

---

## The Dataset: RVL-CDIP

- **320,000** training images
- **40,000** validation images
- **40,000** test images
- 16 document layout classes
- Grayscale TIFF files at scanner resolution
- Source: [adamharley.com/rvl-cdip/](http://adamharley.com/rvl-cdip/) — academic/research license only

**The full dataset is ~37 GB. Never download it locally. Always use Google Colab.**

---

## The Neural Network: ConvNeXt

We use **ConvNeXt Tiny** or **ConvNeXt Small** from the `torchvision` library. These are modern convolutional neural networks pre-trained on ImageNet (millions of natural photos).

**Fine-tuning** means:
1. Start with pre-trained ImageNet weights (the network already understands shapes, edges, textures).
2. Replace the final classification layer (was 1000 ImageNet classes → now 16 document classes).
3. Train on RVL-CDIP so the network adapts to document layouts.

This is much faster than training from scratch.

---

## Training Steps (Run on Google Colab)

```
Step 1: Mount Google Drive, download RVL-CDIP dataset
Step 2: Load ConvNeXt Tiny with pretrained=True
Step 3: Replace the head (final layer) for 16 classes
Step 4: Freeze the backbone, train only the head (linear probe phase)
Step 5: Unfreeze some layers, continue training at a lower learning rate
Step 6: Evaluate on the full 40k test split
Step 7: Pick 50 golden test images (diverse, spanning all classes)
Step 8: Save weights as classifier.pt
Step 9: Generate model_card.json with metrics and SHA-256 hash
```

---

## Files in This Directory

```
app/classifier/
├── README.md           ← you are here
├── model.py            ← loads the trained model for inference
├── overlay.py          ← draws the prediction label on the document image
├── models/
│   ├── classifier.pt   ← the trained neural network weights (~110 MB, Git LFS)
│   └── model_card.json ← metadata: accuracy, hash, environment
└── eval/
    ├── golden.py           ← runs the 50-image golden set test
    ├── golden_expected.json ← expected labels + confidences for those 50 images
    └── golden_images/      ← the 50 TIFF test images
```

---

## model_card.json — What Goes In It

```json
{
  "backbone": "convnext_tiny",
  "weights_enum": "ConvNeXt_Tiny_Weights.IMAGENET1K_V1",
  "freeze_policy": "partial_unfreeze",
  "sha256": "abc123...",
  "test_top1": 0.921,
  "test_top5": 0.987,
  "per_class_accuracy": {
    "letter": 0.94,
    "invoice": 0.93,
    ...
  },
  "environment": {
    "python": "3.11",
    "torch": "2.4.0",
    "torchvision": "0.19.0",
    "colab_gpu": "T4"
  }
}
```

---

## model.py — What It Does

The `model.py` file is used **at inference time** (inside the Docker worker). It:

1. Reads `model_card.json` to get the backbone name and SHA-256.
2. Loads `classifier.pt` from disk.
3. Verifies the SHA-256 hash matches the model card. **If it doesn't match, the worker refuses to start.** This prevents accidentally running the wrong model.
4. Sets the model to `eval()` mode (disables dropout, batch norm uses running stats).
5. Exposes a `predict(image) -> (class_name, confidence)` function.

---

## overlay.py — What It Does

After inference, `overlay.py` takes the original TIFF image and draws the prediction result on top as a PNG. This annotated image is saved back to MinIO so reviewers can visually confirm the classification.

Example overlay: a document image with "INVOICE — 87% confidence" written in the corner.

---

## The Golden Set Test (`eval/golden.py`)

This is a **regression test** that runs in CI on every push.

- It loads the 50 golden TIFF images.
- Runs them through the classifier.
- Compares results against `golden_expected.json`.
- **Pass condition**: every label matches exactly, and every confidence score is within `1e-6` of the expected value.
- **If it fails, CI blocks the merge.** This catches any accidental model changes.

---

## Why SHA-256 Verification?

The SHA-256 hash is a fingerprint of the model file. If someone accidentally overwrites `classifier.pt` with a different model (or a corrupted download), the hash won't match and the system refuses to start. This is a safety net.

---

## What You Need to Know for the Presentation

- Why fine-tuning instead of training from scratch? (faster, less data needed, better accuracy)
- What does "freeze the backbone" mean? (don't update those weights during training)
- What is top-1 vs top-5 accuracy? (top-1 = correct class is #1 prediction; top-5 = correct class is in top 5)
- Why do we verify SHA-256 at startup? (integrity check, prevents wrong model)
- Why 50 golden images specifically? (representative sample, deterministic regression test)
