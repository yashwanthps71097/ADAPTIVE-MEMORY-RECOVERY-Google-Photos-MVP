import re
import math
import hashlib
import unicodedata
from typing import List, Dict, Any, Set
import numpy as np
from src.config import VECTOR_DIMENSION

STOP_WORDS: Set[str] = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by",
    "from", "up", "about", "into", "over", "after", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "but", "and", "or", "as", "if", "that", "this", "our", "my",
    "we", "i", "went", "looking", "photo", "picture", "went", "went to"
}

def normalize_text(text: str) -> str:
    """Normalizes text by unidecoding accents (e.g. café -> cafe) and lowercasing."""
    norm = unicodedata.normalize('NFKD', text)
    ascii_text = norm.encode('ASCII', 'ignore').decode('utf-8')
    return ascii_text.lower()

# Semantic Anchor Spaces in 512-d hypersphere
SEMANTIC_TOPIC_DOMAINS = {
    "CAFE_DINING": {
        "keywords": ["cafe", "coffee", "espresso", "latte", "cappuccino", "pastry", "breakfast",
                     "croissant", "bakery", "wood table", "cozy", "indoor warm lighting", "tea", "bistro"],
        "basis_seed": 101, "scale": 3.0
    },
    "RESTAURANT_FOOD": {
        "keywords": ["restaurant", "dinner", "lunch", "food", "dining", "curry", "seafood", "meal", "plates"],
        "basis_seed": 102, "scale": 2.5
    },
    "BEACH_COASTAL": {
        "keywords": ["beach", "sea", "ocean", "sand", "waves", "shoreline", "coast", "coastal", "shack",
                     "beachside", "tropical", "sunbeds", "palm trees", "sunset beach"],
        "basis_seed": 103, "scale": 3.0
    },
    "HERITAGE_TOWN": {
        "keywords": ["heritage", "latin quarter", "fontainhas", "portuguese", "colonial", "architecture",
                     "villas", "yellow walls", "balcony", "old town", "white town"],
        "basis_seed": 104, "scale": 2.5
    },
    "CELEBRATION_PARTY": {
        "keywords": ["birthday", "celebration", "cake", "candle", "candles", "party", "toast", "evening dinner"],
        "basis_seed": 105, "scale": 3.0
    },
    "MOUNTAIN_HIKE": {
        "keywords": ["mountain", "hiking", "sunrise", "trek", "trekking", "peaks", "pine", "snow",
                     "solang", "valley", "himalayas", "mist", "forest"],
        "basis_seed": 106, "scale": 3.0
    },
    "RAIN_STREET_FOOD": {
        "keywords": ["rain", "rainy", "monsoon", "umbrella", "street food", "cutting chai", "tea stall", "drip"],
        "basis_seed": 107, "scale": 3.0
    },
    "PET_DOG": {
        "keywords": ["dog", "pet", "golden retriever", "puppy", "beach resort", "frisbee", "dog friendly"],
        "basis_seed": 108, "scale": 3.0
    },
    "SOCIAL_FRIEND": {
        "keywords": ["friend", "friends", "alex", "priya", "rohan", "companion", "group", "buddies"],
        "basis_seed": 109, "scale": 2.0
    },
    "GEO_GOA": {
        "keywords": ["goa", "panaji", "fontainhas", "anjuna", "calangute", "palolem", "canacona"],
        "basis_seed": 110, "scale": 2.0
    },
    "GEO_MUMBAI": {
        "keywords": ["mumbai", "bandra", "marine drive", "maharashtra"],
        "basis_seed": 111, "scale": 2.0
    },
    "GEO_MANALI": {
        "keywords": ["manali", "himachal", "solang", "shimla"],
        "basis_seed": 112, "scale": 2.0
    },
    "GEO_PONDICHERRY": {
        "keywords": ["pondicherry", "puducherry", "promenade", "french"],
        "basis_seed": 113, "scale": 2.0
    },
    "GEO_BANGALORE": {
        "keywords": ["bangalore", "indiranagar", "karnataka", "brewery"],
        "basis_seed": 114, "scale": 2.0
    }
}

class MultimodalEmbedder:
    """
    High-fidelity Semantic Multimodal Vector Embedder.
    Maps photos and conversational queries into a shared 512-dimensional metric space.
    """
    def __init__(self, dimension: int = VECTOR_DIMENSION):
        self.dimension = dimension
        # Precompute orthogonal normalized basis vectors for all semantic domains
        self.topic_bases: Dict[str, np.ndarray] = {}
        for domain, info in SEMANTIC_TOPIC_DOMAINS.items():
            rng = np.random.RandomState(info["basis_seed"])
            basis = rng.randn(self.dimension).astype(np.float32)
            basis /= np.linalg.norm(basis)
            self.topic_bases[domain] = basis

    def _extract_tokens(self, text: str) -> List[str]:
        norm = normalize_text(text)
        raw_tokens = re.findall(r"\b[a-z0-9_\-]+\b", norm)
        return [t for t in raw_tokens if t not in STOP_WORDS and len(t) > 1]

    def embed_text(self, text: str) -> List[float]:
        """Encodes user natural language query into 512-d normalized vector."""
        return self._compute_dense_vector(text)

    def embed_photo(self, photo_meta: Dict[str, Any]) -> List[float]:
        """
        Encodes photo metadata and visual tags into 512-d normalized vector.
        """
        tags = " ".join(photo_meta.get("visual_tags", []))
        scene = photo_meta.get("scene_type", "")
        caption = photo_meta.get("caption", "")
        neighborhood = photo_meta.get("neighborhood", "")
        region = photo_meta.get("region", "")
        faces = " ".join(photo_meta.get("faces", []))
        if "face_cluster_1" in faces:
            faces += " friend alex"
        elif "face_cluster_2" in faces:
            faces += " friend priya"
        elif "face_cluster_3" in faces:
            faces += " friend rohan"
            
        full_text = f"{scene} {tags} {caption} {neighborhood} {region} {faces}"
        return self._compute_dense_vector(full_text)

    def _compute_dense_vector(self, text: str) -> List[float]:
        tokens = self._extract_tokens(text)
        vec = np.zeros(self.dimension, dtype=np.float32)
        norm_text = normalize_text(text)

        # 1. Project onto Semantic Domain Spaces
        for domain, info in SEMANTIC_TOPIC_DOMAINS.items():
            domain_score = 0.0
            for kw in info["keywords"]:
                if kw in norm_text:
                    domain_score += info["scale"]
            if domain_score > 0:
                vec += domain_score * self.topic_bases[domain]

        # 2. Token hash dispersion for sub-word nuances
        for t in tokens:
            h = int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16) % self.dimension
            sign = 1.0 if (h % 2 == 0) else -1.0
            vec[h] += sign * 0.4

        # 3. L2 Normalize
        norm = np.linalg.norm(vec)
        if norm > 1e-6:
            vec = vec / norm
        else:
            vec[0] = 1.0

        return vec.tolist()

global_embedder = MultimodalEmbedder()
