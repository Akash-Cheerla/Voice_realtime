# realtime_assistant.py (Railway-compatible version - no pyaudio)

import asyncio
import websockets
import json
import base64
import os
import openai
from openai import OpenAI
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

openai.api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai.api_key)

form_data = {"SiteCompanyName1": None, "SiteAddress": None, "SiteCity": None, "SiteState": None, "SiteZip": None, "SiteVoice": None, "SiteFax": None, "CorporateCompanyName1": None, "CorporateAddress": None, "CorporateCity": None, "CorporateState": None, "CorporateZip": None, "CorporateName": None, "SiteEmail": None, "CorporateVoice": None, "CorporateFax": None, "BusinessWebsite": None, "CorporateEmail": None, "CustomerSvcEmail": None, "AppRetrievalMail": None, "AppRetrievalFax": None, "AppRetrievalFaxNumber": None, "MCC-Desc": None, "MerchantInitials1": None, "MerchantInitials2": None, "MerchantInitials3": None, "MerchantInitials4": None, "MerchantInitials5": None, "MerchantInitials6": None, "MerchantInitials7": None, "signer1signature1": None, "Owner0Name1": None, "Owner0LastName1": None, "signer1signature2": None, "Owner0Name2": None, "Owner0LastName2": None}
conversation_history = []
last_user_msg = ""
last_assistant_msg = ""
end_triggered = False


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


async def send_event(ws, event):
    event["event_id"] = str(uuid.uuid4())
    await ws.send(json.dumps(event))


async def update_session(ws):
    await send_event(ws, {
        "type": "session.update",
        "session": {
            "modalities": ["text"],
            "instructions": """You are an AI assistant designed to help users fill out a Merchant Processing Application and Agreement form. Greet the user in a friendly way when starting.
Your task is to guide the user through each section of the form, asking relevant questions to extract the necessary information required. 
Ensure that the conversation remains professional and user-friendly, providing explanations or examples when necessary to help the user understand the context of each question. DO NOT ANSWER ANY QUESTIONS NOT RELATED TO THE TASK AT HAND
Always prioritize privacy and remind the user not to share sensitive information unless necessary for the form. For sections requiring specific types of data like percentages, business types, or legal requirements, 
offer examples to aid in understanding. Confirm each detail with the user before moving on to the next section. only ask a couple of questions at a time and not all at once. Information needed to fill out the form includes: 
business name also known as doing business as, clients corp/legal name, business address, city, state and zip, the billing address city state and zip, the business phone number, fax number, contact name, contact phone, business email address, business website address, customer service email and most importantly their SIC/MCC and MerchantInitials. 
Once all these fields are collected, read back the entire collected information to the user and ask them to confirm it and mention that it may take a few seconds to process all the information . After they confirm respond with 'END OF CONVERSATION' and nothing else. """,
            "tool_choice": "auto"
        }
    })


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
    global end_triggered, last_user_msg, last_assistant_msg
    try:
        async for message in ws:
            msg = json.loads(message)
            event_type = msg.get("type")

            if event_type == "response.text.done":
                final_text = msg.get("text", "")
                print("🟡 Assistant:", final_text)
                conversation_history.append({"role": "assistant", "text": final_text, "timestamp": datetime.now().isoformat()})
                last_assistant_msg = final_text
                try_extract_fields()
                if "END OF CONVERSATION" in final_text.upper():
                    end_triggered = True

            elif event_type == "input.transcription":
                transcription = msg.get("text", "")
                print("🟢 User:", transcription)
                conversation_history.append({"role": "user", "text": transcription, "timestamp": datetime.now().isoformat()})
                last_user_msg = transcription
                try_extract_fields()

    except Exception as e:
        print("❌ Unexpected error in WebSocket:", e)


async def realtime_client():
    try:
        async with websockets.connect(WS_URI) as ws:
            await update_session(ws)
            await send_initial_message(ws)
            await handle_websocket_messages(ws, None)
    except Exception as e:
        print("❌ Connection error:", e)


async def run_assistant():
    try:
        await realtime_client()
    except KeyboardInterrupt:
        print("👋 Exiting...")
