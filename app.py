from fastapi import FastAPI, UploadFile, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse,JSONResponse, FileResponse
from pdf_reader import extract_pages_from_pdf
from summarizer import summarize_entire_document, summarize_page
import tempfile
import os
import time
from datetime import datetime

app = FastAPI()

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://simpelringkas.id"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# ✅ Serve landing page
@app.get("/", response_class=HTMLResponse)
def landing_page():
    return "<h1>✅ Aplikasi berhasil jalan!</h1>"
    # with open("about-us.html", "r", encoding="utf-8") as f:
        #return f.read()

# ✅ Serve tool page
@app.get("/app", response_class=HTMLResponse)
def tool_page():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

# Variabel global
current_progress = {"page": 0, "total": 0, "status": "idle"}
TEMP_SUMMARY_PATH = "summary.txt"
user_limits = {}
DAILY_LIMIT = 3
PAGE_MODE_DELAY = 3  # Detik antar halaman saat mode = "page"

@app.get("/api/progress")
def get_progress():
    return current_progress

@app.get("/api/download")
def download_summary():
    if os.path.exists(TEMP_SUMMARY_PATH):
        return FileResponse(path=TEMP_SUMMARY_PATH, filename="ringkasan.txt", media_type="text/plain")
    return JSONResponse(status_code=404, content={"message": "Ringkasan belum tersedia."})

@app.post("/api/summarize")
async def summarize(
    request: Request,
    pdf_file: UploadFile,
    language: str = Form("id"),
    mode: str = Form("full")  # "full" atau "page"
):
    global current_progress, user_limits
    current_progress = {"page": 0, "total": 0, "status": "processing"}

    # Baca isi file
    contents = await pdf_file.read()
    file_size = len(contents)

    # Validasi ukuran hanya untuk mode full
    if mode == "full" and file_size > 300 * 1024:
        return JSONResponse(
            status_code=413,
            content={"summary": "❌ Ukuran file PDF melebihi batas 300 KB untuk mode keseluruhan."}
        )

    """
    # Limit ringkasan per IP per hari
    ip = request.client.host
    today = datetime.now().strftime("%Y-%m-%d")
    user_data = user_limits.get(ip)

    if user_data:
        if user_data["date"] == today:
            if user_data["count"] >= DAILY_LIMIT:
                return JSONResponse(
                    status_code=429,
                    content={"summary": "❌ Batas ringkasan harian (3x) tercapai. Coba lagi besok."}
                )
            else:
                user_data["count"] += 1
        else:
            user_limits[ip] = {"date": today, "count": 1}
    else:
        user_limits[ip] = {"date": today, "count": 1}
    """
    try:
        # Simpan file PDF sementara
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        # Ekstrak teks semua halaman
        pages = extract_pages_from_pdf(tmp_path)
        full_text = "\n\n".join(pages)

        if mode == "page":
            all_summaries = []
            for i, page_text in enumerate(pages):
                current_progress["page"] = i + 1
                summary = summarize_page(page_text, language)
                all_summaries.append(f"[Halaman {i+1}]\n{summary.strip()}")
                time.sleep(PAGE_MODE_DELAY)
            final_summary = "\n\n".join(all_summaries)
        else:
            final_summary = summarize_entire_document(full_text, language)

        # Simpan hasil ke file untuk diunduh
        with open(TEMP_SUMMARY_PATH, "w", encoding="utf-8") as f:
            f.write(final_summary)

        current_progress["status"] = "done"
        return JSONResponse(content={"summary": final_summary})

    except Exception as e:
        current_progress["status"] = "error"
        return JSONResponse(status_code=500, content={"summary": f"Gagal memproses: {str(e)}"})
