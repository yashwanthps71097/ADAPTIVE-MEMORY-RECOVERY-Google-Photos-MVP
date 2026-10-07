from typing import List, Dict, Any, Optional
from src.database.models import FaceAnnotation

# Reference companion profile dictionary for MVP episodic scenarios
KNOWN_COMPANION_PROFILES = {
    "face_cluster_1": {
        "name": "Friend (Goa Trip Companion - Alex)",
        "relationship": "friend",
        "description": "Recurring close friend traveling together in Goa café and beach scenes"
    },
    "face_cluster_2": {
        "name": "Friend (Group Celebration - Priya)",
        "relationship": "friend",
        "description": "Friend present during dinner and birthday celebrations"
    },
    "face_cluster_3": {
        "name": "Friend (Hiking Buddy - Rohan)",
        "relationship": "friend",
        "description": "Companion on mountain hikes and outdoor adventures"
    }
}

def annotate_photo_faces(
    photo_metadata_dict: Dict[str, Any],
    detected_face_ids: Optional[List[str]] = None
) -> List[FaceAnnotation]:
    """
    Annotates a photo with recognized face clusters and bounding boxes.
    Enables companion filtering and face avatar suggestions during Phase 3/4.
    """
    annotations = []
    face_ids = detected_face_ids or photo_metadata_dict.get("face_ids", [])
    
    for fid in face_ids:
        profile = KNOWN_COMPANION_PROFILES.get(fid, {
            "name": f"Companion ({fid})",
            "relationship": "friend",
            "description": "Detected travel companion"
        })
        annotations.append(FaceAnnotation(
            face_id=fid,
            companion_label=profile["name"],
            bounding_box=[100, 80, 220, 200]
        ))
        
    return annotations

def get_companion_profile(face_id: str) -> Optional[Dict[str, str]]:
    return KNOWN_COMPANION_PROFILES.get(face_id)
