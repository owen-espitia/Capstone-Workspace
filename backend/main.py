import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

from Data_Manipulation_Pipeline import annotate, input_to_vec
from backend import dal
from backend.auth import (
    ANON_COOKIE,
    ANON_LIMIT,
    SESSION_COOKIE,
    create_access_token,
    decode_access_token,
    decode_anon_cookie,
    encode_anon_cookie,
)

load_dotenv(Path(__file__).with_name(".env"))
app = FastAPI(title="Backend API Gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GDIO_CONFIG = os.getenv("GDINO_CONFIG")
GDIO_CKPT = os.getenv("GDINO_CKPT")
SAM_CKPT = os.getenv("SAM_CKPT")
SAM_MODEL = os.getenv("SAM_MODEL")
DEVICE = os.getenv("DEVICE")
gdino = annotate.load_gdino(GDIO_CONFIG, GDIO_CKPT, DEVICE)
sam_predictor = annotate.load_sam(SAM_CKPT, SAM_MODEL, DEVICE)

_COOKIE_OPTS: dict[str, Any] = {
    "httponly": True,
    "samesite": "lax",
    "path": "/",
}


def _get_current_user(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return decode_access_token(token)


#Pydantic Models
class RegisterBody(BaseModel):
    user_name: str
    user_email: str
    password: str


class LoginBody(BaseModel):
    user_email: str
    password: str


#User Auth endpoints
@app.post("/auth/register")
def register(body: RegisterBody, response: Response):
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    try:
        user = dal.create_user_pg(body.user_name.strip(), body.user_email.strip().lower(), body.password)
    except dal.UserExistsError:
        raise HTTPException(status_code=409, detail="An account with that email already exists")

    token = create_access_token(user["user_id"], user["user_email"], user["user_name"])
    response.set_cookie(SESSION_COOKIE, token, max_age=7 * 24 * 3600, **_COOKIE_OPTS)
    response.delete_cookie(ANON_COOKIE, path="/")
    return {"user": {"id": user["user_id"], "name": user["user_name"], "email": user["user_email"]}}


@app.post("/auth/login")
def login(body: LoginBody, response: Response):
    user = dal.verify_user_pg(body.user_email.strip().lower(), body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user["user_id"], user["user_email"], user["user_name"])
    response.set_cookie(SESSION_COOKIE, token, max_age=7 * 24 * 3600, **_COOKIE_OPTS)
    response.delete_cookie(ANON_COOKIE, path="/")
    return {"user": {"id": user["user_id"], "name": user["user_name"], "email": user["user_email"]}}


@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"message": "Logged out"}


@app.get("/auth/me")
def me(request: Request):
    user = _get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user": {"id": user["sub"], "name": user.get("name"), "email": user["email"]}}


#Inference!!!
@app.post("/predict")
def predict(
    request: Request,
    response: Response,
    image: UploadFile = File(...),
    limit: int = Query(default=5, ge=1, le=100),
):
    """Find catalog matches for the garment detected in an uploaded image."""
    user = _get_current_user(request)

    # Anonymous rate-limiting
    anon_count: int = 0
    if user is None:
        raw = request.cookies.get(ANON_COOKIE)
        anon_count = decode_anon_cookie(raw) if raw else 0
        if anon_count is None:
            anon_count = 0
        if anon_count >= ANON_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="You've used your free requests. Please create an account to continue.",
            )

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

        image_result = input_to_vec.img_to_vector(str(image_path), gdino, sam_predictor)

    if "error" in image_result:
        raise HTTPException(status_code=422, detail=image_result["error"])

    matches = dal.search_catalog(
        image_result["embedding"],
        limit=limit,
        category=image_result["category"],
    )

    # Increment and persist the anonymous counter after a successful request
    if user is None:
        new_count = anon_count + 1
        response.set_cookie(
            ANON_COOKIE, encode_anon_cookie(new_count),
            max_age=30 * 24 * 3600, **_COOKIE_OPTS,
        )
        requests_remaining = ANON_LIMIT - new_count
    else:
        requests_remaining = None

    return {
        "category": image_result["category"],
        "matches": matches,
        "requests_remaining": requests_remaining,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
