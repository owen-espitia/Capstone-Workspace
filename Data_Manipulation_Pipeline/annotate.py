"""
Mask generation pipeline: GroundingDINO → SAM

Detects garment regions with GroundingDINO, then generates pixel-accurate
binary masks with SAM. Outputs one PNG mask per image, resumable.
Usage:
    From the Capstone Directory, run the following command (While in the venv!):
python Data_Manipulation\annotate.py --gdino_config GroundingDINO\GroundingDINO\groundingdino\config\GroundingDINO_SwinT_OGC.py --gdino_ckpt GroundingDINO\groundingdino_swint_ogc.pth --sam_ckpt SAM\sam_vit_b_01ec64.pth --sam_model vit_b --images_dir Data_Manipulation\multi_modal_images\images --output_dir Data_Manipulation\multi_modal_images\masks --text_prompt "shirt . jacket . pants"
"""

import argparse
import os
import sys
import warnings
import json

warnings.filterwarnings("ignore")

import cv2
import numpy as np
import torch
from PIL import Image
from tqdm import tqdm

from groundingdino.util.inference import load_model, load_image, predict
from segment_anything import sam_model_registry, SamPredictor

MIN_DIM = 10

def crop_and_fill(image_source: np.ndarray, mask: np.ndarray, box_xyxy: np.ndarray, bg_fill: str = "white", pad: int = 8) -> np.ndarray:
    #Crop the image to the size of the box (plus padding), replace pixels outside of the mask with bg_fill color, return RGB crop
    H, W, _ = image_source.shape
    x1, y1, x2, y2 = box_xyxy

    #Add padding to coordinates, compare against image border to make sure we do not go out of bounds
    x1 = max(int(x1) - pad, 0); y1 = max(int(y1) - pad, 0)
    x2 = min(int(x2) + pad, W); y2 = min(int(y2) + pad, H)

    crop = image_source[y1:y2, x1:x2].copy()
    crop_mask = mask[y1:y2, x1:x2].astype(bool)
    if bg_fill == "white":
        fill = np.array([255, 255, 255])
    else:
        fill = np.array([127, 127, 127])
    crop[~crop_mask] = fill
    return crop

def boxes_cxcywh_to_xyxy(boxes: torch.Tensor, H: int, W: int) -> np.ndarray:
    """Convert normalised cx,cy,w,h → absolute x1,y1,x2,y2."""
    cx, cy, w, h = boxes.unbind(-1)
    x1 = (cx - w / 2) * W
    y1 = (cy - h / 2) * H
    x2 = (cx + w / 2) * W
    y2 = (cy + h / 2) * H
    return torch.stack([x1, y1, x2, y2], dim=-1).numpy()


def load_gdino(config_path: str, ckpt_path: str, device: str):
    model = load_model(config_path, ckpt_path, device=device)
    model.eval()
    return model


def load_sam(ckpt_path: str, model_type: str, device: str):
    sam = sam_model_registry[model_type](checkpoint=ckpt_path)
    sam.to(device)
    return SamPredictor(sam)

def load_processed_images(manifest_path: str) -> set[str]:
    processed = set()
    if os.path.exists(manifest_path):
        with open(manifest_path, "r") as f:
            for line in f:
                try:
                    processed.add(json.loads(line)["image"])
                except (json.JSONDecodeError, KeyError):
                    continue  # tolerate a truncated last line from a prior crash
    return processed

#Defaults: 
def generate_instances(gdino_model, sam_predictor: SamPredictor, image_path: str, text_prompt: str, box_thresh: float, text_thresh: float, device: str) -> np.ndarray:
    #Returns a list of dicts: {category, score, bounding_box, mask, crop} per detection
    image_src, image_tensor = load_image(image_path)
    H, W, _ = image_src.shape
    with torch.no_grad():
        boxes, logits, phrases = predict(model= gdino_model, image= image_tensor, caption= text_prompt, text_threshold= text_thresh, device= device, box_threshold= box_thresh)
    if boxes.numel() == 0:
        return []
    boxes_xyxy = boxes_cxcywh_to_xyxy(boxes, H, W)
    sam_predictor.set_image(image_src)
    transformed_boxes = sam_predictor.transform.apply_boxes_torch(torch.as_tensor(boxes_xyxy, dtype= torch.float32, device= device), image_src.shape[:2],)
    masks, _, _ = sam_predictor.predict_torch(point_coords= None, point_labels= None, boxes= transformed_boxes, multimask_output= False)
    masks = masks.squeeze(1).cpu().numpy()
    instances = []
    for i in range(len(boxes_xyxy)):
        crop = crop_and_fill(image_source= image_src, mask= masks[i], box_xyxy= boxes_xyxy[i])
        #Make sure that there are no cropped images that are too short or too thin
        if crop.shape[0] < MIN_DIM or crop.shape[1] < MIN_DIM:
            continue
        instances.append({
            "category": phrases[i],
            "score": float(logits[i]),
            "bbox": boxes_xyxy[i].tolist(),
            "mask": (masks[i].astype(np.uint8) * 255),
            "crop": crop
        })
    return instances


def main():
    parser = argparse.ArgumentParser(description="GroundingDINO + SAM mask pipeline")
    parser.add_argument("--gdino_config", required=True, help="GroundingDINO config .py")
    parser.add_argument("--gdino_ckpt", required=True, help="GroundingDINO checkpoint .pth")
    parser.add_argument("--sam_ckpt", required=True, help="SAM checkpoint .pth")
    parser.add_argument("--sam_model", default="vit_b", choices=["vit_b", "vit_l", "vit_h"])
    parser.add_argument("--images_dir", required=True, help="Directory containing input images")
    parser.add_argument("--output_dir", required=True, help="Directory to write mask PNGs")
    parser.add_argument(
        "--text_prompt",
        default="shirt . pants . jacket",
    )
    parser.add_argument("--box_thresh", type=float, default=0.3)
    parser.add_argument("--text_thresh", type=float, default=0.25)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument(
        "--skip_existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip images already recorded in the manifest (resume mode)",
    )
    parser.add_argument(
        "--bg_fill",
        default="white",
        choices=["white", "gray"],
        help="Background fill color for cropped instances",
    )
    args = parser.parse_args()
    manifest_path = os.path.join(os.path.dirname(args.output_dir), "manifest.jsonl")
    crops_dir = os.path.join(os.path.dirname(args.output_dir), "crops")

    os.makedirs(crops_dir, exist_ok=True)
    os.makedirs(args.output_dir, exist_ok=True)

    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    image_paths = sorted(
        p
        for p in (
            os.path.join(args.images_dir, f) for f in os.listdir(args.images_dir)
        )
        if os.path.splitext(p)[1].lower() in image_exts
    )

    if not image_paths:
        print(f"No images found in {args.images_dir}")
        sys.exit(1)

    print(f"Found {len(image_paths)} images  |  device: {args.device}")
    print(f"Text prompt: {args.text_prompt!r}")

    print("Loading GroundingDINO …")
    gdino = load_gdino(args.gdino_config, args.gdino_ckpt, args.device)

    print(f"Loading SAM ({args.sam_model}) …")
    sam_predictor = load_sam(args.sam_ckpt, args.sam_model, args.device)

    processed = load_processed_images(manifest_path) if args.skip_existing else set()
    skipped = no_det = saved = total_crops = errors = 0

    with open(manifest_path, "a", buffering= 1) as manifest_file:
        for img_path in tqdm(image_paths, unit="img"):
            
            if img_path in processed:
                skipped += 1
                continue

            stem = os.path.splitext(os.path.basename(img_path))[0]
            try:
                instances = generate_instances(gdino_model= gdino, sam_predictor=sam_predictor, image_path= img_path, text_prompt= args.text_prompt,box_thresh= args.box_thresh, text_thresh= args.text_thresh, device= args.device)
                if not instances:
                    manifest_file.write(json.dumps({"image": img_path, "instance": None}) + "\n")
                    no_det += 1
                    continue

                records = []
                for idx, instance in enumerate(instances):
                    crop_path = os.path.join(crops_dir, f"{stem}_{idx}.png")
                    cv2.imwrite(crop_path, cv2.cvtColor(instance["crop"], cv2.COLOR_RGB2BGR))
                    records.append({
                        "image": img_path,
                        "instance": idx,
                        "category": instance["category"],
                        "score": instance["score"],
                        "bounding_box": instance["bbox"],
                        "crop_path": crop_path
                    })
                for rec in records:
                    manifest_file.write(json.dumps(rec) + "\n")
                    total_crops += 1
                saved += 1
            except Exception as exc:
                tqdm.write(f"ERROR {img_path}: {exc}")
                errors += 1
                continue

    # for img_path in tqdm(image_paths, unit="img"):
    #     stem = os.path.splitext(os.path.basename(img_path))[0]
    #     out_path = os.path.join(args.output_dir, stem + "_mask.png")

    #     if args.skip_existing and os.path.exists(out_path):
    #         skipped += 1
    #         continue

    #     try:
    #         mask = generate_mask(
    #             gdino,
    #             sam_predictor,
    #             img_path,
    #             args.text_prompt,
    #             args.box_thresh,
    #             args.text_thresh,
    #             args.device,
    #         )
    #     except Exception as exc:
    #         tqdm.write(f"ERROR {img_path}: {exc}")
    #         errors += 1
    #         continue

    #     if mask is None:
    #         tqdm.write(f"NO_DET {img_path}")
    #         no_det += 1
    #         continue

    #     cv2.imwrite(out_path, mask)
    #     saved += 1

    print(
        f"\nDone — saved: {saved}  | total_crops(total instances): {total_crops}|  skipped: {skipped}  |  "
        f"no_detection: {no_det}  |  errors: {errors}"
    )


if __name__ == "__main__":
    main()
