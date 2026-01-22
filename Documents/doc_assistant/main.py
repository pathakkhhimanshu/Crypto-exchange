from fastapi import FastAPI, UploadFile, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import os
import unicodedata

from reader import read_document
from simple_search import search_answer

app = FastAPI()

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

UPLOADS = "uploads"
CURRENT = os.path.join(UPLOADS, "current.txt")

os.makedirs(UPLOADS, exist_ok=True)


# ---------- HELPERS ----------

def safe_filename(name: str) -> str:
    return unicodedata.normalize("NFKD", name)


def get_current_doc():
    if os.path.exists(CURRENT):
        return open(CURRENT, "r", encoding="utf-8").read().strip()
    return None


def list_documents():
    return [
        f for f in os.listdir(UPLOADS)
        if f.endswith((".pdf", ".txt")) and not f.startswith("current")
    ]


# ---------- ROUTES ----------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "documents": [{"name": d, "status": "ready"} for d in list_documents()],
            "doc_name": get_current_doc(),
        },
    )


@app.post("/upload")
async def upload(file: UploadFile):
    filename = safe_filename(file.filename)
    path = os.path.join(UPLOADS, filename)

    with open(path, "wb") as f:
        f.write(await file.read())

    with open(CURRENT, "w", encoding="utf-8") as f:
        f.write(filename)

    return RedirectResponse("/", 303)


@app.get("/select/{name}")
def select_doc(name: str):
    with open(CURRENT, "w", encoding="utf-8") as f:
        f.write(name)
    return RedirectResponse("/", 303)


@app.post("/ask")
async def ask(
    question: str = Form(...),
    mode: str = Form("quick"),
    bullets: str = Form("no")
):
    doc = get_current_doc()
    if not doc:
        return JSONResponse({"error": "No document selected"})

    path = os.path.join(UPLOADS, doc)
    text = read_document(path)

    answer = search_answer(text, question, mode, bullets)

    if not answer:
        return JSONResponse({"error": "No relevant answer found"})

    return JSONResponse({
        "question": question,
        "answer": answer
    })


@app.get("/new-session")
def new_session():
    for f in os.listdir(UPLOADS):
        os.remove(os.path.join(UPLOADS, f))
    return RedirectResponse("/", 303)
