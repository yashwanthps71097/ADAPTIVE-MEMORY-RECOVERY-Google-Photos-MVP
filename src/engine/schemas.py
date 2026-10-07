from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

class SpatialCue(BaseModel):
    region: Optional[str] = None
    neighborhood: Optional[str] = None
    setting: Optional[str] = None       # e.g., cafe, restaurant, beach, mountain, street food
    environment: Optional[str] = None   # e.g., indoor, outdoor, cozy

class TemporalCue(BaseModel):
    relative_concept: Optional[str] = None # e.g., trip, vacation, holiday, birthday
    season: Optional[str] = None           # e.g., monsoon, summer, winter
    time_frame: Optional[str] = None       # e.g., 2 years ago, recent
    time_of_day: Optional[str] = None      # e.g., morning, evening, night

class SocialCue(BaseModel):
    companion_type: Optional[str] = None   # e.g., friend, friends, family, solo, pet/dog
    group_size: Optional[str] = None       # e.g., duo, small group, large group
    companion_names: List[str] = Field(default_factory=list)

class CueChip(BaseModel):
    id: str
    type: Literal["place", "setting", "activity", "people", "temporal", "vibe", "visual"]
    label: str
    value: str
    status: Literal["active", "confirmed", "rejected", "user_selected_tier_1", "user_selected_tier_2"] = "active"
    icon: Optional[str] = None

class ExtractedMemoryCues(BaseModel):
    spatial: SpatialCue = Field(default_factory=SpatialCue)
    temporal: TemporalCue = Field(default_factory=TemporalCue)
    social: SocialCue = Field(default_factory=SocialCue)
    visual_concepts: List[str] = Field(default_factory=list)
    affective_vibe: Optional[str] = None
    confidence_score: float = 0.5
    specificity_score: float = 0.5
    raw_query: str = ""

class SearchConfidenceMetrics(BaseModel):
    top1_score: float = 0.0
    top5_score: float = 0.0
    margin_delta: float = 0.0
    entropy: float = 0.0
    variance: float = 0.0
    status: Literal["CONFIDENT", "WEAK_TIER_1", "STILL_WEAK_TIER_2"] = "CONFIDENT"

class CandidatePhoto(BaseModel):
    photo_id: str
    filename: str
    thumbnail_url: str
    full_photo_url: str
    image_url: Optional[str] = None
    score: float
    vector_score: float
    metadata_score: float
    social_score: float
    temporal_score: float
    matched_cues: List[str] = Field(default_factory=list)
    timestamp: str = ""
    city: Optional[str] = None
    region: Optional[str] = None
    neighborhood: Optional[str] = None
    scene_type: Optional[str] = None
    caption: Optional[str] = None
    event_cluster_id: Optional[str] = None
    event_cluster_name: Optional[str] = None
    location_name: Optional[str] = None
    trip_cluster: Optional[str] = None
    camera_model: Optional[str] = None
    visual_tags: List[str] = Field(default_factory=list)

class Tier1Option(BaseModel):
    option_id: str
    label: str
    filter_modifier: Dict[str, Any] = Field(default_factory=dict)

class Tier1Prompt(BaseModel):
    prompt_id: str
    tier: Literal[1] = 1
    prompt_type: Literal["meaningful_detail_question"] = "meaningful_detail_question"
    question_text: str
    options: List[Tier1Option] = Field(default_factory=list)

class Tier2CueGroup(BaseModel):
    category: str
    cues: List[str] = Field(default_factory=list)

class Tier2Prompt(BaseModel):
    prompt_id: str
    tier: Literal[2] = 2
    prompt_type: Literal["recognition_cue_cloud"] = "recognition_cue_cloud"
    question_text: str = "Which feels familiar?"
    cue_groups: List[Tier2CueGroup] = Field(default_factory=list)

class RecoveryPrompt(BaseModel):
    tier: int
    prompt_type: str
    question_text: str
    tier1: Optional[Tier1Prompt] = None
    tier2: Optional[Tier2Prompt] = None

class SearchRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    top_k: int = 20
    active_cues: Optional[List[CueChip]] = None
    filter_region: Optional[str] = None
    filter_cluster: Optional[str] = None
    filter_scene: Optional[str] = None

class SearchResponse(BaseModel):
    session_id: str
    query: str
    turn_count: int
    extracted_cues: ExtractedMemoryCues
    chips: List[CueChip]
    candidates: List[CandidatePhoto]
    metrics: SearchConfidenceMetrics
    total_hits: int
    relaxed_filter: bool = False
    recovery_tier: Optional[str] = None
    recovery_prompt: Optional[RecoveryPrompt] = None
    is_cue_sufficient: bool = True
    clarification_question: Optional[str] = None
    clarification_options: Optional[List[Dict[str, Any]]] = None
    recognition_cues: Optional[List[str]] = None

class RefineRequest(BaseModel):
    session_id: str
    selected_option_id: Optional[str] = None
    selected_option: Optional[str] = None
    selected_cues: Optional[List[str]] = None
    recognized_cues: Optional[List[str]] = None
    venue_type: Optional[str] = None
    query_addition: Optional[str] = None
    top_k: int = 20

class RefineResponse(BaseModel):
    session_id: str
    turn_count: int
    recovery_tier: str
    extracted_cues: ExtractedMemoryCues
    chips: List[CueChip]
    candidates: List[CandidatePhoto]
    metrics: SearchConfidenceMetrics
    total_hits: int
    recovery_prompt: Optional[RecoveryPrompt] = None

class UpdateChipRequest(BaseModel):
    chip_id: str
    status: Literal["active", "confirmed", "rejected"]

class SessionState(BaseModel):
    session_id: str
    raw_query: str
    turn_count: int = 1
    recovery_tier: str = "initial"
    extracted_cues: ExtractedMemoryCues
    chips: List[CueChip] = Field(default_factory=list)
    active_filter_bounds: Dict[str, Any] = Field(default_factory=dict)
    candidate_photo_ids: List[str] = Field(default_factory=list)
    confidence_score: float = 0.5
    target_retrieved: bool = False
    recovery_prompt: Optional[RecoveryPrompt] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)

class TelemetryEventCreate(BaseModel):
    session_id: str
    event_type: str  # search_started, cues_extracted, tier1_detail_prompt_rendered, tier1_detail_selected, tier2_recognition_cloud_rendered, tier2_cue_recognized, photo_retrieved, session_abandoned
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[float] = None

class CompleteSessionRequest(BaseModel):
    photo_id: str
    target_confirmed: bool = True
    effort_turns: Optional[int] = None
    retrieval_path: List[str] = Field(default_factory=list)

class AbandonSessionRequest(BaseModel):
    reason: Optional[str] = "user_reset"
    turn_count: Optional[int] = None

class TelemetryMetricsSummary(BaseModel):
    total_sessions: int
    successful_retrievals: int
    retrieval_success_rate: float
    avg_ttr_seconds: float
    median_ttr_seconds: float
    tier1_rendered_count: int
    tier1_accepted_count: int
    tier1_acceptance_rate: float
    tier2_rendered_count: int
    tier2_accepted_count: int
    tier2_acceptance_rate: float
    manual_retyping_reduction_rate: float
    recent_events: List[Dict[str, Any]] = Field(default_factory=list)
