"""
Scratch timing script — breaks the per-request inference pipeline into its
three real stages (GroundingDINO detection, SAM segmentation, FashionCLIP
embedding) to see where latency actually goes.

Run from the Capstone-Workspace project root as a module (same reason
backend/main.py has to be run this way — see the earlier import-path fix):

    python -m backend.scratch_pad
"""
import os
import time
from pathlib import Path

import torch
from PIL import Image as PILImage
from dotenv import load_dotenv

from Data_Manipulation_Pipeline import annotate, embed_transformers
from groundingdino.util.inference import load_image, predict

load_dotenv(Path(__file__).with_name(".env"))

GDINO_CONFIG = os.getenv("GDINO_CONFIG")
GDINO_CKPT = os.getenv("GDINO_CKPT")
SAM_CKPT = os.getenv("SAM_CKPT")
SAM_MODEL = os.getenv("SAM_MODEL")
DEVICE = os.getenv("DEVICE", "cpu")

TEXT_PROMPT = "shirt . jacket . pants"
BOX_THRESH = 0.3
TEXT_THRESH = 0.25

TEST_IMAGES = [
    r"C:\workSpace\schoolFiles\Capstone\test_image.jpg",
    r"C:\workSpace\schoolFiles\Capstone\test_image_pants.jpg",
]


def run_once(image_path, gdino, sam_predictor):
    print(f"\n=== {image_path} ===")

    t0 = time.perf_counter()
    image_source, image_tensor = load_image(image_path)
    t1 = time.perf_counter()
    print(f"  load_image:         {t1 - t0:.3f}s")

    with torch.no_grad():
        boxes, logits, phrases = predict(
            model=gdino, image=image_tensor, caption=TEXT_PROMPT,
            box_threshold=BOX_THRESH, text_threshold=TEXT_THRESH, device=DEVICE,
        )
    t2 = time.perf_counter()
    print(f"  GroundingDINO:      {t2 - t1:.3f}s  ({len(boxes)} box(es))")

    if boxes.numel() == 0:
        print("  No detections — stopping here.")
        return

    H, W, _ = image_source.shape
    boxes_xyxy = annotate.boxes_cxcywh_to_xyxy(boxes, H, W)

    sam_predictor.set_image(image_source)
    t3 = time.perf_counter()
    print(f"  SAM.set_image:      {t3 - t2:.3f}s")

    transformed_boxes = sam_predictor.transform.apply_boxes_torch(
        torch.as_tensor(boxes_xyxy, dtype=torch.float32, device=DEVICE),
        image_source.shape[:2],
    )
    masks, _, _ = sam_predictor.predict_torch(
        point_coords=None, point_labels=None, boxes=transformed_boxes, multimask_output=False,
    )
    t4 = time.perf_counter()
    print(f"  SAM.predict_torch:  {t4 - t3:.3f}s")
    sam_total = t4 - t2

    masks = masks.squeeze(1).cpu().numpy()
    crop = annotate.crop_and_fill(image_source=image_source, mask=masks[0], box_xyxy=boxes_xyxy[0])
    t5 = time.perf_counter()
    print(f"  crop_and_fill:      {t5 - t4:.3f}s")

    embeddings = embed_transformers.encode_image_objects([PILImage.fromarray(crop)])
    t6 = time.perf_counter()
    print(f"  FashionCLIP embed:  {t6 - t5:.3f}s")

    total = t6 - t0
    print("  ----")
    print(f"  TOTAL:              {total:.3f}s")
    print(f"  GroundingDINO share: {(t2 - t1) / total * 100:5.1f}%")
    print(f"  SAM share:           {sam_total / total * 100:5.1f}%")
    print(f"  Embedding share:     {(t6 - t5) / total * 100:5.1f}%")


def main():
    t0 = time.perf_counter()
    gdino = annotate.load_gdino(GDINO_CONFIG, GDINO_CKPT, DEVICE)
    sam_predictor = annotate.load_sam(SAM_CKPT, SAM_MODEL, DEVICE)
    print(f"Model loading (one-time, not part of per-request latency): {time.perf_counter() - t0:.3f}s")

    for path in TEST_IMAGES:
        if not os.path.exists(path):
            print(f"Skipping missing test image: {path}")
            continue
        run_once(path, gdino, sam_predictor)


if __name__ == "__main__":
    main()
