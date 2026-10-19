import os
import json
import psycopg
from pgvector.psycopg import register_vector
from dotenv import load_dotenv

load_dotenv(override=True)
print(repr(os.environ.get("DATABASE_URL")))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EMBEDDINGS_PATH = os.path.join(BASE_DIR, "multi_modal_images", "embeddings", "embeddings.jsonl")
DB_DSN = os.environ["DATABASE_URL"]
BATCH_SIZE = 500

def load_records(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)

def insert_batch(cur, batch):
    for rec in batch:
        # image_url is a local filesystem path for now (crop_path from annotate.py).
        # Swap this for an R2 key/URL later — no schema change needed, it's just TEXT.
        cur.execute(
            "INSERT INTO images (image_url, category) VALUES (%s, %s) RETURNING image_id",
            (rec["image_path"], rec["category"]),
        )
        image_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO embeddings (image_id, embedding) VALUES (%s, %s)",
            (image_id, rec["embedding"]),
        )

def main():
    conn = psycopg.connect(DB_DSN, autocommit=False)
    register_vector(conn)

    batch, inserted = [], 0
    with conn.cursor() as cur:
        for rec in load_records(EMBEDDINGS_PATH):
            batch.append(rec)
            if len(batch) >= BATCH_SIZE:
                insert_batch(cur, batch)
                conn.commit()
                inserted += len(batch)
                print(f"Inserted {inserted} rows...")
                batch = []
        if batch:
            insert_batch(cur, batch)
            conn.commit()
            inserted += len(batch)

    print(f"Done — {inserted} rows loaded.")
    conn.close()

if __name__ == "__main__":
    main()