import uuid
import time
import threading
from typing import Dict, Optional, List
from src.engine.schemas import SessionState, CueChip, ExtractedMemoryCues

class SessionManager:
    """
    In-memory thread-safe session store for multi-turn episodic retrieval state.
    """
    def __init__(self, ttl_seconds: int = 3600):
        self._sessions: Dict[str, SessionState] = {}
        self._last_accessed: Dict[str, float] = {}
        self._lock = threading.Lock()
        self.ttl_seconds = ttl_seconds

    def create_or_get_session(
        self,
        session_id: Optional[str] = None,
        query: str = "",
        cues: Optional[ExtractedMemoryCues] = None,
        chips: Optional[List[CueChip]] = None
    ) -> SessionState:
        with self._lock:
            self._cleanup_expired()
            if session_id and session_id in self._sessions:
                sess = self._sessions[session_id]
                sess.turn_count += 1
                if query:
                    sess.raw_query = query
                    sess.history.append({"turn": sess.turn_count, "query": query, "time": time.time()})
                if cues:
                    sess.extracted_cues = cues
                if chips:
                    # Merge or update chips
                    existing_by_val = {c.value: c for c in sess.chips}
                    for new_c in chips:
                        if new_c.value not in existing_by_val:
                            sess.chips.append(new_c)
                self._last_accessed[session_id] = time.time()
                return sess

            # Generate new session
            new_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"
            default_cues = cues or ExtractedMemoryCues(raw_query=query)
            sess = SessionState(
                session_id=new_id,
                raw_query=query,
                turn_count=1,
                recovery_tier="initial",
                extracted_cues=default_cues,
                chips=chips or [],
                active_filter_bounds={},
                candidate_photo_ids=[],
                confidence_score=default_cues.confidence_score,
                target_retrieved=False,
                history=[{"turn": 1, "query": query, "time": time.time()}] if query else []
            )
            self._sessions[new_id] = sess
            self._last_accessed[new_id] = time.time()
            return sess

    def get_session(self, session_id: str) -> Optional[SessionState]:
        with self._lock:
            self._cleanup_expired()
            sess = self._sessions.get(session_id)
            if sess:
                self._last_accessed[session_id] = time.time()
            return sess

    def save_session(self, session: SessionState) -> None:
        with self._lock:
            self._sessions[session.session_id] = session
            self._last_accessed[session.session_id] = time.time()

    def update_chip_status(
        self,
        session_id: str,
        chip_id: str,
        status: str
    ) -> Optional[SessionState]:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                return None
            for c in sess.chips:
                if c.id == chip_id:
                    c.status = status
                    break
            self._last_accessed[session_id] = time.time()
            return sess

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [sid for sid, t in self._last_accessed.items() if now - t > self.ttl_seconds]
        for sid in expired:
            self._sessions.pop(sid, None)
            self._last_accessed.pop(sid, None)

global_session_manager = SessionManager()
