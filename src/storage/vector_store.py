import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from src.config import QDRANT_STORAGE_PATH, COLLECTION_NAME, VECTOR_DIMENSION

def to_qdrant_uuid(raw_id: str) -> str:
    """Ensures point ID is a compliant standard UUID format for Qdrant."""
    try:
        return str(uuid.UUID(str(raw_id)))
    except Exception:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(raw_id)))

class LocalVectorStore:
    """
    Embedded local Qdrant Vector Store with HNSW indexing and payload filtering.
    Does not require external Docker daemon; persists directly to disk.
    """
    def __init__(self, storage_path: Path = QDRANT_STORAGE_PATH, collection_name: str = COLLECTION_NAME):
        self.storage_path = storage_path
        self.collection_name = collection_name
        self.client = QdrantClient(path=str(storage_path))
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in collections:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=qmodels.VectorParams(
                    size=VECTOR_DIMENSION,
                    distance=qmodels.Distance.COSINE
                )
            )
            # Payload filtering is natively supported in local Qdrant; indexes are created if supported
            for field in ["region", "event_cluster_id", "scene_type"]:
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name=field,
                        field_schema=qmodels.PayloadSchemaType.KEYWORD
                    )
                except Exception:
                    pass

    def upsert_photo_vector(
        self,
        photo_id: str,
        vector: List[float],
        payload: Dict[str, Any]
    ) -> None:
        """Upserts a single photo vector with its metadata payload."""
        point = qmodels.PointStruct(
            id=to_qdrant_uuid(photo_id),
            vector=vector,
            payload=payload
        )
        self.client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )

    def upsert_batch(
        self,
        points_data: List[Dict[str, Any]]
    ) -> None:
        """Batch upserts points: each item is {'id': str, 'vector': List[float], 'payload': dict}."""
        points = [
            qmodels.PointStruct(
                id=to_qdrant_uuid(item["id"]),
                vector=item["vector"],
                payload=item["payload"]
            )
            for item in points_data
        ]
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

    def search(
        self,
        query_vector: List[float],
        top_k: int = 20,
        region_filter: Optional[str] = None,
        cluster_filter: Optional[str] = None,
        scene_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes vector search with optional payload filters.
        Returns candidate photo IDs, cosine similarity scores, and payloads.
        """
        must_conditions = []
        if region_filter:
            must_conditions.append(
                qmodels.FieldCondition(key="region", match=qmodels.MatchValue(value=region_filter))
            )
        if cluster_filter:
            must_conditions.append(
                qmodels.FieldCondition(key="event_cluster_id", match=qmodels.MatchValue(value=cluster_filter))
            )
        if scene_filter:
            SCENE_SYNONYMS = {
                "beach": ["beach", "pet_beach", "beach_cafe"],
                "beachside": ["beach", "pet_beach", "beach_cafe"],
                "cafe": ["cafe", "beach_cafe", "urban_cafe", "restaurant"],
                "restaurant": ["restaurant", "cafe", "urban_cafe"],
                "mountain": ["mountain_hiking", "mountain_scenery"],
                "mountain_trail": ["mountain_hiking", "mountain_scenery"],
                "street_food": ["street_food"],
                "celebration": ["celebration"]
            }
            mapped_scenes = SCENE_SYNONYMS.get(scene_filter)
            if mapped_scenes:
                must_conditions.append(
                    qmodels.FieldCondition(key="scene_type", match=qmodels.MatchAny(any=mapped_scenes))
                )
            else:
                must_conditions.append(
                    qmodels.FieldCondition(key="scene_type", match=qmodels.MatchValue(value=scene_filter))
                )

        query_filter = qmodels.Filter(must=must_conditions) if must_conditions else None

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k
        )
        results = response.points

        return [
            {
                "photo_id": hit.payload.get("photo_id", str(hit.id)) if hit.payload else str(hit.id),
                "score": float(hit.score),
                "payload": hit.payload
            }
            for hit in results
        ]

    def count(self) -> int:
        """Returns total vector count in the collection."""
        res = self.client.count(collection_name=self.collection_name)
        return res.count
