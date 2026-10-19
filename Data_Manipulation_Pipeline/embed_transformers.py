from transformers import CLIPModel, CLIPProcessor
from PIL import Image
import torch
import json
import os
import numpy as np

MIN_DIM = 10
BATCH_SIZE = 256
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_FILE_PATH = os.path.join(BASE_DIR, "multi_modal_images", "manifest.jsonl")
OUTPUT_DIR = os.path.join(BASE_DIR, "multi_modal_images", "embeddings")
OUTPUT_FILE_PATH = os.path.join(OUTPUT_DIR, "embeddings.jsonl")
os.makedirs(OUTPUT_DIR, exist_ok=True)
records = []

MODEL_NAME = "patrickjohncyh/fashion-clip"
device = "cuda" if torch.cuda.is_available() else "cpu"
model = CLIPModel.from_pretrained(MODEL_NAME).to(device).eval()
processor = CLIPProcessor.from_pretrained(MODEL_NAME)
err = 0

# embed_transformers.py
def encode_image_objects(images):
    if not images:
        return np.empty((0, model.config.projection_dim))
    inputs = processor(images=images, return_tensors="pt", padding=True).to(device)
    with torch.no_grad():
        feats = model.get_image_features(**inputs)
    return feats.cpu().numpy()

def encode_images(paths):

    #Instead of trying to convert every image from an in-line loop, extrude to a full loop and edd error handling
    images = []
    kept_paths = [] #Our oringinal annotate.py produced some degenerate crops, some having a regular width and an extremely small height, these are functionally noise
    #Therfore we store the kept crops in a seperate list so when we zip later, it all falls into place

    for path in paths:
        try:
            img = Image.open(path).convert("RGB")
            #Make sure that the crop is not just a teeny sliver!
            if img.width < MIN_DIM or img.height < MIN_DIM:
                print(f"Degenerate crop, too small. Crop: {path} | Size: {img.size}")
                continue
            images.append(img)
            kept_paths.append(path)
        except Exception as e:
            print(f"Failed to load {path}: {e}")

    if not images:
        return np.empty((0, model.config.projection_dim)), []
    inputs = processor(images=images, return_tensors="pt", padding=True).to(device)
    with torch.no_grad():
        feats = model.get_image_features(**inputs)
    return feats.cpu().numpy(), kept_paths

def encode_text(texts):
    inputs = processor(text=texts, return_tensors="pt", padding=True).to(device)
    with torch.no_grad():
        feats = model.get_text_features(**inputs)
    return feats.cpu().numpy()

def run():
    print("Building record list...")
    with open(MANIFEST_FILE_PATH, "r", encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))
    
    #Make sure that all records include an instance of a mask
    records = [r for r in records if r.get("instance") is not None]
    
    all_embeddings = []
    
    print("Encoding images...")
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
    
        image_paths = [x["crop_path"] for x in batch]
        categories = [x["category"] for x in batch]
        #List of embeddings derived from encoded images
        image_embeddings, image_paths = encode_images(image_paths)
    
        for row, embedding in zip(batch, image_embeddings):
            all_embeddings.append({
                "image_path": row["image"], #I want to include the path to the original image, this will become important when we use R2 image hosting instead of local hosting
                "crop_path": row["crop_path"],
                "category": row["category"],
                "embedding": embedding.tolist()
            })
    
    print("Writing embeddings to output file...")
    with open(OUTPUT_FILE_PATH, "w", encoding='utf-8') as f:
        for record in all_embeddings:
            f.write(json.dumps(record) + "\n")
    
    print("Complete!")