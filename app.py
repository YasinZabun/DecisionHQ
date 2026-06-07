import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from orchestrator import DecisionHQOrchestrator

_jobs: dict[str, asyncio.Queue] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    _jobs.clear()


app = FastAPI(title="Karar Karargahı", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


class AnalyzeRequest(BaseModel):
    text: str


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/analyze")
async def start_analysis(req: AnalyzeRequest):
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
async def stream(job_id: str):
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
