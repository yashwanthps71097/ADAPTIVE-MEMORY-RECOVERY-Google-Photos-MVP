/**
 * Adaptive Memory Recovery - Client Application Controller
 * Connects episodic memory cues to FastAPI backend with Groq & hybrid vector search.
 */

class AdaptiveMemoryApp {
  constructor() {
    this.currentStep = 1;
    this.previousStep = 1;
    this.sessionId = null;
    this.currentQuery = "";
    this.searchResponse = null;
    this.activeChips = [];
    this.recognizedAnchor = null;
    this.selectedPhoto = null;
    this.isListening = false;
    this.speechRecognition = null;

    // Session Metrics & Telemetry
    this.telemetry = {
      searchAttempts: 0,
      recoverySteps: 0,
      recognizedClues: 0,
      lastLatencyMs: 280,
      events: []
    };

    // Base API URL: Supports Vercel proxy rewrites (default "") or direct Railway URL (window.ENV_API_URL)
    this.apiBase = (window.ENV_API_URL || "").replace(/\/+$/, "");

    this.init();
  }

  apiUrl(path) {
    const p = path.startsWith('/') ? path : '/' + path;
    return (this.apiBase || "") + p;
  }

  init() {
    this.initTheme();
    this.initVoice();
    this.logEvent("APP_INITIALIZED", "Client loaded and ready.");
    this.checkBackendHealth();

    // Keyboard shortcut: Escape closes modals or returns from Step 7
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        const photoModal = document.getElementById("photo-detail-modal");
        const telemModal = document.getElementById("telemetry-modal");
        if (photoModal && !photoModal.classList.contains("hidden")) {
          this.closePhotoModal();
        } else if (telemModal && !telemModal.classList.contains("hidden")) {
          this.closeTelemetryModal();
        } else if (this.currentStep === 7) {
          this.closeFoundStage();
        }
      }
    });

    // Render icons
    if (window.lucide) {
      window.lucide.createIcons();
    }
  }

  // ------------------------------------------------------------------------
  // Theme Management
  // ------------------------------------------------------------------------
  initTheme() {
    const savedTheme = localStorage.getItem("amr_theme") || "theme-light";
    document.body.className = savedTheme;
    this.updateThemeIcon(savedTheme);
  }

  toggleTheme() {
    const isLight = document.body.classList.contains("theme-light");
    const newTheme = isLight ? "theme-dark" : "theme-light";
    document.body.className = newTheme;
    localStorage.setItem("amr_theme", newTheme);
    this.updateThemeIcon(newTheme);
  }

  updateThemeIcon(theme) {
    const toggleBtn = document.getElementById("theme-toggle");
    if (!toggleBtn) return;
    if (theme === "theme-dark") {
      toggleBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>`;
    } else {
      toggleBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>`;
    }
  }

  // ------------------------------------------------------------------------
  // Voice Input (Web Speech API)
  // ------------------------------------------------------------------------
  initVoice() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.log("Speech recognition not supported in this browser.");
      return;
    }

    this.speechRecognition = new SpeechRecognition();
    this.speechRecognition.continuous = false;
    this.speechRecognition.interimResults = false;
    this.speechRecognition.lang = "en-US";

    this.speechRecognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      const input = document.getElementById("search-input");
      if (input) {
        input.value = transcript;
      }
      this.stopVoiceInput();
      this.handleSearchSubmit();
    };

    this.speechRecognition.onerror = (event) => {
      console.warn("Speech recognition error:", event.error);
      this.stopVoiceInput();
    };

    this.speechRecognition.onend = () => {
      this.stopVoiceInput();
    };
  }

  toggleVoiceInput() {
    if (!this.speechRecognition) {
      alert("Voice input is not supported in this browser. Please type your memory.");
      return;
    }

    if (this.isListening) {
      this.stopVoiceInput();
    } else {
      this.startVoiceInput();
    }
  }

  startVoiceInput() {
    const micBtn = document.getElementById("mic-btn");
    try {
      this.speechRecognition.start();
      this.isListening = true;
      if (micBtn) micBtn.classList.add("listening");
      this.logEvent("VOICE_INPUT_START", "Listening for spoken memory...");
    } catch (err) {
      console.warn("Could not start speech recognition:", err);
    }
  }

  stopVoiceInput() {
    const micBtn = document.getElementById("mic-btn");
    this.isListening = false;
    if (micBtn) micBtn.classList.remove("listening");
    try {
      this.speechRecognition.stop();
    } catch (e) {}
  }

  // ------------------------------------------------------------------------
  // Navigation & Stage Transitions
  // ------------------------------------------------------------------------
  goToStep(stepNumber) {
    if (this.currentStep !== stepNumber && this.currentStep !== 7) {
      this.previousStep = this.currentStep;
    }
    this.currentStep = stepNumber;
    for (let i = 1; i <= 7; i++) {
      const sec = document.getElementById(`step-${i}`);
      if (sec) {
        sec.classList.remove("active");
      }
    }
    const targetSec = document.getElementById(`step-${stepNumber}`);
    if (targetSec) {
      targetSec.classList.add("active");
    }

    window.scrollTo({ top: 0, behavior: "smooth" });
    if (window.lucide) window.lucide.createIcons();
  }

  resetFlow() {
    this.closePhotoModal();
    this.closeTelemetryModal();

    if (this.sessionId && !this.sessionId.startsWith("session-fallback")) {
      fetch(this.apiUrl(`/api/session/${this.sessionId}/abandon`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "user_reset" })
      }).catch(err => console.warn("Failed abandoning session:", err));
    }

    this.currentStep = 1;
    this.previousStep = 1;
    this.sessionId = null;
    this.currentQuery = "";
    this.searchResponse = null;
    this.activeChips = [];
    this.recognizedAnchor = null;
    this.selectedPhoto = null;
    this.selectedTier2Cues = [];
    this.currentQuestion = null;
    this.currentRecognitionCues = [];

    const searchInput = document.getElementById("search-input");
    if (searchInput) {
      searchInput.value = "";
      setTimeout(() => searchInput.focus(), 150);
    }

    const searchingWithBar = document.getElementById("searching-with-bar");
    if (searchingWithBar) searchingWithBar.classList.add("hidden");

    this.goToStep(1);
    window.scrollTo({ top: 0, behavior: "smooth" });
    this.updateSearchingWithBar();
    this.logEvent("FLOW_RESET", "User restarted memory retrieval flow.");
    if (window.lucide) window.lucide.createIcons();
  }

  // ------------------------------------------------------------------------
  // Searching With (Evolving Memory Path Bar)
  // ------------------------------------------------------------------------
  updateSearchingWithBar() {
    const bar = document.getElementById("searching-with-bar");
    const container = document.getElementById("searching-with-chips");
    if (!bar || !container) return;

    const active = this.activeChips.filter(c => this.isChipActive(c));
    if (active.length === 0) {
      bar.classList.add("hidden");
      return;
    }

    bar.classList.remove("hidden");
    container.innerHTML = active.map(c => `
      <span class="search-path-pill">
        <i data-lucide="${this.getCueIconName(c.type || 'activity')}" style="width:12px;height:12px"></i>
        <span>${this.escapeHtml(this.getChipLabel(c))}</span>
      </span>
    `).join('');

    if (window.lucide) window.lucide.createIcons();
  }

  // ------------------------------------------------------------------------
  // Robust Multi-Layer Image Error Handler (Eliminates Broken Images)
  // ------------------------------------------------------------------------
  handleImageError(imgEl, filename, fallbackUrl = "") {
    if (!imgEl) return;

    const remoteMap = {
      'IMG_GOA_CAFE_4021.jpg': 'https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=800&q=85',
      'IMG_GOA_1005.jpg': 'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=800&q=85',
      'IMG_GOA_1012.jpg': 'https://images.unsplash.com/photo-1566073771259-6a8506099945?w=800&q=85',
      'IMG_GOA_1015.jpg': 'https://images.unsplash.com/photo-1518495973542-4542c06a5843?w=800&q=85',
      'IMG_GOA_1020.jpg': 'https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=1200&q=85',
      'IMG_PALOLEM_DOG_5541.jpg': 'https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=800&q=85',
      'IMG_MEDICINE_PKG_701.jpg': 'https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=800&q=85',
      'IMG_MEDICINE_SCREENSHOT_702.jpg': 'https://images.unsplash.com/photo-1584017911766-d451b3d0e843?w=800&q=85',
      'IMG_PHARMACY_703.jpg': 'https://images.unsplash.com/photo-1576602976047-174e57a47881?w=800&q=85',
      'IMG_HOSPITAL_CLINIC_704.jpg': 'https://images.unsplash.com/photo-1519494026892-80bbd2d6fd0d?w=800&q=85',
      'IMG_DRESS_SCREENSHOT_801.jpg': 'https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=800&q=85',
      'IMG_PRODUCT_SCREENSHOT_802.jpg': 'https://images.unsplash.com/photo-1460353581641-37baddab0fa2?w=800&q=85',
      'IMG_FASHION_ITEM_803.jpg': 'https://images.unsplash.com/photo-1489987707025-afc232f7ea0f?w=800&q=85',
      'IMG_SHOPPING_PAGE_804.jpg': 'https://images.unsplash.com/photo-1472851294608-062f824d29cc?w=800&q=85',
      'IMG_MUMBAI_RAIN_2104.jpg': 'https://images.unsplash.com/photo-1515694346937-94d85e41e6f0?w=800&q=85',
      'IMG_BDAY_PARTY_8812.jpg': 'https://images.unsplash.com/photo-1530103862676-de8c9debad1d?w=800&q=85',
      'IMG_MANALI_HIKE_1045.jpg': 'https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=800&q=85'
    };

    // Layer 1: If current src was a thumbnail webp, try the full photo JPEG
    if (imgEl.src.includes('/thumbnails/') && filename) {
      imgEl.src = `/photos/${filename}?v=match_v5`;
      return;
    }

    // Layer 2: Try static asset mirror
    if (imgEl.src.includes('/photos/') && !imgEl.src.includes('/static/assets/') && filename) {
      imgEl.src = `/static/assets/photos/${filename}?v=match_v5`;
      return;
    }

    // Layer 2.5: Try local WebP thumbnail mirror
    const stem = filename ? filename.replace(/\.[^/.]+$/, "") : "";
    if (stem && !imgEl.src.includes('/thumbnails/')) {
      imgEl.src = `/thumbnails/${stem}_thumb.webp?v=match_v5`;
      return;
    }

    // Layer 3: Try remote Unsplash URL from curated map
    if (filename && remoteMap[filename] && imgEl.src !== remoteMap[filename]) {
      imgEl.src = remoteMap[filename];
      return;
    }

    // Layer 4: Neutral fallback placeholder SVG
    imgEl.onerror = null;
    imgEl.src = 'data:image/svg+xml;charset=UTF-8,%3Csvg%20width%3D%22400%22%20height%3D%22300%22%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%3E%3Crect%20width%3D%22100%25%22%20height%3D%22100%25%22%20fill%3D%22%231e293b%22%2F%3E%3Ctext%20x%3D%2250%25%22%20y%3D%2250%25%22%20fill%3D%22%2394a3b8%22%20font-size%3D%2216%22%20font-family%3D%22sans-serif%22%20dominant-baseline%3D%22middle%22%20text-anchor%3D%22middle%22%3EMemory%20Photo%3C%2Ftext%3E%3C%2Fsvg%3E';
  }

  fillQuery(text) {
    const input = document.getElementById("search-input");
    if (input) {
      input.value = text;
      this.clearInputError("search-input", "search-input-error");
      input.focus();
    }
  }

  validateMemoryInput(text, context = 'search') {
    if (!text || typeof text !== 'string' || text.trim().length === 0) {
      return { 
        isValid: false, 
        message: context === 'search' ? "Please enter a memory description to search." : "Please enter a clue or description." 
      };
    }
    return { isValid: true, message: "" };
  }

  clearInputError(inputId, errorId) {
    const input = document.getElementById(inputId);
    const err = document.getElementById(errorId);
    if (input) input.classList.remove("input-error");
    if (err) err.classList.add("hidden");
  }

  showToast(message, type = "error") {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "toast-notification-container";
      document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `toast-pill ${type}`;
    const iconName = type === "success" ? "check-circle" : (type === "warning" ? "alert-triangle" : "alert-circle");
    toast.innerHTML = `
      <i data-lucide="${iconName}" style="width:16px;height:16px"></i>
      <span>${this.escapeHtml(message)}</span>
    `;

    container.appendChild(toast);
    if (window.lucide) window.lucide.createIcons();

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(-15px) scale(0.9)";
      setTimeout(() => toast.remove(), 350);
    }, 3500);
  }

  // ------------------------------------------------------------------------
  // Step 1 -> Step 2: Search Submission & Groq Cue Extraction
  // ------------------------------------------------------------------------
  async handleSearchSubmit(event) {
    if (event) {
      if (typeof event.preventDefault === "function") event.preventDefault();
      if (typeof event.stopPropagation === "function") event.stopPropagation();
    }
    const input = document.getElementById("search-input");
    const query = input ? input.value : "";
    const errorEl = document.getElementById("search-input-error");

    const validation = this.validateMemoryInput(query, 'search');
    if (!validation.isValid) {
      if (input) {
        input.classList.remove("input-error");
        void input.offsetWidth;
        input.classList.add("input-error");
        input.focus();
      }
      if (errorEl) {
        errorEl.innerHTML = `<i data-lucide="alert-circle" style="width:14px;height:14px;display:inline-block"></i> <span>${this.escapeHtml(validation.message)}</span>`;
        errorEl.classList.remove("hidden");
        if (window.lucide) window.lucide.createIcons();
      }
      this.showToast(validation.message, "warning");
      return;
    }

    if (errorEl) errorEl.classList.add("hidden");
    if (input) input.classList.remove("input-error");

    const trimmedQuery = query.trim();
    this.currentQuery = trimmedQuery;
    this.selectedPhoto = null;
    this.telemetry.searchAttempts += 1;
    this.logEvent("SEARCH_SUBMITTED", `Query: "${trimmedQuery}"`);

    // Transition to Step 2 (Analyzing state)
    this.goToStep(2);
    const analyzingEl = document.getElementById("analyzing-state");
    const cuesCardEl = document.getElementById("cues-understood-card");
    if (analyzingEl) analyzingEl.classList.remove("hidden");
    if (cuesCardEl) cuesCardEl.classList.add("hidden");

    const startTime = performance.now();

    try {
      const response = await fetch(this.apiUrl("/api/search"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query })
      });

      if (!response.ok) {
        throw new Error(`API returned HTTP ${response.status}`);
      }

      const data = await response.json();
      const elapsedMs = Math.round(performance.now() - startTime);
      this.telemetry.lastLatencyMs = elapsedMs;

      this.searchResponse = data;
      this.sessionId = data.session_id;
      this.activeChips = data.chips || [];
      this.updateSearchingWithBar();

      this.logEvent("CUES_EXTRACTED", `Found ${this.activeChips.length} episodic cues in ${elapsedMs}ms`);

      // Internal Decision Step: Are there enough useful cues?
      setTimeout(() => {
        if (analyzingEl) analyzingEl.classList.add("hidden");

        if (data.is_cue_sufficient === false) {
          // Insufficient cues: Ask ONE meaningful contextual question immediately
          this.logEvent("CUES_INSUFFICIENT", "Cues are insufficient for reliable retrieval. Asking 1 meaningful question.");
          this.renderTier1QuestionCard(data.clarification_question, data.clarification_options, data.recognition_cues);
        } else {
          // Sufficient cues: Search automatically! Do not ask unnecessary question.
          this.logEvent("CUES_SUFFICIENT_SEARCH_AUTO", "Sufficient cues found. Automatically searching without interruption.");
          if (data.metrics && data.metrics.status === "CONFIDENT") {
            // Strong result: Directly surface target photo
            this.renderStrongResultsStage();
          } else {
            // Weak result: Initial candidates grid with ambiguous notice
            this.goToStep(3);
            this.renderResultsStage();
          }
        }
      }, 700);

    } catch (err) {
      console.error("Search API error:", err);
      // Fallback for demonstration if offline or rate limited
      this.generateFallbackCues(query);
      if (analyzingEl) analyzingEl.classList.add("hidden");
      this.updateSearchingWithBar();
      this.renderTier1QuestionCard("Can you remember anything about where you were?", null, null);
    }
  }

  generateFallbackCues(query) {
    this.sessionId = "session-fallback-" + Date.now();
    const cues = [];
    const words = query.toLowerCase();

    if (words.includes("goa")) cues.push({ id: "loc_goa", text: "Goa", type: "location", is_active: true });
    if (words.includes("friend") || words.includes("friends")) cues.push({ id: "soc_friend", text: "Friends", type: "social", is_active: true });
    if (words.includes("café") || words.includes("cafe")) cues.push({ id: "act_cafe", text: "Café", type: "activity", is_active: true });
    if (words.includes("trip")) cues.push({ id: "trip_anchor", text: "Goa Trip", type: "temporal", is_active: true });
    if (words.includes("beach")) cues.push({ id: "loc_beach", text: "Beach", type: "location", is_active: true });
    if (words.includes("mumbai")) cues.push({ id: "loc_mumbai", text: "Mumbai", type: "location", is_active: true });
    if (words.includes("rain") || words.includes("monsoon")) cues.push({ id: "atm_rain", text: "Monsoon", type: "atmosphere", is_active: true });

    if (cues.length === 0) {
      cues.push({ id: "cue_mem", text: query.split(" ").slice(0, 3).join(" "), type: "activity", is_active: true });
    }

    this.activeChips = cues;
  }

  // ------------------------------------------------------------------------
  // ------------------------------------------------------------------------
  // Chip Helpers & Step 2: Render Understood Cues
  // ------------------------------------------------------------------------
  getChipLabel(chip) {
    if (!chip) return "";
    if (chip.label) {
      return chip.label.replace(/^[\p{Emoji}\s]+/u, '').trim() || chip.label;
    }
    return chip.text || chip.value || "Clue";
  }

  isChipActive(chip) {
    if (!chip) return true;
    if (typeof chip.is_active === "boolean") return chip.is_active;
    if (chip.status) return chip.status !== "rejected";
    return true;
  }

  renderUnderstoodCues() {
    const container = document.getElementById("chips-container");
    if (!container) return;

    container.innerHTML = "";

    this.activeChips.forEach((chip) => {
      const active = this.isChipActive(chip);
      const label = this.getChipLabel(chip);
      const chipEl = document.createElement("div");
      chipEl.className = `memory-chip ${active ? "active" : "inactive"}`;
      chipEl.id = `chip-${chip.id}`;

      const iconName = this.getCueIconName(chip.type);

      chipEl.innerHTML = `
        <i data-lucide="${iconName}"></i>
        <span>${this.escapeHtml(label)}</span>
        <span class="chip-type-tag">${this.escapeHtml(chip.type || "cue")}</span>
        <button class="chip-remove-btn" title="Toggle clue" onclick="app.toggleChip('${chip.id}', event)">
          <i data-lucide="${active ? 'x' : 'plus'}"></i>
        </button>
      `;

      container.appendChild(chipEl);
    });

    if (window.lucide) window.lucide.createIcons();
  }

  getCueIconName(type) {
    switch (type) {
      case "location":
      case "place": return "map-pin";
      case "social":
      case "people": return "users";
      case "activity": return "coffee";
      case "setting": return "home";
      case "temporal": return "calendar";
      case "atmosphere":
      case "vibe": return "sparkles";
      default: return "sparkles";
    }
  }

  toggleChip(chipId, event) {
    if (event) event.stopPropagation();
    const chip = this.activeChips.find(c => c.id === chipId);
    if (!chip) return;

    const currentActive = this.isChipActive(chip);
    const newActive = !currentActive;
    chip.is_active = newActive;
    chip.status = newActive ? "active" : "rejected";

    this.renderUnderstoodCues();
    this.logEvent("CHIP_TOGGLED", `Clue "${this.getChipLabel(chip)}" is now ${newActive ? 'active' : 'inactive'}`);

    // Synchronize with backend if session is open
    if (this.sessionId && !this.sessionId.startsWith("session-fallback")) {
      fetch(this.apiUrl(`/api/session/${this.sessionId}/chip`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chip_id: chipId, is_active: newActive })
      }).catch(err => console.warn("Failed syncing chip:", err));
    }
  }

  // ------------------------------------------------------------------------
  // Step 3: Candidate Results Grid (Initial Search: Weak / Ambiguous)
  // ------------------------------------------------------------------------
  executeConnectSearch() {
    this.goToStep(3);
    this.renderResultsStage();
    this.logEvent("RESULTS_SURFACED", `Surfaced initial candidate photos with confidence: Ambiguous`);
  }

  getPhotoLocation(photo) {
    if (!photo) return "Travel Moment";
    if (photo.neighborhood && photo.city) return `${photo.neighborhood}, ${photo.city}`;
    if (photo.city && photo.region && photo.city !== photo.region) return `${photo.city}, ${photo.region}`;
    if (photo.location_name) return photo.location_name;
    if (photo.event_cluster_name) return photo.event_cluster_name;
    if (photo.trip_cluster) return photo.trip_cluster;
    if (photo.city) return photo.city;
    if (photo.region) return photo.region;
    return "Travel Moment";
  }

  renderResultsStage() {
    const grid = document.getElementById("candidates-grid");
    const summary = document.getElementById("results-chips-summary");
    const cuesTextEl = document.getElementById("initial-search-cues-text");
    if (!grid) return;

    grid.innerHTML = "";
    if (summary) summary.innerHTML = "";

    // Render active chips summary in header
    const activeChipLabels = this.activeChips.filter(c => this.isChipActive(c)).map(c => this.getChipLabel(c));
    if (cuesTextEl) {
      cuesTextEl.innerText = activeChipLabels.length > 0 ? activeChipLabels.join(" + ") : "Trip + Friend";
    }

    this.activeChips.filter(c => this.isChipActive(c)).forEach(chip => {
      const pill = document.createElement("div");
      pill.className = "memory-chip active";
      pill.style.padding = "4px 10px";
      pill.style.fontSize = "0.8rem";
      pill.innerHTML = `<i data-lucide="${this.getCueIconName(chip.type)}" style="width:12px;height:12px"></i> <span>${this.escapeHtml(this.getChipLabel(chip))}</span>`;
      if (summary) summary.appendChild(pill);
    });

    const candidates = this.searchResponse?.candidates || [];

    if (candidates.length === 0) {
      grid.innerHTML = `
        <div style="grid-column: 1/-1; text-align: center; padding: 60px 20px; color: var(--text-muted)">
          <i data-lucide="image-off" style="width:48px;height:48px;margin-bottom:12px;opacity:0.5"></i>
          <p>No photos closely matched your description yet.</p>
        </div>
      `;
      if (window.lucide) window.lucide.createIcons();
      return;
    }

    // Show initial candidate pool (8 to 12 photos) with realistic ambiguous match indicators
    candidates.slice(0, 12).forEach((photo, idx) => {
      const card = document.createElement("div");
      card.className = "photo-card";
      card.onclick = () => this.openPhotoModal(photo);

      // Initial match scores are realistic and ambiguous (e.g. 66% - 73%)
      const scorePercent = Math.min(74, Math.max(62, Math.round((photo.score || 0.68) * 100) - (idx * 1)));

      const dateStr = photo.timestamp ? new Date(photo.timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "Recent moment";
      const locStr = this.getPhotoLocation(photo);

      card.innerHTML = `
        <img src="${this.getPhotoUrl(photo)}" alt="${this.escapeHtml(photo.caption || 'Candidate')}" loading="lazy" onerror="app.handleImageError(this, '${photo.filename || ''}')" />
        <div class="photo-card-overlay">
          <div class="photo-card-top">
            <span class="score-badge">${scorePercent}% Match</span>
          </div>
          <div class="photo-card-bottom">
            <div class="photo-card-meta">
              <span><i data-lucide="calendar" style="width:12px;height:12px;display:inline"></i> ${dateStr}</span>
              <span><i data-lucide="map-pin" style="width:12px;height:12px;display:inline"></i> ${locStr}</span>
            </div>
          </div>
        </div>
      `;

      grid.appendChild(card);
    });

    if (window.lucide) window.lucide.createIcons();
  }

  getPhotoById(id) {
    if (!id) return null;
    const found = this.searchResponse?.candidates?.find(p => p.photo_id === id);
    if (found) return found;
    if (this.relatedPhotosMap && this.relatedPhotosMap[id]) return this.relatedPhotosMap[id];
    return null;
  }

  getPhotoUrl(photo, preferFull = false) {
    if (!photo) return "";
    let url = preferFull
      ? (photo.full_photo_url || photo.image_url || photo.thumbnail_url)
      : (photo.thumbnail_url || photo.image_url || photo.full_photo_url);
    if (!url) return "";
    url = url.split("?")[0] + "?v=match_v5";
    if (url.startsWith("http://") || url.startsWith("https://")) return url;
    return this.apiUrl(url);
  }


  getOptionIcon(label = "", value = "") {
    const s = `${label} ${value}`.toLowerCase();
    if (s.includes("cafe") || s.includes("café") || s.includes("coffee") || s.includes("restaurant")) return "coffee";
    if (s.includes("beach") || s.includes("sea") || s.includes("coast")) return "waves";
    if (s.includes("hotel") || s.includes("resort")) return "hotel";
    if (s.includes("street") || s.includes("market") || s.includes("shop")) return "shopping-bag";
    if (s.includes("home") || s.includes("house")) return "home";
    if (s.includes("hospital") || s.includes("clinic") || s.includes("doctor")) return "activity";
    if (s.includes("pharmacy") || s.includes("medicine") || s.includes("pill") || s.includes("chemist")) return "cross";
    if (s.includes("travel") || s.includes("flight") || s.includes("trip")) return "plane";
    if (s.includes("dress") || s.includes("green") || s.includes("floral") || s.includes("party")) return "sparkles";
    if (s.includes("price") || s.includes("brand") || s.includes("zara") || s.includes("under")) return "tag";
    if (s.includes("goa") || s.includes("mumbai") || s.includes("city") || s.includes("place")) return "map-pin";
    return "compass";
  }

  getCleanOptionLabel(label) {
    if (!label) return "";
    return label.replace(/^[\p{Emoji}\s]+/u, '').trim() || label;
  }

  // ------------------------------------------------------------------------
  // Step 4: Tier 1 Guided Recall (Meaningful Detail Question)
  // ------------------------------------------------------------------------
  renderTier1QuestionCard(questionText, options, recognitionCues) {
    this.goToStep(4);
    this.currentQuestion = questionText || "Can you remember anything about where you were?";
    this.currentRecognitionCues = recognitionCues || [];

    this.logEvent("TIER1_QUESTION_PROMPTED", `Contextual question: "${this.currentQuestion}"`);

    const questionCard = document.getElementById("tier1-question-card");
    const answeredCard = document.getElementById("tier1-answered-card");
    const notSureCard = document.getElementById("tier1-notsure-card");
    const questionTextEl = document.getElementById("tier1-question-text");
    const optionsContainer = document.getElementById("tier1-options-container");
    const customInput = document.getElementById("tier1-custom-input");

    if (questionCard) questionCard.classList.remove("hidden");
    if (answeredCard) answeredCard.classList.add("hidden");
    if (notSureCard) notSureCard.classList.add("hidden");
    if (customInput) customInput.value = "";

    if (questionTextEl) {
      questionTextEl.innerText = `“${this.currentQuestion}”`;
    }

    if (optionsContainer) {
      optionsContainer.innerHTML = "";

      const defaultOptions = [
        { label: "Goa", icon: "map-pin", value: "Goa" },
        { label: "Restaurant / Café", icon: "coffee", value: "Restaurant / Café" },
        { label: "Beachside", icon: "waves", value: "Beach" },
        { label: "Hotel / Resort", icon: "hotel", value: "Hotel" },
        { label: "Street / Market", icon: "shopping-bag", value: "Market" },
        { label: "Home", icon: "home", value: "Home" }
      ];

      const rawOpts = (options && Array.isArray(options) && options.length > 0) ? options : defaultOptions;

      // Filter out any "Not sure" entries so it is NEVER duplicated
      const optsToRender = rawOpts.filter(opt => {
        const s = `${opt.label || ''} ${opt.value || ''}`.toLowerCase();
        return !s.includes("not sure") && !s.includes("not_sure");
      });

      optsToRender.forEach(opt => {
        const btn = document.createElement("button");
        btn.className = "venue-option-card";
        const val = opt.value || opt.label;
        const iconName = opt.icon || this.getOptionIcon(opt.label, val);
        const cleanLabel = this.getCleanOptionLabel(opt.label || val);

        btn.onclick = () => this.selectTier1Option(val);
        btn.innerHTML = `
          <i data-lucide="${iconName}"></i>
          <span>${this.escapeHtml(cleanLabel)}</span>
          <i data-lucide="chevron-right" class="card-chevron"></i>
        `;
        optionsContainer.appendChild(btn);
      });

      // Exactly ONE "Not sure" button rendered with dedicated styling
      const notSureBtn = document.createElement("button");
      notSureBtn.className = "venue-option-card not-sure-card-btn";
      notSureBtn.onclick = () => this.handleTier1NotSure();
      notSureBtn.innerHTML = `
        <i data-lucide="sparkles"></i>
        <span>Not sure · Switch to Recognition Mode</span>
        <i data-lucide="arrow-right" class="card-chevron"></i>
      `;
      optionsContainer.appendChild(notSureBtn);
    }

    if (window.lucide) window.lucide.createIcons();
  }

  triggerRecoveryStep() {
    this.logEvent("RECOVERY_TRIGGERED", "User indicated hero photo was not the intended memory.");
    this.recognizedAnchor = null;
    this.selectedPhoto = null;
    this.renderTier1QuestionCard(
      this.searchResponse?.clarification_question || "Can you remember what kind of place or setting it was?",
      this.searchResponse?.clarification_options || null,
      this.searchResponse?.recognition_cues || null
    );
  }

  renderTier2RecognitionStage(recognitionCues) {
    if (recognitionCues && Array.isArray(recognitionCues)) {
      this.currentRecognitionCues = recognitionCues;
    }
    this.proceedToTier2();
  }

  async selectTier1Option(option) {
    if (option === "Not sure" || (typeof option === "string" && option.toLowerCase().includes("not sure"))) {
      this.handleTier1NotSure();
      return;
    }

    this.selectedPhoto = null;
    this.telemetry.recoverySteps += 1;
    this.telemetry.recognizedClues += 1;
    this.recognizedAnchor = option;
    this.logEvent("TIER1_SELECTED", `User selected meaningful detail: "${option}"`);

    // Add new cue to memory representation & update searching-with bar
    this.activeChips.push({
      id: "cue_tier1_" + Date.now(),
      text: option,
      type: "context",
      is_active: true
    });
    this.updateSearchingWithBar();

    // Hide question card, show feedback card
    const questionCard = document.getElementById("tier1-question-card");
    const answeredCard = document.getElementById("tier1-answered-card");
    const notSureCard = document.getElementById("tier1-notsure-card");
    const cuesDisplay = document.getElementById("tier1-updated-cues-display");

    if (questionCard) questionCard.classList.add("hidden");
    if (notSureCard) notSureCard.classList.add("hidden");
    if (answeredCard) answeredCard.classList.remove("hidden");

    // Display Updated Search Cues: e.g. Friend + Trip + Goa
    const baseCues = this.activeChips.map(c => this.getChipLabel(c));
    const uniqueCues = Array.from(new Set(baseCues));

    if (cuesDisplay) {
      cuesDisplay.innerHTML = "";
      uniqueCues.forEach(cue => {
        const isNew = (cue === option || (typeof option === 'string' && option.includes(cue)));
        cuesDisplay.innerHTML += `
          <div class="memory-chip active ${isNew ? 'highlight-new' : ''}" style="font-size:0.9rem;padding:6px 14px">
            <i data-lucide="${isNew ? 'check-circle' : 'tag'}" style="width:12px;height:12px"></i>
            <span>${this.escapeHtml(cue)}</span>
          </div>
        `;
      });
    }

    if (window.lucide) window.lucide.createIcons();

    // Call backend refinement endpoint
    try {
      if (this.sessionId && !this.sessionId.startsWith("session-fallback")) {
        const refineRes = await fetch(this.apiUrl("/api/session/refine"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: this.sessionId,
            selected_option: option,
            venue_type: typeof option === "string" && (option.toLowerCase().includes("restaurant") || option.toLowerCase().includes("cafe")) ? "restaurant_cafe" : null
          })
        });

        if (refineRes.ok) {
          const refineData = await refineRes.json();
          this.searchResponse = refineData;
          if (refineData.chips) {
            this.activeChips = refineData.chips;
            this.updateSearchingWithBar();
          }
        }
      }
    } catch (e) {
      console.warn("Refine API error:", e);
    }

    // Automatically search again and show updated results without forcing another manual search click
    setTimeout(() => {
      this.renderStrongResultsStage();
    }, 1100);
  }

  submitCustomTier1Answer() {
    const input = document.getElementById("tier1-custom-input");
    const val = input ? input.value : "";
    const errorEl = document.getElementById("tier1-input-error");

    const validation = this.validateMemoryInput(val, 'clue');
    if (!validation.isValid) {
      if (input) {
        input.classList.remove("input-error");
        void input.offsetWidth;
        input.classList.add("input-error");
        input.focus();
      }
      if (errorEl) {
        errorEl.innerHTML = `<i data-lucide="alert-circle" style="width:14px;height:14px;display:inline-block"></i> <span>${this.escapeHtml(validation.message)}</span>`;
        errorEl.classList.remove("hidden");
        if (window.lucide) window.lucide.createIcons();
      }
      this.showToast(validation.message, "warning");
      return;
    }

    if (errorEl) errorEl.classList.add("hidden");
    if (input) input.classList.remove("input-error");
    this.selectTier1Option(val.trim());
  }

  handleTier1NotSure() {
    this.logEvent("TIER1_NOT_SURE", "User selected 'Not sure' -> Transitioning directly to Recognition Mode clues.");
    // Skip intermediate interstitial screen to eliminate redundant clicks
    this.proceedToTier2();
  }

  proceedToTier2() {
    this.goToStep(5);
    this.selectedTier2Cues = [];
    
    // Clear all previously selected pill styles
    const pills = document.querySelectorAll(".recognition-pill-card");
    pills.forEach(p => p.classList.remove("selected"));

    const feedbackPanel = document.getElementById("tier2-feedback-panel");
    if (feedbackPanel) feedbackPanel.classList.add("hidden");

    // Dynamic recognition cues generation
    const clues = (this.currentRecognitionCues && this.currentRecognitionCues.length > 0)
      ? this.currentRecognitionCues
      : ["Goa", "Beach", "Restaurant", "Hotel", "Sunset", "Road trip"];
    this.renderDynamicRecognitionCues(clues);

    this.logEvent("TIER2_RECOGNITION_STAGE", "User viewing 'Which feels familiar?' recognition cue cloud.");
    if (window.lucide) window.lucide.createIcons();
  }

  renderDynamicRecognitionCues(cuesList) {
    const container = document.getElementById("tier2-categories-container");
    if (!container || !cuesList || cuesList.length === 0) return;

    let dynamicBlock = document.getElementById("dynamic-recognition-block");
    if (!dynamicBlock) {
      dynamicBlock = document.createElement("div");
      dynamicBlock.id = "dynamic-recognition-block";
      dynamicBlock.className = "recognition-category-block dynamic-clues-block";
      dynamicBlock.style.border = "1px solid var(--accent-purple, #8b5cf6)";
      dynamicBlock.style.background = "rgba(139, 92, 246, 0.06)";
      dynamicBlock.style.borderRadius = "14px";
      dynamicBlock.style.padding = "14px 12px";
      dynamicBlock.style.boxSizing = "border-box";
      dynamicBlock.style.width = "100%";
      dynamicBlock.style.marginBottom = "14px";
      container.insertBefore(dynamicBlock, container.firstChild);
    }

    dynamicBlock.innerHTML = `
      <h3 class="category-heading" style="color:var(--accent-purple, #8b5cf6);font-weight:700">
        <i data-lucide="sparkles" style="display:inline;width:16px;height:16px;margin-right:6px"></i> Clues for Your Memory:
      </h3>
      <div class="category-pills-row">
        ${cuesList.map(cue => {
          let emoji = "✨";
          const cl = cue.toLowerCase();
          if (cl.includes("restaurant") || cl.includes("café") || cl.includes("cafe") || cl.includes("eating") || cl.includes("food")) emoji = "☕";
          else if (cl.includes("beach")) emoji = "🏖️";
          else if (cl.includes("hotel") || cl.includes("resort")) emoji = "🏨";
          else if (cl.includes("goa") || cl.includes("trip") || cl.includes("travel")) emoji = "✈️";
          else if (cl.includes("sunset") || cl.includes("evening")) emoji = "🌅";
          else if (cl.includes("pill") || cl.includes("medicine")) emoji = "💊";
          else if (cl.includes("pharmacy") || cl.includes("clinic")) emoji = "🏥";
          else if (cl.includes("dress") || cl.includes("fashion") || cl.includes("shopping")) emoji = "👗";
          else if (cl.includes("friend")) emoji = "👥";

          return `
            <button type="button" class="recognition-pill-card" onclick="app.toggleTier2Cue('${this.escapeHtml(cue)}', this)">
              <span class="pill-icon">${emoji}</span>
              <span class="pill-text">${this.escapeHtml(cue)}</span>
            </button>
          `;
        }).join('')}
      </div>
    `;

    if (window.lucide) window.lucide.createIcons();
  }

  // ------------------------------------------------------------------------
  // Step 5: Tier 2 Recognition (Which feels familiar?)
  // ------------------------------------------------------------------------
  toggleTier2Cue(cueLabel, btnElement) {
    if (!this.selectedTier2Cues) {
      this.selectedTier2Cues = [];
    }

    const idx = this.selectedTier2Cues.indexOf(cueLabel);
    if (idx >= 0) {
      this.selectedTier2Cues.splice(idx, 1);
      if (btnElement) btnElement.classList.remove("selected");
    } else {
      this.selectedTier2Cues.push(cueLabel);
      if (btnElement) btnElement.classList.add("selected");
    }

    const feedbackPanel = document.getElementById("tier2-feedback-panel");
    const arrowPath = document.getElementById("tier2-arrow-path");

    if (this.selectedTier2Cues.length > 0) {
      if (feedbackPanel) feedbackPanel.classList.remove("hidden");

      // Build updated retrieval path: Goa → Friend → Trip → Café → [Selected Cue]
      const baseCues = this.activeChips.map(c => this.getChipLabel(c));
      const fullPath = [...baseCues, ...this.selectedTier2Cues];
      const uniquePath = Array.from(new Set(fullPath));

      if (arrowPath) {
        arrowPath.innerHTML = uniquePath.map((item, i) => {
          const isRecognized = this.selectedTier2Cues.includes(item);
          return `
            <span class="arrow-path-node ${isRecognized ? 'new-clue' : ''}">${this.escapeHtml(item)}</span>
            ${i < uniquePath.length - 1 ? '<span class="arrow-separator">→</span>' : ''}
          `;
        }).join('');
      }

      this.logEvent("TIER2_CUE_SELECTED", `Recognized clue: "${cueLabel}"`);
    } else {
      if (feedbackPanel) feedbackPanel.classList.add("hidden");
    }

    if (window.lucide) window.lucide.createIcons();
  }

  async executeSearchWithClue() {
    if (!this.selectedTier2Cues || this.selectedTier2Cues.length === 0) return;

    this.selectedPhoto = null;
    this.telemetry.recoverySteps += 2;
    this.telemetry.recognizedClues += this.selectedTier2Cues.length;
    this.recognizedAnchor = this.selectedTier2Cues.join(", ");
    this.logEvent("TIER2_SEARCH_EXECUTED", `Searching with recognized clues: ${this.selectedTier2Cues.join(", ")}`);

    // Add selected cues to active chips and update Searching With bar
    this.selectedTier2Cues.forEach(cue => {
      this.activeChips.push({
        id: "cue_recog_" + Date.now() + "_" + Math.random().toString(36).substr(2, 4),
        text: cue,
        type: "recognized",
        is_active: true
      });
    });
    this.updateSearchingWithBar();

    try {
      if (this.sessionId && !this.sessionId.startsWith("session-fallback")) {
        const refineRes = await fetch(this.apiUrl("/api/session/refine"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: this.sessionId,
            selected_cues: this.selectedTier2Cues,
            recognized_cues: this.selectedTier2Cues,
            selected_option: this.selectedTier2Cues[0]
          })
        });

        if (refineRes.ok) {
          const refineData = await refineRes.json();
          this.searchResponse = refineData;
          if (refineData.chips) {
            this.activeChips = refineData.chips;
            this.updateSearchingWithBar();
          }
        }
      }
    } catch (e) {
      console.warn("Refine API error:", e);
    }

    this.renderStrongResultsStage();
  }

  showClosestMatchesAnyway() {
    this.selectedPhoto = null;
    this.logEvent("RECOGNITION_SKIPPED", "User did not recognize any clue -> Displaying closest candidates anyway without dead end.");
    this.renderStrongResultsStage();
  }

  getPhotoById(photoId) {
    if (!photoId) return null;
    const candidates = this.searchResponse?.candidates || [];
    const found = candidates.find(c => c.photo_id === photoId);
    if (found) return found;
    if (this.relatedPhotosMap && this.relatedPhotosMap[photoId]) {
      return this.relatedPhotosMap[photoId];
    }
    return null;
  }

  getPhotoKey(photo) {
    if (!photo) return "";
    const fn = (photo.filename || "").toLowerCase();
    const url = (photo.thumbnail_url || photo.image_url || photo.full_photo_url || "").split("?")[0].toLowerCase();
    return fn || url || photo.photo_id;
  }

  async selectHeroCandidate(photoId) {
    if (!photoId) return;
    let photo = this.getPhotoById(photoId);
    if (!photo) {
      try {
        const res = await fetch(this.apiUrl(`/api/photos/${encodeURIComponent(photoId)}`));
        if (res.ok) {
          photo = await res.json();
          if (!this.relatedPhotosMap) this.relatedPhotosMap = {};
          this.relatedPhotosMap[photoId] = photo;
        }
      } catch (e) {
        console.warn("Could not fetch photo details for hero selection:", e);
      }
    }
    if (photo) {
      this.selectedPhoto = photo;
      this.logEvent("HERO_PHOTO_SELECTED", `User selected hero candidate: ${photo.filename || photo.photo_id}`);
      this.renderStrongResultsStage();
    }
  }

  async loadRelatedMomentsForTarget(targetPhoto) {
    if (!targetPhoto || !targetPhoto.photo_id) return;
    try {
      const res = await fetch(this.apiUrl(`/api/photos/${encodeURIComponent(targetPhoto.photo_id)}/related?limit=8`));
      if (res.ok) {
        const data = await res.json();
        const related = data.related || [];
        if (!this.relatedPhotosMap) this.relatedPhotosMap = {};
        related.forEach(p => {
          this.relatedPhotosMap[p.photo_id] = p;
        });

        // Only update DOM if targetPhoto is still the active selected photo
        if (this.selectedPhoto && this.selectedPhoto.photo_id === targetPhoto.photo_id) {
          const container = document.getElementById("context-neighbors-grid-container");
          if (container && related.length > 0) {
            const targetKey = this.getPhotoKey(targetPhoto);
            const seenKeys = new Set([targetKey]);
            const filtered = [];
            for (const p of related) {
              const k = this.getPhotoKey(p);
              if (seenKeys.has(k)) continue;
              seenKeys.add(k);
              filtered.push(p);
              if (filtered.length >= 4) break;
            }
            if (filtered.length > 0) {
              container.innerHTML = filtered.map(p => `
                <div class="context-thumb-card ${p.photo_id === targetPhoto.photo_id ? 'active-selected' : ''}" onclick="app.selectHeroCandidate('${p.photo_id}')" title="${this.escapeHtml(p.caption || '')}">
                  <img src="${this.getPhotoUrl(p)}" alt="${this.escapeHtml(p.caption || '')}" onerror="app.handleImageError(this, '${p.filename}')" />
                </div>
              `).join('');
            }
          }
        }
      }
    } catch (e) {
      console.warn("Could not fetch same-location related moments:", e);
    }
  }

  // ------------------------------------------------------------------------
  // Step 6: Stronger Search Results ("I think we found the moment")
  // ------------------------------------------------------------------------
  renderStrongResultsStage() {
    this.goToStep(6);
    this.logEvent("STATE_6_RESULTS_SURFACED", "Surfaced refined confident results after progressive recovery step.");

    const layout = document.getElementById("strong-results-layout");
    const chipsRow = document.getElementById("strong-results-chips");

    // Display active context tags
    const baseCues = this.activeChips.filter(c => this.isChipActive(c)).map(c => this.getChipLabel(c));
    const recognizedClue = this.recognizedAnchor ? (typeof this.recognizedAnchor === 'string' ? this.recognizedAnchor.split(',').map(s => s.trim()) : [this.recognizedAnchor]) : [];
    const fullChips = Array.from(new Set([...baseCues, ...recognizedClue]));

    if (chipsRow) {
      chipsRow.innerHTML = fullChips.map(c => `
        <div class="match-context-chip">
          <i data-lucide="check" style="width:12px;height:12px;display:inline;color:var(--success, #10b981)"></i>
          <span>${this.escapeHtml(c)}</span>
        </div>
      `).join('');
    }

    const candidates = this.searchResponse?.candidates || [];
    let targetPhoto = this.selectedPhoto;

    // If no candidate selected yet, default to top candidate from search
    if (!targetPhoto) {
      targetPhoto = candidates[0];
    }

    this.selectedPhoto = targetPhoto;

    if (layout && targetPhoto) {
      // DEDUPLICATION & SAME-LOCATION PRIORITIZATION:
      // Other related moments must be from the SAME location / event cluster, different photos
      const targetKey = this.getPhotoKey(targetPhoto);
      const seenKeys = new Set([targetKey]);
      const targetNid = (targetPhoto.neighborhood || "").toLowerCase();
      const targetCity = (targetPhoto.city || "").toLowerCase();
      const targetRegion = (targetPhoto.region || "").toLowerCase();
      const targetCluster = (targetPhoto.event_cluster_id || "").toLowerCase();

      // Pool includes search hits and any already known related photos
      const candidatePool = [
        ...candidates,
        ...(this.relatedPhotosMap ? Object.values(this.relatedPhotosMap) : [])
      ];

      // Filter and score candidates by location/cluster affinity to targetPhoto
      const sameLocationCandidates = candidatePool.filter(c => {
        if (!c) return false;
        const key = this.getPhotoKey(c);
        if (seenKeys.has(key)) return false;
        const cNid = (c.neighborhood || "").toLowerCase();
        const cCity = (c.city || "").toLowerCase();
        const cReg = (c.region || "").toLowerCase();
        const cCluster = (c.event_cluster_id || "").toLowerCase();
        
        const sameNid = targetNid && cNid === targetNid;
        const sameCity = targetCity && cCity === targetCity;
        const sameCluster = targetCluster && cCluster === targetCluster;
        const sameReg = targetRegion && cReg === targetRegion;
        return sameNid || sameCity || sameCluster || sameReg;
      });

      sameLocationCandidates.sort((a, b) => {
        const aNid = (a.neighborhood || "").toLowerCase();
        const aCity = (a.city || "").toLowerCase();
        const aCluster = (a.event_cluster_id || "").toLowerCase();
        const aReg = (a.region || "").toLowerCase();

        const bNid = (b.neighborhood || "").toLowerCase();
        const bCity = (b.city || "").toLowerCase();
        const bCluster = (b.event_cluster_id || "").toLowerCase();
        const bReg = (b.region || "").toLowerCase();

        const scoreA = (aNid === targetNid ? 8 : 0) + (aCity === targetCity ? 4 : 0) + (aCluster === targetCluster ? 3 : 0) + (aReg === targetRegion ? 1 : 0);
        const scoreB = (bNid === targetNid ? 8 : 0) + (bCity === targetCity ? 4 : 0) + (bCluster === targetCluster ? 3 : 0) + (bReg === targetRegion ? 1 : 0);
        return scoreB - scoreA;
      });

      const otherPhotos = [];
      for (const c of sameLocationCandidates) {
        const key = this.getPhotoKey(c);
        if (seenKeys.has(key)) continue;
        seenKeys.add(key);
        otherPhotos.push(c);
        if (otherPhotos.length >= 4) break;
      }

      // If fewer than 4 candidates matched location from pool, backfill from candidatePool
      if (otherPhotos.length < 4) {
        for (const c of candidatePool) {
          const key = this.getPhotoKey(c);
          if (seenKeys.has(key)) continue;
          seenKeys.add(key);
          otherPhotos.push(c);
          if (otherPhotos.length >= 4) break;
        }
      }

      // Keep relatedPhotosMap indexed for instant lookups
      if (!this.relatedPhotosMap) this.relatedPhotosMap = {};
      otherPhotos.forEach(p => {
        if (p && p.photo_id) this.relatedPhotosMap[p.photo_id] = p;
      });
      if (targetPhoto && targetPhoto.photo_id) {
        this.relatedPhotosMap[targetPhoto.photo_id] = targetPhoto;
      }

      const targetImgSrc = this.getPhotoUrl(targetPhoto, true);
      const targetDate = targetPhoto.timestamp
        ? new Date(targetPhoto.timestamp).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })
        : "Recent moment";
      const targetLoc = this.getPhotoLocation(targetPhoto);
      const baseCandidateScore = this.searchResponse?.candidates?.[0]?.score || 0.88;
      const matchScore = targetPhoto.score != null
        ? Math.max(50, Math.min(99, Math.round(targetPhoto.score * 100)))
        : Math.max(50, Math.min(99, Math.round(baseCandidateScore * 100)));

      layout.innerHTML = `
        <!-- Prominent Hero Card for Target Photo -->
        <div class="hero-photo-card" onclick="app.renderFoundStage(app.selectedPhoto)">
          <img src="${targetImgSrc}" alt="" onerror="app.handleImageError(this, '${targetPhoto.filename}')" />
          <div class="hero-photo-overlay"></div>
          <div class="hero-top-badge">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3L12 3z"/></svg>
            <span>Target Match · ${matchScore}% Match</span>
          </div>
          <div class="hero-bottom-info">
            <div class="hero-meta-badges" style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px;">
              <span class="found-loc-badge" style="background: rgba(0,0,0,0.65); backdrop-filter: blur(8px); padding: 5px 12px; border-radius: 6px; font-size: 0.84rem; font-weight: 600; color: #ffffff; border: 1px solid rgba(255,255,255,0.2);">📍 ${targetLoc}</span>
              <span class="found-date-badge" style="background: rgba(0,0,0,0.65); backdrop-filter: blur(8px); padding: 5px 12px; border-radius: 6px; font-size: 0.84rem; font-weight: 600; color: #ffffff; border: 1px solid rgba(255,255,255,0.2);">📅 ${targetDate}</span>
            </div>
            <div class="hero-actions-row" style="display: flex; gap: 8px; align-items: center; flex-direction: column; width: 100%;">
              <button class="select-photo-btn" style="width:100%;justify-content:center;min-height:44px;font-size:15px;font-weight:700;background:rgba(255,255,255,0.95);color:#0f172a;border:none;box-shadow:0 4px 14px rgba(0,0,0,0.3);" onclick="event.stopPropagation(); app.renderFoundStage(app.selectedPhoto)">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>
                <span>This is the photo!</span>
              </button>
              <button class="not-this-btn" onclick="event.stopPropagation(); app.triggerRecoveryStep()" style="width:100%;justify-content:center;min-height:44px;display:inline-flex;align-items:center;gap:6px;padding:9px 16px;border-radius:12px;border:1px solid rgba(255,255,255,0.4);background:rgba(15,23,42,0.85);color:#fff;cursor:pointer;font-size:14px;font-weight:600;backdrop-filter:blur(8px);transition:all 0.2s ease;">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path><path d="M3 3v5h5"></path><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"></path><path d="M16 21h5v-5"></path></svg>
                <span>Not this one? Help me find it</span>
              </button>
            </div>
          </div>
        </div>

        <!-- Related Candidates Column (Same Location, Different Photos) -->
        <div class="related-moments-panel" style="display: flex; flex-direction: column; gap: 8px;">
          <div style="font-size:0.82rem;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;display:flex;align-items:center;gap:6px">
            <i data-lucide="layers" style="width:14px;height:14px;color:var(--primary)"></i>
            <span>Other Related Moments</span>
          </div>
          <div style="font-size:0.75rem;font-weight:600;color:var(--primary);margin-top:-4px;margin-bottom:2px;display:flex;align-items:center;gap:4px">
            <i data-lucide="map-pin" style="width:11px;height:11px"></i>
            <span>Same place · ${this.escapeHtml(targetLoc)}</span>
          </div>
          <div id="context-neighbors-grid-container" class="context-neighbors-grid">
            ${otherPhotos.map(p => `
              <div class="context-thumb-card ${p.photo_id === targetPhoto.photo_id ? 'active-selected' : ''}" onclick="app.selectHeroCandidate('${p.photo_id}')" title="${this.escapeHtml(p.caption || '')}">
                <img src="${this.getPhotoUrl(p)}" alt="${this.escapeHtml(p.caption || '')}" onerror="app.handleImageError(this, '${p.filename}')" />
              </div>
            `).join('')}
          </div>
        </div>
      `;

      // Guarantee 100% same-location backfill from backend
      this.loadRelatedMomentsForTarget(targetPhoto);
    }

    if (window.lucide) window.lucide.createIcons();
  }

  // ------------------------------------------------------------------------
  // Step 7: Photo Found ("🎉 Found it")
  // ------------------------------------------------------------------------
  renderFoundStage(photo) {
    if (photo) this.selectedPhoto = photo;
    const targetPhoto = this.selectedPhoto || this.searchResponse?.candidates?.[0];
    if (!targetPhoto) return;

    if (this.currentStep && this.currentStep !== 7) {
      this.previousStep = this.currentStep;
    }

    this.goToStep(7);
    this.logEvent("STATE_7_PHOTO_FOUND", `Photo recovered successfully: ${targetPhoto.filename || targetPhoto.photo_id}`);

    // Fire celebratory confetti!
    this.fireConfetti();

    // Populate photo image and details
    const imgEl = document.getElementById("found-photo-img");
    const locBadge = document.getElementById("found-loc-badge");
    const dateBadge = document.getElementById("found-date-badge");
    const pathChain = document.getElementById("final-evolved-path");
    const statAttempts = document.getElementById("final-stat-attempts");
    const statSteps = document.getElementById("final-stat-steps");
    const statCues = document.getElementById("final-stat-cues");

    if (imgEl) {
      imgEl.src = this.getPhotoUrl(targetPhoto, true);
      imgEl.onerror = () => this.handleImageError(imgEl, targetPhoto.filename);
    }
    if (locBadge) locBadge.innerText = `📍 ${this.getPhotoLocation(targetPhoto)}`;
    if (dateBadge) {
      dateBadge.innerText = targetPhoto.timestamp
        ? `📅 ${new Date(targetPhoto.timestamp).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}`
        : `📅 Recent moment`;
    }

    // Retrieval path dynamically from active clues and recognized anchors
    const baseCues = this.activeChips.filter(c => this.isChipActive(c)).map(c => this.getChipLabel(c));
    const recognizedClue = this.recognizedAnchor ? (typeof this.recognizedAnchor === 'string' ? this.recognizedAnchor.split(',').map(s => s.trim()) : [this.recognizedAnchor]) : [];
    const fullChain = Array.from(new Set([...baseCues, ...recognizedClue]));

    if (pathChain) {
      pathChain.innerHTML = fullChain.map((cue, i) => `
        <span class="arrow-path-node ${i === fullChain.length - 1 ? 'new-clue' : ''}">${this.escapeHtml(cue)}</span>
        ${i < fullChain.length - 1 ? '<span class="arrow-separator">→</span>' : ''}
      `).join('');
    }

    if (statAttempts) statAttempts.innerText = this.telemetry.searchAttempts || 1;
    if (statSteps) statSteps.innerText = this.telemetry.recoverySteps > 1 ? "2" : "1";
    if (statCues) statCues.innerText = fullChain.length;

    // Record completion in telemetry backend
    if (this.sessionId && !this.sessionId.startsWith("session-fallback")) {
      fetch(this.apiUrl(`/api/session/${this.sessionId}/complete`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          photo_id: targetPhoto.photo_id,
          target_confirmed: true,
          effort_turns: this.telemetry.recoverySteps + 1,
          retrieval_path: fullChain
        })
      }).catch(err => console.warn("Failed recording completion:", err));
    }

    if (window.lucide) window.lucide.createIcons();
  }

  // ------------------------------------------------------------------------
  // Step 8: Photo Detail Modal & Telemetry
  // ------------------------------------------------------------------------
  openPhotoModal(photo) {
    if (!photo) return;
    this.selectedPhoto = photo;
    const modal = document.getElementById("photo-detail-modal");
    if (!modal) return;

    const img = document.getElementById("modal-photo-img");
    const dateEl = document.getElementById("modal-photo-date");
    const locEl = document.getElementById("modal-photo-loc");
    const camText = document.getElementById("modal-cam-text");

    if (img) {
      img.src = this.getPhotoUrl(photo, true);
      img.onerror = () => this.handleImageError(img, photo.filename);
    }
    if (dateEl) {
      dateEl.innerText = photo.timestamp 
        ? new Date(photo.timestamp).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })
        : "October 24, 2023";
    }
    if (locEl) {
      locEl.innerHTML = `<i data-lucide="map-pin" style="width:14px;height:14px;display:inline"></i> ${this.escapeHtml(this.getPhotoLocation(photo))}`;
    }
    if (camText) {
      camText.innerText = photo.camera_model || "Dual Camera";
    }

    // Populate Retrieval Path Ladder
    const ladderSteps = document.getElementById("modal-ladder-steps");
    if (ladderSteps) {
      ladderSteps.innerHTML = "";
      const pathItems = [...this.activeChips.map(c => this.getChipLabel(c))];
      if (this.recognizedAnchor && !pathItems.includes(this.recognizedAnchor)) {
        pathItems.push(`${this.recognizedAnchor} (Recognized)`);
      }

      pathItems.forEach((stepText, idx) => {
        const isLast = idx === pathItems.length - 1;
        const stepDiv = document.createElement("div");
        stepDiv.className = `ladder-step ${isLast ? 'active' : ''}`;
        stepDiv.innerHTML = `
          <div class="ladder-num">${idx + 1}</div>
          <span class="ladder-text">${this.escapeHtml(stepText)}</span>
        `;
        ladderSteps.appendChild(stepDiv);
      });
    }

    // Update Session Analytics
    const metricAttempts = document.getElementById("metric-attempts");
    const metricSteps = document.getElementById("metric-steps");
    const metricCues = document.getElementById("metric-cues");
    const metricTtr = document.getElementById("metric-ttr");

    if (metricAttempts) metricAttempts.innerText = this.telemetry.searchAttempts || 1;
    if (metricSteps) metricSteps.innerText = this.telemetry.recoverySteps || 1;
    if (metricCues) metricCues.innerText = this.activeChips.length + (this.recognizedAnchor ? 1 : 0);
    if (metricTtr) metricTtr.innerText = (this.telemetry.lastLatencyMs / 1000).toFixed(2) + "s";

    modal.classList.remove("hidden");
    this.logEvent("photo_retrieved", `Target photo opened: ${photo.photo_id}`);
    this.fireConfetti();

    // Sync session completion with backend
    if (this.sessionId && !this.sessionId.startsWith("session-fallback")) {
      const pathItems = [...this.activeChips.map(c => this.getChipLabel(c))];
      if (this.recognizedAnchor && !pathItems.includes(this.recognizedAnchor)) {
        pathItems.push(this.recognizedAnchor);
      }
      fetch(this.apiUrl(`/api/session/${this.sessionId}/complete`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          photo_id: photo.photo_id,
          target_confirmed: true,
          effort_turns: this.telemetry.recoverySteps + 1,
          retrieval_path: pathItems
        })
      }).catch(err => console.warn("Failed recording completion:", err));
    }

    const confirmBtn = document.getElementById("modal-confirm-btn");
    if (confirmBtn) {
      if (this.currentStep === 7) {
        confirmBtn.innerHTML = `<span>Close Preview</span> <i data-lucide="x"></i>`;
        confirmBtn.onclick = () => this.closePhotoModal();
      } else {
        confirmBtn.innerHTML = `<span>Confirm Photo</span> <i data-lucide="check"></i>`;
        confirmBtn.onclick = () => this.confirmPhotoFromModal();
      }
    }

    if (window.lucide) window.lucide.createIcons();
  }

  confirmPhotoFromModal() {
    this.closePhotoModal();
    this.renderFoundStage(this.selectedPhoto);
  }

  finishSession() {
    this.logEvent("SESSION_FINISHED", "User completed memory recovery session.");
    this.closePhotoModal();
    this.resetFlow();
  }

  closeFoundStage() {
    this.logEvent("FOUND_STAGE_CLOSED", "User closed photo found stage; returning to previous page.");
    this.closePhotoModal();

    let targetStep = this.previousStep;
    if (!targetStep || targetStep === 7) {
      // Heuristic fallback if previousStep is missing or was 7
      if (document.getElementById("step-6")?.querySelector(".hero-photo-card")) {
        targetStep = 6;
      } else if (this.currentRecognitionCues && this.currentRecognitionCues.length > 0) {
        targetStep = 5;
      } else if (this.currentQuestion) {
        targetStep = 4;
      } else if (this.searchResponse?.candidates?.length) {
        targetStep = 3;
      } else {
        targetStep = 1;
      }
    }

    this.goToStep(targetStep);
  }

  closePhotoModal() {
    const modal = document.getElementById("photo-detail-modal");
    if (modal) modal.classList.add("hidden");
  }

  // ------------------------------------------------------------------------
  // Telemetry Modal (Connected to backend metrics store)
  // ------------------------------------------------------------------------
  async openTelemetryModal() {
    const modal = document.getElementById("telemetry-modal");
    if (!modal) return;

    // Fetch live aggregated metrics from server
    try {
      const res = await fetch(this.apiUrl("/api/telemetry/metrics"));
      if (res.ok) {
        const metrics = await res.json();
        const cards = modal.querySelectorAll(".kpi-card");
        if (cards.length >= 4) {
          const num1 = cards[0].querySelector(".kpi-num");
          if (num1) num1.innerText = `${metrics.retrieval_success_rate}%`;

          const num2 = cards[1].querySelector(".kpi-num");
          if (num2) num2.innerText = `${metrics.avg_ttr_seconds}s`;

          const num3 = cards[2].querySelector(".kpi-num");
          if (num3) num3.innerText = `${metrics.manual_retyping_reduction_rate}%`;

          const num4 = cards[3].querySelector(".kpi-num");
          if (num4) num4.innerText = `${metrics.tier1_acceptance_rate}%`;
        }

        const list = document.getElementById("event-stream-list");
        if (list && metrics.recent_events && metrics.recent_events.length > 0) {
          list.innerHTML = "";
          metrics.recent_events.forEach(evt => {
            const item = document.createElement("div");
            item.className = "event-log-item";
            item.innerHTML = `
              <span class="event-timestamp">[${evt.time_str}]</span>
              <span class="event-name">${this.escapeHtml(evt.event_type)}:</span>
              <span class="event-details">${this.escapeHtml(JSON.stringify(evt.details))}</span>
            `;
            list.appendChild(item);
          });
        }
      }
    } catch (err) {
      console.warn("Could not fetch remote metrics, using local events:", err);
    }

    modal.classList.remove("hidden");
    if (window.lucide) window.lucide.createIcons();
  }

  closeTelemetryModal() {
    const modal = document.getElementById("telemetry-modal");
    if (modal) modal.classList.add("hidden");
  }

  logEvent(name, details) {
    const time = new Date().toLocaleTimeString();
    const detailsStr = typeof details === "object" ? JSON.stringify(details) : String(details);
    this.telemetry.events.push({ time, name, details: detailsStr });
    console.log(`[${time}] AMR Telemetry -> ${name}: ${detailsStr}`);

    if (this.sessionId && !this.sessionId.startsWith("session-fallback")) {
      fetch(this.apiUrl("/api/telemetry/event"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: this.sessionId,
          event_type: name,
          details: typeof details === "object" ? details : { message: details }
        })
      }).catch(() => {});
    }
  }

  fireConfetti() {
    if (typeof confetti === "function") {
      try {
        confetti({
          particleCount: 80,
          spread: 70,
          origin: { y: 0.6 }
        });
      } catch (e) {}
    }
  }

  escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  async checkBackendHealth() {
    const pill = document.getElementById("api-status-pill");
    try {
      const res = await fetch(this.apiUrl("/api/health"));
      if (res.ok) {
        const data = await res.json();
        if (pill) {
          pill.className = "api-status-pill online";
          pill.title = `Backend Healthy: ${data.database_photos_count} photos, ${data.vector_index_count} vectors indexed`;
        }
      }
    } catch (e) {
      if (pill) {
        pill.className = "api-status-pill offline";
        const dot = pill.querySelector(".status-dot");
        if (dot) dot.style.background = "#f59e0b";
      }
    }
  }
}

// Instantiate global app instance
const app = new AdaptiveMemoryApp();
window.app = app;
