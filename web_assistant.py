import tempfile
import base64
import os
import whisper
from openai import OpenAI
import soundfile as sf
import io

model = whisper.load_model("base")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def transcribe_audio(file_path):
    result = model.transcribe(file_path)
    return result.get("text", "")

def query_gpt_response(user_text):
    system_prompt = "You are an AI assistant helping fill out a merchant processing form. Keep your responses concise and formal."
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text}
    ]
    response = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0.4
    )
    return response.choices[0].message.content.strip()

def synthesize_speech(text):
    speech_response = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=text,
        response_format="wav"
    )
    audio_bytes = speech_response.content
    return base64.b64encode(audio_bytes).decode("utf-8")

def process_audio_input(file_path):
    user_text = transcribe_audio(file_path)
    print("User said:", user_text)
    reply = query_gpt_response(user_text)
    print("Assistant replied:", reply)
    reply_audio_b64 = synthesize_speech(reply)
    return reply, reply_audio_b64
