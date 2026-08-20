import os
import uuid
import time
import json
import logging
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.schemas import (
    ChatRequest,
    ChatResponse,
    PipelineResult,
    ProjectInfo,
    VersionInfo
)
from app.pipeline import pipeline
from app.agent_router import agent_router
from app.project_manager import project_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ATS Engineering AI — Text-to-CAD Workbench",
    version="1.0.0",
    description="Professional Text-to-CAD Engineering Workbench powered by Gemma and OpenCascade"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active WebSocket connections
active_connections: Dict[str, List[WebSocket]] = {}

async def broadcast_event(session_id: Optional[str], event: str, data: Dict[str, Any]):
    """Broadcast status or progress events to all connected WebSockets for this session (or all)"""
    targets = []
    if session_id and session_id in active_connections:
        targets.extend(active_connections[session_id])
    if "global" in active_connections:
        targets.extend(active_connections["global"])

    payload = {"event": event, "timestamp": time.time(), "data": data}
    for ws in list(set(targets)):
        try:
            await ws.send_json(payload)
        except Exception as e:
            logger.debug(f"WebSocket broadcast error: {e}")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "ATS Engineering AI Text-to-CAD Workbench",
        "engine": "OpenCascade 7.9 / build123d 0.11",
        "model": settings.VLLM_MODEL,
        "vllm_endpoint": settings.VLLM_API_BASE,
        "connected_workstations": len(agent_router.list_agents())
    }

@app.get("/api/status")
async def get_system_status():
    return {
        "gemma": {
            "status": "connected",
            "model": settings.VLLM_MODEL,
            "endpoint": settings.VLLM_API_BASE,
            "vram_gb": 96
        },
        "cad_kernel": {
            "status": "ready",
            "name": "OpenCascade B-Rep / build123d",
            "precision": "ISO standard manifold"
        },
        "workstation": {
            "ip": settings.DEFAULT_WORKSTATION_IP,
            "user": settings.DEFAULT_USER_NAME,
            "agents_count": len(agent_router.list_agents())
        },
        "timestamp": time.time()
    }

@app.get("/api/agents")
async def get_agents():
    return {"agents": agent_router.list_agents()}

@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    agents = agent_router.list_agents()
    for ag in agents:
        if ag.agent_id == agent_id:
            return ag
    raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

# ==========================================
# Projects & Version History APIs
# ==========================================

@app.get("/api/projects", response_model=List[ProjectInfo])
async def list_projects():
    return project_manager.list_projects()

@app.post("/api/projects", response_model=ProjectInfo)
async def create_project(data: Dict[str, Any]):
    name = data.get("name", "Mechanical Part")
    p_id = data.get("project_id")
    return project_manager.create_project(name=name, project_id=p_id)

@app.get("/api/projects/{project_id}", response_model=ProjectInfo)
async def get_project(project_id: str):
    proj = project_manager.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return proj

@app.post("/api/projects/{project_id}/versions", response_model=ChatResponse)
async def generate_project_version(project_id: str, req: ChatRequest):
    job_id = f"cad_{uuid.uuid4().hex[:8]}"
    workstation = req.workstation_ip or settings.DEFAULT_WORKSTATION_IP
    session_id = req.session_id or "global"

    agent_router.acquire_lock(workstation, job_id)
    try:
        # Step 1: Planning
        await broadcast_event(session_id, "stage", {"stage": "planning", "message": "Analyzing natural-language prompt with Gemma..."})
        
        # Step 2: Generating
        await broadcast_event(session_id, "stage", {"stage": "generating", "message": "Synthesizing structured parametric CAD topology..."})

        # Context enrichment from project if available
        context = dict(req.context or {})
        if not context.get("previous_code"):
            proj = project_manager.get_project(project_id)
            if proj and proj.versions:
                last_v = proj.versions[-1]
                if last_v.plan and last_v.plan.python_script:
                    context["previous_code"] = last_v.plan.python_script
                elif last_v.validation and last_v.validation.python_path and os.path.exists(last_v.validation.python_path):
                    with open(last_v.validation.python_path, "r", encoding="utf-8") as f:
                        context["previous_code"] = f.read()
                if not context.get("previous_prompt"):
                    context["previous_prompt"] = last_v.prompt

        # Run pipeline
        res = await pipeline.run(
            prompt=req.prompt,
            job_id=job_id,
            workstation_ip=workstation,
            context=context
        )

        if not res.success:
            await broadcast_event(session_id, "stage", {"stage": "error", "message": res.error or "CAD generation failed"})
            return ChatResponse(
                success=False,
                tool="error",
                shape="error",
                parameters={},
                job_id=job_id,
                workstation_ip=workstation,
                message=f"CAD Generation Failed: {res.error}",
                duration_ms=res.duration_ms
            )

        # Step 3 & 4: Building & Validating
        await broadcast_event(session_id, "stage", {"stage": "building", "message": "Constructing 3D B-Rep solid manifold..."})
        await broadcast_event(session_id, "stage", {"stage": "validating", "message": "Verifying topology & STEP manifold..."})

        # Step 5: Exporting & Saving Version
        await broadcast_event(session_id, "stage", {"stage": "exporting", "message": "Compiling STEP, STL, GLB, and Python..."})
        
        v_info = project_manager.add_version(
            project_id=project_id,
            prompt=req.prompt,
            job_id=job_id,
            plan=res.plan,
            validation=res.validation,
            duration_ms=res.duration_ms
        )

        # Step 6: Complete
        await broadcast_event(session_id, "stage", {
            "stage": "complete",
            "message": "CAD Solid ready for inspection",
            "version": v_info.version_label,
            "volume_mm3": res.validation.volume_mm3 if res.validation else 0
        })

        return ChatResponse(
            success=True,
            tool=res.plan.tool,
            shape=res.plan.shape_type,
            parameters=res.plan.parameters or {
                "length_mm": res.plan.length_mm,
                "width_mm": res.plan.width_mm,
                "height_mm": res.plan.height_mm
            },
            job_id=job_id,
            workstation_ip=workstation,
            message=f"✓ Solid CAD Model Verified & Generated ({res.plan.explanation or res.prompt})",
            project_id=project_id,
            version_id=v_info.version_id,
            version_num=v_info.version_num,
            validation=res.validation,
            step_url=v_info.step_url,
            stl_url=v_info.stl_url,
            glb_url=v_info.glb_url,
            python_url=v_info.python_url,
            plan_url=v_info.plan_url,
            validation_url=v_info.validation_url,
            duration_ms=res.duration_ms,
            gemma_duration_ms=res.gemma_duration_ms,
            cad_build_duration_ms=res.cad_build_duration_ms
        )
    finally:
        agent_router.release_lock(workstation)

@app.post("/api/projects/{project_id}/versions/{version_label}/restore")
async def restore_project_version(project_id: str, version_label: str):
    v = project_manager.restore_version(project_id, version_label)
    if not v:
        raise HTTPException(status_code=404, detail="Could not restore version")
    return v

@app.delete("/api/projects/{project_id}/versions/{version_label}")
async def delete_project_version(project_id: str, version_label: str):
    ok = project_manager.delete_version(project_id, version_label)
    if not ok:
        raise HTTPException(status_code=404, detail="Version not found")
    return {"success": True, "message": f"Version {version_label} deleted"}

@app.get("/api/projects/{project_id}/versions/{version_label}/files/{file_name}")
async def get_version_file(project_id: str, version_label: str, file_name: str):
    file_path = project_manager.get_version_file_path(project_id, version_label, file_name)
    if not file_path or not os.path.exists(file_path):
        # Fallback check in general exports directory
        fallback_path = os.path.join(settings.EXPORT_DIR, file_name)
        if os.path.exists(fallback_path):
            file_path = fallback_path
        else:
            raise HTTPException(status_code=404, detail=f"File {file_name} not found in {version_label}")

    media_types = {
        ".step": "application/step",
        ".stp": "application/step",
        ".stl": "model/stl",
        ".glb": "model/gltf-binary",
        ".gltf": "model/gltf+json",
        ".py": "text/plain",
        ".json": "application/json"
    }
    ext = os.path.splitext(file_name)[1].lower()
    media_type = media_types.get(ext, "application/octet-stream")
    return FileResponse(file_path, filename=file_name, media_type=media_type)

# ==========================================
# Legacy & Standard Chat / Generate Endpoints
# ==========================================

@app.post("/api/generate", response_model=PipelineResult)
async def generate_cad(req: ChatRequest):
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    workstation = req.workstation_ip or settings.DEFAULT_WORKSTATION_IP

    result = await pipeline.run(
        prompt=req.prompt,
        job_id=job_id,
        workstation_ip=workstation,
        context=req.context
    )
    return result

@app.post("/api/chat", response_model=ChatResponse)
async def chat_handler(req: ChatRequest):
    # Route through project version generator
    project_id = req.project_id or "proj_default"
    return await generate_project_version(project_id, req)

@app.get("/api/export/{file_name}")
async def export_file(file_name: str):
    file_path = os.path.join(settings.EXPORT_DIR, file_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File {file_name} not found")
    media_types = {
        ".step": "application/step",
        ".stl": "model/stl",
        ".glb": "model/gltf-binary",
        ".py": "text/plain",
        ".json": "application/json"
    }
    ext = os.path.splitext(file_name)[1].lower()
    media_type = media_types.get(ext, "application/octet-stream")
    return FileResponse(file_path, filename=file_name, media_type=media_type)

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    if session_id not in active_connections:
        active_connections[session_id] = []
    active_connections[session_id].append(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await websocket.send_json({"event": "ack", "data": data})
    except WebSocketDisconnect:
        if session_id in active_connections and websocket in active_connections[session_id]:
            active_connections[session_id].remove(websocket)

# Mount static files directory for workbench UI
os.makedirs(settings.STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")

@app.get("/")
async def get_index():
    index_file = os.path.join(settings.STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return HTMLResponse("<h1>CAD Workbench UI loading...</h1>")
