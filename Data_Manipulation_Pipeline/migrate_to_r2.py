import os
from pathlib import Path

import boto3
import psycopg
from botocore.exceptions import ClientError
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

# image_url values in the DB are relative paths resolved against the ORIGINAL
# NOTE: since I cannot upload images to the repo, this script is ran where I process my images (where annotate.py first ran), not this repo
LOCAL_IMAGES_ROOT = Path(r"C:\workSpace\schoolFiles\Capstone")

R2_ACCOUNT_ID = os.environ["R2_ACCOUNT_ID"]
R2_ACCESS_KEY_ID = os.environ["R2_ACCESS_KEY_ID"]
R2_SECRET_ACCESS_KEY = os.environ["R2_SECRET_ACCESS_KEY"]
R2_BUCKET = os.environ["R2_BUCKET"]
R2_PUBLIC_BASE_URL = os.environ["R2_PUBLIC_BASE_URL"].rstrip("/")
DATABASE_URL = os.environ["DATABASE_URL"]

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    region_name="auto",
)


def object_exists(key: str) -> bool:
    try:
        s3.head_object(Bucket=R2_BUCKET, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


def main():
    conn = psycopg.connect(DATABASE_URL, autocommit=False)
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT image_url FROM images")
        old_paths = [row[0] for row in cur.fetchall()]

    print(f"{len(old_paths)} unique images to migrate")

    uploaded = skipped = missing = errors = 0
    with conn.cursor() as cur:
        for i, old_path in enumerate(old_paths, 1):
            rel = Path(old_path.replace("\\", "/"))
            local_path = LOCAL_IMAGES_ROOT / rel
            # Full relative path as the key — avoids any filename-collision risk
            # from flattening everything into the bucket root.
            key = str(rel).replace("\\", "/")

            if not local_path.exists():
                print(f"MISSING: {local_path}")
                missing += 1
                continue

            try:
                if not object_exists(key):
                    s3.upload_file(str(local_path), R2_BUCKET, key)
                    uploaded += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"ERROR uploading {local_path}: {e}")
                errors += 1
                continue

            new_url = f"{R2_PUBLIC_BASE_URL}/{key}"
            cur.execute("UPDATE images SET image_url = %s WHERE image_url = %s", (new_url, old_path))

            if i % 500 == 0:
                conn.commit()
                print(f"...{i}/{len(old_paths)} processed")

        conn.commit()

    print(f"Done — uploaded: {uploaded}  already_in_bucket: {skipped}  missing_locally: {missing}  errors: {errors}")
    conn.close()


if __name__ == "__main__":
    main()
