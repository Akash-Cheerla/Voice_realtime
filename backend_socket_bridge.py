# backend_socket_bridge.py (new file to stream browser audio chunks to Azure GPT-4o)

import os
import json
import base64
import uuid
import asyncio
import websockets
from datetime import datetime
from openai import OpenAI
from fastapi import UploadFile
import tempfile
import subprocess

AZURE_WS_URI = f"wss://{os.getenv('AZURE_HOST')}/openai/realtime?api-version=2024-10-01-preview&deployment=gpt-4o-mini-realtime-preview&api-key={os.getenv('AZURE_API_KEY')}"
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def stream_to_gpt_and_respond(text_input: str):
    try:
        async with websockets.connect(AZURE_WS_URI) as ws:
            await ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "modalities": ["text"],
                    "tool_choice": "auto"
                },
                "event_id": str(uuid.uuid4())
            }))

            await ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text_input}]
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
        print("[WebSocket Error]", e)
        return "Sorry, something went wrong."

def convert_webm_to_wav(input_path):
    output_path = input_path.replace(".webm", ".wav")
    subprocess.run(["ffmpeg", "-y", "-i", input_path, output_path], capture_output=True)
    return output_path

def generate_tts_response(text: str) -> str:
    speech = openai_client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=text,
        response_format="wav"
    )
    return base64.b64encode(speech.content).decode("utf-8")

def process_browser_audio(audio: UploadFile):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_webm:
        content = audio.file.read()
        temp_webm.write(content)
        webm_path = temp_webm.name

    wav_path = convert_webm_to_wav(webm_path)

    import whisper
    model = whisper.load_model("base")
    transcription = model.transcribe(wav_path).get("text", "")
    print("🗣 Transcribed:", transcription)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    reply_text = loop.run_until_complete(stream_to_gpt_and_respond(transcription))
    print("🤖 GPT-4o said:", reply_text)

    audio_b64 = generate_tts_response(reply_text)
    return transcription, reply_text, audio_b64
