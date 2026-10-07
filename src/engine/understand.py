import re
import json
import logging
from typing import List, Dict, Any, Tuple, Optional
from groq import Groq

from src.config import GROQ_API_KEY, GROQ_MODEL, GROQ_FALLBACK_MODELS
from src.engine.schemas import (
    ExtractedMemoryCues, SpatialCue, TemporalCue, SocialCue, CueChip
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert cognitive memory slot extractor for an AI-native episodic photo retrieval engine.
Human episodic memory is fuzzy, relational, and emotional. Your task is to analyze vague conversational queries
(e.g., "that small café we went to during our Goa trip with my friend") and parse them into structured memory facets.

You MUST respond strictly with a valid JSON object following this exact schema:
{
  "spatial": {
    "region": "string or null (e.g. Goa, Mumbai, Manali, Pondicherry, Bangalore)",
    "neighborhood": "string or null (e.g. Fontainhas, Bandra, Solang)",
    "setting": "string or null (e.g. cafe, beach, mountain, restaurant, street food, resort)",
    "environment": "string or null (e.g. indoor, outdoor, cozy, warm lighting)"
  },
  "temporal": {
    "relative_concept": "string or null (e.g. trip, vacation, birthday, weekend)",
    "season": "string or null (e.g. monsoon, summer, winter)",
    "time_frame": "string or null (e.g. 2 years ago, recent)",
    "time_of_day": "string or null (e.g. sunrise, morning, afternoon, evening, night)"
  },
  "social": {
    "companion_type": "string or null (e.g. friend, friends, family, dog/pet, solo)",
    "group_size": "string or null (e.g. duo, small group, group)",
    "companion_names": ["list of companion names if mentioned, e.g. Alex, Priya, Rohan"]
  },
  "visual_concepts": ["list of explicit or implicit visual elements, e.g. coffee, wood table, candles, umbrella, cake"],
  "affective_vibe": "string or null (e.g. cozy, relaxed, celebratory, adventurous, rainy)",
  "confidence_score": 0.0 to 1.0 (how confident you are in the semantic extraction),
  "specificity_score": 0.0 to 1.0 (query specificity: 0.1 for 'trip' or 'food', 0.8+ for detailed multi-cue queries)
}

Do not include any conversational explanations or markdown outside the JSON block. Output raw JSON only."""

# Heuristic dictionaries for resilient offline/fallback extraction
KNOWN_REGIONS = {
    "goa": "Goa",
    "panaji": "Goa",
    "fontainhas": "Goa",
    "anjuna": "Goa",
    "calangute": "Goa",
    "palolem": "Goa",
    "mumbai": "Mumbai",
    "bandra": "Mumbai",
    "marine drive": "Mumbai",
    "manali": "Manali",
    "solang": "Manali",
    "himachal": "Manali",
    "pondicherry": "Pondicherry",
    "puducherry": "Pondicherry",
    "bangalore": "Bangalore",
    "bengaluru": "Bangalore"
}

KNOWN_SETTINGS = {
    "cafe": "cafe",
    "café": "cafe",
    "coffee": "cafe",
    "bistro": "cafe",
    "restaurant": "restaurant",
    "dining": "restaurant",
    "dinner": "restaurant",
    "beach": "beach",
    "coast": "beach",
    "sea": "beach",
    "ocean": "beach",
    "mountain": "mountain",
    "hike": "mountain",
    "trek": "mountain",
    "trail": "mountain",
    "peaks": "mountain",
    "street food": "street_food",
    "food market": "street_food",
    "tea stall": "street_food",
    "chai": "street_food",
    "party": "celebration",
    "birthday": "celebration"
}

KNOWN_SOCIAL = {
    "friend": ("friend", "duo"),
    "friends": ("friends", "small group"),
    "alex": ("friend", "duo"),
    "priya": ("friend", "duo"),
    "rohan": ("friend", "duo"),
    "family": ("family", "group"),
    "dog": ("dog", "pet"),
    "pet": ("pet", "pet"),
    "puppy": ("dog", "pet"),
    "group": ("friends", "group")
}

class GroqCueExtractor:
    """
    Cognitive Semantic Slot Extractor.
    Translates unstructured human episodic memories into structured dimensional cues
    using Groq API LPU inference with resilient local fallback.
    """
    def __init__(self, api_key: str = GROQ_API_KEY, model: str = GROQ_MODEL):
        self.api_key = api_key
        self.preferred_model = model
        self.client: Optional[Groq] = None
        self._cache: Dict[str, Tuple[ExtractedMemoryCues, List[CueChip]]] = {}
        if self.api_key:
            try:
                self.client = Groq(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Groq client: {e}")

    def extract_cues(self, query: str) -> Tuple[ExtractedMemoryCues, List[CueChip]]:
        """
        Extracts structured episodic memory cues from natural language query.
        Returns both the structured Pydantic object and a list of interactive UI chips.
        """
        norm_key = re.sub(r"[^\w\s]", "", query).strip().lower()
        if norm_key in self._cache:
            cues_cached, chips_cached = self._cache[norm_key]
            # Return fresh copies
            return cues_cached.model_copy(deep=True), [c.model_copy(deep=True) for c in chips_cached]

        cues: Optional[ExtractedMemoryCues] = None

        if self.client:
            # Try primary model then fallbacks
            models_to_try = [self.preferred_model]
            for fb in GROQ_FALLBACK_MODELS:
                if fb not in models_to_try:
                    models_to_try.append(fb)

            for model_name in models_to_try:
                try:
                    cues = self._call_groq_api(query, model_name)
                    if cues:
                        break
                except Exception as e:
                    logger.warning(f"Groq extraction failed with model {model_name}: {e}")

        # Fallback to local heuristic parser if Groq was unavailable or failed
        if not cues:
            cues = self._fallback_heuristic_extraction(query)

        cues.raw_query = query
        chips = self.generate_chips(cues)
        self._cache[norm_key] = (cues, chips)
        return cues, chips

    def _call_groq_api(self, query: str, model_name: str) -> Optional[ExtractedMemoryCues]:
        if not self.client:
            return None

        response = self.client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=500
        )

        raw_text = response.choices[0].message.content or ""
        parsed_json = self._sanitize_and_parse_json(raw_text)
        if not parsed_json:
            return None

        spatial = SpatialCue(**(parsed_json.get("spatial") or {}))
        temporal = TemporalCue(**(parsed_json.get("temporal") or {}))
        social = SocialCue(**(parsed_json.get("social") or {}))

        return ExtractedMemoryCues(
            spatial=spatial,
            temporal=temporal,
            social=social,
            visual_concepts=parsed_json.get("visual_concepts") or [],
            affective_vibe=parsed_json.get("affective_vibe"),
            confidence_score=float(parsed_json.get("confidence_score", 0.85)),
            specificity_score=float(parsed_json.get("specificity_score", 0.7)),
            raw_query=query
        )

    def _sanitize_and_parse_json(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """Defensively parses JSON from LLM output, stripping markdown backticks."""
        clean_text = raw_text.strip()
        # Remove markdown code blocks if present
        clean_text = re.sub(r"^```(?:json)?", "", clean_text, flags=re.MULTILINE)
        clean_text = re.sub(r"```$", "", clean_text, flags=re.MULTILINE).strip()

        # Extract the outermost JSON object
        match = re.search(r"(\{.*\})", clean_text, re.DOTALL)
        if match:
            clean_text = match.group(1)

        try:
            return json.loads(clean_text)
        except Exception as e:
            logger.error(f"Failed to parse JSON from LLM: {e}. Raw content: {raw_text[:200]}")
            return None

    def _fallback_heuristic_extraction(self, query: str) -> ExtractedMemoryCues:
        """Deterministic rule-based slot extraction when offline or during API outage."""
        lower_q = query.lower()
        spatial = SpatialCue()
        temporal = TemporalCue()
        social = SocialCue()
        visual_concepts = []
        affective_vibe = None

        # 1. Detect Spatial
        for kw, reg in KNOWN_REGIONS.items():
            if re.search(rf"\b{re.escape(kw)}\b", lower_q):
                spatial.region = reg
                break

        for kw, set_type in KNOWN_SETTINGS.items():
            if re.search(rf"\b{re.escape(kw)}\b", lower_q):
                spatial.setting = set_type
                break

        if "fontainhas" in lower_q:
            spatial.neighborhood = "Fontainhas"
        elif "bandra" in lower_q:
            spatial.neighborhood = "Bandra"
        elif "solang" in lower_q:
            spatial.neighborhood = "Solang"

        if "indoor" in lower_q or "inside" in lower_q:
            spatial.environment = "indoor"
        elif "outdoor" in lower_q or "outside" in lower_q:
            spatial.environment = "outdoor"

        # 2. Detect Temporal
        if "trip" in lower_q or "vacation" in lower_q:
            temporal.relative_concept = "trip"
        elif "birthday" in lower_q:
            temporal.relative_concept = "birthday"

        if "monsoon" in lower_q or "rain" in lower_q or "rainy" in lower_q:
            temporal.season = "monsoon"
        elif "summer" in lower_q:
            temporal.season = "summer"
        elif "winter" in lower_q:
            temporal.season = "winter"

        if "sunrise" in lower_q:
            temporal.time_of_day = "sunrise"
        elif "morning" in lower_q:
            temporal.time_of_day = "morning"
        elif "evening" in lower_q or "sunset" in lower_q:
            temporal.time_of_day = "evening"
        elif "night" in lower_q:
            temporal.time_of_day = "night"

        # 3. Detect Social
        for kw, (comp_type, grp_size) in KNOWN_SOCIAL.items():
            if re.search(rf"\b{re.escape(kw)}\b", lower_q):
                social.companion_type = comp_type
                social.group_size = grp_size
                if kw in ["alex", "priya", "rohan"]:
                    social.companion_names.append(kw.capitalize())
                break

        # 4. Visual concepts
        visual_keywords = [
            "coffee", "tea", "cake", "candle", "candles", "umbrella", "waves", "sand",
            "wood table", "peaks", "snow", "trail", "street food", "pastry", "cutting chai",
            "golden retriever", "dog"
        ]
        for vk in visual_keywords:
            if vk in lower_q:
                visual_concepts.append(vk)

        # 5. Affective vibe
        if "cozy" in lower_q or "small" in lower_q:
            affective_vibe = "cozy"
        elif "party" in lower_q or "celebration" in lower_q:
            affective_vibe = "celebratory"
        elif "rain" in lower_q:
            affective_vibe = "rainy"
        elif "hike" in lower_q or "sunrise" in lower_q:
            affective_vibe = "adventurous"

        # Specificity score
        word_count = len(query.split())
        specificity = min(1.0, max(0.2, word_count / 10.0))

        return ExtractedMemoryCues(
            spatial=spatial,
            temporal=temporal,
            social=social,
            visual_concepts=visual_concepts,
            affective_vibe=affective_vibe,
            confidence_score=0.80,
            specificity_score=specificity,
            raw_query=query
        )

    def generate_chips(self, cues: ExtractedMemoryCues) -> List[CueChip]:
        """
        Converts extracted memory cues into interactive, color-coded UI chips.
        """
        chips: List[CueChip] = []
        chip_counter = 1

        # Place / Region chip
        if cues.spatial.region:
            chips.append(CueChip(
                id=f"chip_geo_{chip_counter}",
                type="place",
                label=f"📍 {cues.spatial.region}",
                value=cues.spatial.region,
                status="confirmed",
                icon="map-pin"
            ))
            chip_counter += 1

        # Setting chip
        if cues.spatial.setting:
            setting_labels = {
                "cafe": "☕ Café",
                "restaurant": "🍽️ Restaurant",
                "beach": "🏖️ Beach",
                "mountain": "⛰️ Mountain / Hike",
                "street_food": "🍲 Street Food",
                "celebration": "🎂 Celebration"
            }
            label = setting_labels.get(cues.spatial.setting.lower(), f"🏛️ {cues.spatial.setting.title()}")
            chips.append(CueChip(
                id=f"chip_setting_{chip_counter}",
                type="setting",
                label=label,
                value=cues.spatial.setting,
                status="active",
                icon="coffee" if cues.spatial.setting.lower() == "cafe" else "compass"
            ))
            chip_counter += 1

        # Social / Companion chip
        if cues.social.companion_type:
            comp_type = cues.social.companion_type.lower()
            if comp_type in ["friend", "friends"]:
                label = "👥 With Friend"
            elif comp_type in ["dog", "pet"]:
                label = "🐕 Pet / Dog"
            elif comp_type == "family":
                label = "👨‍👩‍👧 Family"
            else:
                label = f"👥 {cues.social.companion_type.title()}"

            chips.append(CueChip(
                id=f"chip_social_{chip_counter}",
                type="people",
                label=label,
                value=cues.social.companion_type,
                status="active",
                icon="users"
            ))
            chip_counter += 1

        # Temporal / Event chip
        if cues.temporal.relative_concept:
            concept = cues.temporal.relative_concept.title()
            if cues.spatial.region:
                label = f"🌴 {cues.spatial.region} {concept}"
            else:
                label = f"🌴 {concept}"
            chips.append(CueChip(
                id=f"chip_temporal_{chip_counter}",
                type="temporal",
                label=label,
                value=cues.temporal.relative_concept,
                status="active",
                icon="calendar"
            ))
            chip_counter += 1

        # Season or time of day
        if cues.temporal.season:
            chips.append(CueChip(
                id=f"chip_season_{chip_counter}",
                type="temporal",
                label=f"🌧️ {cues.temporal.season.title()}",
                value=cues.temporal.season,
                status="active",
                icon="cloud-rain"
            ))
            chip_counter += 1
        elif cues.temporal.time_of_day:
            chips.append(CueChip(
                id=f"chip_tod_{chip_counter}",
                type="temporal",
                label=f"🌅 {cues.temporal.time_of_day.title()}",
                value=cues.temporal.time_of_day,
                status="active",
                icon="sun"
            ))
            chip_counter += 1

        # Vibe chip
        if cues.affective_vibe:
            chips.append(CueChip(
                id=f"chip_vibe_{chip_counter}",
                type="vibe",
                label=f"✨ {cues.affective_vibe.title()}",
                value=cues.affective_vibe,
                status="active",
                icon="sparkles"
            ))
            chip_counter += 1

        # Key visual items (up to 2 chips)
        for vc in cues.visual_concepts[:2]:
            chips.append(CueChip(
                id=f"chip_visual_{chip_counter}",
                type="visual",
                label=f"🔍 {vc.title()}",
                value=vc,
                status="active",
                icon="tag"
            ))
            chip_counter += 1

        return chips

    def _generate_dynamic_clarification_with_groq(self, raw_query: str, cues: ExtractedMemoryCues) -> Optional[Dict[str, Any]]:
        """Uses Groq LPU to produce an intelligent, human-friendly clarification question and options for novel memories."""
        if not self.client:
            return None

        prompt = f"""You are a human episodic memory assistant. The user remembered an incomplete photo memory:
"{raw_query}"

Generate ONE meaningful, natural, easy-to-answer contextual clarification question to help retrieve the photo, along with 4 distinct, helpful selectable options.

Output strictly valid JSON with no markdown wrapping:
{{
  "clarification_question": "One natural question (e.g. 'Do you remember what kind of food you were having?')",
  "clarification_options": [
    {{"label": "Short Option 1", "value": "Value 1", "icon": "coffee"}},
    {{"label": "Short Option 2", "value": "Value 2", "icon": "map-pin"}},
    {{"label": "Short Option 3", "value": "Value 3", "icon": "users"}},
    {{"label": "Short Option 4", "value": "Value 4", "icon": "home"}}
  ],
  "recognition_cues": ["Cue 1", "Cue 2", "Cue 3", "Cue 4", "Cue 5"]
}}
Allowed icons: coffee, map-pin, waves, hotel, shopping-bag, home, users, activity, cross, plane, sparkles, tag, mountain, trees, sun, car, receipt, smartphone."""

        try:
            completion = self.client.chat.completions.create(
                model=self.preferred_model,
                messages=[
                    {"role": "system", "content": "You generate helpful photo memory recall questions. Output pure JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=250
            )
            content = completion.choices[0].message.content or ""
            parsed = self._sanitize_and_parse_json(content)
            if parsed and "clarification_question" in parsed and "clarification_options" in parsed:
                opts = []
                for i, o in enumerate(parsed["clarification_options"][:5]):
                    opts.append({
                        "option_id": f"dyn_opt_{i+1}",
                        "label": o.get("label", ""),
                        "value": o.get("value", o.get("label", "")),
                        "icon": o.get("icon", "compass")
                    })
                return {
                    "is_sufficient": False,
                    "clarification_question": parsed["clarification_question"],
                    "clarification_options": opts,
                    "recognition_cues": parsed.get("recognition_cues", ["Context", "Memory", "Moment"])
                }
        except Exception as e:
            logger.warning(f"Dynamic Groq question generation failed: {e}")
        return None

    def check_cue_sufficiency(self, cues: ExtractedMemoryCues, raw_query: str) -> Dict[str, Any]:
        """
        Internal decision step after memory understanding:
        "Do I have enough useful contextual information to make a meaningful retrieval attempt?"
        Does NOT expose technical scores or completeness metrics to the user.
        Generates contextual clarification questions tailored to the specific memory domain.
        """
        q_lower = raw_query.lower()

        # Check sufficiency:
        specific_settings = {"cafe", "restaurant", "beach", "hotel", "resort", "mountain", "street_food", "celebration", "pharmacy", "hospital", "clinic", "shop", "boutique"}
        setting_val = (cues.spatial.setting or "").lower()
        has_setting = setting_val in specific_settings or (bool(setting_val) and setting_val not in ["trip", "vacation", "holiday", "tour", "travel", "photo", "picture", "moment", "outing", "outdoor", "day"])

        has_region = bool(cues.spatial.region or cues.spatial.neighborhood)
        has_social = bool(cues.social.companion_type or cues.social.companion_names)
        has_temporal = bool(cues.temporal.relative_concept or cues.temporal.season or cues.temporal.time_of_day)
        has_visual = bool(cues.visual_concepts)

        dimension_count = sum([has_region, has_setting, has_social, has_temporal, has_visual])

        # 1. Medicine / Health
        if any(k in q_lower for k in ["medicine", "pill", "tablet", "prescription", "doctor", "pharmacy"]):
            has_place = bool(any(k in q_lower for k in ["home", "pharmacy", "hospital", "clinic", "travel", "house", "counter"]) or cues.spatial.region)
            if not has_place:
                return {
                    "is_sufficient": False,
                    "clarification_question": "Do you remember where you were when you took it?",
                    "clarification_options": [
                        {"option_id": "opt_home", "label": "Home", "value": "Home", "icon": "home"},
                        {"option_id": "opt_hospital", "label": "Hospital / Clinic", "value": "Hospital / Clinic", "icon": "activity"},
                        {"option_id": "opt_pharmacy", "label": "Pharmacy", "value": "Pharmacy", "icon": "cross"},
                        {"option_id": "opt_travel", "label": "Traveling", "value": "Traveling", "icon": "plane"}
                    ],
                    "recognition_cues": ["Home", "Pharmacy", "Hospital", "Medicine Box", "Prescription", "Health App"]
                }
            return {"is_sufficient": True}

        # 2. Shopping / Clothes / Fashion
        if any(k in q_lower for k in ["dress", "shirt", "shoes", "bought", "shopping", "clothes", "fashion"]):
            has_details = bool(
                any(k in q_lower for k in [
                    "red", "blue", "green", "black", "white", "pink", "emerald", "floral",
                    "party", "evening", "zara", "price", "sneakers", "boutique", "brand",
                    "wanted to buy", "buy", "wishlist"
                ])
                or bool(cues.visual_concepts)
            )
            if not has_details:
                return {
                    "is_sufficient": False,
                    "clarification_question": "Do you remember anything about the dress or item?",
                    "clarification_options": [
                        {"option_id": "opt_green_floral", "label": "Emerald Green / Floral", "value": "Emerald Green / Floral", "icon": "sparkles"},
                        {"option_id": "opt_party", "label": "Party / Evening", "value": "Party / Evening", "icon": "sparkles"},
                        {"option_id": "opt_brand", "label": "Zara / Designer", "value": "Zara / Designer", "icon": "shopping-bag"},
                        {"option_id": "opt_price", "label": "Under ₹3000", "value": "Under ₹3000", "icon": "tag"}
                    ],
                    "recognition_cues": ["Emerald Green", "Floral", "Party Dress", "Online Shopping", "Boutique", "Wishlist"]
                }
            return {"is_sufficient": True}

        # 0. Check for generic/vague trip or companion queries lacking a specific location or setting
        # e.g., "That photo from my trip with my friend.", "That photo with my friend.", "A picture from my vacation."
        has_explicit_setting = any(k in q_lower for k in [
            "cafe", "café", "coffee", "restaurant", "beach", "hotel", "resort", "hike", "hiking",
            "mountain", "market", "chai", "street food", "cake", "birthday", "party", "hospital",
            "clinic", "pharmacy", "medicine", "dress", "shopping", "store", "shop"
        ])
        is_generic_vague_query = (
            any(k in q_lower for k in ["trip", "vacation", "holiday", "friend", "friends", "tour", "travel", "outing"])
            and not has_region
            and not has_explicit_setting
        )
        if is_generic_vague_query:
            return {
                "is_sufficient": False,
                "clarification_question": "Can you remember anything about where you were?",
                "clarification_options": [
                    {"option_id": "opt_goa", "label": "Goa", "value": "Goa", "icon": "map-pin"},
                    {"option_id": "opt_cafe", "label": "Café / Restaurant", "value": "Café / Restaurant", "icon": "coffee"},
                    {"option_id": "opt_beach", "label": "Beach / Seaside", "value": "Beach", "icon": "waves"},
                    {"option_id": "opt_hotel", "label": "Hotel / Resort", "value": "Hotel / Resort", "icon": "hotel"},
                    {"option_id": "opt_street", "label": "Street / Market", "value": "Street / Market", "icon": "shopping-bag"},
                    {"option_id": "opt_home", "label": "Home", "value": "Home", "icon": "home"}
                ],
                "recognition_cues": ["Goa", "Beach", "Restaurant", "Hotel", "Sunset", "Road trip", "Friends", "Evening"]
            }

        # If user gave enough specific details, auto-search immediately!
        # Detailed queries (e.g. "That small café we went to during our Goa trip with my friend")
        if (has_setting and (has_region or has_temporal)) or (has_setting and has_social and (has_region or has_temporal)) or (dimension_count >= 3 and has_region):
            return {"is_sufficient": True}

        # 3. Pets / Dog (with word-boundary check so "vacation" does not match "cat")
        if any(re.search(rf"\b{k}\b", q_lower) for k in ["dog", "dogs", "pet", "pets", "puppy", "puppies", "cat", "cats"]):
            if not has_region and not has_setting:
                return {
                    "is_sufficient": False,
                    "clarification_question": "Where was your pet in this photo?",
                    "clarification_options": [
                        {"option_id": "opt_beach", "label": "Beach / Seaside", "value": "Beach", "icon": "waves"},
                        {"option_id": "opt_park", "label": "Park / Outdoors", "value": "Outdoor", "icon": "trees"},
                        {"option_id": "opt_home", "label": "At Home", "value": "Home", "icon": "home"},
                        {"option_id": "opt_trip", "label": "On a Road Trip", "value": "Road Trip", "icon": "car"}
                    ],
                    "recognition_cues": ["Beach", "Golden Retriever", "Playing in sand", "Park", "Backyard", "Living room"]
                }
            return {"is_sufficient": True}

        # 4. Celebration / Birthday / Party
        if any(k in q_lower for k in ["birthday", "cake", "celebrat", "bday"]):
            if not has_setting and not has_region:
                return {
                    "is_sufficient": False,
                    "clarification_question": "Do you remember where or with whom you celebrated?",
                    "clarification_options": [
                        {"option_id": "opt_friends", "label": "With Friends", "value": "Friends", "icon": "users"},
                        {"option_id": "opt_home", "label": "At Home", "value": "Home", "icon": "home"},
                        {"option_id": "opt_restaurant", "label": "Restaurant / Café", "value": "Restaurant / Café", "icon": "coffee"},
                        {"option_id": "opt_cake", "label": "Blowing Birthday Candles", "value": "Birthday Cake", "icon": "sparkles"}
                    ],
                    "recognition_cues": ["Birthday Cake", "Candles", "Party", "Friends", "Balloons", "Evening"]
                }
            return {"is_sufficient": True}

        # 5. Mountain / Hike / Trek
        if any(k in q_lower for k in ["hike", "trek", "mountain", "snow", "trail", "hill"]):
            if not has_region:
                return {
                    "is_sufficient": False,
                    "clarification_question": "Do you remember which place or trail it was?",
                    "clarification_options": [
                        {"option_id": "opt_manali", "label": "Manali / Solang Valley", "value": "Manali", "icon": "mountain"},
                        {"option_id": "opt_forest", "label": "Forest Trail", "value": "Forest Trail", "icon": "trees"},
                        {"option_id": "opt_sunrise", "label": "Sunrise Viewpoint", "value": "Sunrise", "icon": "sun"},
                        {"option_id": "opt_snow", "label": "Snowy Peaks", "value": "Snow Peaks", "icon": "cloud-snow"}
                    ],
                    "recognition_cues": ["Manali", "Solang", "Hiking Trail", "Sunrise", "Mountains", "Backpack"]
                }
            return {"is_sufficient": True}

        # 6. Rain / Monsoon / Street Food
        if any(k in q_lower for k in ["rain", "monsoon", "chai", "tea stall", "street food"]):
            if not has_region:
                return {
                    "is_sufficient": False,
                    "clarification_question": "Do you remember where you were enjoying the food or rain?",
                    "clarification_options": [
                        {"option_id": "opt_mumbai", "label": "Mumbai Street Food", "value": "Mumbai", "icon": "shopping-bag"},
                        {"option_id": "opt_stall", "label": "Tea Stall / Café", "value": "Café / Restaurant", "icon": "coffee"},
                        {"option_id": "opt_sea", "label": "Marine Drive / Sea", "value": "Beach", "icon": "waves"},
                        {"option_id": "opt_car", "label": "Drive in Rain", "value": "Drive", "icon": "car"}
                    ],
                    "recognition_cues": ["Mumbai", "Monsoon", "Cutting Chai", "Street Food", "Umbrella", "Bandra"]
                }
            return {"is_sufficient": True}

        # 7. Document / Screenshot / Receipt
        if any(k in q_lower for k in ["screenshot", "document", "receipt", "ticket", "bill", "invoice", "paper"]):
            has_subject = any(k in q_lower for k in ["dress", "shirt", "shoe", "shoes", "medicine", "prescription", "sneaker", "sneakers", "item", "flight", "hotel"])
            if not has_subject:
                return {
                    "is_sufficient": False,
                    "clarification_question": "What type of document or screenshot was it?",
                    "clarification_options": [
                        {"option_id": "opt_receipt", "label": "Bill / Receipt", "value": "Receipt", "icon": "receipt"},
                        {"option_id": "opt_ticket", "label": "Travel Ticket / Booking", "value": "Ticket", "icon": "ticket"},
                        {"option_id": "opt_app", "label": "App Order / Confirmation", "value": "App Order", "icon": "smartphone"},
                        {"option_id": "opt_clothing", "label": "Item Wishlist / Fashion", "value": "Fashion Wishlist", "icon": "shopping-bag"}
                    ],
                    "recognition_cues": ["Receipt", "Order Confirmation", "Prescription", "Wishlist", "Ticket", "Booking"]
                }
            return {"is_sufficient": True}

        # 8. Trip / Vacation / Outing Scenario
        if any(k in q_lower for k in ["trip", "vacation", "holiday", "tour", "travel"]):
            return {
                "is_sufficient": False,
                "clarification_question": "Can you remember anything about where you were?",
                "clarification_options": [
                    {"option_id": "opt_goa", "label": "Goa", "value": "Goa", "icon": "map-pin"},
                    {"option_id": "opt_cafe", "label": "Café / Restaurant", "value": "Café / Restaurant", "icon": "coffee"},
                    {"option_id": "opt_beach", "label": "Beach", "value": "Beach", "icon": "waves"},
                    {"option_id": "opt_hotel", "label": "Hotel / Resort", "value": "Hotel / Resort", "icon": "hotel"},
                    {"option_id": "opt_street", "label": "Street / Market", "value": "Street / Market", "icon": "shopping-bag"},
                    {"option_id": "opt_home", "label": "Home", "value": "Home", "icon": "home"}
                ],
                "recognition_cues": ["Goa", "Beach", "Restaurant", "Hotel", "Sunset", "Road trip", "Friends", "Evening"]
            }

        # 9. Dynamic Groq Clarification Generation for any other novel memory
        if self.client:
            dynamic_result = self._generate_dynamic_clarification_with_groq(raw_query, cues)
            if dynamic_result:
                return dynamic_result

        # 9. Default Trip / Outing Scenario
        return {
            "is_sufficient": False,
            "clarification_question": "Can you remember anything about where you were?",
            "clarification_options": [
                {"option_id": "opt_goa", "label": "Goa", "value": "Goa", "icon": "map-pin"},
                {"option_id": "opt_cafe", "label": "Café / Restaurant", "value": "Café / Restaurant", "icon": "coffee"},
                {"option_id": "opt_beach", "label": "Beach", "value": "Beach", "icon": "waves"},
                {"option_id": "opt_hotel", "label": "Hotel / Resort", "value": "Hotel / Resort", "icon": "hotel"},
                {"option_id": "opt_street", "label": "Street / Market", "value": "Street / Market", "icon": "shopping-bag"},
                {"option_id": "opt_home", "label": "Home", "value": "Home", "icon": "home"}
            ],
            "recognition_cues": ["Goa", "Beach", "Restaurant", "Hotel", "Sunset", "Road trip", "Friends", "Evening"]
        }

global_cue_extractor = GroqCueExtractor()
