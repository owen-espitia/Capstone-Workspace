import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

from Data_Manipulation_Pipeline import annotate, input_to_vec, student_segmenter
from backend import dal, storage
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
STUDENT_CKPT = os.getenv("STUDENT_CKPT")
gdino = annotate.load_gdino(GDIO_CONFIG, GDIO_CKPT, DEVICE)
# Segmenter: the student model when STUDENT_CKPT points at a checkpoint, otherwise SAM
student = None
sam_predictor = None
if STUDENT_CKPT and os.path.exists(STUDENT_CKPT):
    student = student_segmenter.load_student(STUDENT_CKPT, DEVICE)
    print(f"Segmenter: student model ({STUDENT_CKPT})")
else:
    if STUDENT_CKPT:
        print(f"WARNING: STUDENT_CKPT={STUDENT_CKPT} not found, falling back to SAM")
    sam_predictor = annotate.load_sam(SAM_CKPT, SAM_MODEL, DEVICE)
    print("Segmenter: SAM")

_COOKIE_OPTS: dict[str, Any] = {
    "httponly": True,
    "samesite": "lax",
    "path": "/",
}


def _log_timings(timings: dict[str, float]) -> str:
    """Print one line of per-stage times (ms) for a /predict request; returns it as a Server-Timing header value."""
    engine = "student" if student is not None else "sam"
    print(f"[predict:{engine}] " + " | ".join(f"{k} {v * 1000:.0f}ms" for k, v in timings.items()), flush=True)
    return ", ".join(f"{k};dur={v * 1000:.1f}" for k, v in timings.items())


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
    t_request = time.perf_counter()
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

    timings: dict[str, float] = {"validate": time.perf_counter() - t_request}
    suffix = Path(image.filename).suffix.lower()
    upload_bytes: bytes | None = None
    with tempfile.TemporaryDirectory(prefix="capstone-predict-") as temp_dir:
        image_path = Path(temp_dir) / f"upload{suffix}"
        with image_path.open("wb") as destination:
            shutil.copyfileobj(image.file, destination)

        image_result = input_to_vec.img_to_vector(str(image_path), gdino, sam_predictor, student, timings)

        # Keep the upload for logged-in users so it can show up in their history
        if user is not None and "error" not in image_result:
            upload_bytes = image_path.read_bytes()

    if "error" in image_result:
        timings["total"] = time.perf_counter() - t_request
        _log_timings(timings)
        raise HTTPException(status_code=422, detail=image_result["error"])

    t_search = time.perf_counter()
    matches = dal.search_catalog(
        image_result["embedding"],
        limit=limit,
        category=image_result["category"],
    )
    timings["db_search"] = time.perf_counter() - t_search
    timings["total"] = time.perf_counter() - t_request
    response.headers["Server-Timing"] = _log_timings(timings)

    # Logged-in users: store the upload + results so /history never re-runs inference
    if upload_bytes is not None and matches:
        saved_name = f"{uuid.uuid4().hex}{suffix}"
        uploaded = False
        try:
            storage.put_user_image(saved_name, upload_bytes, image.content_type)
            uploaded = True
            dal.save_inference(int(user["sub"]), saved_name, matches)
        except Exception as error:  # never fail the prediction because history couldn't be saved
            print(f"WARNING: could not save inference history: {error}", flush=True)
            if uploaded:
                storage.delete_user_image(saved_name)

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


#History: a logged-in user's past uploads and their stored top matches
@app.get("/history")
def history(
    request: Request,
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    user = _get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    items = dal.get_user_history(int(user["sub"]), limit=limit + 1, offset=offset)
    has_more = len(items) > limit
    return {
        "items": [
            {
                "inference_id": item["inference_id"],
                "created_at": item["created_at"].isoformat(),
                "image_url": f"/api/history/image/{item['user_image_url']}",
                "matches": [
                    {
                        "image_id": m["image_id"],
                        "image_url": m["image_url"],
                        "category": m["category"],
                        "similarity": m["similarity"],
                    }
                    for m in item["matches"]
                ],
            }
            for item in items[:limit]
        ],
        "has_more": has_more,
    }


@app.delete("/history/{inference_id}")
def delete_history_item(inference_id: int, request: Request):
    """Remove one history entry and its uploaded photo (owner only)."""
    user = _get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    filenames = dal.delete_inference(int(user["sub"]), inference_id)
    if filenames is None:
        raise HTTPException(status_code=404, detail="History item not found")
    for filename in filenames:
        storage.delete_user_image(filename)
    return {"deleted": inference_id}


@app.get("/history/image/{filename}")
def history_image(filename: str, request: Request):
    """Serve a user's own uploaded photo (only to its owner)."""
    user = _get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # filename is a bare uuid name we generated; reject anything path-like
    if filename != Path(filename).name or not dal.user_owns_image(int(user["sub"]), filename):
        raise HTTPException(status_code=404, detail="Image not found")
    stored = storage.get_user_image(filename)
    if stored is None:
        raise HTTPException(status_code=404, detail="Image not found")
    body, content_type = stored
    return StreamingResponse(
        body.iter_chunks(64 * 1024),
        media_type=content_type or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=86400"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
