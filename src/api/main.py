import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.config import (
    RAW_PHOTOS_DIR, THUMBNAILS_DIR, SQLITE_DB_PATH,
    GROQ_API_KEY, GROQ_MODEL, HOST, PORT
)
from src.database.db import get_all_photos, get_all_clusters, get_photo_by_id, get_related_photos
from src.engine.schemas import (
    SearchRequest, SearchResponse, CueChip,
    SessionState, UpdateChipRequest,
    RefineRequest, RefineResponse, RecoveryPrompt,
    Tier1Prompt, Tier1Option, Tier2Prompt, Tier2CueGroup,
    TelemetryEventCreate, TelemetryMetricsSummary,
    CompleteSessionRequest, AbandonSessionRequest
)
from src.engine.understand import global_cue_extractor
from src.engine.connect import global_retriever
from src.engine.session import global_session_manager
from src.engine.recover import global_recover_engine
from src.engine.telemetry import global_telemetry_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("api")

app = FastAPI(
    title="AI-Native Photo Retrieval MVP API",
    description="Cognitive memory-guided episodic photo retrieval engine powered by Groq LPU and hybrid vector search.",
    version="0.2.0"
)

# Enable CORS for local client development and remote Vercel frontend deployments
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Verifies database & vector store exist on boot; auto-seeds if running in a fresh Railway container."""
    try:
        photos = get_all_photos(SQLITE_DB_PATH)
        if len(photos) == 0:
            logger.warning("Photo database empty or missing. Triggering auto-ingestion pipeline...")
            from ingest import run_ingestion_pipeline
            run_ingestion_pipeline(generate_dataset=True)
        else:
            logger.info(f"Database online with {len(photos)} photos.")
    except Exception as e:
        logger.warning(f"Error checking photo database on startup: {e}. Attempting auto-ingestion...")
        try:
            from ingest import run_ingestion_pipeline
            run_ingestion_pipeline(generate_dataset=True)
        except Exception as ex:
            logger.error(f"Failed to auto-ingest photo dataset: {ex}")

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if any(path.startswith(p) for p in ["/thumbnails", "/photos", "/static"]):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Mount static directories for thumbnails, raw photos, and client UI assets
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if THUMBNAILS_DIR.exists():
    app.mount("/thumbnails", StaticFiles(directory=str(THUMBNAILS_DIR)), name="thumbnails")
if RAW_PHOTOS_DIR.exists():
    app.mount("/photos", StaticFiles(directory=str(RAW_PHOTOS_DIR)), name="photos")

@app.get("/", tags=["General"])
async def root():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "service": "AI-Native Photo Retrieval MVP API",
        "version": "0.2.0",
        "status": "online",
        "docs_url": "/docs"
    }

@app.get("/api", tags=["General"])
async def api_info():
    return {
        "service": "AI-Native Photo Retrieval MVP API",
        "version": "0.2.0",
        "status": "online",
        "docs_url": "/docs",
        "endpoints": [
            "/api/search",
            "/api/session/{session_id}",
            "/api/session/refine",
            "/api/session/{session_id}/complete",
            "/api/session/{session_id}/abandon",
            "/api/telemetry/event",
            "/api/telemetry/metrics",
            "/api/telemetry/session/{session_id}",
            "/api/clusters",
            "/api/photos/{photo_id}",
            "/api/health"
        ]
    }

@app.get("/api/health", tags=["General"])
async def health_check():
    """Health status and collection metrics."""
    try:
        photos = get_all_photos(SQLITE_DB_PATH)
        clusters = get_all_clusters(SQLITE_DB_PATH)
        vectors_count = global_retriever.vector_store.count()
        return {
            "status": "healthy",
            "groq_configured": bool(GROQ_API_KEY),
            "groq_model": GROQ_MODEL,
            "database_photos_count": len(photos),
            "database_clusters_count": len(clusters),
            "vector_index_count": vectors_count
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "status": "degraded",
            "error": str(e)
        }

@app.post("/api/search", response_model=SearchResponse, tags=["Search & Retrieval"])
async def search_photos(request: SearchRequest):
    """
    Core Search API (Understand + Connect).
    1. Extracts episodic memory cues from natural language query via Groq.
    2. Synchronizes session state and interactive chips.
    3. Executes hybrid search (dense vector + metadata filtering + score fusion).
    4. Evaluates result confidence metrics.
    """
    if not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query string cannot be empty."
        )

    try:
        # Step 1: The "Understand" Engine - extract cues
        extracted_cues, generated_chips = global_cue_extractor.extract_cues(request.query)

        # Step 1.5: Internal Cue Sufficiency Check
        sufficiency_info = global_cue_extractor.check_cue_sufficiency(extracted_cues, request.query)
        is_sufficient = sufficiency_info.get("is_sufficient", True)
        clarification_q = sufficiency_info.get("clarification_question")
        clarification_opts = sufficiency_info.get("clarification_options")
        recognition_cues = sufficiency_info.get("recognition_cues")

        # Step 2: Session synchronization
        active_chips = request.active_cues if request.active_cues is not None else generated_chips
        session = global_session_manager.create_or_get_session(
            session_id=request.session_id,
            query=request.query,
            cues=extracted_cues,
            chips=active_chips
        )

        # Step 3: The "Connect" Engine - execute hybrid retrieval
        candidates, metrics, relaxed = global_retriever.search(
            query=request.query,
            cues=extracted_cues,
            active_chips=session.chips,
            top_k=request.top_k,
            turn_count=session.turn_count,
            filter_region=request.filter_region,
            filter_cluster=request.filter_cluster,
            filter_scene=request.filter_scene
        )

        # Step 4: Check if recovery prompt should be generated
        recovery_prompt: Optional[RecoveryPrompt] = None
        if not is_sufficient:
            # Insufficient cues: prompt contextual clarification
            options = []
            if clarification_opts:
                from src.engine.schemas import Tier1Option
                for opt in clarification_opts:
                    options.append(Tier1Option(
                        option_id=opt.get("option_id", "opt_1"),
                        label=opt.get("label", ""),
                        filter_modifier={"value": opt.get("value", "")}
                    ))
            tier1 = Tier1Prompt(
                prompt_id=f"pvt_suff_{abs(hash(request.query)) % 10000}",
                question_text=clarification_q or "Can you remember anything about where you were?",
                options=options
            )
            recovery_prompt = RecoveryPrompt(
                tier=1,
                prompt_type="meaningful_detail_question",
                question_text=tier1.question_text,
                tier1=tier1
            )
            session.recovery_tier = "tier_1_recovery"
        elif metrics.status == "WEAK_TIER_1":
            tier1 = global_recover_engine.generate_tier1_prompt(candidates, extracted_cues, request.query)
            recovery_prompt = RecoveryPrompt(
                tier=1,
                prompt_type="meaningful_detail_question",
                question_text=tier1.question_text,
                tier1=tier1
            )
            session.recovery_tier = "tier_1_recovery"
        elif metrics.status == "STILL_WEAK_TIER_2":
            tier2 = global_recover_engine.generate_tier2_prompt(candidates, extracted_cues, request.query)
            recovery_prompt = RecoveryPrompt(
                tier=2,
                prompt_type="recognition_cue_cloud",
                question_text=tier2.question_text,
                tier2=tier2
            )
            session.recovery_tier = "tier_2_recognition"
        else:
            session.recovery_tier = "confident"

        # Step 5: Update session state
        session.candidate_photo_ids = [c.photo_id for c in candidates]
        session.confidence_score = metrics.top1_score
        session.recovery_prompt = recovery_prompt
        global_session_manager.save_session(session)

        # Telemetry Logging
        global_telemetry_engine.start_or_update_session(
            session_id=session.session_id,
            raw_query=request.query,
            cues_count=len(session.chips)
        )
        global_telemetry_engine.log_event(
            session_id=session.session_id,
            event_type="cues_extracted",
            details={"count": len(session.chips), "cues": [c.label for c in session.chips], "is_cue_sufficient": is_sufficient}
        )
        if recovery_prompt:
            if recovery_prompt.tier == 1:
                opts = [o.label for o in (recovery_prompt.tier1.options if recovery_prompt.tier1 else [])]
                global_telemetry_engine.record_tier1_rendered(session.session_id, recovery_prompt.question_text, opts)
            elif recovery_prompt.tier == 2:
                global_telemetry_engine.record_tier2_rendered(session.session_id, recovery_prompt.question_text, [])

        return SearchResponse(
            session_id=session.session_id,
            query=request.query,
            turn_count=session.turn_count,
            extracted_cues=extracted_cues,
            chips=session.chips,
            candidates=candidates,
            metrics=metrics,
            total_hits=len(candidates),
            relaxed_filter=relaxed,
            recovery_tier=session.recovery_tier,
            recovery_prompt=recovery_prompt,
            is_cue_sufficient=is_sufficient,
            clarification_question=clarification_q,
            clarification_options=clarification_opts,
            recognition_cues=recognition_cues
        )

    except Exception as e:
        logger.exception(f"Error during search execution: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search pipeline encountered an error: {str(e)}"
        )

@app.post("/api/session/refine", response_model=RefineResponse, tags=["Search & Retrieval"])
async def refine_session(request: RefineRequest):
    """
    Progressive Recovery Disambiguation Endpoint.
    Ingests user setting choice (Tier 1) or recognized cues (Tier 2),
    updates retrieval session, and re-executes search or escalates recovery ladder.
    """
    try:
        # Telemetry for pivot selection
        opt_choice = request.selected_option or request.selected_option_id or request.venue_type
        if opt_choice:
            global_telemetry_engine.record_tier1_selected(request.session_id, str(opt_choice))

        cues_choice = request.selected_cues or request.recognized_cues
        if cues_choice:
            global_telemetry_engine.record_tier2_selected(request.session_id, cues_choice)

        candidates, metrics, recovery_prompt, session = global_recover_engine.refine_session(request)

        if recovery_prompt and recovery_prompt.tier == 2:
            global_telemetry_engine.record_tier2_rendered(session.session_id, recovery_prompt.question_text, [])

        if metrics.status == "CONFIDENT" and len(candidates) > 0:
            session.target_retrieved = True
            global_telemetry_engine.record_completion(session.session_id, candidates[0].photo_id, session.turn_count)

        return RefineResponse(
            session_id=session.session_id,
            turn_count=session.turn_count,
            recovery_tier=session.recovery_tier,
            extracted_cues=session.extracted_cues,
            chips=session.chips,
            candidates=candidates,
            metrics=metrics,
            total_hits=len(candidates),
            recovery_prompt=recovery_prompt
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Error during refine execution: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Refine pipeline encountered an error: {str(e)}"
        )

@app.post("/api/telemetry/event", tags=["Telemetry"])
async def log_telemetry_event(event: TelemetryEventCreate):
    """Ingest a telemetry event from client interactions."""
    global_telemetry_engine.log_event(
        session_id=event.session_id,
        event_type=event.event_type,
        details=event.details,
        timestamp=event.timestamp
    )
    return {"status": "recorded", "event_type": event.event_type}

@app.get("/api/telemetry/metrics", response_model=TelemetryMetricsSummary, tags=["Telemetry"])
async def get_telemetry_metrics():
    """Returns aggregated product KPIs and evaluation benchmarks across all sessions."""
    return global_telemetry_engine.calculate_metrics()

@app.get("/api/telemetry/session/{session_id}", tags=["Telemetry"])
async def get_session_telemetry(session_id: str):
    """Retrieves all telemetry events and ladder progression for a session."""
    events = global_telemetry_engine.get_session_events(session_id)
    session = global_session_manager.get_session(session_id)
    return {
        "session_id": session_id,
        "events": events,
        "turn_count": session.turn_count if session else 1,
        "target_retrieved": session.target_retrieved if session else False
    }

@app.post("/api/session/{session_id}/complete", tags=["Session"])
async def complete_session(session_id: str, req: CompleteSessionRequest):
    """Marks photo retrieval completed and logs photo_retrieved with duration and path."""
    session = global_session_manager.get_session(session_id)
    if session:
        session.target_retrieved = True
        global_session_manager.save_session(session)
    global_telemetry_engine.record_completion(
        session_id=session_id,
        photo_id=req.photo_id,
        effort_turns=req.effort_turns or (session.turn_count if session else 1),
        path=req.retrieval_path
    )
    return {"status": "completed", "session_id": session_id, "photo_id": req.photo_id}

@app.post("/api/session/{session_id}/abandon", tags=["Session"])
async def abandon_session(session_id: str, req: AbandonSessionRequest = AbandonSessionRequest()):
    """Marks a session abandoned when the user cancels or resets flow."""
    global_telemetry_engine.record_abandonment(session_id, req.reason or "user_reset")
    return {"status": "abandoned", "session_id": session_id}

@app.get("/api/session/{session_id}", response_model=SessionState, tags=["Session"])
async def get_session(session_id: str):
    """Retrieves the current multi-turn session state."""
    session = global_session_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' not found."
        )
    return session

@app.post("/api/session/{session_id}/chip", response_model=SessionState, tags=["Session"])
async def update_session_chip(session_id: str, req: UpdateChipRequest):
    """Updates the status of a specific memory cue chip (e.g. confirm or reject)."""
    session = global_session_manager.update_chip_status(session_id, req.chip_id, req.status)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' not found."
        )
    return session

@app.get("/api/clusters", tags=["Metadata & Exploration"])
async def list_clusters():
    """Lists all spatio-temporal event clusters discovered during ingestion."""
    clusters = get_all_clusters(SQLITE_DB_PATH)
    return {"clusters": clusters, "total": len(clusters)}

@app.get("/api/photos/{photo_id}", tags=["Metadata & Exploration"])
async def get_photo(photo_id: str):
    """Retrieves full photo metadata by ID."""
    photo = get_photo_by_id(photo_id, SQLITE_DB_PATH)
    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Photo with ID '{photo_id}' not found."
        )
    fn = photo.get("filename", "")
    stem = fn.rsplit(".", 1)[0] if "." in fn else fn
    photo["thumbnail_url"] = f"/thumbnails/{stem}_thumb.webp?v=real_v3"
    photo["full_photo_url"] = f"/photos/{fn}?v=real_v3"
    photo["image_url"] = f"/photos/{fn}?v=real_v3"
    return photo

@app.get("/api/photos/{photo_id}/related", tags=["Metadata & Exploration"])
async def get_photo_related(photo_id: str, limit: int = 8):
    """Retrieves photos from the SAME location and event cluster as the target photo."""
    related = get_related_photos(photo_id, limit=limit, db_path=SQLITE_DB_PATH)
    for p in related:
        fn = p.get("filename", "")
        stem = fn.rsplit(".", 1)[0] if "." in fn else fn
        p["thumbnail_url"] = f"/thumbnails/{stem}_thumb.webp?v=match_v5"
        p["full_photo_url"] = f"/photos/{fn}?v=match_v5"
        p["image_url"] = f"/photos/{fn}?v=match_v5"
    return {"related": related, "total": len(related)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host=HOST, port=PORT, reload=True)
