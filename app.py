import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from orchestrator import DecisionHQOrchestrator

load_dotenv()

LOGIN_USERNAME = os.getenv("LOGIN_USERNAME", "admin")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "karar2024")
SECRET_KEY     = os.getenv("SECRET_KEY", "degistir-beni-gizli-anahtar-2024")

_jobs: dict[str, asyncio.Queue] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    _jobs.clear()


app = FastAPI(title="Karar Karargahı", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=86400)  # 24 saat
app.mount("/static", StaticFiles(directory="static"), name="static")


def is_logged_in(request: Request) -> bool:
    return request.session.get("authenticated") is True


# ── AUTH ROUTES ──────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    with open("static/login.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == LOGIN_USERNAME and password == LOGIN_PASSWORD:
        request.session["authenticated"] = True
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url="/login?error=1", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# ── PROTECTED ROUTES ─────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


class AnalyzeRequest(BaseModel):
    text: str


@app.post("/analyze")
async def start_analysis(req: AnalyzeRequest, request: Request):
    if not is_logged_in(request):
        raise HTTPException(status_code=401, detail="Oturum açmanız gerekiyor.")
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Metin boş olamaz.")

    job_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _jobs[job_id] = queue

    async def run():
        try:
            orchestrator = DecisionHQOrchestrator()

            async def on_event(event_type: str, data: dict):
                await queue.put({"type": event_type, **data})

            result = await orchestrator.run_pipeline(req.text, on_event=on_event)
            await queue.put({"type": "complete", "result": result})
        except Exception as e:
            await queue.put({"type": "error", "message": str(e)})

    asyncio.create_task(run())
    return {"job_id": job_id}


@app.get("/stream/{job_id}")
async def stream(job_id: str, request: Request):
    if not is_logged_in(request):
        raise HTTPException(status_code=401, detail="Oturum açmanız gerekiyor.")

    queue = _jobs.get(job_id)
    if not queue:
        raise HTTPException(status_code=404, detail="İş bulunamadı.")

    async def generator():
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=600)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") in ("complete", "error"):
                    break
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Zaman aşımı.'})}\n\n"
        finally:
            _jobs.pop(job_id, None)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
