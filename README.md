KanyaRakshak — Distributed LLM-Integrated Personal Safety System

A full-stack, cloud-deployed personal safety application combining real-time geolocation tracking, emergency SOS dispatch with geospatial responder discovery, and an LLM-powered conversational safety assistant — built and deployed as a distributed microservice system across four managed cloud services.

Live demo: thunderous-puppy-34aa43.netlify.app
Hackathon: 🏆 Winner — RAMpage V2.5 24-Hour Hackathon (AI/ML Track) — highest overall score across AI/ML, Web, Blockchain, and IoT tracks

System Architecture
┌──────────────────┐        HTTPS         ┌───────────────────────┐
│   Frontend        │ ──────────────────▶ │   Backend (FastAPI)    │
│   (Netlify)        │ ◀────────────────── │   (Render, Python)     │
│   HTML/JS/Tailwind │      JSON API        │   async/await          │
└──────────────────┘                      └───────────┬─────────────┘
                                                       │
                         ┌─────────────────────────────┼──────────────────────────┐
                         ▼                             ▼                          ▼
               ┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
               │  Upstash Redis    │       │  Groq LLM API     │       │  ntfy.sh          │
               │  (TLS-secured)    │       │  (Llama 3.1       │       │  (push alerts     │
               │  Geospatial index │       │   8B Instant)     │       │   to responders)  │
               │  + session store  │       │                   │       │                   │
               └──────────────────┘       └──────────────────┘       └──────────────────┘

Every component is independently deployable and independently replaceable — the LLM provider, cache layer, and notification layer are all swappable without touching the other services. Deliberate microservice decomposition rather than a monolith.

What This Project Demonstrates
Distributed systems design: Four independently deployed services communicating over well-defined HTTPS APIs — each component horizontally scalable and replaceable without touching the others.
Applied LLM integration: Not just calling an API — designing session-aware conversational state (per-session Redis memory, capped at 8 turns), prompt grounding with structured city-safety domain data, and evaluating a build-vs-buy tradeoff (self-hosted Ollama vs. managed Groq inference) based on real deployment constraints.
Geospatial data engineering: Redis GEOADD / GEOSEARCH for real-time proximity queries (500m responder radius) — the same pattern used in ride-hailing and delivery systems — without a full geospatial database.
Async systems engineering: FastAPI with async/await throughout for concurrent I/O-bound operations; BackgroundTasks-spawned workers for long-running SOS tracking loops decoupled from the request/response cycle.
Production debugging discipline: Seven documented deployment failures, each root-caused via log inspection — not guesswork. Surfaces only when moving from local prototype to real multi-service cloud deployment.
Security-conscious defaults: TLS-secured Redis (rediss://) for live GPS coordinate data; secrets managed via .env + .gitignore; key rotation on exposure; environment-variable-driven config for deployment parity.
End-to-end ownership: From architecture decision to a publicly live, dynamically working system on desktop and mobile — not a notebook or a local demo.
Core Capabilities
🚨 Emergency SOS Dispatch
User taps SOS button → frontend sends coordinates to /api/v1/voice-distress
Backend sets ACTIVE alert state in Redis, writes location to geospatial index
GEOSEARCH finds all users within 500m radius
Push notification dispatched via ntfy.sh to responder channel with live coordinates + resolution link
Background async worker polls user's live position every 2 minutes, re-broadcasting until resolved
Responder hits /api/v1/resolve → Redis state flips to RESOLVED, background loop terminates
📍 Real-Time Geolocation Tracking
Client pings /api/v1/telemetry every 15 seconds with current coordinates
Backend writes to Redis geospatial index via GEOADD
Live map rendered in browser via Leaflet.js using browser Geolocation API
Deployed over HTTPS (Netlify) — required because browsers block navigator.geolocation on insecure HTTP origins; this constraint shaped the entire deployment architecture
🤖 LLM-Powered Safety Assistant (Three-Generation Evolution)
Version	Approach	Limitation	Resolution
V1	Hardcoded keyword dictionary	Not intelligent; no conversational context	—
V2	Self-hosted Ollama (local LLM container)	Not viable for public deployment — requires persistent GPU/CPU process	—
V3 (final)	Groq cloud API (Llama 3.1 8B Instant)	Zero infrastructure to maintain; free-tier low-latency inference	Production
Per-session conversational memory stored in Redis (last 8 turns, keyed by session ID)
System prompt grounded in structured city-level safety data (risk levels, safe/caution zones per city)
Responses are conversational and factually anchored — not purely generative
API Endpoints
Method	Endpoint	Description
POST	/api/v1/telemetry	Submit periodic location update; writes to Redis geospatial index
POST	/api/v1/voice-distress	Trigger SOS alert; sets ACTIVE state, geosearch, dispatches notification, starts background tracking loop
POST	/api/v1/chat	Send message to LLM safety assistant; loads session history from Redis, calls Groq, appends response
GET	/api/v1/resolve	Mark active alert resolved; terminates background tracking worker

Interactive API docs available at /docs on the deployed backend (FastAPI auto-generated Swagger UI).

Technology Stack
Layer	Technology	Why
Frontend	HTML5, Tailwind CSS, vanilla JS, Leaflet.js	Lightweight, no build step — safety-critical UI must load fast
Backend	Python, FastAPI, async/await, Uvicorn	Async I/O for concurrent location updates, LLM calls, and push notifications
Data / cache	Redis (Upstash, managed, TLS)	Native GEOADD/GEOSEARCH for proximity queries; session store; alert state
LLM inference	Groq API (Llama 3.1 8B Instant)	Free-tier, low-latency, OpenAI-compatible cloud inference
Notifications	ntfy.sh	Lightweight push notification channel for responder alerts
Backend hosting	Render (free web service)	Zero-cost, git-integrated continuous deployment
Frontend hosting	Netlify (static hosting)	HTTPS by default — required for browser geolocation API
Version control	Git + GitHub	Full history, .gitignore-enforced secret hygiene
Config management	.env + python-dotenv, Render dashboard env vars	Secrets never committed to source control
Deployment & Engineering Challenges Solved
Challenge	Root Cause	Resolution
Chatbot felt scripted, not conversational	Hardcoded keyword-matching logic	Replaced with Groq LLM call + session-based conversational memory in Redis
App only worked on one WiFi network	Frontend hardcoded to LAN IP address	Migrated frontend and backend to public HTTPS hosts (Netlify + Render)
Live map / geolocation silently failed on mobile	Browsers block navigator.geolocation on non-secure (HTTP) origins	Deployed frontend over HTTPS via Netlify
Redis authentication failures on deploy	TLS connection string parsing errors from copy-paste artifacts	Diagnosed via direct traceback inspection; corrected rediss:// connection string
Emergency resolution links broken post-deploy	Hardcoded localhost:8000 links baked into alert messages	Replaced with environment-variable-driven BASE_URL, injected per deployment environment
Static frontend serving 404	Publish-directory misconfiguration in Netlify UI (base/publish directory nesting bug)	Solved with explicit version-controlled netlify.toml, overriding UI settings — reproducible deployment
Heavy unused dependencies slowing builds	numpy, soundfile, librosa imported but never used	Removed from requirements.txt; reduced build time and deployment footprint
Repository Structure
kanyarakshak-core/
├── backend/
│   ├── main.py              # FastAPI app: telemetry, SOS dispatch, chat endpoints
│   ├── database.py          # Redis connection helper
│   ├── requirements.txt
│   ├── render.yaml          # Render deployment config (Blueprint)
│   └── .env.example         # Environment variable template
├── dashboard/
│   └── index.html           # Frontend UI (map, SOS button, chat interface)
├── chatbot/
│   └── app.py               # Standalone Chainlit chat interface (alternate frontend)
├── netlify.toml             # Netlify build/publish config (overrides UI settings)
├── docker-compose.yml       # Local dev: Redis + optional Ollama containers
└── README.md
Local Development

Prerequisites: Python 3.11+, Groq API key (free tier), Upstash Redis instance (free tier)

bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Fill in GROQ_API_KEY, REDIS_URL, and BASE_URL
uvicorn main:app --reload --host 0.0.0.0 --port 8000

Then open dashboard/index.html in a browser (update API_BASE inside it to http://localhost:8000).

Optional — local Redis + Ollama via Docker:

bash
docker compose up -d
Environment Variables
Variable	Description
GROQ_API_KEY	API key for Groq's chat completions endpoint
REDIS_URL	Redis connection string (rediss://... for TLS-secured Upstash)
BASE_URL	Public base URL of deployed backend — used to build resolution links in alert notifications
Possible Future Work
Real acoustic panic-detection on recorded audio (current voice endpoint accepts audio but doesn't yet analyse it — natural extension using audio classification models)
Migrating the geospatial search to a production-grade clustering algorithm as user density scales
Authentication and encrypted user identity handling (current system uses ephemeral session IDs without persistent accounts)
Monitoring / observability layer (structured logging, error alerting — currently relies on Render's basic logs)
Load-testing the background tracking-worker pattern under many concurrent active alerts (each spawns its own async loop)

Note: Free-tier Render services spin down after inactivity. The first request after idling may take 30–50 seconds while the instance wakes up.
