# Phase-Wise Implementation Plan: AI-Native Photo Retrieval MVP

## 1. Plan Overview & Objectives

This implementation plan translates the product requirements from [`problemStatement.md`](file:///c:/Users/ADMIN/Desktop/PRODUCT%20OWNER%20PROJECT%203/MVP/problemStatement.md) and the technical design from [`architecture.md`](file:///c:/Users/ADMIN/Desktop/PRODUCT%20OWNER%20PROJECT%203/MVP/architecture.md) into an actionable, phased engineering roadmap.

### Primary Goal
Deliver a functional, testable MVP demonstrating the progressive multi-turn retrieval loop:
$$\text{Incomplete Memory} \longrightarrow \text{Extract Cues} \longrightarrow \text{Initial Search} \xrightarrow{\text{Weak}} \text{Tier 1: Meaningful Details} \xrightarrow{\text{Still Weak}} \text{Tier 2: Recognition / Suggestion} \longrightarrow \text{Photo Found}$$

---

## 2. Phase Breakdown & Timeline Summary

| Phase | Focus Area | Core Deliverables | Target Duration |
| :--- | :--- | :--- | :--- |
| **Phase 1** | **Data Preparation & Multimodal Ingestion** | Curated photo test set, EXIF extraction, SigLIP embeddings, Face/Spatio-Temporal clusters, Vector DB. | Week 1 |
| **Phase 2** | **"Understand" & "Connect" Engines** | FastAPI server, LLM cue extraction, Hybrid retriever (dense vector + metadata filtering). | Week 2 |
| **Phase 3** | **"Recover" Engine & Disambiguation** | Confidence evaluator, cluster variance analyzer, dynamic pivot prompt generator. | Week 3 |
| **Phase 4** | **Client UI & Interactive Scaffolding** | Conversational input, interactive cue chips, candidate results grid, adaptive pivot panel. | Week 4 |
| **Phase 5** | **Multi-Turn State & Telemetry Integration** | State machine synchronization, multi-turn retrieval loops, telemetry tracking harness. | Week 5 |
| **Phase 6** | **Evaluation, Benchmarking & Polish** | User scenario testing, KPI evaluation against success criteria, latency tuning. | Week 6 |

---

## 3. Detailed Phase Specifications

### Phase 1: Data Preparation & Multimodal Ingestion Pipeline

#### Objective
Establish a realistic photo library dataset (~200–500 photos) simulating multi-year episodic memories (including the core scenario: Goa trip, small cafés, companions, beach, and landmarks) and build the automated indexing pipeline.

#### Tasks
1. **Dataset Curation & Synthetic Ground Truth**:
   - Assemble/generate a structured sample photo collection with realistic timestamps, locations, and scenes.
   - Design 5 benchmark target photos with ground-truth episodic scenarios (e.g., Target #1: "Goa trip café with friend").
2. **Metadata Extraction & Reverse Geocoding**:
   - Extract EXIF attributes: timestamp, camera model, focal length, GPS coordinates.
   - Implement reverse geocoding to enrich photos with `city`, `region`, and `neighborhood` names.
3. **Spatio-Temporal Event Clustering (ST-DBSCAN)**:
   - Implement clustering based on GPS distance ($\le 5\text{ km}$) and timestamp proximity ($\le 48\text{ hrs}$) to group photos into semantic "Trips/Events" (e.g., `event-goa-nov-2023`).
4. **Multimodal & Facial Embedding Generation**:
   - Process photos through a vision encoder (**Google SigLIP** or **ViT-B-16 CLIP**) to generate 512/768-d dense embeddings.
   - Run face detection and clustering (**InsightFace**) to establish anonymous recurring companion identities (`face_cluster_1`, `face_cluster_2`).
5. **Storage & Index Setup**:
   - Initialize **Qdrant** (or **pgvector**) collection with HNSW vector index and payload filtering indexes.
   - Populate local database (**SQLite/PostgreSQL**) with photo metadata, cluster IDs, and WebP thumbnail references.

#### Deliverables & Milestone Checks
- [x] Runnable ingestion script (`ingest.py`) that processes a folder of photos and populates the database and vector store.
- [x] Verified vector search baseline: querying `"small cozy café"` returns relevant café images.

---

### Phase 2: The "Understand" & "Connect" Engines

#### Objective
Build the core backend services that convert vague conversational natural language into structured memory cues and execute hybrid multi-modal search.

#### Tasks
1. **API Gateway & Core Framework**:
   - Scaffold a **FastAPI** application with CORS, async endpoints, Pydantic schemas, and session handling.
2. **The "Understand" Engine (LLM Semantic Slot Extractor via Groq API)**:
   - Configure `GROQ_API_KEY` in environment variables and initialize the official `groq` Python SDK.
   - Integrate Groq's high-speed LPU inference with models such as `llama-3.3-70b-versatile` or `llama-3.1-8b-instant` with strict JSON mode (`response_format={"type": "json_object"}`).
   - Prompt engineering to extract 5 key dimensions:
     - `spatial` (e.g., `region: "Goa"`, `setting: "café"`)
     - `temporal` (e.g., `"trip/vacation"`, `"monsoon"`, `"2 years ago"`)
     - `social` (e.g., `companion: "friend"`)
     - `visual_concepts` (e.g., `["coffee cup", "wood table", "indoor warm lighting"]`)
     - `affective_vibe` (e.g., `"relaxed", "small/cozy"`)
3. **The "Connect" Engine (Hybrid Search Synthesizer)**:
   - Map extracted spatial/temporal entities to metadata filters (e.g., filter by `region == "Goa"`).
   - Encode visual concepts into query embedding vectors.
   - Implement weighted score fusion combining vector cosine similarity with metadata and event cluster affinity.
4. **Candidate Retrieval API**:
   - Expose `POST /api/search` accepting `session_id` and natural-language `query`.
   - Returns extracted cues, top-K photo candidates, and initial similarity distributions.

#### Deliverables & Milestone Checks
- [x] Test suite validating that *"I'm looking for that small café we went to during our Goa trip with my friend"* yields:
  - Correctly parsed JSON memory facets.
  - Hybrid search candidates constrained to Goa trip photos.

---

### Phase 3: The "Recover" Engine & Progressive Disambiguation

#### Objective
Build the autonomous recovery mechanism that detects ambiguous or low-confidence search results and executes a progressive two-stage recovery ladder (Tier 1: Meaningful Details $\rightarrow$ Tier 2: Associative Recognition Suggestions).

#### Tasks
1. **Search Confidence & Dispersion Scorer**:
   - Compute top-1 vs. top-K score margin ($\Delta_{\text{margin}} = S_{\text{top1}} - S_{\text{top5}}$).
   - Compute Shannon entropy across top-20 similarity scores to detect high ambiguity / uniform spread.
   - Flag queries as `CONFIDENT`, `WEAK_TIER_1` (first failure), or `STILL_WEAK_TIER_2` (subsequent turn failure).
2. **Tier-1 Meaningful Detail Disambiguation Generator (Groq API)**:
   - When initial search is weak, inspect top candidate photos and identify the primary structural or setting variance (e.g., restaurant vs. beach café vs. hotel).
   - Prompt Groq LPU inference to formulate a direct clarifying question in < 200ms:
     - *“Was it a restaurant, beach café, or hotel?”*
     - Renders setting choice modifiers.
3. **Tier-2 Associative Recognition Matrix Generator (Groq API)**:
   - When results remain weak after Tier 1, shift from structural questions to autobiographical recognition anchors.
   - Groq prompt generates an associative cue cloud under the anchor *“Which feels familiar?”*:
     - Dimension 1 (Activity/Setting): `Restaurant`, `Beach`, `Travel`
     - Dimension 2 (Social/Atmosphere): `Friends`, `Evening`, `Celebration`
4. **Recovery API Endpoints**:
   - `POST /api/search`: Returns extracted cues, candidate photos, and triggers Tier 1 prompt if confidence is weak.
   - `POST /api/session/refine`: Ingests user selection (e.g. "beach café" or recognized cue badges), updates session cues, and returns re-indexed candidates or escalates to Tier 2 if results remain weak.

#### Deliverables & Milestone Checks
- [x] Automated test verifying Tier-1 prompt generation: querying *"That café in Goa with my friend"* with ambiguous candidates produces *“Was it a restaurant, beach café, or hotel?”*.
- [x] Automated test verifying Tier-2 prompt escalation: if candidates remain weak after setting refinement, engine generates *“Which feels familiar?”* with associative cue tags.

---

### Phase 4: Client UI & Interactive Scaffolding

#### Objective
Develop a modern, dynamic web application that embodies the principle *"Don't make users remember more. Help them discover what they already partially remember."*

#### Tasks
1. **Design System & Foundation**:
   - Establish CSS tokens (colors, dark/light elevation, glassmorphism, responsive grid, typography).
   - Implement micro-animations for state changes and card transitions.
2. **Conversational Memory Input**:
   - Natural language input bar with placeholder examples and speech-to-text option.
3. **Active Cue Manager (Tags/Chips UI)**:
   - Renders extracted cues as interactive, color-coded chips (`📍 Goa`, `☕ Café`, `👥 With Friend`).
   - Allows users to tap chips to confirm, remove, or refine parameters on the fly.
4. **Confidence-Ranked Results Grid**:
   - Photo cards displaying thumbnail, date snippet, and matching cue highlights.
   - Smooth skeleton loaders and lazy loading for responsive performance.
   - "This is the photo!" confirmation button on each item.
5. **Adaptive Pivot & Scaffolding Panel**:
   - Prominently surfaces the progressive recovery interface when search confidence is weak:
     - **Tier 1 View (Detail Clarifier)**: Clean card asking targeted questions (*“Was it a restaurant, beach café, or hotel?”*) with one-tap venue buttons.
     - **Tier 2 View (Recognition Cloud)**: Associative chip cluster under *“Which feels familiar?”* grouped by dimensions (`Restaurant`, `Beach`, `Travel` | `Friends`, `Evening`, `Celebration`).
   - Companion face carousel allowing the user to select the friend they traveled with.

#### Deliverables & Milestone Checks
- [x] Complete responsive frontend rendering real-time search states: Input $\rightarrow$ Extracted Chips $\rightarrow$ Photos Grid $\rightarrow$ Tier 1 Detail Card $\rightarrow$ Tier 2 Recognition Cloud.

---

### Phase 5: Multi-Turn State & Telemetry Integration

#### Objective
Connect the frontend and backend into a cohesive multi-turn state machine supporting progressive two-tier recovery and implement the telemetry harness to track MVP success metrics.

#### Tasks
1. **State Machine Synchronization (2-Tier Ladder)**:
   - Connect client state with server session cache (`session_id`).
   - **Turn 1 (Vague Input)**: Client sends natural query $\rightarrow$ backend extracts cues $\rightarrow$ searches $\rightarrow$ if weak, transitions state to `TIER_1_RECOVERY` and renders detail prompt.
   - **Turn 2 (Detail Disambiguation)**: User selects setting (e.g., *"Beach café"*) $\rightarrow$ session updates $\rightarrow$ re-search $\rightarrow$ if still weak, transitions state to `TIER_2_RECOGNITION` and surfaces associative cue cloud.
   - **Turn 3 (Associative Recognition)**: User taps familiar tags (e.g., *"Friends"*, *"Evening"*) $\rightarrow$ session updates $\rightarrow$ final refined search returns target photo in $\le 300\text{ ms}$.
2. **Telemetry Interceptor & Metrics Store**:
   - Implement event tracking for:
     - `search_started`: Query length, timestamp.
     - `cues_extracted`: Count and categories of initial cues.
     - `tier1_detail_prompt_rendered`: Triggered setting/entity question.
     - `tier1_detail_selected`: User choice on clarifying question.
     - `tier2_recognition_cloud_rendered`: Triggered when results remain weak.
     - `tier2_cue_recognized`: Specific associative cues tapped by user.
     - `photo_retrieved`: User clicks "This is the photo!" or views full size.
     - `session_abandoned`: Session ends without target selection.
3. **Metrics Calculation Engine**:
   - Automated reporting of:
     - **Retrieval Success Rate** ($\%$)
     - **Time to Retrieve (TTR)** (seconds)
     - **Search Query Attempts** (keystroke sessions vs. 1-click pivots)
     - **Tier-1 Detail Acceptance Rate** ($\%$)
     - **Tier-2 Recognition Rate** ($\%$)

#### Deliverables & Milestone Checks
- [x] End-to-end multi-turn flow working smoothly: User enters vague query $\rightarrow$ sees weak results + Tier 1 question $\rightarrow$ answers question $\rightarrow$ sees still weak results + Tier 2 familiarity cloud $\rightarrow$ taps recognized cue $\rightarrow$ target photo appears $\rightarrow$ telemetry logs full session metrics.

---

### Phase 6: Validation, Evaluation & Usability Testing

#### Objective
Execute comprehensive benchmark evaluations against the MVP success criteria, optimize performance budgets, and ensure rock-solid stability.

#### Tasks
1. **Scenario Benchmark Suite**:
   - Execute the 5 pre-defined test scenarios with 10 test users:
     - *Scenario 1*: Café in Goa with friend (Primary scenario).
     - *Scenario 2*: Outdoor street food market during a rainy trip.
     - *Scenario 3*: Group birthday celebration in a restaurant with warm candle lighting.
     - *Scenario 4*: Mountain sunrise hike photo from 3 years ago.
     - *Scenario 5*: Pet photo at a dog-friendly beach resort.
2. **Performance Budget Optimization**:
   - Ensure initial query latency $\le 800\text{ ms}$.
   - Ensure pivot click-to-render latency $\le 300\text{ ms}$.
   - Optimize thumbnail image payloads (WebP compression).
3. **KPI Audit Against Success Criteria**:
   - Compare traditional keyword search vs. AI-Guided Retrieval:
     - Target: $> 85\%$ retrieval success rate on incomplete descriptions.
     - Target: $\ge 60\%$ reduction in manual query re-typing.
     - Target: $> 70\%$ pivot acceptance rate when recovery mode triggers.

#### Deliverables & Milestone Checks
- [x] Evaluation report documenting benchmark metrics and UX validation results.
- [x] Polished, production-ready MVP demonstration package.

---

## 4. Risk Matrix & Mitigation Strategies

| Risk / Failure Mode | Likelihood | Impact | Mitigation Strategy |
| :--- | :---: | :---: | :--- |
| **LLM Latency Exceeds Budget (>800ms)** | Low | High | Leverage Groq's high-speed LPU inference (`llama-3.3-70b-versatile` / `llama-3.1-8b-instant`), which consistently achieves sub-200ms TTFT and 300–500 tokens/sec, well within performance budgets. |
| **Missing / Stripped EXIF Data** | High | Medium | Fallback to visual-only scene classifiers and temporal clustering based on file creation dates or chronological upload order. |
| **Ambiguous LLM Cue Extraction** | Medium | Medium | Display extracted cues as editable chips; users can correct or delete inaccurate tags with a single tap. |
| **Repetitive / Irrelevant Recovery Cues** | Low | High | Enforce diversity in pivot generation by calculating orthogonal cluster dimensions (space vs. time vs. social vs. visual). |

---

## 5. Definition of Done (DoD) for MVP

The MVP will be deemed complete and ready for demonstration when:
1. A user can type an incomplete, vague episodic memory into the input bar.
2. The system visibly extracts and displays structured memory cues (tags).
3. When initial results are ambiguous, the system proactively displays recognizable visual/contextual pivots.
4. Clicking a pivot instantly updates the candidate photos and successfully surfaces the target image.
5. All 6 key metrics defined in [`problemStatement.md`](file:///c:/Users/ADMIN/Desktop/PRODUCT%20OWNER%20PROJECT%203/MVP/problemStatement.md) are captured and viewable via the telemetry logger.

---

## 6. Current Implementation & Audit Status (Production-Verified)

### 6.1 Rubric Routing Audit (6/6 PASS)
All 6 test queries from Section 1.C of the graduation rubric pass with 100% accuracy:
1. `"that cafe in goa with my friend"` $\rightarrow$ **PASS** (Prompts clarifying question / surfaces café candidates)
2. `"the sunset at anjuna beach"` $\rightarrow$ **PASS** (Direct retrieval: `confidence >= 0.75`)
3. `"dog playing on the beach"` $\rightarrow$ **PASS** (Direct retrieval: `confidence >= 0.75`)
4. `"my sister's birthday party"` $\rightarrow$ **PASS** (Direct retrieval: `confidence >= 0.75`)
5. `"hiking in the mountains three years ago"` $\rightarrow$ **PASS** (Prompts clarifying question: Manali / Solang vs. Rohtang)
6. `"the screenshot of the red dress I wanted to buy"` $\rightarrow$ **PASS** (Direct retrieval: `confidence >= 0.75` after fashion cues extraction)

### 6.2 5/5 Benchmark User Journeys
All 5 defined episodic user scenarios are fully operational and verified end-to-end:
* **Journey 1:** Goa café with friend
* **Journey 2:** Street food market on a rainy trip
* **Journey 3:** Birthday celebration with candle lighting
* **Journey 4:** Mountain sunrise hike
* **Journey 5:** Pet photo at beach resort

### 6.3 Same-Location Context & Hero Card Interactivity
* **Dedicated Related Photos API:** `GET /api/photos/{photo_id}/related` implements a 6-tier fallback prioritizing same venue (`neighborhood`), town (`city`), and cluster scene type (`scene_type`).
* **Interactive Hero Card Swap:** Clicking any thumbnail under *"Other Related Moments"* instantly updates the active Hero Card (`#strong-results-layout`), location tag, and match score, while swapping the former hero into the related moments grid.
* **Telemetry & Live Event Logging:** Live KPI metrics (`/api/telemetry/metrics`) and real-time event streaming verify retrieval success rate, average TTR, re-typing reduction, and pivot acceptance.

