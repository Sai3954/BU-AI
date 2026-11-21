"""Load content into the database and (re)build the search index.

    python -m app.ingest            # load seed knowledge base, embed, rebuild
    python -m app.ingest --embed    # only compute missing embeddings
"""
from __future__ import annotations

import json
import logging
import sys

from sqlalchemy import select

from .config import settings
from .db import Chunk, SessionLocal, init_db
from .llm import get_embedder
from .retrieval import index

log = logging.getLogger(__name__)


def load_seed(force: bool = False) -> int:
    """Insert the hand-checked seed knowledge base plus passages generated from the structured data
    (programs, office directory). Crawled content for the same URL takes priority over seed text."""
    from .features import passages
    data = json.loads(settings.SEED_FILE.read_text(encoding="utf-8")) + passages()
    n = 0
    with SessionLocal() as s:
        if not force and s.scalar(select(Chunk.id).where(Chunk.source == "seed").limit(1)) is not None:
            return 0
        crawled = {u for (u,) in s.execute(select(Chunk.url).where(Chunk.source == "crawl").distinct())}
        for d in data:
            key = f"seed:{d['id']}"
            row = s.scalar(select(Chunk).where(Chunk.key == key))
            if row is None:
                row = Chunk(key=key)
                s.add(row)
            row.url, row.title, row.category = d["url"], d["title"], d["cat"]
            row.audiences = ",".join(d.get("audiences", ["all"]))
            row.text, row.updated_label, row.source = d["text"], d.get("updated", ""), "seed"
            row.embedding = None
            n += 1
        s.commit()
    return n


def embed_missing() -> int:
    emb = get_embedder()
    if emb.name == "none":
        return 0
    with SessionLocal() as s:
        done = 0
        while True:  # in batches, so a large knowledge base never sits in memory twice
            rows = list(s.scalars(select(Chunk).where(Chunk.embedding.is_(None)).limit(512)))
            if not rows:
                return done
            vecs = emb.embed([f"{r.title}\n{r.text}" for r in rows])
            if not vecs:
                return done
            for r, v in zip(rows, vecs):
                r.embedding = json.dumps(v)
            s.commit()
            done += len(rows)
            s.expunge_all()


def rebuild_index() -> int:
    from .redact import refresh_allowlist
    cols = (Chunk.id, Chunk.url, Chunk.title, Chunk.category, Chunk.audiences, Chunk.text, Chunk.updated_label,
            Chunk.embedding, Chunk.source)
    with SessionLocal() as s:
        index.build(s.execute(select(*cols).order_by(Chunk.id).execution_options(yield_per=500)))
    refresh_allowlist(d.text for d in index.docs)  # published contacts that redaction must keep
    return len(index.docs)


def bootstrap() -> dict:
    init_db()
    from .crawl import load_export
    crawled = load_export(str(settings.CRAWLED_FILE))  # pages saved by the crawl job (if any)
    seeded = load_seed()
    try:
        embedded = embed_missing()
    except Exception as e:
        log.warning("Embedding failed, continuing with keyword search only: %s", e)
        embedded = 0
    total = rebuild_index()
    return {"crawled_pages": crawled, "seeded": seeded, "embedded": embedded, "chunks": total,
            "vectors": index.has_vectors}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    if "--embed" not in sys.argv:
        print("seed rows:", load_seed(force=True))
    print("embedded:", embed_missing())
    print("index size:", rebuild_index())
