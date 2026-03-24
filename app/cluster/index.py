import os
from qdrant_client import QdrantClient
from dotenv import load_dotenv

load_dotenv()
qurl = os.getenv("QdrantClient_url")
qkey = os.getenv("QdrantClient_key")
client = QdrantClient(
    url=qurl, 
    api_key=qkey,
)
collection_name = "knowledge_base"
model_name = "BAAI/bge-small-en-v1.5"

client.create_collection(
    collection_name=collection_name,
    vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE)
)

print(client.get_collections())