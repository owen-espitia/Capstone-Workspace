"""Private storage for logged-in users' uploaded photos (Cloudflare R2).

Photos live in their own private bucket (R2_USER_BUCKET) and are never linked
publicly: the API streams them back only to their owner.
"""
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

# A dedicated NON-public bucket (never the public catalog bucket). Required, no default,
# so uploads can't silently land somewhere public if the variable is missing.
R2_BUCKET = os.environ.get("R2_USER_BUCKET")
USER_UPLOAD_PREFIX = "user-uploads/"


@lru_cache(maxsize=1)
def _client() -> Any:
    if not R2_BUCKET:
        raise RuntimeError("R2_USER_BUCKET is not set (name of the private bucket for user uploads)")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def _key(filename: str) -> str:
    return f"{USER_UPLOAD_PREFIX}{filename}"


def put_user_image(filename: str, data: bytes, content_type: str | None) -> None:
    _client().put_object(
        Bucket=R2_BUCKET,
        Key=_key(filename),
        Body=data,
        ContentType=content_type or "application/octet-stream",
    )


def get_user_image(filename: str) -> tuple[Any, str | None] | None:
    """Return (streaming body, content type), or None if the object doesn't exist."""
    try:
        obj = _client().get_object(Bucket=R2_BUCKET, Key=_key(filename))
    except ClientError as error:
        if error.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return None
        raise
    return obj["Body"], obj.get("ContentType")


def delete_user_image(filename: str) -> None:
    try:
        _client().delete_object(Bucket=R2_BUCKET, Key=_key(filename))
    except ClientError as error:
        print(f"WARNING: could not delete {filename} from R2: {error}", flush=True)
