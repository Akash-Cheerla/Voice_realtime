import os
import json
import base64
from fastapi import FastAPI, Request, UploadFile, File, Body
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from openai import OpenAI
from fill_pdf_logic import fill_pdf

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class ConfirmRequest(BaseModel):
    confirmed: bool

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "AZURE_API_KEY": os.getenv("AZURE_API_KEY")
    })

@app.get("/form-data")
async def get_form_data():
    if os.path.exists("filled_form.json"):
        with open("filled_form.json", "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        filtered_data = {
            k: v for k, v in raw_data.items()
            if v is not None and v.strip().lower() != "null"
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

@app.post("/tts")
async def tts_endpoint(payload: dict = Body(...)):
    try:
        text = payload.get("text", "")
        if not text:
            return JSONResponse(content={"error": "No text provided"}, status_code=400)

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        speech = client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=text,
            response_format="wav"
        )
        audio_bytes = speech.content
        b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
        return {"audio_b64": b64_audio}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
