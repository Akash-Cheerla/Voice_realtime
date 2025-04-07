# realtime_assistant.py
# ✅ Complete version of your voice assistant logic

import asyncio
import websockets
import json
import base64
import os
import openai
from openai import OpenAI
import tempfile
import whisper
import wave
import uuid
import pyaudio
import numpy as np
from datetime import datetime

# -------------------------------
# Configuration
# -------------------------------
RESOURCE_HOST = "admin-m7q8p9qe-eastus2.cognitiveservices.azure.com"
API_VERSION = "2024-10-01-preview"
DEPLOYMENT = "gpt-4o-mini-realtime-preview"
API_KEY = os.getenv("AZURE_API_KEY")

WS_URI = (
    f"wss://{RESOURCE_HOST}/openai/realtime"
    f"?api-version={API_VERSION}"
    f"&deployment={DEPLOYMENT}"
    f"&api-key={API_KEY}"
)

INPUT_RATE = 16000
TARGET_RATE = 24000
OUTPUT_RATE = 48000
CHUNK = 1024
FORMAT = pyaudio.paInt16
INPUT_CHANNELS = 1
OUTPUT_CHANNELS = 2
SPEECH_THRESHOLD = 200

# -------------------------------
# Globals
# -------------------------------
global_loop = None
audio_queue = asyncio.Queue()
conversation_history = []
end_triggered = False
current_assistant_item_id = None
assistant_truncated = False
current_assistant_type = None
model = whisper.load_model("base")
# openai.api_key = API_KEY
openai.api_key = os.getenv("OPENAI_API_KEY")

form_data = {"SiteCompanyName1": None, "SiteAddress": None, "SiteCity": None, "SiteState": None, "SiteZip": None, "SiteVoice": None, "SiteFax": None, "CorporateCompanyName1": None, "CorporateAddress": None, "CorporateCity": None, "CorporateState": None, "CorporateZip": None, "CorporateName": None, "SiteEmail": None, "CorporateVoice": None, "CorporateFax": None, "BusinessWebsite": None, "CorporateEmail": None, "CustomerSvcEmail": None, "AppRetrievalMail": None, "AppRetrievalFax": None, "AppRetrievalFaxNumber": None, "MCC-Desc": None, "MerchantInitials1": None, "MerchantInitials2": None, "MerchantInitials3": None, "MerchantInitials4": None, "MerchantInitials5": None, "MerchantInitials6": None, "MerchantInitials7": None, "signer1signature1": None, "Owner0Name1": None, "Owner0LastName1": None, "signer1signature2": None, "Owner0Name2": None, "Owner0LastName2": None}
last_user_msg = ""
last_assistant_msg = ""

def extract_fields_with_llm(user_text, assistant_question):
    prompt = f"""
You are helping to fill out a merchant processing application form. Based on the assistant's question and the user's response, extract only the field values using the exact field names from this list:

{list(form_data.keys())}

Assistant: {assistant_question}
User: {user_text}

Respond ONLY with a valid JSON object using only the field names above.
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You extract structured fields from conversations."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        content = response.choices[0].message.content.strip()
        print("🧠 LLM raw output:", content)

        if content.startswith("{") and content.endswith("}"):
            parsed = json.loads(content)
            for key, value in parsed.items():
                if key in form_data:
                    form_data[key] = value
        else:
            print("⚠️ LLM response was not valid JSON.")
    except Exception as e:
        print("❌ LLM extraction failed:", e)

def try_extract_fields():
    global last_user_msg, last_assistant_msg
    if last_user_msg and last_assistant_msg:
        extract_fields_with_llm(last_user_msg, last_assistant_msg)

def resample_audio(audio_data, orig_rate, target_rate):
    data = np.frombuffer(audio_data, dtype=np.int16)
    new_length = int(len(data) * target_rate / orig_rate)
    original_indices = np.linspace(0, 1, num=len(data))
    new_indices = np.linspace(0, 1, num=new_length)
    resampled = np.interp(new_indices, original_indices, data).astype(np.int16)
    return resampled.tobytes()

def open_microphone_stream():
    pa = pyaudio.PyAudio()
    stream = pa.open(format=FORMAT,
                     channels=INPUT_CHANNELS,
                     rate=INPUT_RATE,
                     input=True,
                     frames_per_buffer=CHUNK,
                     stream_callback=microphone_callback)
    stream.start_stream()
    print("🎙️ Microphone stream started.")
    return pa, stream

def open_output_stream():
    pa = pyaudio.PyAudio()
    stream = pa.open(format=FORMAT,
                     channels=OUTPUT_CHANNELS,
                     rate=OUTPUT_RATE,
                     output=True,
                     frames_per_buffer=CHUNK)
    return pa, stream

def play_audio(audio_bytes, output_stream):
    upsampled = resample_audio(audio_bytes, TARGET_RATE, OUTPUT_RATE)
    mono_data = np.frombuffer(upsampled, dtype=np.int16)
    stereo_data = np.repeat(mono_data, 2)
    output_stream.write(stereo_data.tobytes())

def microphone_callback(in_data, frame_count, time_info, status):
    if global_loop is not None:
        global_loop.call_soon_threadsafe(audio_queue.put_nowait, in_data)
    return (None, pyaudio.paContinue)

def get_current_time(args):
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

async def send_event(ws, event):
    event["event_id"] = str(uuid.uuid4())
    await ws.send(json.dumps(event))

async def update_session(ws):
    await send_event(ws, {
        "type": "session.update",
        "session": {
            "modalities": ["audio", "text"],
            "instructions": """You are an AI assistant designed to help users fill out a Merchant Processing Application and Agreement form. Greet the user in a friendly way when starting.
Your task is to guide the user through each section of the form, asking relevant questions to extract the necessary information required. 
Ensure that the conversation remains professional and user-friendly, providing explanations or examples when necessary to help the user understand the context of each question. DO NOT ANSWER ANY QUESTIONS NOT RELATED TO THE TASK AT HAND
Always prioritize privacy and remind the user not to share sensitive information unless necessary for the form. For sections requiring specific types of data like percentages, business types, or legal requirements, 
offer examples to aid in understanding. Confirm each detail with the user before moving on to the next section. only ask a couple of questions at a time and not all at once. Information needed to fill out the form includes: 
business name also known as doing business as, clients corp/legal name, business address, city, state and zip, the billing address city state and zip, the business phone number, fax number, contact name, contact phone, business email address, business website address, customer service email and most importantly their SIC/MCC and MerchantInitials. 
Once all these fields are collected, read back the entire collected information to the user and ask them to confirm it and mention that it may take a few seconds to process all the information . After they confirm respond with 'END OF CONVERSATION' and nothing else. """,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500,
                "create_response": True
            },
            "tools": [
                {
                    "type": "function",
                    "name": "get_current_time",
                    "description": "Returns the current time.",
                    "parameters": {"type": "object", "properties": {}}
                }
            ],
            "tool_choice": "auto"
        }
    })

async def process_microphone(ws):
    global assistant_truncated, current_assistant_item_id
    while not end_triggered:
        chunk = await audio_queue.get()
        resampled_chunk = resample_audio(chunk, INPUT_RATE, TARGET_RATE)
        rms = np.sqrt(np.mean(np.frombuffer(resampled_chunk, dtype=np.int16).astype(np.float32) ** 2))
        if rms > SPEECH_THRESHOLD and current_assistant_item_id and not assistant_truncated:
            await send_event(ws, {
                "type": "conversation.item.truncate",
                "item_id": current_assistant_item_id,
                "content_index": 0,
                "audio_end_ms": 0
            })
            assistant_truncated = True
        await send_event(ws, {
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(resampled_chunk).decode("utf-8")
        })
        await asyncio.sleep(0.01)

async def send_initial_message(ws):
    text = "Hello, can we get started by telling me the first steps?"
    await send_event(ws, {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}]
        }
    })
    conversation_history.append({"role": "user", "text": text, "timestamp": datetime.now().isoformat()})
    await send_event(ws, {"type": "response.create"})
    print("🟢 User:", text)


async def handle_websocket_messages(ws, output_stream):
    global current_assistant_item_id, assistant_truncated, end_triggered, current_assistant_type
    global last_user_msg, last_assistant_msg
    partial_text = ""
    assistant_audio_buffer = b""

    try:
        async for message in ws:
            try:
                msg = json.loads(message)
            except Exception:
                print("❌ Failed to parse message:", message)
                continue

            event_type = msg.get("type")

            if event_type == "response.audio.delta":
                delta_b64 = msg.get("delta", "")
                if delta_b64:
                    audio_data = base64.b64decode(delta_b64)
                    play_audio(audio_data, output_stream)
                    assistant_audio_buffer += audio_data

            elif event_type == "response.audio.done":
                if assistant_audio_buffer:
                    try:
                        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_audio:
                            with wave.open(tmp_audio, 'wb') as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(24000)
                                wf.writeframes(assistant_audio_buffer)
                            tmp_audio_path = tmp_audio.name

                        result = model.transcribe(tmp_audio_path)
                        transcribed_text = result.get("text", "").strip()

                        if transcribed_text:
                            print("\n🟡 Assistant (transcribed):", transcribed_text)
                            conversation_history.append({
                                "role": "assistant",
                                "text": transcribed_text,
                                "timestamp": datetime.now().isoformat()
                            })
                            last_assistant_msg = transcribed_text
                            try_extract_fields()

                            # ✅ Patch: Detect END OF CONVERSATION in audio transcription
                            if "END OF CONVERSATION" in transcribed_text.upper() and not end_triggered:
                                end_triggered = True
                                print("🛑 END OF CONVERSATION (from audio). Saving and exiting.")
                                with open("filled_form.json", "w", encoding="utf-8") as f:
                                    json.dump(form_data, f, indent=2, ensure_ascii=False)
                                print("✅ Extracted form data saved to 'filled_form.json'")

                        os.remove(tmp_audio_path)
                        assistant_audio_buffer = b""
                    except Exception as e:
                        print("❌ Whisper transcription failed:", e)

                current_assistant_item_id = None
                assistant_truncated = False
                current_assistant_type = None

            elif event_type == "response.text.delta":
                delta_text = msg.get("delta", "")
                partial_text += delta_text
                print(delta_text, end="", flush=True)

            elif event_type == "response.text.done":
                final_text = msg.get("text", "") or partial_text
                print("\n🟡 Assistant:", final_text)
                if final_text.strip():
                    conversation_history.append({
                        "role": "assistant",
                        "text": final_text,
                        "timestamp": datetime.now().isoformat()
                    })
                    last_assistant_msg = final_text
                    try_extract_fields()

                partial_text = ""
                current_assistant_item_id = None
                current_assistant_type = None
                assistant_truncated = False

                if "END OF CONVERSATION" in final_text.upper():
                    end_triggered = True
                    print("🛑 END OF CONVERSATION detected. Exiting...")
                    with open("filled_form.json", "w", encoding="utf-8") as f:
                        json.dump(form_data, f, indent=2, ensure_ascii=False)
                    print("✅ Extracted form data saved to 'filled_form.json'")
                    return

            elif event_type == "input.transcription":
                transcription = msg.get("text", "")
                if transcription:
                    print("\n🟢 User (transcribed):", transcription)
                    conversation_history.append({
                        "role": "user",
                        "text": transcription,
                        "timestamp": datetime.now().isoformat()
                    })
                    last_user_msg = transcription
                    try_extract_fields()

            elif event_type == "conversation.item.created":
                item = msg.get("item", {})
                role = item.get("role")
                content = item.get("content", [])
                msg_type = item.get("type", "")

                if msg_type == "message":
                    msg_text = ""
                    for c in content:
                        if c.get("type") == "input_text":
                            msg_text += c.get("text", "")
                        if c.get("type") == "input_audio" and c.get("transcript"):
                            msg_text += c.get("transcript", "")

                    if not msg_text:
                        msg_text = item.get("text", "")

                    if role == "user" and msg_text:
                        print("🟢 User:", msg_text)
                        conversation_history.append({
                            "role": "user",
                            "text": msg_text,
                            "timestamp": datetime.now().isoformat()
                        })
                        last_user_msg = msg_text
                        try_extract_fields()

                    elif role == "assistant":
                        current_assistant_item_id = item.get("id")
                        current_assistant_type = item.get("message_format", "text")
                        assistant_truncated = False
                        print(f"📌 Assistant message ID: {current_assistant_item_id} ({current_assistant_type})")

                        if msg_text:
                            print("🟡 Assistant (created):", msg_text)
                            conversation_history.append({
                                "role": "assistant",
                                "text": msg_text,
                                "timestamp": datetime.now().isoformat()
                            })
                            last_assistant_msg = msg_text
                            try_extract_fields()

                        if "END OF CONVERSATION" in msg_text.upper():
                            end_triggered = True
                            print("🛑 END OF CONVERSATION detected. Exiting...")
                            with open("filled_form.json", "w", encoding="utf-8") as f:
                                json.dump(form_data, f, indent=2, ensure_ascii=False)
                            print("✅ Extracted form data saved to 'filled_form.json'")
                            return

            elif event_type == "error":
                error_info = msg.get("error", {})
                print("❌ Error from API:", error_info)

    except asyncio.CancelledError:
        print("🟨 Message handler cancelled.")
    except Exception as e:
        print("❌ Unexpected error in handle_websocket_messages:", e)



async def realtime_client():
    global global_loop
    global_loop = asyncio.get_event_loop()
    pa_in, mic = open_microphone_stream()
    pa_out, speaker = open_output_stream()

    try:
        async with websockets.connect(WS_URI) as ws:
            await update_session(ws)
            await send_initial_message(ws)
            mic_task = asyncio.create_task(process_microphone(ws))
            msg_task = asyncio.create_task(handle_websocket_messages(ws, speaker))

            while not end_triggered:
                await asyncio.sleep(0.5)

            mic_task.cancel()
            msg_task.cancel()
            await asyncio.gather(mic_task, msg_task, return_exceptions=True)

    finally:
        mic.stop_stream()
        mic.close()
        pa_in.terminate()
        speaker.stop_stream()
        speaker.close()
        pa_out.terminate()
        with open("conversation_history.json", "w", encoding="utf-8") as f:
            json.dump(conversation_history, f, indent=2, ensure_ascii=False)
        with open("filled_form.json", "w", encoding="utf-8") as f:
            json.dump(form_data, f, indent=2, ensure_ascii=False)
        print("✅ Conversation saved to 'conversation_history.json'")
        print("✅ Form data saved to 'filled_form.json'")
        print("✅ Session ended.")


async def run_assistant():
    try:
        await realtime_client()
    except KeyboardInterrupt:
        print("👋 Exiting...")
