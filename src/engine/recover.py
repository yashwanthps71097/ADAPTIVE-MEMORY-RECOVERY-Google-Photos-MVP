import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from groq import Groq

from src.config import GROQ_API_KEY, GROQ_MODEL, GROQ_FALLBACK_MODELS
from src.engine.schemas import (
    CandidatePhoto, ExtractedMemoryCues,
    Tier1Prompt, Tier1Option,
    Tier2Prompt, Tier2CueGroup,
    RecoveryPrompt, RefineRequest, RefineResponse,
    SessionState, CueChip
)
from src.engine.session import global_session_manager
from src.engine.connect import global_retriever

logger = logging.getLogger(__name__)

TIER1_SYSTEM_PROMPT = """You are the Disambiguation Recovery Agent for an AI-native episodic photo retrieval engine.
When initial episodic search results are ambiguous or have high variance across venues, your goal is to formulate
a direct, concise clarifying question isolating the primary setting or venue type.

Output strictly a JSON object following this exact schema:
{
  "question_text": "Do you remember what kind of place it was?",
  "options": [
    { "option_id": "opt_restaurant_cafe", "label": "Restaurant / Café", "filter_modifier": { "venue_type": "restaurant_cafe" } },
    { "option_id": "opt_beachside", "label": "Beachside", "filter_modifier": { "venue_type": "beachside" } },
    { "option_id": "opt_hotel_resort", "label": "Hotel / Resort", "filter_modifier": { "venue_type": "hotel_resort" } },
    { "option_id": "opt_street_market", "label": "Street / Market", "filter_modifier": { "venue_type": "street_market" } },
    { "option_id": "opt_home", "label": "Home", "filter_modifier": { "venue_type": "home" } },
    { "option_id": "opt_not_sure", "label": "Not sure", "filter_modifier": { "action": "escalate_tier2" } }
  ]
}
Output only valid JSON."""

TIER2_SYSTEM_PROMPT = """You are the Associative Recognition Agent for an AI-native episodic photo retrieval engine.
When structural questions fail to disambiguate results, shift from structural categorization to autobiographical recognition anchors.
Formulate an associative cue cloud under the anchor "Which feels familiar?" across 4 orthogonal dimensions:
1. Setting: (e.g., Restaurant, Beach, Hotel, Outdoor)
2. Social: (e.g., Friends, Family, Group)
3. Atmosphere: (e.g., Evening, Sunny, Cozy, Celebration)
4. Activity: (e.g., Travel, Eating, Coffee, Shopping)

Output strictly a JSON object following this exact schema:
{
  "question_text": "Which feels familiar?",
  "cue_groups": [
    {
      "category": "Setting",
      "cues": ["Restaurant", "Beach", "Hotel", "Outdoor"]
    },
    {
      "category": "Social",
      "cues": ["Friends", "Family", "Group"]
    },
    {
      "category": "Atmosphere",
      "cues": ["Evening", "Sunny", "Cozy", "Celebration"]
    },
    {
      "category": "Activity",
      "cues": ["Travel", "Eating", "Coffee", "Shopping"]
    }
  ]
}
Output only valid JSON."""

class RecoverEngine:
    """
    The Recover Engine.
    Executes autonomous progressive disambiguation:
    - Tier 1: Meaningful Details (Setting/Venue Discrimination)
    - Tier 2: Associative Recognition Matrix ("Which feels familiar?")
    """
    def __init__(self, api_key: str = GROQ_API_KEY, model: str = GROQ_MODEL):
        self.api_key = api_key
        self.preferred_model = model
        self.client: Optional[Groq] = None
        self._cache: Dict[str, Any] = {}
        if self.api_key:
            try:
                self.client = Groq(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Groq client in RecoverEngine: {e}")

    def generate_tier1_prompt(
        self,
        candidates: List[CandidatePhoto],
        cues: Optional[ExtractedMemoryCues] = None,
        query: str = ""
    ) -> Tier1Prompt:
        """
        Generates Tier-1 clarifying question isolating setting/venue variance.
        Produces: "Was it a restaurant, beach café, or hotel?"
        """
        norm_query = re.sub(r'[^\w\s]', '', query).strip().lower()
        cache_key = f"tier1_{norm_query}"
        if cache_key in self._cache:
            return self._cache[cache_key].model_copy(deep=True)

        candidate_scenes = list({c.scene_type for c in candidates if c.scene_type})

        # Try Groq API first
        if self.client:
            models = [self.preferred_model] + [m for m in GROQ_FALLBACK_MODELS if m != self.preferred_model]
            user_content = (
                f"Query: {query}\n"
                f"Detected scenes in candidate pool: {candidate_scenes}\n"
                f"Extracted cues: {cues.model_dump() if cues else {}}"
            )
            for m in models:
                try:
                    res = self.client.chat.completions.create(
                        model=m,
                        messages=[
                            {"role": "system", "content": TIER1_SYSTEM_PROMPT},
                            {"role": "user", "content": user_content}
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.1,
                        max_tokens=400
                    )
                    raw_text = res.choices[0].message.content or ""
                    parsed = self._sanitize_and_parse_json(raw_text)
                    if parsed and "question_text" in parsed and "options" in parsed:
                        options = [Tier1Option(**opt) for opt in parsed["options"]]
                        if not any("not sure" in o.label.lower() for o in options):
                            options.append(Tier1Option(option_id="opt_not_sure", label="Not sure", filter_modifier={"action": "escalate_tier2"}))
                        prompt = Tier1Prompt(
                            prompt_id=f"pvt_tier1_{abs(hash(query)) % 10000}",
                            question_text=parsed.get("question_text", "Do you remember what kind of place it was?"),
                            options=options
                        )
                        self._cache[cache_key] = prompt
                        return prompt
                except Exception as e:
                    logger.warning(f"Groq Tier-1 generation failed with {m}: {e}")

        # Fallback deterministic generation
        prompt = self._fallback_tier1_prompt(candidates, cues, query)
        self._cache[cache_key] = prompt
        return prompt

    def generate_tier2_prompt(
        self,
        candidates: List[CandidatePhoto],
        cues: Optional[ExtractedMemoryCues] = None,
        query: str = ""
    ) -> Tier2Prompt:
        """
        Generates Tier-2 associative recognition matrix under "Which feels familiar?".
        """
        norm_query = re.sub(r'[^\w\s]', '', query).strip().lower()
        cache_key = f"tier2_{norm_query}"
        if cache_key in self._cache:
            return self._cache[cache_key].model_copy(deep=True)

        if self.client:
            models = [self.preferred_model] + [m for m in GROQ_FALLBACK_MODELS if m != self.preferred_model]
            user_content = (
                f"Query: {query}\n"
                f"Weak candidate scenes: {list({c.scene_type for c in candidates if c.scene_type})}\n"
                f"Candidate visual tags: {list({t for c in candidates for t in getattr(c, 'visual_tags', getattr(c, 'matched_cues', []))[:3]})}"
            )
            for m in models:
                try:
                    res = self.client.chat.completions.create(
                        model=m,
                        messages=[
                            {"role": "system", "content": TIER2_SYSTEM_PROMPT},
                            {"role": "user", "content": user_content}
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.1,
                        max_tokens=400
                    )
                    raw_text = res.choices[0].message.content or ""
                    parsed = self._sanitize_and_parse_json(raw_text)
                    if parsed and "cue_groups" in parsed:
                        groups = [Tier2CueGroup(**g) for g in parsed["cue_groups"]]
                        prompt = Tier2Prompt(
                            prompt_id=f"pvt_tier2_{abs(hash(query)) % 10000}",
                            question_text=parsed.get("question_text", "Which feels familiar?"),
                            cue_groups=groups
                        )
                        self._cache[cache_key] = prompt
                        return prompt
                except Exception as e:
                    logger.warning(f"Groq Tier-2 generation failed with {m}: {e}")

        # Fallback deterministic generation
        prompt = self._fallback_tier2_prompt(candidates, cues, query)
        self._cache[cache_key] = prompt
        return prompt

    def refine_session(
        self,
        refine_req: RefineRequest
    ) -> Tuple[List[CandidatePhoto], Any, Optional[RecoveryPrompt], SessionState]:
        """
        Ingests user disambiguation selection (Tier 1 setting choice or Tier 2 recognized cues),
        updates session state, and executes refined hybrid retrieval pass.
        """
        session = global_session_manager.get_session(refine_req.session_id)
        if not session:
            raise ValueError(f"Session '{refine_req.session_id}' not found.")

        session.turn_count += 1
        filter_scene = None

        # 1. Process Tier 1 selection (e.g. "Restaurant / Café", "Beachside", or "Not sure")
        option_val = refine_req.selected_option_id or refine_req.selected_option or refine_req.venue_type
        if option_val:
            opt_str = str(option_val).lower().strip()
            if "not_sure" in opt_str or "not sure" in opt_str:
                # User chose "Not sure" -> escalate immediately to Tier 2 Recognition
                tier2 = self.generate_tier2_prompt([], session.extracted_cues, session.raw_query)
                recovery_prompt = RecoveryPrompt(
                    tier=2,
                    prompt_type="recognition_cue_cloud",
                    question_text=tier2.question_text,
                    tier2=tier2
                )
                session.recovery_tier = "tier_2_recognition"
                session.recovery_prompt = recovery_prompt
                global_session_manager.save_session(session)
                # Keep existing candidates
                candidates, metrics, _ = global_retriever.search(
                    query=session.raw_query,
                    cues=session.extracted_cues,
                    active_chips=session.chips,
                    top_k=20,
                    turn_count=session.turn_count
                )
                return candidates, metrics, recovery_prompt, session

            if "beach_cafe" in opt_str:
                setting_label = "Beach Café"
                setting_val = "beach_cafe"
                filter_scene = "beach_cafe"
            elif "goa" in opt_str:
                setting_label = "Goa"
                setting_val = "goa"
                filter_scene = None
                session.extracted_cues.spatial.region = "Goa"
            elif "restaurant" in opt_str or "caf" in opt_str:
                setting_label = "Restaurant / Café"
                setting_val = "cafe"
                filter_scene = "cafe"
            elif "beach" in opt_str:
                setting_label = "Beachside"
                setting_val = "beach"
                filter_scene = "beach"
            elif "hotel" in opt_str or "resort" in opt_str:
                setting_label = "Hotel / Resort"
                setting_val = "hotel_resort"
                filter_scene = "hotel_resort"
            elif "street" in opt_str or "market" in opt_str:
                setting_label = "Street / Market"
                setting_val = "street_food"
                filter_scene = "street_food"
            elif "pharmacy" in opt_str or "chemist" in opt_str:
                setting_label = "Pharmacy"
                setting_val = "pharmacy"
                filter_scene = None
                session.extracted_cues.visual_concepts.extend(["pharmacy", "medicine"])
                session.raw_query = f"{session.raw_query} pharmacy medicine"
            elif "hospital" in opt_str or "clinic" in opt_str:
                setting_label = "Hospital / Clinic"
                setting_val = "clinic"
                filter_scene = None
                session.extracted_cues.visual_concepts.extend(["clinic", "hospital", "medicine"])
                session.raw_query = f"{session.raw_query} hospital clinic medicine"
            elif "green" in opt_str or "floral" in opt_str or "dress" in opt_str:
                setting_label = "Green Dress"
                setting_val = "screenshot"
                filter_scene = None
                session.extracted_cues.visual_concepts.extend(["dress", "green dress", "screenshot"])
                session.raw_query = f"{session.raw_query} green dress screenshot shopping"
            elif "home" in opt_str:
                setting_label = "Home"
                setting_val = "home"
                filter_scene = "home"
                session.extracted_cues.visual_concepts.append("medicine")
                session.raw_query = f"{session.raw_query} home medicine"
            else:
                setting_label = str(option_val)
                setting_val = setting_label.lower().replace(" ", "_")
                filter_scene = setting_val
                session.raw_query = f"{session.raw_query} {setting_label}"

            # Add confirmed Tier 1 chip
            session.chips.append(CueChip(
                id=f"chip_tier1_{session.turn_count}",
                type="setting",
                label=f"☕ {setting_label}",
                value=setting_val,
                status="user_selected_tier_1",
                icon="check-circle"
            ))
            session.extracted_cues.spatial.setting = setting_val

        # 2. Process Tier 2 selection (e.g. ["Restaurant"] or ["Friends", "Evening"])
        cues_list = refine_req.selected_cues or refine_req.recognized_cues
        if cues_list:
            for cue_text in cues_list:
                cue_lower = cue_text.lower().strip()
                if "restaurant" in cue_lower or "cafe" in cue_lower or "coffee" in cue_lower:
                    filter_scene = "cafe"
                    cue_type = "setting"
                    session.extracted_cues.spatial.setting = "cafe"
                elif cue_lower in ["beach", "hotel", "outdoor"]:
                    filter_scene = cue_lower
                    cue_type = "setting"
                    session.extracted_cues.spatial.setting = cue_lower
                elif "dog" in cue_lower or "pet" in cue_lower:
                    cue_type = "people"
                    session.extracted_cues.social.companion_type = "dog"
                elif cue_lower in ["friends", "friend", "family", "group"]:
                    cue_type = "people"
                    session.extracted_cues.social.companion_type = cue_lower
                elif cue_lower in ["evening", "night", "morning", "sunset", "sunny"]:
                    cue_type = "temporal"
                    session.extracted_cues.temporal.time_of_day = cue_lower
                elif cue_lower in ["celebration", "cozy"]:
                    cue_type = "vibe"
                    session.extracted_cues.affective_vibe = cue_lower
                else:
                    cue_type = "activity"

                session.chips.append(CueChip(
                    id=f"chip_tier2_{abs(hash(cue_text)) % 10000}",
                    type=cue_type,
                    label=f"✨ {cue_text}",
                    value=cue_text,
                    status="user_selected_tier_2",
                    icon="tag"
                ))

        if refine_req.query_addition:
            session.raw_query = f"{session.raw_query} {refine_req.query_addition}"

        # 3. Execute refined hybrid retrieval
        candidates, metrics, relaxed = global_retriever.search(
            query=session.raw_query,
            cues=session.extracted_cues,
            active_chips=session.chips,
            top_k=refine_req.top_k,
            turn_count=session.turn_count,
            filter_scene=filter_scene
        )

        session.candidate_photo_ids = [c.photo_id for c in candidates]
        session.confidence_score = metrics.top1_score

        # 4. Determine next recovery ladder step if still weak
        recovery_prompt: Optional[RecoveryPrompt] = None
        if metrics.status == "CONFIDENT":
            session.recovery_tier = "confident"
            session.target_retrieved = True
        elif metrics.status == "WEAK_TIER_1":
            tier1 = self.generate_tier1_prompt(candidates, session.extracted_cues, session.raw_query)
            recovery_prompt = RecoveryPrompt(
                tier=1,
                prompt_type="meaningful_detail_question",
                question_text=tier1.question_text,
                tier1=tier1
            )
            session.recovery_tier = "tier_1_recovery"
        else: # STILL_WEAK_TIER_2 or subsequent turn
            tier2 = self.generate_tier2_prompt(candidates, session.extracted_cues, session.raw_query)
            recovery_prompt = RecoveryPrompt(
                tier=2,
                prompt_type="recognition_cue_cloud",
                question_text=tier2.question_text,
                tier2=tier2
            )
            session.recovery_tier = "tier_2_recognition"

        session.recovery_prompt = recovery_prompt
        global_session_manager.save_session(session)

        return candidates, metrics, recovery_prompt, session

    def _fallback_tier1_prompt(
        self,
        candidates: List[CandidatePhoto],
        cues: Optional[ExtractedMemoryCues],
        query: str
    ) -> Tier1Prompt:
        """Deterministic Tier 1 prompt fallback producing exact required specification."""
        return Tier1Prompt(
            prompt_id=f"pvt_tier1_{abs(hash(query)) % 10000}",
            question_text="Do you remember what kind of place it was?",
            options=[
                Tier1Option(option_id="opt_restaurant_cafe", label="Restaurant / Café", filter_modifier={"venue_type": "restaurant_cafe"}),
                Tier1Option(option_id="opt_beachside", label="Beachside", filter_modifier={"venue_type": "beachside"}),
                Tier1Option(option_id="opt_hotel_resort", label="Hotel / Resort", filter_modifier={"venue_type": "hotel_resort"}),
                Tier1Option(option_id="opt_street_market", label="Street / Market", filter_modifier={"venue_type": "street_market"}),
                Tier1Option(option_id="opt_home", label="Home", filter_modifier={"venue_type": "home"}),
                Tier1Option(option_id="opt_not_sure", label="Not sure", filter_modifier={"action": "escalate_tier2"})
            ]
        )

    def _fallback_tier2_prompt(
        self,
        candidates: List[CandidatePhoto],
        cues: Optional[ExtractedMemoryCues],
        query: str
    ) -> Tier2Prompt:
        """Deterministic Tier 2 prompt fallback producing exact required associative matrix."""
        return Tier2Prompt(
            prompt_id=f"pvt_tier2_{abs(hash(query)) % 10000}",
            question_text="Which feels familiar?",
            cue_groups=[
                Tier2CueGroup(
                    category="Setting",
                    cues=["Restaurant", "Beach", "Hotel", "Outdoor"]
                ),
                Tier2CueGroup(
                    category="Social",
                    cues=["Friends", "Family", "Group"]
                ),
                Tier2CueGroup(
                    category="Atmosphere",
                    cues=["Evening", "Sunny", "Cozy", "Celebration"]
                ),
                Tier2CueGroup(
                    category="Activity",
                    cues=["Travel", "Eating", "Coffee", "Shopping"]
                )
            ]
        )

    def _sanitize_and_parse_json(self, raw_text: str) -> Optional[Dict[str, Any]]:
        clean_text = raw_text.strip()
        clean_text = re.sub(r"^```(?:json)?", "", clean_text, flags=re.MULTILINE)
        clean_text = re.sub(r"```$", "", clean_text, flags=re.MULTILINE).strip()
        match = re.search(r"(\{.*\})", clean_text, re.DOTALL)
        if match:
            clean_text = match.group(1)
        try:
            return json.loads(clean_text)
        except Exception as e:
            logger.error(f"JSON parse error in RecoverEngine: {e}")
            return None

global_recover_engine = RecoverEngine()
