"""SDD QA Automation Dashboard - FastAPI server.

Run with the framework's virtual environment (it already has FastAPI, uvicorn and PyYAML):

    ..\\qa-sdd-crewai-framework\\.venv\\Scripts\\python.exe server.py

then open http://127.0.0.1:8090
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from dashboard import catalog
from dashboard.config import FRAMEWORK_DIR, HOST, PORT, STATIC_DIR, framework_available, framework_python
from dashboard.pipeline import STOP_FLAGS, Runner, new_run_id

app = FastAPI(title="SDD QA Automation Dashboard", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/meta")
def meta() -> dict:
    return {"framework_dir": str(FRAMEWORK_DIR), "framework_available": framework_available(),
            "python": framework_python(), "agents": catalog.agents(), "flows": catalog.FLOWS,
            "pipeline": catalog.PIPELINE_KEYS}


@app.get("/api/testcases")
def testcases() -> dict:
    return {"framework": catalog.real_test_cases(), "simulated": catalog.demo_test_cases()}


@app.get("/api/snapshot")
def snapshot() -> dict:
    return catalog.framework_snapshot()


@app.get("/api/runs")
def runs() -> list:
    return catalog.dashboard_runs()


@app.get("/api/run/stream")
async def run_stream(ids: str = Query(..., description="comma-separated test case IDs"),
                     speed: float = 1.0, headed: bool = False) -> StreamingResponse:
    selected = [i.strip() for i in ids.split(",") if i.strip()]
    if not selected:
        raise HTTPException(400, "no test cases selected")
    run_id = new_run_id()
    runner = Runner(run_id, selected, speed, headed)

    async def stream() -> AsyncIterator[str]:
        yield ": connected\n\n"
        try:
            async for ev in runner.events():
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        except asyncio.CancelledError:  # browser closed the stream
            runner.stop.set()
            raise

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/run/{run_id}/stop")
def stop(run_id: str) -> dict:
    flag = STOP_FLAGS.get(run_id)
    if flag:
        flag.set()
    return {"run_id": run_id, "stopping": bool(flag)}


if __name__ == "__main__":
    print(f"SDD QA Dashboard on http://{HOST}:{PORT}  (framework: {FRAMEWORK_DIR})")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
