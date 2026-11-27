# API image (FastAPI + GroundingDINO + student segmenter + FashionCLIP), CPU only.
# Build context is the repository root:  docker build -f backend/Dockerfile .
# Model weights are NOT baked in; mount them at /models (see docker-compose.yml).

FROM python:3.11-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PIP_NO_CACHE_DIR=1
RUN pip install --upgrade pip setuptools wheel

# CPU wheels keep the image ~2 GB smaller than the default CUDA build; the API runs with DEVICE=cpu
RUN pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
# groundingdino-py's setup.py imports torch, so it must build without isolation
RUN pip install --no-build-isolation groundingdino-py==0.4.0
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt


FROM python:3.11-slim
# libgl1 / libglib2.0-0 are needed by opencv-python
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /opt/venv /opt/venv

RUN useradd --create-home app && mkdir -p /app /models /hf-cache && chown app:app /app /hf-cache
WORKDIR /app
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/hf-cache \
    DEVICE=cpu \
    GDINO_CONFIG=/app/config/GroundingDINO_SwinT_OGC.py \
    GDINO_CKPT=/models/groundingdino_swint_ogc.pth \
    SAM_CKPT=/models/sam_vit_b_01ec64.pth \
    SAM_MODEL=vit_b \
    STUDENT_CKPT=/models/best_segment.pt \
    YOLO_CKPT=/models/best_obj_detect.pt

# The GroundingDINO model config ships inside the groundingdino-py package
RUN mkdir -p /app/config && python -c "import groundingdino, os, shutil; shutil.copy(os.path.join(os.path.dirname(groundingdino.__file__), 'config', 'GroundingDINO_SwinT_OGC.py'), '/app/config/')" \
    && chown -R app:app /app/config

COPY --chown=app:app backend ./backend
COPY --chown=app:app Data_Manipulation_Pipeline ./Data_Manipulation_Pipeline

USER app
EXPOSE 8000
# Models load at import time, so the first start (plus the one-time HF download of FashionCLIP and bert) is slow
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
