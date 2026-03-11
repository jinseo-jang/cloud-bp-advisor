from src.config import GEMINI_FLASH_MODEL
import json
import asyncio
from src.state import GraphState
from src.agents.orchestrator import orchestrator_node
from langchain_core.callbacks.base import BaseCallbackHandler
from src.agents.aws_architect import aws_architect_stream
from src.agents.gcp_architect import gcp_architect_stream

async def design_streaming_loop(req: str):
    """
    Executes Phase 1 nodes asynchronously, yielding progress and thoughts.
    In a real implementation we would attach a custom AsyncCallbackHandler to the agent_executor
    to yield token by token. For simplicity within the constraints, we will stream the node transitions 
    and block-level outputs, explicitly extracting '<thought>' tags if they appear in LLM output.
    """
    yield "data: {\"type\": \"status\", \"message\": \"[Orchestrator] Analyzing requirements...\"}\n\n"
    
    # 1. Orchestrator
    try:
        # Run sync node in executor to not block event loop
        state = await asyncio.to_thread(orchestrator_node, GraphState(user_requirement=req))
        yield "data: {\"type\": \"status\", \"message\": \"[Orchestrator] Extracted technical constraints.\"}\n\n"
    except Exception as e:
        yield f"data: {{\"type\": \"error\", \"message\": \"Orchestrator failed: {str(e)}\"}}\n\n"
        state = GraphState(user_requirement=req)
        
    yield "data: {\"type\": \"status\", \"message\": \"[System] Executing AWS and GCP Architects in parallel...\"}\n\n"
    
    queue = asyncio.Queue()
    
    async def run_aws(st):
        try:
            async for chunk in aws_architect_stream(st):
                await queue.put(chunk)
        except Exception as e:
            await queue.put({"type": "error", "message": f"AWS Architecture failed: {str(e)}"})

    async def run_gcp(st):
        try:
            # Stagger GCP architect to avoid simultaneous high-token API bursts that trigger 429/quota exhaustion
            await asyncio.sleep(2)
            async for chunk in gcp_architect_stream(st):
                await queue.put(chunk)
        except Exception as e:
            await queue.put({"type": "error", "message": f"GCP Architecture failed: {str(e)}"})

    # Launch both generators concurrently
    aws_task = asyncio.create_task(run_aws(GraphState(user_requirement=state.get("user_requirement"))))
    gcp_task = asyncio.create_task(run_gcp(GraphState(user_requirement=state.get("user_requirement"))))


    # Listen to the queue until both tasks finish
    async def consumer():
        active_tasks = 2
        while active_tasks > 0 or not queue.empty():
            if not queue.empty():
                item = await queue.get()
                if item.get("type") == "final":
                    yield f"data: {json.dumps({'type': 'proposal', 'cloud': item['cloud'], 'data': item['state_update']['architecture_proposals'][item['cloud']]})}\n\n"
                    yield f"data: {{\"type\": \"status\", \"message\": \"[{item['cloud']} Architect] Completed design!\"}}\n\n"
                    active_tasks -= 1
                elif item.get("type") == "error":
                    yield f"data: {json.dumps(item)}\n\n"
                    active_tasks -= 1
                elif item.get("type") == "stream":
                    # Stream raw text chunk
                    yield f"data: {json.dumps(item)}\n\n"
            else:
                await asyncio.sleep(0.01)
                if aws_task.done() and gcp_task.done() and queue.empty():
                    break

    async for sse_chunk in consumer():
        yield sse_chunk

    yield "data: {\"type\": \"status\", \"message\": \"[System] Architecture Design Phase Complete.\"}\n\n"
    yield "data: {\"type\": \"done\"}\n\n"

from src.agents.tf_coder import TF_CODER_SYSTEM_PROMPT, infracost_estimate
from src.agents.qa_validator import QA_VALIDATOR_SYSTEM_PROMPT, tfsec_scan
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
# Use context7_mcp if available in tools? We'll import it:
from src.agents.tools import context7_mcp

async def implement_streaming_loop(req: dict):
    cloud = req.get("selected_cloud", "AWS")
    state = GraphState(
        user_requirement=req.get("user_requirement", ""),
        selected_cloud=cloud,
        architecture_proposals=req.get("architecture_proposals", {}),
        qa_feedback=req.get("qa_feedback", [])
    )
    
    yield f"data: {{\"type\": \"status\", \"message\": \"[{cloud} TF Coder] Initializing Terraform generation pipeline...\"}}\n\n"
    
    proposals = state.get("architecture_proposals", {})
    selected_arch = proposals.get(cloud, {})
    
    prev_code = req.get("terraform_code", "")
    feedback = state.get("qa_feedback", [])
    
    max_loops = 3
    final_tf_code = ""
    final_tf_metadata = {}

    for loop_idx in range(max_loops):
        if loop_idx > 0:
            yield f"data: {{\"type\": \"status\", \"message\": \"[{cloud} TF Coder] Fixing Terraform code based on QA Feedback (Attempt {loop_idx+1})...\"}}\n\n"
        
        yield f"data: {{\"type\": \"clear_stream\", \"cloud\": \"{cloud}\"}}\n\n"
        
        feedback_str = f"QA Feedback to incorporate:\\n{feedback[-1]}" if feedback else "No feedback. Initial clean run."
        prev_code_str = f"Previous Generated Code that caused the error:\\n```hcl\\n{prev_code}\\n```\\n" if prev_code else ""
        
        prompt = (
            f"Target Cloud: {cloud}\\nArchitecture Proposal: {json.dumps(selected_arch)}\\n{prev_code_str}{feedback_str}\\n\\n"
            "CRITICAL Requirement: DO NOT output any generic notes. Return your response strictly as a JSON object with two keys: 'terraform_code' (string containing the raw HCL) and 'terraform_metadata' (dictionary containing any tags or settings)."
        )
        
        llm = ChatGoogleGenerativeAI(model=GEMINI_FLASH_MODEL, temperature=0.1, project="duper-project-1", location="global", client_options={"api_endpoint": "https://aiplatform.googleapis.com"})
        llm.client._api_client._http_options.api_version = "v1"
        agent_executor = create_react_agent(llm, [], prompt=TF_CODER_SYSTEM_PROMPT)
        
        final_text = ""
        try:
            async for event in agent_executor.astream_events({"messages": [("user", prompt)]}, version="v2"):
                if event["event"] == "on_chat_model_stream":
                    chunk = event["data"]["chunk"].content
                    parsed_chunk = ""
                    if isinstance(chunk, str): parsed_chunk = chunk
                    elif isinstance(chunk, list): parsed_chunk = "".join(str(m.get("text", "")) if isinstance(m, dict) else str(m) for m in chunk)
                    if parsed_chunk:
                        final_text += parsed_chunk
                        yield f"data: {json.dumps({'type': 'stream', 'cloud': cloud, 'chunk': parsed_chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'TF Coder failed: {e}'})}\n\n"

        try:
            if "```json" in final_text:
                json_str = final_text.split("```json")[1].split("```")[0].strip()
            else:
                json_str = final_text.strip("` \n")
                if json_str.startswith("json"): json_str = json_str[4:].strip()
            parsed = json.loads(json_str)
            final_tf_code = parsed.get("terraform_code", "")
            final_tf_metadata = parsed.get("terraform_metadata", {})
        except Exception as e:
            final_tf_code = f"// Fallback mocked code due to parse error\nresource \"example\" \"fallback\" {{}}"
            final_tf_metadata = {"cloud": cloud, "tags": ["fallback"]}

        prev_code = final_tf_code

        # Yield Terraform Code to Timeline
        yield f"data: {json.dumps({'type': 'terraform_code', 'code': final_tf_code})}\n\n"

        # QA Validator Phase
        yield f"data: {{\"type\": \"status\", \"message\": \"[{cloud} QA Validator] Scanning generated HCL code...\"}}\n\n"
        yield f"data: {{\"type\": \"clear_stream\", \"cloud\": \"{cloud}\"}}\n\n"
        
        qa_prompt = f"Review the following Terraform code. Run tfsec_scan on it. If it fails or you find issues, describe them in detail with ACTIONABLE corrections. Otherwise, output exactly 'PASS'.\n\n```hcl\n{final_tf_code}\n```"
        
        qa_llm = ChatGoogleGenerativeAI(model=GEMINI_FLASH_MODEL, temperature=0.0, project="duper-project-1", location="global", client_options={"api_endpoint": "https://aiplatform.googleapis.com"})
        qa_llm.client._api_client._http_options.api_version = "v1"
        qa_agent_executor = create_react_agent(qa_llm, [tfsec_scan], prompt=QA_VALIDATOR_SYSTEM_PROMPT)
        
        qa_final_text = ""
        try:
            async for event in qa_agent_executor.astream_events({"messages": [("user", qa_prompt)]}, version="v2"):
                if event["event"] == "on_chat_model_stream":
                    chunk = event["data"]["chunk"].content
                    parsed_chunk = ""
                    if isinstance(chunk, str): parsed_chunk = chunk
                    elif isinstance(chunk, list): parsed_chunk = "".join(str(m.get("text", "")) if isinstance(m, dict) else str(m) for m in chunk)
                    if parsed_chunk:
                        qa_final_text += parsed_chunk
                        yield f"data: {json.dumps({'type': 'stream', 'cloud': cloud, 'chunk': parsed_chunk})}\n\n"
                elif event["event"] == "on_tool_start":
                    tool_name = event.get("name")
                    msg = {"type": "status", "message": f"[{cloud} QA Validator] Calling security scanner {tool_name}..."}
                    yield f"data: {json.dumps(msg)}\n\n"
        except Exception as e:
            qa_final_text += f"\nQA Validator Error: {str(e)}"

        # Yield QA Scan Result to Timeline
        yield f"data: {json.dumps({'type': 'qa_scan_result', 'result': qa_final_text})}\n\n"

        if "CRITICAL:" in qa_final_text or "ERROR:" in qa_final_text or "Violations found" in qa_final_text or "PASS" not in qa_final_text:
            feedback.append("QA Scan Failed with the following details. Please generate a NEW corrected terraform code:\n" + qa_final_text)
        else:
            yield f"data: {{\"type\": \"status\", \"message\": \"[{cloud} QA Validator] Code passed all security policies!\"}}\n\n"
            break

    yield f"data: {json.dumps({'type': 'final_tf', 'data': {'terraform_code': final_tf_code, 'metadata': final_tf_metadata}})}\n\n"
    yield "data: {\"type\": \"done\"}\n\n"
