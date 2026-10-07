from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class ExifMetadata(BaseModel):
    camera_model: Optional[str] = "iPhone 14 Pro"
    focal_length: Optional[float] = 24.0
    iso: Optional[int] = 64
    has_gps: bool = True

class GeocodedLocation(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = "India"
    neighborhood: Optional[str] = None

class FaceAnnotation(BaseModel):
    face_id: str
    companion_label: Optional[str] = None
    bounding_box: Optional[List[int]] = None

class PhotoMetadata(BaseModel):
    photo_id: str
    filename: str
    storage_path: str
    thumbnail_path: str
    timestamp: str
    exif: ExifMetadata
    location: GeocodedLocation
    event_cluster_id: Optional[str] = None
    faces: List[FaceAnnotation] = Field(default_factory=list)
    visual_tags: List[str] = Field(default_factory=list)
    scene_type: str = "general"
    caption: str = ""
    embedding_vector_id: str

class EventCluster(BaseModel):
    cluster_id: str
    cluster_name: str
    region: Optional[str] = None
    start_time: str
    end_time: str
    photo_count: int
    sample_photo_ids: List[str] = Field(default_factory=list)
