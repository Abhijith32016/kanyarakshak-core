import chainlit as cl
import httpx

# The address of your running FastAPI backend
BACKEND_URL = "http://localhost:8000/api/v1/chat"

@cl.on_chat_start
async def start():
    cl.user_session.set("session_id", "USER-A46FA6")
    await cl.Message(
        content="🤖 Welcome to KanyaRakshak Safety Assistant! Ask me anything about location safety or precautions."
    ).send()

@cl.on_message
async def main(message: cl.Message):
    session_id = cl.user_session.get("session_id")
    
    # Forward the user's message to the FastAPI backend LLM engine
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                BACKEND_URL,
                json={"session_id": session_id, "message": message.content},
                timeout=15.0
            )
            
            if response.status_code == 200:
                backend_data = response.json()
                reply = backend_data.get("response", "⚠️ Received an invalid response from security core.")
            else:
                reply = f"⚠️ Core engine returned an error status: {response.status_code}"
                
        except Exception as e:
            reply = "🚨 Unable to reach the KanyaRakshak Security Core. Please check if your backend terminal is running!"

    # Send the backend's real LLM/database answer back to the UI interface
    await cl.Message(content=reply).send()