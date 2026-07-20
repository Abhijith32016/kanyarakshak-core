import asyncio
import json
import logging
import os
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis
import httpx
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KanyaRakshakCore")

app = FastAPI(title="KanyaRakshak Unified Core Engine", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connect to Redis
# Local dev: falls back to localhost. Deployed: set REDIS_URL to your Upstash "rediss://..." connection string.
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
try:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    r.ping()
    logger.info("Successfully connected to Redis Geospatial fabric.")
except redis.exceptions.ConnectionError:
    logger.error("Redis fabric offline!")

# Public base URL of this backend, used to build links (e.g. the /resolve link sent to police).
# Set this to your deployed Render URL, e.g. https://kanyarakshak-core.onrender.com
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

CRIME_RATE_DATABASE = {
    "hyderabad": {"risk_level": "Low to Moderate", "safe_zones": ["Gachibowli", "HITEC City"], "caution_zones": ["Isolated dark links"]},
    "delhi": {"risk_level": "High Risk Profile", "safe_zones": ["Connaught Place (Main areas)"], "caution_zones": ["Outer ring unlit paths"]},
    "bengaluru": {"risk_level": "Moderate", "safe_zones": ["Indiranagar", "Electronic City"], "caution_zones": ["Unpatrolled corridors"]}
}

# --- LLM configuration: Groq (free tier, cloud-hosted, OpenAI-compatible API) ---
# Sign up free at https://console.groq.com -> API Keys, then set GROQ_API_KEY as an env var.
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.1-8b-instant"
CHAT_HISTORY_TURNS = 8  # how many past messages to keep as context per session

SYSTEM_PROMPT = (
    "You are the KanyaRakshak Safety Assistant, a supportive personal-safety chatbot for a women's "
    "safety app. Be warm, concise, and practical. You can discuss general safety tips, help the user "
    "think through a situation, and remind them that tapping the SOS button triggers an emergency alert "
    "with live location tracking to nearby responders and police. "
    "Reference this known city safety data when relevant (don't force it into unrelated replies): "
    f"{json.dumps(CRIME_RATE_DATABASE)}. "
    "If the user describes an active emergency or says they are in danger, tell them clearly to press the "
    "SOS button in the app or call local emergency services immediately, in addition to anything else you say."
)

class TelemetryCheckIn(BaseModel):
    session_id: str
    latitude: float
    longitude: float

class ChatQuery(BaseModel):
    session_id: str
    message: str

# 2-MINUTE POLICE TRACKING LOOP WORKER
async def continuous_tracking_worker(session_id: str, initial_lat: float, initial_lng: float):
    logger.info(f"Police 2-minute tracking loop spawned for: {session_id}")
    while True:
        status = r.get(f"alert:{session_id}:status")
        if status != "ACTIVE":
            logger.info(f"Alert resolved. Killing tracking worker for {session_id}.")
            break
            
        current_lat = float(r.get(f"user:{session_id}:lat") or initial_lat)
        current_lng = float(r.get(f"user:{session_id}:lng") or initial_lng)
        
        async with httpx.AsyncClient() as client:
            try:
                # Continuous broadcast directly to the ntfy channel for police monitoring
                await client.post(
                    "https://ntfy.sh/kanyarakshak_alert_channel",
                    data=f"🚨 [POLICE TRACE FEED] User {session_id} is active.\nLocation: {current_lat},{current_lng}\nMark Solved: {BASE_URL}/api/v1/resolve?session_id={session_id}",
                    headers={"Title": "ACTIVE PATROL TRACE", "Priority": "4"}
                )
            except Exception as e:
                logger.error(f"Failed to push tracking loop: {e}")
                
        await asyncio.sleep(120)

@app.post("/api/v1/telemetry")
async def update_telemetry(data: TelemetryCheckIn):
    r.set(f"user:{data.session_id}:lat", str(data.latitude))
    r.set(f"user:{data.session_id}:lng", str(data.longitude))
    r.geoadd("active_users_mesh", (data.longitude, data.latitude, data.session_id))
    return {"status": "synchronized"}

# UNIFIED CHATBOT ENGINE (LLM-backed via Groq cloud API, with per-session memory in Redis)
@app.post("/api/v1/chat")
async def chatbot_respond(query: ChatQuery):
    history_key = f"chat:{query.session_id}:history"

    # Load prior turns for this session
    raw_history = r.get(history_key)
    try:
        history = json.loads(raw_history) if raw_history else []
    except (TypeError, ValueError):
        history = []

    history.append({"role": "user", "content": query.message})

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history[-CHAT_HISTORY_TURNS:]

    reply_text = None
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY is not set.")
    else:
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    json={"model": GROQ_MODEL, "messages": messages, "temperature": 0.6},
                )
                resp.raise_for_status()
                reply_text = resp.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                logger.error(f"Groq chat call failed: {e}")

    if not reply_text:
        reply_text = (
            "⚠️ I couldn't reach the AI assistant right now. If this is an emergency, "
            "please press the SOS button. Otherwise, check that GROQ_API_KEY is configured correctly."
        )
    else:
        history.append({"role": "assistant", "content": reply_text})
        r.set(history_key, json.dumps(history[-CHAT_HISTORY_TURNS:]))

    return {"response": reply_text}

# VOICE & BUTTON EMERGENCY PROCESSING DISPATCH
@app.post("/api/v1/voice-distress")
async def process_voice_distress(
    background_tasks: BackgroundTasks,
    session_id: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    audio_file: UploadFile = File(...)
):
    r.set(f"alert:{session_id}:status", "ACTIVE")
    r.set(f"user:{session_id}:lat", str(latitude))
    r.set(f"user:{session_id}:lng", str(longitude))

    # Add mock mesh users into the database if the mesh is empty for demonstration purposes
    r.geoadd("active_users_mesh", (longitude + 0.002, latitude + 0.002, "MESH_USER_POLICE_ALPHA"))
    r.geoadd("active_users_mesh", (longitude - 0.001, latitude + 0.001, "MESH_USER_CITIZEN_BRAVO"))

    nearby_responders = []
    try:
        nearby_responders = r.geosearch("active_users_mesh", longitude=longitude, latitude=latitude, radius=500, unit="m")
        nearby_responders = [user for user in nearby_responders if user != session_id]
    except Exception as e:
        logger.error(f"Geospatial mesh error: {e}")

    # Dispatch immediately to ntfy.sh for police and responders
    async with httpx.AsyncClient() as client:
        await client.post(
            "https://ntfy.sh/kanyarakshak_alert_channel",
            data=f"🚨 EMERGENCY ALERT! User: {session_id}.\nLocation: {latitude},{longitude}\nAlerted Neighbors: {', '.join(nearby_responders)}\nClick to Clear: {BASE_URL}/api/v1/resolve?session_id={session_id}",
            headers={"Title": "CRITICAL EMERGENCY SOS", "Priority": "5"}
        )

    # Spawn the 2-minute background tracking loop task
    background_tasks.add_task(continuous_tracking_worker, session_id, latitude, longitude)

    return {
        "threat_detected": True,
        "nearby_alerts_dispatched": len(nearby_responders),
        "alerted_users": nearby_responders
    }

@app.get("/api/v1/resolve")
async def resolve_incident(session_id: str = Query(..., description="Target session ID")):
    r.set(f"alert:{session_id}:status", "RESOLVED")
    return {"message": f"Incident for session {session_id} has been resolved. Tracking loops terminated."}