#!/usr/bin/env python3
"""
LexiCore Knowledge Engine - Ingestion & Vector Indexing Pipeline
"""

import os
import logging
import psycopg2
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME_V2', 'lexicore_db'),
    'user': os.getenv('DB_USER', 'lexi_admin'),
    'password': os.getenv('DB_PASSWORD', 'lexi_secure_password_2026')
}

COLLECTION_NAME = os.getenv("COLLECTION_NAME", "lexicore_knowledge")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
BATCH_SIZE = 100

def main():
    logger.info("Connecting to LexiCore PostgreSQL Store...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        logger.info("✅ Connected to PostgreSQL")
    except Exception as e:
        logger.error(f"❌ Connection failed: {e}")
        return

    # 1. Initialize Schema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id SERIAL PRIMARY KEY,
            chunk_id VARCHAR(255) UNIQUE,
            parent_id VARCHAR(255),
            content TEXT NOT NULL,
            compliance_tier VARCHAR(100) DEFAULT 'GENERAL',
            tier_id INT DEFAULT 0,
            quality_score FLOAT DEFAULT 0.5,
            metadata JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()

    # 2. Check Count & Seed Sample Compliance Knowledge Data
    cursor.execute("SELECT COUNT(*) FROM knowledge_chunks")
    total_chunks = cursor.fetchone()[0]

    if total_chunks == 0:
        logger.info("Database empty. Seeding domain knowledge chunks...")
        cursor.execute("""
            INSERT INTO knowledge_chunks (chunk_id, parent_id, content, compliance_tier, tier_id, quality_score)
            VALUES 
            ('p1', NULL, 'LexiCore Governance Protocol: All enterprise financial and security logs must be archived exclusively on secure Z: storage arrays under 256-bit air-gapped encryption.', 'SECURITY_LEVEL_1', 1, 0.98),
            ('c1', 'p1', 'Enterprise logs must be archived exclusively on secure Z: storage arrays.', 'SECURITY_LEVEL_1', 1, 0.98)
            ON CONFLICT DO NOTHING;
        """)
        conn.commit()
        cursor.execute("SELECT COUNT(*) FROM knowledge_chunks")
        total_chunks = cursor.fetchone()[0]

    logger.info(f"Found {total_chunks:,} chunks to process")

    # 3. Vector Database Setup
    logger.info("Initializing Qdrant Vector Engine...")
    qdrant_path = os.path.join(os.path.dirname(__file__), '..', 'qdrant_local_storage')
    client = QdrantClient(path=qdrant_path)

    try:
        client.delete_collection(COLLECTION_NAME)
        logger.info(f"Refreshed vector collection: {COLLECTION_NAME}")
    except Exception:
        pass

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE)
    )

    # 4. Embed & Index
    logger.info("Loading BGE Embedding Transformer...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    cursor.execute("SELECT id, content, compliance_tier, tier_id, quality_score FROM knowledge_chunks ORDER BY id")
    batch = cursor.fetchall()

    if batch:
        texts = [row[1][:512] for row in batch]
        embeddings = model.encode(texts, show_progress_bar=False)

        points = []
        for i, row in enumerate(batch):
            chunk_id, content, tier, tier_id, quality = row
            points.append(PointStruct(
                id=chunk_id,
                vector=embeddings[i].tolist(),
                payload={
                    "compliance_tier": tier or "GENERAL",
                    "tier_id": tier_id or 0,
                    "quality_score": float(quality) if quality else 0.5,
                    "content_preview": content[:200] if content else ""
                }
            ))

        client.upsert(collection_name=COLLECTION_NAME, points=points)

    logger.info(f"✅ LexiCore Indexing Complete. Vectors stored in '{COLLECTION_NAME}'")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()