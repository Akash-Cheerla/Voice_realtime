# main.py (FastAPI backend for voice assistant + PDF filler)

import asyncio
import json
import os
from fastapi import FastAPI, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from realtime_assistant import run_assistant  # From your full assistant script
from fill_pdf_logic import fill_pdf  # From your working PDF filler script

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
        await run_assistant()  # This is your full realtime assistant script
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.get("/form-data")
async def get_form_data():
    if os.path.exists("filled_form.json"):
        with open("filled_form.json", "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        # ✅ Only return fields with meaningful values
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

        input_pdf = "form_template.pdf"  # Make sure this matches your PDF file
        output_pdf = "output_filled.pdf"
        fill_pdf(input_pdf, output_pdf, field_values)

        return {"status": "filled", "download_url": "/download"}
    return {"status": "cancelled"}

@app.get("/download")
async def download_pdf():
    return FileResponse("output_filled.pdf", media_type="application/pdf", filename="Merchant_Form_Filled.pdf")
