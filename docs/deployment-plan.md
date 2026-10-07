# Production Deployment Plan: Vercel (Frontend) & Railway (Backend)

This document provides an end-to-end guide for deploying the **AI-Native Photo Retrieval MVP**. The system follows a decoupled architecture:
* **Frontend**: Hosted on **Vercel** (Global Edge CDN, zero server maintenance, instant cache-busting).
* **Backend**: Hosted on **Railway** (Python 3.11 container running FastAPI, Groq LPU inference, Qdrant vector index, and SQLite metadata store).

---

## 1. Architectural Overview & Network Topology

```
┌────────────────────────────────────────────────────────┐
│                   CLIENT BROWSER                       │
└───────────────────────────┬────────────────────────────┘
                            │ HTTPS
                            ▼
┌────────────────────────────────────────────────────────┐
│                   VERCEL EDGE CDN                      │
│  • Serves index.html, index.css, app.js                │
│  • Rewrites proxy /api/*, /photos/*, /thumbnails/*     │
└───────────────────────────┬────────────────────────────┘
                            │ Reverse Proxy / HTTPS
                            ▼
┌────────────────────────────────────────────────────────┐
│                   RAILWAY CONTAINER                    │
│  • FastAPI Backend (Uvicorn on $PORT)                  │
│  • SQLite Metadata DB (data/photos.db)                 │
│  • Qdrant Vector Index (data/qdrant_db)                │
│  • Static Photo & WebP Assets                          │
│  • Groq LPU Inference (qwen3.8-27b / llama-3.3-70b)    │
└────────────────────────────────────────────────────────┘
```

### Why This Split Model?
1. **Zero CORS Friction:** Vercel reverse-proxies API calls directly to Railway, allowing the frontend to make relative requests (`/api/search`, `/photos/...`) without cross-origin blocks.
2. **High-Speed Static Delivery:** Client assets load in $< 50\text{ ms}$ globally via Vercel's edge cache.
3. **Dedicated Python Compute:** Machine learning and vector search dependencies (`qdrant-client`, `scikit-learn`, `numpy`) run in a dedicated Linux container on Railway with generous RAM and CPU allocations.

---

## 2. Pre-Deployment Checklist & Repository Preparation

### 2.1 Essential Deployment Files Created in Repository

Before deploying, ensure these three configuration files are present in the project root:

1. **[`requirements.txt`](file:///c:/Users/ADMIN/Desktop/PRODUCT%20OWNER%20PROJECT%203/MVP/requirements.txt)**:
   ```txt
   fastapi>=0.115.0
   uvicorn[standard]>=0.30.0
   pydantic>=2.8.0
   httpx>=0.27.0
   groq>=0.11.0
   qdrant-client>=1.11.0
   scikit-learn>=1.5.0
   numpy>=1.26.0
   pillow>=10.4.0
   python-dotenv>=1.0.0
   ```

2. **[`Procfile`](file:///c:/Users/ADMIN/Desktop/PRODUCT%20OWNER%20PROJECT%203/MVP/Procfile)** (instructs Railway how to start the app):
   ```procfile
   web: uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
   ```

3. **`vercel.json`** (instructs Vercel how to route and proxy requests):
   *(See Section 4.2 for full template)*

### 2.2 Data Assets Verification
Ensure the following directories are committed to Git:
* `data/photos.db` (pre-populated with 252 photos and clusters)
* `data/qdrant_db/` (embedded vector collection)
* `data/thumbnails/` (WebP thumbnails)
* `data/raw_photos/` (full JPEG/PNG assets)

---

## 3. Step-by-Step Backend Deployment on Railway

### Step 3.1: Create a Project on Railway
1. Sign in to [Railway](https://railway.app/) using your GitHub account.
2. Click **"+ New Project"** $\rightarrow$ **"Deploy from GitHub repo"**.
3. Select your repository: `PRODUCT OWNER PROJECT 3` (or your repository name).

### Step 3.2: Configure Build & Start Settings
Railway will automatically detect Python from `requirements.txt`.
Verify under **Settings $\rightarrow$ Deploy**:
* **Build Command**: *(leave blank or `pip install -r requirements.txt`)*
* **Start Command**: `uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}`
* **Healthcheck Path**: `/api/health`
* **Restart Policy**: `On failure` (Max 10 retries)

### Step 3.3: Set Environment Variables
In Railway, navigate to the **Variables** tab for the backend service and add:

| Variable Name | Recommended Value | Description |
| :--- | :--- | :--- |
| `GROQ_API_KEY` | `gsk_...` | Your production Groq API Key |
| `GROQ_MODEL` | `qwen/qwen3.8-27b` | Primary Groq model (or `llama-3.3-70b-versatile`) |
| `HOST` | `0.0.0.0` | Bind address for container |
| `PORT` | `8000` | Railway automatically assigns `$PORT` |
| `PYTHONUNBUFFERED` | `1` | Ensures logs stream in real-time |

### Step 3.4: Generate a Public Domain
1. In Railway, go to **Settings $\rightarrow$ Networking $\rightarrow$ Public Networking**.
2. Click **"Generate Domain"**.
3. Railway will provide a URL like:
   ```
   https://mvp-backend-production.up.railway.app
   ```
4. Save this URL — you will need it for the Vercel frontend configuration.

### Step 3.5: Verify Backend Health
Open the Railway public domain in your browser or run:
```bash
curl https://<your-railway-backend-url>/api/health
```
Expected Response:
```json
{
  "status": "healthy",
  "groq_configured": true,
  "groq_model": "qwen/qwen3.8-27b",
  "database_photos_count": 252,
  "database_clusters_count": 5,
  "vector_index_count": 259
}
```

---

## 4. Step-by-Step Frontend Deployment on Vercel

### Step 4.1: Configure `vercel.json`
Create a `vercel.json` file in the root directory. Replace `https://YOUR-RAILWAY-DOMAIN.up.railway.app` with your actual Railway domain generated in Step 3.4:

```json
{
  "version": 2,
  "cleanUrls": true,
  "trailingSlash": false,
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://adaptive-memory-recovery-google-photos-mvp-production.up.railway.app/api/:path*"
    },
    {
      "source": "/photos/:path*",
      "destination": "https://adaptive-memory-recovery-google-photos-mvp-production.up.railway.app/photos/:path*"
    },
    {
      "source": "/thumbnails/:path*",
      "destination": "https://adaptive-memory-recovery-google-photos-mvp-production.up.railway.app/thumbnails/:path*"
    },
    {
      "source": "/(.*)",
      "destination": "/src/api/static/$1"
    }
  ]
}
```

### Step 4.2: Alternative Approach (Static Directory Deployment)
If deploying just the `src/api/static` folder as the root on Vercel:
1. Place a `vercel.json` inside `src/api/static/vercel.json`:
   ```json
   {
     "rewrites": [
       {
         "source": "/api/:path*",
         "destination": "https://YOUR-RAILWAY-DOMAIN.up.railway.app/api/:path*"
       },
       {
         "source": "/photos/:path*",
         "destination": "https://YOUR-RAILWAY-DOMAIN.up.railway.app/photos/:path*"
       },
       {
         "source": "/thumbnails/:path*",
         "destination": "https://YOUR-RAILWAY-DOMAIN.up.railway.app/thumbnails/:path*"
       }
     ]
   }
   ```
2. When importing the project in Vercel, set **Root Directory** to `src/api/static`.

### Step 4.3: Deploying via Vercel Dashboard
1. Log in to [Vercel](https://vercel.com/) and click **"Add New..." $\rightarrow$ "Project"**.
2. Select your GitHub repository.
3. In **Project Settings**:
   * **Framework Preset**: `Other`
   * **Root Directory**: `.` *(or `src/api/static` if using Option 4.2)*
   * **Build Command**: *(leave empty)*
   * **Output Directory**: *(leave empty)*
4. Click **"Deploy"**.
5. Once complete, Vercel gives you a production URL:
   ```
   https://adaptive-memory-mvp.vercel.app
   ```

---

## 5. End-to-End Smoke Testing & Verification

Once both services are deployed, test the live Vercel URL:

| Test Case | Query / Action | Expected Result |
| :--- | :--- | :--- |
| **1. Health Check** | Look at top-right status pill | Shows green `"Backend Online (252 photos, 259 vectors)"` |
| **2. Vague Recall (Tier 1)** | `"that cafe in goa with my friend"` | Clarifying prompt appears: *"Was it a restaurant, beach café, or hotel?"* |
| **3. Direct Retrieval** | `"the sunset at anjuna beach"` | Direct high-confidence retrieval ($\ge 75\%$) displaying golden hour photo. |
| **4. Fashion Screenshot** | `"the screenshot of the red dress I wanted to buy"` | Immediate retrieval of fashion item with red dress visual cues. |
| **5. Related Moments Swap** | Search `"resort room in goa"`, then click thumbnail under *"Other Related Moments"* | Thumbnail instantly becomes the Hero Card with updated location badge and match score. |
| **6. Retrieval Celebration** | Click `"This is the photo!"` on Hero Card | Confetti fires, Step 7 opens, telemetry records session completion. |
| **7. Telemetry Modal** | Click **"Telemetry"** button in navigation header | Live KPI cards update (Success rate, TTR seconds, Event log stream). |

---

## 6. Troubleshooting & Common Pitfalls

### 1. `CORS Error` in Browser Console
* **Cause**: Frontend is attempting to query `http://127.0.0.1:8000` or Railway directly without HTTPS proxy.
* **Fix**: Ensure `vercel.json` contains the `/api/:path*` rewrite rule pointing to your Railway domain, and ensure frontend fetch calls use relative paths (e.g., `fetch('/api/search')`).

### 2. Railway Container Exits with `Code 137` (Out of Memory)
* **Cause**: Loading heavy ML models into memory during container boot.
* **Fix**: The backend uses Groq API for LLM inference (external LPU) and lightweight pre-computed Qdrant embeddings, which uses $< 400\text{ MB}$ RAM. Ensure `qdrant-client` is running in local embedded mode (`data/qdrant_db`) or connected to a remote Qdrant instance.

### 3. Missing Photos / 404 on Image Thumbnails
* **Cause**: Git LFS or `.gitignore` omitted image files under `data/raw_photos/` or `data/thumbnails/`.
* **Fix**: Check `git status` to ensure all 252 images in `data/raw_photos/` and `data/thumbnails/` are committed to the repository before pushing to Railway.

### 4. Vercel Returns `404 Not Found` for Root URL
* **Cause**: Vercel looked for `index.html` in the repository root while the file was in `src/api/static/`.
* **Fix**: Ensure `vercel.json` has the rewrite rule `"source": "/(.*)", "destination": "/src/api/static/$1"` OR set the Vercel Root Directory setting to `src/api/static`.

---

## 7. Maintenance & Operational Monitoring

* **Railway Logs**: Monitor live FastAPI request logs via the **Deployments $\rightarrow$ View Logs** tab on Railway.
* **Groq Rate Limits**: Groq's free tier provides generous TPM limits (30 RPM / 14,400 RPD for Qwen/Llama models), more than sufficient for user testing and fellowship evaluation.
* **Telemetry Store**: The built-in `/api/telemetry/metrics` endpoint provides real-time audit statistics for your evaluation presentation.
