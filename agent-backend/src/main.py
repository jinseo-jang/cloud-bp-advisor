from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from src.state import GraphState
from src.agents.orchestrator import orchestrator_node
from src.agents.aws_architect import aws_architect_node
from src.agents.gcp_architect import gcp_architect_node
from src.agents.tf_coder import tf_coder_node
from src.agents.qa_validator import qa_validator_node
from src.agents.tf_runner import execute_and_correct_loop
from src.agents.async_stream import design_streaming_loop, implement_streaming_loop
from fastapi.responses import StreamingResponse

app = FastAPI(
    title="Enterprise Cloud Architecture",
    version="1.0.0"
)

class RequirementRequest(BaseModel):
    requirement: str

class SelectionRequest(BaseModel):
    selected_cloud: str
    user_requirement: str = "N/A"
    architecture_proposals: dict = {}
    qa_feedback: list = []
    terraform_code: str = ""

@app.post("/api/v1/phase1/design")
async def trigger_phase1_design(req: RequirementRequest):
    # Phase 1: Deep Search & Architecture Design (Sync Execution)
    state = GraphState(user_requirement=req.requirement)
    state.update(orchestrator_node(state))
    state.update(aws_architect_node(state))
    state.update(gcp_architect_node(state))
    
    return {
        "status": "success",
        "proposals": state.get("architecture_proposals", {})
    }

@app.post("/api/v1/phase1/stream")
async def trigger_phase1_stream(req: RequirementRequest):
    return StreamingResponse(design_streaming_loop(req.requirement), media_type="text/event-stream")

@app.post("/api/v1/phase2/implement")
async def trigger_phase2_implement(req: SelectionRequest):
    if req.selected_cloud not in ["AWS", "GCP"]:
        raise HTTPException(status_code=400, detail="Invalid cloud selection.")
        
    state = GraphState(
        user_requirement=req.user_requirement, 
        selected_cloud=req.selected_cloud,
        architecture_proposals=req.architecture_proposals,
        qa_feedback=req.qa_feedback
    )
    state.update(tf_coder_node(state))
    state.update(qa_validator_node(state))
    
    return {
        "status": "success",
        "terraform_code": state.get("terraform_code", ""),
        "metadata": state.get("terraform_metadata", {})
    }

@app.post("/api/v1/phase2/implement_stream")
async def trigger_phase2_implement_stream(req: SelectionRequest):
    return StreamingResponse(implement_streaming_loop(req.model_dump()), media_type="text/event-stream")

class ExecuteRequest(BaseModel):
    terraform_code: str
    selected_cloud: str
    architecture_proposals: dict = {}

@app.post("/api/v1/phase3/execute")
async def trigger_phase3_execute(req: ExecuteRequest):
    state = GraphState(
        user_requirement="N/A", 
        selected_cloud=req.selected_cloud,
        architecture_proposals=req.architecture_proposals,
        terraform_code=req.terraform_code
    )
    return StreamingResponse(execute_and_correct_loop(state), media_type="text/event-stream")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

# Inject httpx debugging
import logging
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch = logging.StreamHandler()
ch.setFormatter(formatter)
httpx_logger.addHandler(ch)
