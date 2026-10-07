import math
import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from src.config import SQLITE_DB_PATH, QDRANT_STORAGE_PATH, COLLECTION_NAME, RAW_PHOTOS_DIR, THUMBNAILS_DIR
from src.database.db import get_connection, get_all_clusters
from src.storage.vector_store import LocalVectorStore
from src.indexing.embedder import global_embedder
from src.engine.schemas import (
    ExtractedMemoryCues, CandidatePhoto, SearchConfidenceMetrics, CueChip
)

logger = logging.getLogger(__name__)

CITY_TO_REGION = {
    "mumbai": "Maharashtra",
    "bandra": "Maharashtra",
    "manali": "Himachal Pradesh",
    "solang": "Himachal Pradesh",
    "bangalore": "Karnataka",
    "bengaluru": "Karnataka",
    "pondicherry": "Puducherry",
    "puducherry": "Puducherry",
    "goa": "Goa",
    "panaji": "Goa",
    "anjuna": "Goa",
    "calangute": "Goa",
    "palolem": "Goa",
    "canacona": "Goa"
}

class HybridRetriever:
    """
    The Connect Engine.
    Executes multi-modal hybrid retrieval combining dense vector similarity with
    spatio-temporal metadata filtering, social face affinity, and event clusters.
    """
    def __init__(
        self,
        vector_store: Optional[LocalVectorStore] = None,
        db_path=SQLITE_DB_PATH
    ):
        self.db_path = db_path
        self.vector_store = vector_store or LocalVectorStore(
            storage_path=QDRANT_STORAGE_PATH,
            collection_name=COLLECTION_NAME
        )
        self._clusters_cache: Dict[str, Dict[str, Any]] = {}
        self._load_clusters_cache()

    def _load_clusters_cache(self) -> None:
        try:
            clusters = get_all_clusters(self.db_path)
            self._clusters_cache = {c["cluster_id"]: c for c in clusters}
        except Exception as e:
            logger.warning(f"Could not load event clusters cache: {e}")

    def search(
        self,
        query: str,
        cues: ExtractedMemoryCues,
        active_chips: Optional[List[CueChip]] = None,
        top_k: int = 20,
        turn_count: int = 1,
        filter_region: Optional[str] = None,
        filter_cluster: Optional[str] = None,
        filter_scene: Optional[str] = None
    ) -> Tuple[List[CandidatePhoto], SearchConfidenceMetrics, bool]:
        """
        Executes hybrid retrieval using dense vectors, metadata filtering, and score fusion.
        """
        # 1. Synthesize rich text for vector embedding
        dense_query_text = self._build_query_text(query, cues, active_chips)
        query_vector = global_embedder.embed_text(dense_query_text)

        # 2. Determine initial hard filters (spatial region and explicit filters)
        extracted_reg = cues.spatial.region if self._is_chip_active(active_chips, "place") else None
        target_reg = filter_region or extracted_reg
        region_filter = None
        if target_reg:
            # Map city to Qdrant's region payload (e.g. Mumbai -> Maharashtra)
            region_filter = CITY_TO_REGION.get(target_reg.lower(), target_reg)

        cluster_filter = filter_cluster or None
        scene_filter = filter_scene or None

        # 3. First search pass with payload filters
        vector_hits = self.vector_store.search(
            query_vector=query_vector,
            top_k=max(top_k * 2, 50),
            region_filter=region_filter,
            cluster_filter=cluster_filter,
            scene_filter=scene_filter
        )

        relaxed = False
        # Soft filter relaxation if hard filter resulted in insufficient candidates
        if len(vector_hits) < 3 and (region_filter or cluster_filter or scene_filter):
            logger.info("Hard metadata filter yielded < 3 candidates; executing relaxed search pass.")
            vector_hits = self.vector_store.search(
                query_vector=query_vector,
                top_k=max(top_k * 2, 50),
                region_filter=None,
                cluster_filter=None,
                scene_filter=None
            )
            relaxed = True

        if not vector_hits:
            return [], SearchConfidenceMetrics(status="WEAK_TIER_1" if turn_count == 1 else "STILL_WEAK_TIER_2"), relaxed

        # 4. Fetch photo metadata from SQLite in batch
        photo_ids = [hit["photo_id"] for hit in vector_hits]
        photos_meta = self._fetch_photos_metadata(photo_ids)

        # Check active query dimensions for dynamic weight normalization
        has_meta_cues = bool(cues.spatial.region or cues.spatial.setting or cues.spatial.neighborhood or region_filter or scene_filter)
        has_social_cues = bool(cues.social.companion_type or cues.social.companion_names)
        has_temporal_cues = bool(cues.temporal.relative_concept or cues.temporal.season or cues.temporal.time_of_day or cluster_filter)

        w_v = 0.50
        w_m = 0.25 if has_meta_cues else 0.0
        w_s = 0.15 if has_social_cues else 0.0
        w_t = 0.10 if has_temporal_cues else 0.0
        total_w = w_v + w_m + w_s + w_t

        # 5. Weighted Score Fusion
        seen_pids = set()
        seen_filenames = set()
        seen_image_hashes = set()
        scored_candidates: List[CandidatePhoto] = []
        for hit in vector_hits:
            pid = hit["photo_id"]
            if pid in seen_pids:
                continue
            meta = photos_meta.get(pid)
            if not meta:
                continue

            fn = meta.get("filename", "")
            if fn and fn in seen_filenames:
                continue

            # Deduplicate by visual file hash so no two candidates share identical images
            img_hash = self._get_image_file_hash(fn)
            if img_hash and img_hash in seen_image_hashes:
                continue

            seen_pids.add(pid)
            if fn:
                seen_filenames.add(fn)
            if img_hash:
                seen_image_hashes.add(img_hash)

            v_score = float(hit["score"])
            m_score, matched_meta = self._compute_metadata_score(meta, cues, target_reg, scene_filter)
            s_score, matched_social = self._compute_social_score(meta, cues)
            t_score, matched_temporal = self._compute_temporal_score(meta, cues, cluster_filter)

            # Normalized weighted fusion across active dimensions
            weighted_sum = (
                w_v * v_score +
                w_m * m_score +
                w_s * s_score +
                w_t * t_score
            )
            final_score = weighted_sum / total_w
            final_score = min(1.0, max(0.0, final_score))

            matched_cues = list(set(matched_meta + matched_social + matched_temporal))

            # Build thumbnail and full photo URLs
            fn = meta.get("filename", "")
            stem = fn.rsplit(".", 1)[0] if "." in fn else fn
            thumb_url = f"/thumbnails/{stem}_thumb.webp?v=match_v5"
            full_url = f"/photos/{fn}?v=match_v5"

            cluster_id = meta.get("event_cluster_id")
            cluster_name = self._clusters_cache.get(cluster_id, {}).get("cluster_name") if cluster_id else None

            city_name = meta.get("city")
            region_name = meta.get("region")
            neighborhood_name = meta.get("neighborhood")
            loc_label = f"{neighborhood_name}, {city_name}" if (neighborhood_name and city_name) else (f"{city_name}, {region_name}" if (city_name and region_name) else (city_name or region_name or cluster_name or "Travel Moment"))

            candidate = CandidatePhoto(
                photo_id=pid,
                filename=fn,
                thumbnail_url=thumb_url,
                full_photo_url=full_url,
                image_url=full_url,
                score=round(final_score, 4),
                vector_score=round(v_score, 4),
                metadata_score=round(m_score, 4),
                social_score=round(s_score, 4),
                temporal_score=round(t_score, 4),
                matched_cues=matched_cues,
                timestamp=meta.get("timestamp", ""),
                city=city_name,
                region=region_name,
                neighborhood=neighborhood_name,
                scene_type=meta.get("scene_type"),
                caption=meta.get("caption"),
                visual_tags=meta.get("visual_tags", []),
                faces=meta.get("faces", []),
                event_cluster_id=cluster_id,
                event_cluster_name=cluster_name,
                location_name=loc_label,
                trip_cluster=cluster_name or region_name,
                camera_model=meta.get("camera_model") or "Dual Camera"
            )
            scored_candidates.append(candidate)

        # Sort candidates descending by fused score
        scored_candidates.sort(key=lambda c: c.score, reverse=True)
        top_candidates = scored_candidates[:top_k]

        # 6. Compute Confidence & Dispersion Metrics
        metrics = self._evaluate_confidence(top_candidates, turn_count)

        return top_candidates, metrics, relaxed

    def _build_query_text(
        self,
        query: str,
        cues: ExtractedMemoryCues,
        active_chips: Optional[List[CueChip]]
    ) -> str:
        """Synthesizes an enriched semantic prompt from query and confirmed facets."""
        parts = [query]
        if cues.visual_concepts:
            parts.extend(cues.visual_concepts)
        if cues.spatial.setting:
            parts.append(cues.spatial.setting)
        if cues.spatial.region:
            parts.append(cues.spatial.region)
        if cues.affective_vibe:
            parts.append(cues.affective_vibe)
        if cues.social.companion_type:
            parts.append(cues.social.companion_type)

        if active_chips:
            for chip in active_chips:
                if chip.status in ["confirmed", "user_selected_tier_1", "user_selected_tier_2"]:
                    parts.append(chip.value)

        return " ".join(parts)

    def _is_chip_active(self, chips: Optional[List[CueChip]], chip_type: str) -> bool:
        if not chips:
            return True
        for c in chips:
            if c.type == chip_type and c.status == "rejected":
                return False
        return True

    def _get_image_file_hash(self, filename: str) -> Optional[str]:
        if not filename:
            return None
        if not hasattr(self, "_img_hash_cache"):
            self._img_hash_cache: Dict[str, str] = {}
        if filename in self._img_hash_cache:
            return self._img_hash_cache[filename]

        path = RAW_PHOTOS_DIR / filename
        if not path.exists():
            stem = filename.rsplit(".", 1)[0] if "." in filename else filename
            path = THUMBNAILS_DIR / f"{stem}_thumb.webp"

        if path.exists():
            import hashlib
            try:
                with open(path, "rb") as f:
                    h = hashlib.md5(f.read()).hexdigest()
                    self._img_hash_cache[filename] = h
                    return h
            except Exception:
                pass
        return None

    def _fetch_photos_metadata(self, photo_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Batch fetches photo metadata from SQLite."""
        if not photo_ids:
            return {}
        placeholders = ",".join("?" for _ in photo_ids)
        query = f"SELECT * FROM photos WHERE photo_id IN ({placeholders})"

        import json
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, photo_ids)
            rows = cursor.fetchall()
            result = {}
            for r in rows:
                d = dict(r)
                d["faces"] = json.loads(d["faces_json"]) if d.get("faces_json") else []
                d["visual_tags"] = json.loads(d["visual_tags_json"]) if d.get("visual_tags_json") else []
                result[d["photo_id"]] = d
            return result

    def _compute_metadata_score(
        self,
        meta: Dict[str, Any],
        cues: ExtractedMemoryCues,
        target_place_cue: Optional[str],
        scene_filter: Optional[str]
    ) -> Tuple[float, List[str]]:
        score = 0.5  # Base score
        matched = []

        # Geographic match (checks city, region, and neighborhood)
        target_place = (target_place_cue or cues.spatial.region or "").lower()
        if target_place:
            photo_places = " ".join([
                str(meta.get("city") or ""),
                str(meta.get("region") or ""),
                str(meta.get("neighborhood") or "")
            ]).lower()
            mapped_region = CITY_TO_REGION.get(target_place, target_place).lower()
            if target_place in photo_places or mapped_region in photo_places:
                score += 0.35
                loc_label = meta.get("city") or meta.get("region")
                matched.append(f"📍 {loc_label}")
            else:
                score -= 0.2

        # Neighborhood match
        if cues.spatial.neighborhood and meta.get("neighborhood"):
            if cues.spatial.neighborhood.lower() in meta["neighborhood"].lower():
                score += 0.20
                matched.append(f"🏘️ {meta['neighborhood']}")

        # Setting / Scene match with token-based fuzzy matching
        target_scene = (scene_filter or cues.spatial.setting or "").lower().replace("_", " ")
        if "beachside" in target_scene:
            target_scene = target_scene.replace("beachside", "beach")
        photo_scene = str(meta.get("scene_type") or "").lower().replace("_", " ")
        if target_scene and photo_scene:
            scene_tokens = set(target_scene.split())
            photo_tokens = set(photo_scene.split())
            if (scene_tokens & photo_tokens) or target_scene in photo_scene or photo_scene in target_scene:
                score += 0.35
                matched.append(f"🏛️ {meta['scene_type'].title()}")
            elif "celebration" in photo_scene and ("party" in target_scene or "birthday" in target_scene or (cues.affective_vibe and "celebrat" in cues.affective_vibe.lower())):
                score += 0.35
                matched.append(f"🏛️ Celebration")

        # Visual concepts and tags match
        concepts_to_match = list(cues.visual_concepts or [])
        if cues.raw_query:
            concepts_to_match.extend(cues.raw_query.lower().split())

        photo_tags = [str(t).lower() for t in meta.get("visual_tags", [])]
        photo_caption = str(meta.get("caption") or "").lower()
        photo_fn = str(meta.get("filename") or "").lower()

        matched_concepts = []
        for concept in concepts_to_match:
            cl = str(concept).lower().strip()
            if len(cl) < 3 or cl in ["the", "that", "this", "from", "with", "took", "year", "picture", "photo"]:
                continue
            if any(cl in t for t in photo_tags) or cl in photo_caption or cl in photo_fn:
                matched_concepts.append(cl)

        if matched_concepts:
            score += min(0.40, 0.20 * len(set(matched_concepts)))
            matched.append(f"🏷️ {matched_concepts[0].title()}")

        return min(1.0, max(0.0, score)), matched

    def _compute_social_score(
        self,
        meta: Dict[str, Any],
        cues: ExtractedMemoryCues
    ) -> Tuple[float, List[str]]:
        score = 0.5
        matched = []
        faces = meta.get("faces", [])

        if cues.social.companion_type:
            comp = cues.social.companion_type.lower()
            if comp in ["friend", "friends"]:
                if len(faces) > 0:
                    score += 0.4
                    # Check for recurring companion label if available
                    comp_name = None
                    if isinstance(faces[0], dict):
                        comp_name = faces[0].get("companion_label")
                    elif isinstance(faces[0], str):
                        comp_name = faces[0]
                    if comp_name:
                        matched.append(f"👥 Friend ({comp_name})")
                    else:
                        matched.append("👥 Friend Present")
                else:
                    score -= 0.1
            elif "dog" in comp or "pet" in comp:
                tags = meta.get("visual_tags", [])
                if any("dog" in t.lower() or "retriever" in t.lower() or "pet" in t.lower() for t in tags):
                    score += 0.5
                    matched.append("🐕 Dog Companion")
            elif comp == "solo":
                if len(faces) == 0:
                    score += 0.3
                    matched.append("👤 Solo Scene")

        return min(1.0, max(0.0, score)), matched

    def _compute_temporal_score(
        self,
        meta: Dict[str, Any],
        cues: ExtractedMemoryCues,
        cluster_filter: Optional[str]
    ) -> Tuple[float, List[str]]:
        score = 0.5
        matched = []
        cid = meta.get("event_cluster_id")
        tags = meta.get("visual_tags", [])
        caption = meta.get("caption", "").lower()

        if cluster_filter and cid == cluster_filter:
            score += 0.4
            matched.append(f"🌴 {self._clusters_cache.get(cid, {}).get('cluster_name', 'Event Cluster')}")
        elif cid and cid in self._clusters_cache:
            cluster_name = self._clusters_cache[cid].get("cluster_name", "")
            if cues.spatial.region and cues.spatial.region.lower() in cluster_name.lower():
                score += 0.3
                matched.append(f"🌴 {cluster_name}")

        # Check relative concept (e.g. birthday, party, trip)
        if cues.temporal.relative_concept:
            concept = cues.temporal.relative_concept.lower()
            if concept in ["birthday", "party", "celebration"]:
                if any(concept in t.lower() for t in tags) or concept in caption or meta.get("scene_type") == "celebration":
                    score += 0.40
                    matched.append(f"🎂 {concept.title()}")
            elif concept in ["trip", "vacation"] and cid:
                score += 0.30
                matched.append(f"🌴 {concept.title()}")

        # Season / time of day check against timestamp or visual tags
        if cues.temporal.season:
            season = cues.temporal.season.lower()
            if season == "monsoon" and any("rain" in t.lower() or "umbrella" in t.lower() for t in tags):
                score += 0.3
                matched.append("🌧️ Monsoon Rain")

        if cues.temporal.time_of_day:
            tod = cues.temporal.time_of_day.lower()
            if tod in ["sunrise", "morning"] and any("sunrise" in t.lower() or "morning" in t.lower() for t in tags):
                score += 0.3
                matched.append(f"🌅 {tod.title()}")
            elif tod in ["evening", "night"] and (any("evening" in t.lower() or "night" in t.lower() for t in tags) or "dinner" in caption):
                score += 0.2
                matched.append(f"🌙 {tod.title()}")

        return min(1.0, max(0.0, score)), matched

    def _evaluate_confidence(
        self,
        candidates: List[CandidatePhoto],
        turn_count: int
    ) -> SearchConfidenceMetrics:
        """
        Evaluates search confidence, margin delta, and Shannon entropy.
        Flags status as CONFIDENT, WEAK_TIER_1, or STILL_WEAK_TIER_2.
        """
        if not candidates:
            return SearchConfidenceMetrics(
                status="WEAK_TIER_1" if turn_count <= 1 else "STILL_WEAK_TIER_2"
            )

        top1 = candidates[0].score
        top5 = candidates[min(4, len(candidates) - 1)].score
        margin = round(top1 - top5, 4)

        # Shannon entropy across top candidate scores
        scores = np.array([c.score for c in candidates[:20]], dtype=np.float64)
        sum_scores = np.sum(scores)
        if sum_scores > 0:
            probs = scores / sum_scores
            entropy = float(-np.sum(probs * np.log2(np.maximum(probs, 1e-9))))
            variance = float(np.var(scores))
        else:
            entropy = 0.0
            variance = 0.0

        # Classification rule based on architecture & core product principle:
        # If top1 is strong (>= 0.75) and margin is distinct (>= 0.04), status is CONFIDENT.
        # Otherwise, initial search is WEAK_TIER_1 (ambiguous result) and subsequent is STILL_WEAK_TIER_2.
        if top1 >= 0.75 and margin >= 0.04:
            status = "CONFIDENT"
        elif turn_count <= 1:
            status = "WEAK_TIER_1"
        else:
            status = "STILL_WEAK_TIER_2"

        return SearchConfidenceMetrics(
            top1_score=round(top1, 4),
            top5_score=round(top5, 4),
            margin_delta=margin,
            entropy=round(entropy, 4),
            variance=round(variance, 6),
            status=status
        )

global_retriever = HybridRetriever()
