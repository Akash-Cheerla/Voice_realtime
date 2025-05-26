# # main.py (FastAPI backend for voice assistant + PDF filler)

# import asyncio
# import json
# import os
# from fastapi import FastAPI, Request
# from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
# from fastapi.staticfiles import StaticFiles
# from fastapi.templating import Jinja2Templates
# from pydantic import BaseModel
# from realtime_assistant import run_assistant  # From your cloud-safe assistant
# from fill_pdf_logic import fill_pdf  # From your working PDF filler script

# app = FastAPI()
# app.mount("/static", StaticFiles(directory="static"), name="static")
# templates = Jinja2Templates(directory="templates")

# class ConfirmRequest(BaseModel):
#     confirmed: bool

# @app.get("/", response_class=HTMLResponse)
# async def index(request: Request):
#     return templates.TemplateResponse("index.html", {"request": request})

# @app.post("/start-assistant")
# async def start_assistant():
#     try:
#         await run_assistant()
#         return {"status": "success"}
#     except Exception as e:
#         return {"status": "error", "detail": str(e)}

# @app.get("/form-data")
# async def get_form_data():
#     if os.path.exists("filled_form.json"):
#         with open("filled_form.json", "r", encoding="utf-8") as f:
#             raw_data = json.load(f)
#         filtered_data = {
#             k: v for k, v in raw_data.items()
#             if v and v.strip().lower() != "null"
#         }
#         return JSONResponse(content=filtered_data)
#     return JSONResponse(content={}, status_code=404)

# @app.post("/confirm")
# async def confirm_form(request: ConfirmRequest):
#     if request.confirmed:
#         with open("filled_form.json", "r", encoding="utf-8") as f:
#             field_values = json.load(f)
#         input_pdf = "form_template.pdf"
#         output_pdf = "output_filled.pdf"
#         fill_pdf(input_pdf, output_pdf, field_values)
#         return {"status": "filled", "download_url": "/download"}
#     return {"status": "cancelled"}

# @app.get("/download")
# async def download_pdf():
#     return FileResponse("output_filled.pdf", media_type="application/pdf", filename="Merchant_Form_Filled.pdf")


# main.py (FastAPI backend for voice assistant + PDF filler)

import asyncio
import json
import os
import base64
import tempfile
from fastapi import FastAPI, Request, UploadFile, WebSocket, WebSocketDisconnect, File
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from realtime_assistant import run_assistant  # For local mic testing (optional)
from fill_pdf_logic import fill_pdf  # From your working PDF filler script
from web_assistant import process_audio_input  # New logic for browser mic

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class ConfirmRequest(BaseModel):
    confirmed: bool

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/start-assistant")
async def start_assistant():
    try:
        await run_assistant()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.get("/form-data")
async def get_form_data():
    if os.path.exists("filled_form.json"):
        with open("filled_form.json", "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        filtered_data = {
            k: v for k, v in raw_data.items()
            if v is not None and v != "" and v != "null"
        }
        return JSONResponse(content=filtered_data)
    return JSONResponse(content={}, status_code=404)

@app.post("/confirm")
async def confirm_form(request: ConfirmRequest):
    if request.confirmed:
        with open("filled_form.json", "r", encoding="utf-8") as f:
            field_values = json.load(f)

        input_pdf = "form_template.pdf"
        output_pdf = "output_filled.pdf"
        fill_pdf(input_pdf, output_pdf, field_values)

        return {"status": "filled", "download_url": "/download"}
    return {"status": "cancelled"}

@app.get("/download")
async def download_pdf():
    return FileResponse("output_filled.pdf", media_type="application/pdf", filename="Merchant_Form_Filled.pdf")

@app.post("/upload-audio")
async def upload_audio(audio: UploadFile = File(...)):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_file:
            contents = await audio.read()
            temp_file.write(contents)
            temp_path = temp_file.name

        text, reply_b64 = process_audio_input(temp_path)
        os.remove(temp_path)

        return JSONResponse(content={"text": text, "audio_b64": reply_b64})

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
