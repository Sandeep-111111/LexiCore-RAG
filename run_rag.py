import requests
from qdrant_client import QdrantClient, models

# 1. Connect to Qdrant Vector Store
qdrant = QdrantClient(host="localhost", port=6333)
collection_name = "defense_docs"

# Re-create collection for a clean slate
if qdrant.collection_exists(collection_name):
    qdrant.delete_collection(collection_name)

qdrant.create_collection(
    collection_name=collection_name,
    vectors_config=models.VectorParams(size=4, distance=models.Distance.COSINE),
)

# 2. Insert dummy embedded document chunk
qdrant.upsert(
    collection_name=collection_name,
    points=[
        models.PointStruct(
            id=1,
            vector=[0.1, 0.2, 0.3, 0.4],
            payload={"text": "LexiCore protocol requires air-gapped storage on Z drive."}
        )
    ]
)

# 3. Retrieve context chunk from Qdrant using updated API
search_result = qdrant.query_points(
    collection_name=collection_name,
    query=[0.1, 0.2, 0.3, 0.4],
    limit=1
)
retrieved_context = search_result.points[0].payload["text"]
print(f"\n[RETRIEVED CONTEXT FROM QDRANT]: {retrieved_context}\n")

# 4. Pass Context + Prompt to Local Ollama Llama 3.2 Model
prompt = f"Context: {retrieved_context}\n\nQuestion: Where does LexiCore require storage?\nAnswer concisely:"

response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "llama3.2:1b",
        "prompt": prompt,
        "stream": False
    }
)

print(f"[LLM GENERATED RESPONSE]: {response.json()['response'].strip()}")