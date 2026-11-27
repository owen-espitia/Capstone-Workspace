"""
Fast garment detector (YOLO11) that runs before GroundingDINO.

GroundingDINO costs 3.5-5.8 s per request on CPU; this model costs ~0.1 s. It is trained on GroundingDINO's own
boxes (plus synthetic flat-lays), so it returns the same four classes, which map back to the raw phrases the catalog
and the API category filter use.

detect() returns the usable detections, best first, or an empty list plus the reason the caller should fall back
to GroundingDINO:
    no_detection     the model found nothing at all
    low_confidence   nothing at or above MIN_CONF (default 0.35)
    full_image_box   every confident box covers more than MAX_BOX_FRAC (default 85%) of the image. On photos it
                     does not understand the model tends to draw one box around the whole frame, with middling
                     confidence, so size is checked as well as score.

Thresholds can be changed with the YOLO_MIN_CONF and YOLO_MAX_BOX_FRAC environment variables.
Note: ultralytics is AGPL-3.0 licensed.
"""
import os
import threading

import numpy as np

MIN_CONF = float(os.getenv("YOLO_MIN_CONF", "0.35"))
MAX_BOX_FRAC = float(os.getenv("YOLO_MAX_BOX_FRAC", "0.85"))
IMGSZ = 640

# detector class -> raw GroundingDINO phrase used by the catalog (images.category) and /predict's category filter
CLASS_TO_CATEGORY = {"top": "shirt", "top_or_jacket": "shirt jacket", "jacket": "jacket", "pants": "pants"}

_lock = threading.Lock()  # one predict at a time; FastAPI runs the endpoint in a thread pool


def load_detector(ckpt_path: str, device: str):
    from ultralytics import YOLO  # imported lazily so the API still starts without ultralytics when YOLO is unused

    model = YOLO(ckpt_path)
    unknown = set(model.names.values()) - set(CLASS_TO_CATEGORY)
    if unknown:
        raise ValueError(f"{ckpt_path} has classes the catalog does not know: {sorted(unknown)}")
    model.predict(np.zeros((IMGSZ, IMGSZ, 3), np.uint8), device=device, imgsz=IMGSZ, verbose=False)  # warm-up
    return model


def detect(model, image_rgb: np.ndarray, device: str, min_conf: float = MIN_CONF, max_box_frac: float = MAX_BOX_FRAC):
    """Returns (detections, fallback_reason). Each detection is {category, score, bbox (xyxy pixels), label}."""
    H, W = image_rgb.shape[:2]
    with _lock:
        # ultralytics treats numpy input as BGR; conf is kept low here so the reason for falling back is known
        res = model.predict(np.ascontiguousarray(image_rgb[..., ::-1]), device=device, imgsz=IMGSZ, conf=0.05, verbose=False)[0]
    dets = [
        {"label": model.names[int(c)], "category": CLASS_TO_CATEGORY[model.names[int(c)]], "score": float(s), "bbox": b.tolist()}
        for b, s, c in zip(res.boxes.xyxy.cpu().numpy(), res.boxes.conf.cpu().numpy(), res.boxes.cls.cpu().numpy())
    ]
    if not dets:
        return [], "no_detection"
    confident = [d for d in dets if d["score"] >= min_conf]
    if not confident:
        return [], "low_confidence"
    usable = [d for d in confident if (d["bbox"][2] - d["bbox"][0]) * (d["bbox"][3] - d["bbox"][1]) <= max_box_frac * W * H]
    if not usable:
        return [], "full_image_box"
    return sorted(usable, key=lambda d: -d["score"]), None
