"""
Student segmentation model (box crop -> garment mask), the fast replacement for SAM in the API.

Self-contained copy of the inference side of Data_Manipulation/student_model.py and student_dataset.py.
Keep PAD and SIZE equal to what the checkpoint was trained with (train_student.py defaults: 256 / 0.10).

generate_instances_student mirrors annotate.generate_instances (same dict keys), so callers can swap
one for the other.
"""
import time

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from groundingdino.util.inference import load_image, predict
from torchvision.models import mobilenet_v3_large

from . import annotate

SIZE = 256
PAD = 0.10
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# mobilenet_v3_large.features indices whose outputs end each resolution (stride 2, 4, 8, 16, 32)
SKIP_IDX = (1, 3, 6, 12, 16)
SKIP_CH = (16, 24, 40, 112, 960)


def _conv_block(cin, cout):
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
        nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
    )


class StudentUNet(nn.Module):
    def __init__(self, decoder_ch=(128, 64, 48, 32)):
        super().__init__()
        self.encoder = mobilenet_v3_large(weights=None).features[: SKIP_IDX[-1] + 1]
        chans = [SKIP_CH[-1], *decoder_ch]
        self.decoders = nn.ModuleList(_conv_block(chans[i] + SKIP_CH[3 - i], chans[i + 1]) for i in range(4))
        self.head = nn.Conv2d(decoder_ch[-1], 1, 1)

    def forward(self, x):
        size = x.shape[-2:]
        skips = []
        for i, layer in enumerate(self.encoder):
            x = layer(x)
            if i in SKIP_IDX:
                skips.append(x)
        x = skips.pop()
        for dec in self.decoders:
            skip = skips.pop()
            x = F.interpolate(x, size=skip.shape[-2:], mode="bilinear", align_corners=False)
            x = dec(torch.cat([x, skip], dim=1))
        x = F.interpolate(x, size=size, mode="bilinear", align_corners=False)
        return self.head(x)


def load_student(ckpt_path: str, device: str) -> StudentUNet:
    model = StudentUNet()
    model.load_state_dict(torch.load(ckpt_path, map_location=device, weights_only=True))
    return model.to(device).eval()


def _crop_matrix(box_xyxy):
    """Affine matrix mapping image coordinates to the SIZE x SIZE crop of the padded box."""
    x1, y1, x2, y2 = box_xyxy
    w, h = x2 - x1, y2 - y1
    x1, y1, x2, y2 = x1 - PAD * w, y1 - PAD * h, x2 + PAD * w, y2 + PAD * h
    sx, sy = SIZE / (x2 - x1), SIZE / (y2 - y1)
    return np.array([[sx, 0, -x1 * sx], [0, sy, -y1 * sy]], dtype=np.float32)


@torch.no_grad()
def student_masks(student: StudentUNet, image_rgb: np.ndarray, boxes_xyxy) -> list[np.ndarray]:
    """One boolean (H, W) mask per box."""
    H, W = image_rgb.shape[:2]
    device = next(student.parameters()).device
    mats, crops = [], []
    for box in boxes_xyxy:
        M = _crop_matrix(box)
        mats.append(M)
        crop = cv2.warpAffine(image_rgb, M, (SIZE, SIZE), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        crops.append(torch.from_numpy(np.ascontiguousarray(((crop.astype(np.float32) / 255.0 - MEAN) / STD).transpose(2, 0, 1))))
    probs = student(torch.stack(crops).to(device)).float().sigmoid()[:, 0].cpu().numpy()
    # M maps image -> crop, so as an inverse map it pastes crop-space probabilities back into the image
    return [
        cv2.warpAffine(p, M, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_CONSTANT, borderValue=0) > 0.5
        for M, p in zip(mats, probs)
    ]


def generate_instances_student(gdino_model, student: StudentUNet, image_path: str, text_prompt: str,
                               box_thresh: float, text_thresh: float, device: str, timings: dict | None = None) -> list[dict]:
    """Same contract as annotate.generate_instances: list of {category, score, bbox, mask, crop}.

    If `timings` is given, seconds spent per stage are stored in it (load_image, detect, segment, crop).
    """
    t0 = time.perf_counter()
    image_src, image_tensor = load_image(image_path)
    H, W, _ = image_src.shape
    t1 = time.perf_counter()
    with torch.no_grad():
        boxes, logits, phrases = predict(model=gdino_model, image=image_tensor, caption=text_prompt,
                                         text_threshold=text_thresh, box_threshold=box_thresh, device=device)
    t2 = time.perf_counter()
    if timings is not None:
        timings.update(load_image=t1 - t0, detect=t2 - t1)
    if boxes.numel() == 0:
        return []
    boxes_xyxy = annotate.boxes_cxcywh_to_xyxy(boxes, H, W)
    masks = student_masks(student, image_src, boxes_xyxy)
    t3 = time.perf_counter()
    if timings is not None:
        timings["segment"] = t3 - t2

    instances = []
    for i, mask in enumerate(masks):
        if not mask.any():  # nothing predicted inside this box; a blank crop would embed as noise
            continue
        crop = annotate.crop_and_fill(image_source=image_src, mask=mask, box_xyxy=boxes_xyxy[i])
        if crop.shape[0] < annotate.MIN_DIM or crop.shape[1] < annotate.MIN_DIM:
            continue
        instances.append({
            "category": phrases[i],
            "score": float(logits[i]),
            "bbox": boxes_xyxy[i].tolist(),
            "mask": mask.astype(np.uint8) * 255,
            "crop": crop,
        })
    if timings is not None:
        timings["crop"] = time.perf_counter() - t3
    return instances
