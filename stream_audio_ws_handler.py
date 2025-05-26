# stream_audio_ws_handler.py

import os
import io
import base64
import uuid
import json
import asyncio
import websockets
import numpy as np
import soundfile as sf
import faster_whisper
from openai import OpenAI
from starlette.websockets import WebSocket

# Load Whisper model (faster-whisper for real-time)
model = faster_whisper.WhisperModel("base", compute_type="int8")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Azure GPT-4o WS connection setup
AZURE_WS = f"wss://{os.getenv('AZURE_HOST')}/openai/realtime?api-version=2024-10-01-preview&deployment=gpt-4o-mini-realtime-preview&api-key={os.getenv('AZURE_API_KEY')}"

async def stream_text_to_gpt(user_text: str) -> str:
    try:
        async with websockets.connect(AZURE_WS) as ws:
            await ws.send(json.dumps({
                "type": "session.update",
                "session": {"modalities": ["text"], "tool_choice": "auto"},
                "event_id": str(uuid.uuid4())
            }))
            await ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_text}]
                },
                "event_id": str(uuid.uuid4())
            }))
            await ws.send(json.dumps({"type": "response.create", "event_id": str(uuid.uuid4())}))

            full_response = ""
            async for message in ws:
                data = json.loads(message)
                if data.get("type") == "response.text.delta":
                    full_response += data.get("text", "")
                elif data.get("type") == "response.text.done":
                    break
            return full_response
    except Exception as e:
        print("[WebSocket GPT Error]", e)
        return "Sorry, something went wrong."

def convert_pcm_to_wav(pcm_data):
    arr = np.frombuffer(pcm_data, dtype=np.int16)
    buffer = io.BytesIO()
    sf.write(buffer, arr, 16000, format='WAV')
    buffer.seek(0)
    return buffer

async def handle_audio_stream(websocket: WebSocket):
    await websocket.accept()
    print("🔌 WebSocket client connected")

    pcm_buffer = bytearray()
    last_transcript = ""

    try:
        while True:
            chunk = await websocket.receive_bytes()
            pcm_buffer.extend(chunk)

            if len(pcm_buffer) >= 32000:  # 1 second of audio at 16kHz
                wav_data = convert_pcm_to_wav(pcm_buffer)
                segments, _ = model.transcribe(wav_data, beam_size=1)
                text = " ".join([seg.text.strip() for seg in segments])

                if text and text != last_transcript:
                    print("🗣", text)
                    reply = await stream_text_to_gpt(text)
                    print("🤖", reply)
                    last_transcript = text

                    speech = client.audio.speech.create(
                        model="tts-1",
                        voice="nova",
                        input=reply,
                        response_format="wav"
                    )
                    reply_audio_b64 = base64.b64encode(speech.content).decode("utf-8")

                    await websocket.send_text(json.dumps({
                        "text": reply,
                        "audio_b64": reply_audio_b64
                    }))

                pcm_buffer.clear()

    except Exception as e:
        print("❌ Stream closed or error:", e)
        await websocket.close()
