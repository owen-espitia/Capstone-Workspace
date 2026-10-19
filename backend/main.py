#This is going to be the main API file for my Capstone!
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, HTTPException, File, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from PIL import Image, UnidentifiedImageError
from Data_Manipulation_Pipeline import input_to_vec, annotate
from backend import dal

load_dotenv(Path(__file__).with_name(".env"))
app = FastAPI(title="Backend API Gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

#Load heavy models
GDIO_CONFIG = os.getenv("GDINO_CONFIG")
GDIO_CKPT = os.getenv("GDINO_CKPT")
SAM_CKPT = os.getenv("SAM_CKPT")
SAM_MODEL = os.getenv("SAM_MODEL")
DEVICE = os.getenv("DEVICE")
gdino = annotate.load_gdino(GDIO_CONFIG, GDIO_CKPT, DEVICE)
sam_predictor = annotate.load_sam(SAM_CKPT, SAM_MODEL, DEVICE)

# TEST_FILEPATH = "C:/workSpace/schoolFiles/Capstone/test_image_pants.jpg"
# TEST_FILEPATH_2 = "C:/workSpace/schoolFiles/Capstone/test_image.jpg"

# image_test = input_to_vec.img_to_vector(TEST_FILEPATH, gdino, sam_predictor)
# image_test_2 = input_to_vec.img_to_vector(TEST_FILEPATH_2, gdino, sam_predictor)

# print("Testing brown pants image")
# print(dal.search_catalog(image_test["embedding"], category=image_test["category"]))
# print("Testing black shirt image")
# print(dal.search_catalog(image_test_2["embedding"], category=image_test_2["category"]))
@app.post("/predict")
def predict(
    image: UploadFile = File(...),
    limit: int = Query(default=5, ge=1, le=100),
):
    """Find catalog matches for the garment detected in an uploaded image."""
    if not image.filename:
        raise HTTPException(status_code=400, detail="An image file is required")

    if not image.file.read(1):
        raise HTTPException(status_code=400, detail="The uploaded image is empty")
    image.file.seek(0)

    try:
        with Image.open(image.file) as uploaded_image:
            uploaded_image.verify()
    except (UnidentifiedImageError, OSError) as error:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid image") from error
    finally:
        image.file.seek(0)

    suffix = Path(image.filename).suffix.lower()
    with tempfile.TemporaryDirectory(prefix="capstone-predict-") as temp_dir:
        image_path = Path(temp_dir) / f"upload{suffix}"
        with image_path.open("wb") as destination:
            shutil.copyfileobj(image.file, destination)

        image_result = input_to_vec.img_to_vector(
            str(image_path),
            gdino,
            sam_predictor,
        )

    if "error" in image_result:
        raise HTTPException(status_code=422, detail=image_result["error"])

    matches = dal.search_catalog(
        image_result["embedding"],
        limit=limit,
        category=image_result["category"],
    )
    print(matches)
    return {
        "category": image_result["category"],
        "matches": matches,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)