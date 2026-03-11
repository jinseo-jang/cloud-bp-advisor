from src.config import GEMINI_FLASH_MODEL, GEMINI_PRO_MODEL, GCP_PROJECT_ID
import json
import os
import asyncio
import uuid
from typing import TypedDict, List, Annotated, Dict, Any, Union
import operator
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field

class TerraformCodeGeneration(BaseModel):
    terraform_code: str = Field(description="The complete, fully functioning raw Terraform HCL script.")
    terraform_metadata: dict = Field(description="Any tags or metadata generated for the Vertex AI RAG ingestion.")

class TerraformSandboxFix(BaseModel):
    terraform_code: str = Field(description="The complete, fully corrected raw Terraform HCL script without truncation (# ...).")

from src.memory import MemoryBank
from src.agents.prompts import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    AWS_ARCHITECT_SYSTEM_PROMPT,
    GCP_ARCHITECT_SYSTEM_PROMPT,
    TF_CODER_SYSTEM_PROMPT,
    QA_VALIDATOR_SYSTEM_PROMPT,
    TF_CODER_SANDBOX_FIX_SYSTEM_PROMPT,
    TF_FINAL_FAILURE_PROMPT
)
from src.agents.tools import tfsec_scan
from src.agents.pubsub_firestore import publish_job_and_stream_logs

def extract_json_safely(text) -> dict:
    import re
    try:
        if isinstance(text, list):
            text = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in text)
        if not isinstance(text, str):
            text = str(text)
            
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {"error": "JSON {} boundaries not found in output", "raw": text[:200]}
    except Exception as e:
        return {"error": f"JSON parse error: {str(e)}"}

def merge_dicts(a: dict, b: dict) -> dict:
    if not a: a = {}
    if not b: b = {}
    c = a.copy()
    for k, v in b.items():
        if v is None:
            if k in c:
                del c[k]
        else:
            c[k] = v
    return c

class GraphState(TypedDict):
    user_requirement: str
    architecture_proposals: Annotated[dict, merge_dicts]
    selected_cloud: str
    user_feedback: str
    terraform_code: str
    qa_feedback: Annotated[List[str], operator.add]
    sandbox_feedback: str
    qa_final_text: str
    qa_security_warning: str
    retry_count: int
    sandbox_retry_count: int
    phase: str
    job_id: str

def get_llm(model_name: str = GEMINI_FLASH_MODEL) -> ChatGoogleGenerativeAI:
    llm = ChatGoogleGenerativeAI(
        model=model_name, 
        temperature=0.1, 
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", GCP_PROJECT_ID), 
        location="global", 
        client_options={"api_endpoint": "https://aiplatform.googleapis.com"}
    )
    llm.client._api_client._http_options.api_version = "v1"
    return llm

async def orchestrator_node(state: GraphState, config: RunnableConfig):
    llm = get_llm()
    req = state.get("user_requirement", "")
    
    # Only retrieve here. Generation happens asynchronously at the end of the workflow.
    memory_bank = MemoryBank(user_id="default_user")
    user_memories = memory_bank.retrieve_memories()
    
    messages = [
        SystemMessage(content=f"{ORCHESTRATOR_SYSTEM_PROMPT}\n\n[Vertex AI Memory Bank Context: {user_memories}]"),
        HumanMessage(content=f"User Requirement:\n{req}")
    ]
    res = await llm.ainvoke(messages, config)
    return {"user_requirement": res.content, "phase": "architecting"}

async def aws_architect_node(state: GraphState, config: RunnableConfig):
    llm = get_llm()
    req = state.get("user_requirement", "")
    feedback = state.get("user_feedback", "")
    proposals = state.get("architecture_proposals", {})
    prev_aws = proposals.get("AWS", {})
    
    prev_str = f"\n\nPrevious Architecture Proposal to Refine:\n{json.dumps(prev_aws, indent=2)}\n" if prev_aws and feedback else ""
    feedback_str = f"\nUser Architectural Feedback: {feedback}" if feedback else ""
    
    messages = [
        SystemMessage(content=AWS_ARCHITECT_SYSTEM_PROMPT),
        HumanMessage(content=f"Architectural Brief:\n{req}{feedback_str}{prev_str}\n\nIMPORTANT: Output ONLY valid JSON. Do not output any markdown code blocks, do not use function calls.")
    ]
    
    parsed = {"error": "Failed to generate architecture"}
    for attempt in range(3):
        try:
            if attempt > 0:
                retry_llm = get_llm()
                retry_llm.temperature = 0.4 + (0.2 * attempt) # Increase temperature to break deterministic loop
                res = await retry_llm.ainvoke(messages + [HumanMessage(content=f"Attempt {attempt+1}: Your previous response was empty or invalid JSON. Please return ONLY a valid JSON object without using any tools or function calls.")], config)
            else:
                res = await llm.ainvoke(messages, config)
                
            if not res.content or (isinstance(res.content, list) and not res.content):
                parsed = {"error": "LLM returned empty content (MALFORMED_FUNCTION_CALL)", "raw": ""}
                continue
                
            parsed = extract_json_safely(res.content)
            if "error" not in parsed:
                break
        except Exception as e:
            parsed = {"error": str(e)}
            
    return {"architecture_proposals": {"AWS": parsed}}

async def gcp_architect_node(state: GraphState, config: RunnableConfig):
    llm = get_llm()
    req = state.get("user_requirement", "")
    feedback = state.get("user_feedback", "")
    proposals = state.get("architecture_proposals", {})
    prev_gcp = proposals.get("GCP", {})
    
    prev_str = f"\n\nPrevious Architecture Proposal to Refine:\n{json.dumps(prev_gcp, indent=2)}\n" if prev_gcp and feedback else ""
    feedback_str = f"\nUser Architectural Feedback: {feedback}" if feedback else ""
    
    messages = [
        SystemMessage(content=GCP_ARCHITECT_SYSTEM_PROMPT),
        HumanMessage(content=f"Architectural Brief:\n{req}{feedback_str}{prev_str}\n\nIMPORTANT: Output ONLY valid JSON. Do not output any markdown code blocks, do not use function calls.")
    ]
    
    parsed = {"error": "Failed to generate architecture"}
    for attempt in range(3):
        try:
            if attempt > 0:
                retry_llm = get_llm()
                retry_llm.temperature = 0.4 + (0.2 * attempt) # Increase temperature to break deterministic loop
                res = await retry_llm.ainvoke(messages + [HumanMessage(content=f"Attempt {attempt+1}: Your previous response was empty or invalid JSON. Please return ONLY a valid JSON object without using any tools or function calls.")], config)
            else:
                res = await llm.ainvoke(messages, config)
                
            if not res.content or (isinstance(res.content, list) and not res.content):
                parsed = {"error": "LLM returned empty content (MALFORMED_FUNCTION_CALL)", "raw": ""}
                continue
                
            parsed = extract_json_safely(res.content)
            if "error" not in parsed:
                break
        except Exception as e:
            parsed = {"error": str(e)}
            
    return {"architecture_proposals": {"GCP": parsed}}

def merge_architectures_node(state: GraphState):
    # Synchronization node for the parallel architects
    return {"user_feedback": ""} # Clear feedback so it doesn't leak into next step

def feedback_review_node(state: GraphState):
    # Wipe-out the unused architecture proposal and massive user context 
    # to drastically reduce the LangSmith state payload passed to tf_coder.
    cloud = state.get("selected_cloud", "AWS")
    unselected_cloud = "GCP" if cloud == "AWS" else "AWS"
    
    return {
        "phase": "reviewing_feedback",
        "architecture_proposals": {unselected_cloud: None}
    }

def route_after_feedback(state: GraphState) -> List[str]:
    feedback = state.get("user_feedback", "").strip()
    if feedback:
        return ["aws_architect", "gcp_architect"]
    else:
        return ["tf_coder"]

def extract_hcl_safely(text: str) -> str:
    import re
    # Find all hcl or terraform code blocks
    matches = re.findall(r'```(?:terraform|hcl)?\n(.*?)\n```', text, re.DOTALL)
    
    # 2nd Layer Regex Scrubber: Comment out invalid raw text headers that the LLM sneakily injects.
    def scrub_hcl(chunk: str) -> str:
        lines = chunk.split('\n')
        scrubbed = []
        pattern = re.compile(r'^(?:[a-zA-Z0-9_\-]+\.tf|=+|-+|Variables|Outputs|Main|Provider|###+.*###*)$', re.IGNORECASE)
        for line in lines:
            stripped = line.strip()
            # If the entire line is just a word like "main.tf" or "====", we comment it out.
            if stripped and pattern.match(stripped):
                scrubbed.append(f"# {line}")
            else:
                scrubbed.append(line)
        return "\n".join(scrubbed)
        
    if matches:
        longest_match = max(matches, key=len)
        return scrub_hcl(longest_match.strip())
        
    if "resource " in text or "provider " in text or "module " in text or "terraform {" in text:
        return scrub_hcl(text.strip())
        
    return ""

async def tf_coder_node(state: GraphState, config: RunnableConfig):
    cloud = state.get("selected_cloud", "AWS")
    proposals = state.get("architecture_proposals", {})
    selected_arch = proposals.get(cloud, {})
    prev_code = state.get("terraform_code", "")
    qa_feedback = state.get("qa_feedback", [])
    sandbox_fb = state.get("sandbox_feedback", "")
    
    feedback_str = ""
    if qa_feedback:
        feedback_str += f"QA Feedback to incorporate:\n{qa_feedback[-1]}\n"
    if sandbox_fb:
        feedback_str += f"CRITICAL - Sandbox Execution Failed with this error:\n{sandbox_fb}\nFix the architecture or code to resolve this."
        
    if not feedback_str:
        feedback_str = "No feedback. Initial clean run."
        
    prev_code_str = f"Previous Generated Code that caused the error:\n```hcl\n{prev_code}\n```\n" if prev_code else ""
    
    prompt = (
        f"Target Cloud: {cloud}\nArchitecture Proposal: {json.dumps(selected_arch)}\n{prev_code_str}{feedback_str}\n\n"
        "CRITICAL Requirement: DO NOT output any generic notes. Return your response strictly as a JSON object with two keys: 'terraform_code' (string containing the raw HCL) and 'terraform_metadata' (dictionary containing any tags or settings)."
    )
    
    llm = get_llm(GEMINI_PRO_MODEL)
    structured_llm = llm.with_structured_output(TerraformCodeGeneration)
    
    await adispatch_custom_event("sandbox_log", {"log": "\n🤖 Compiling core Terraform architecture (Strict JSON Mode)...\n"})
    
    try:
        res = await structured_llm.ainvoke([
            SystemMessage(content=TF_CODER_SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ], config)
        final_tf_code = res.terraform_code if res and hasattr(res, 'terraform_code') else ""
        if not final_tf_code:
            raise ValueError("Structured LLM returned empty terraform_code")
    except Exception as e:
        await adispatch_custom_event("sandbox_log", {"log": f"\n❌ Strict output parsing failed: {str(e)}. Using fallback mock.\n"})
        final_tf_code = f"// Fallback mocked code due to parse error\nresource \"example\" \"fallback\" {{}}"
        
    return {
        "terraform_code": final_tf_code, 
        "sandbox_feedback": "", 
        "phase": "qa_validation",
        "user_feedback": ""
    }

async def qa_validator_node(state: GraphState, config: RunnableConfig):
    final_tf_code = state.get("terraform_code", "")
    retry_count = state.get("retry_count", 0) + 1
    qa_feedback_list = state.get("qa_feedback", [])
    
    previous_feedback_str = ""
    if retry_count > 1 and qa_feedback_list:
        previous_feedback_str = (
            f"\n\n🚨 PREVIOUS QA FEEDBACK (Iteration {retry_count-1}):\n"
            f"{qa_feedback_list[-1]}\n\n"
            f"CRITICAL CONSTRAINT: You are performing a follow-up verification. "
            f"Your SOLE PURPOSE is to check if the EXACT issues flagged in the previous feedback have been resolved. "
            f"DO NOT flag any new security issues or change your baseline rules unless it is a critical syntax error introduced during the fix.\n"
            f"CRITICAL OUTPUT RULES: DO NOT explain your verification process step-by-step. If all previous issues are resolved, output EXACTLY AND ONLY 'PASS_SECURITY' with absolutely no other text. If they are not resolved, output EXACTLY 'FAIL_SECURITY' followed by a brief 1-2 sentence instruction on what is still missing."
        )
        
    # 1. Direct Python Execution of Tool
    scan_result = tfsec_scan.invoke({"hcl_content": final_tf_code})
    
    # 2. Inject result directly into the prompt
    qa_prompt = (
        f"Review the following Terraform code. I have already run tfsec_scan for you, and here is the output:\n"
        f"[{scan_result}]\n\n"
        f"If the scan reveals ANY HIGH or CRITICAL issues, or if the code is invalid, you MUST include the exact word 'FAIL_SECURITY' in your final response along with instructions to fix it.\n"
        f"If the scan is clean, or if the previously flagged issues are now resolved, output exactly and only 'PASS_SECURITY'.\n\n```hcl\n{final_tf_code}\n```"
        f"{previous_feedback_str}"
    )
    
    qa_llm = get_llm()
    qa_llm.temperature = 0.0
    
    # 3. Single LLM Invocation without ReAct Loop
    res = await qa_llm.ainvoke([
        SystemMessage(content=QA_VALIDATOR_SYSTEM_PROMPT),
        HumanMessage(content=qa_prompt)
    ], config)
    
    final_text_obj = res.content
    
    # Safely convert the object to a clean string
    if isinstance(final_text_obj, list):
        # Sometime LLM returns [{'type': 'text', 'text': 'Actual message'}]
        texts = []
        for b in final_text_obj:
            if isinstance(b, dict):
                texts.append(str(b.get("text", "")))
            else:
                texts.append(str(b))
        final_text = "\n".join(texts)
    elif isinstance(final_text_obj, str):
        # Check if the string itself is a printed list of dicts (e.g. "[{'type': 'text' ...}]")
        if final_text_obj.startswith("[{") and "'text':" in final_text_obj:
            try:
                import ast
                parsed_list = ast.literal_eval(final_text_obj)
                final_text = "\n".join([b.get("text", "") for b in parsed_list if isinstance(b, dict)])
            except:
                final_text = final_text_obj
        else:
            final_text = final_text_obj
    else:
        final_text = str(final_text_obj)
        
    retry_count = state.get("retry_count", 0) + 1
    
    new_qa_fb = []
    qa_security_warning = ""
    
    if "FAIL_SECURITY" in final_text or "PASS_SECURITY" not in final_text:
        if retry_count >= 2:
            final_text += "\n\n🚨 **[System Warning]** 최대 재시도(Retry) 횟수 3회를 초과했습니다. 더 이상 자가 치유를 시도하지 않고, 사용자 강제 승인(Human-in-the-Loop) 단계로 넘어갑니다."
            
            # Extract just the failure reason from the verbose text if possible, or use the whole text
            clean_error_msg = final_text.split("FAIL_SECURITY")[-1].strip() if "FAIL_SECURITY" in final_text else final_text
            clean_error_hcl_comments = "\n".join([f"# {line}" for line in clean_error_msg.split("\n") if line.strip()])
            
            qa_security_warning = f"🚨 AI QA SYSTEM WARNING: MAXIMUM RETRIES EXCEEDED 🚨\nTHIS CODE FAILED FINAL VERIFICATION. USE WITH EXTREME CAUTION.\n\nREASON FOR FAILURE:\n{clean_error_msg}"
            
            # Inject reason directly into the Terraform code so the user sees it in the browser code block
            final_tf_code = f"/* \n{qa_security_warning}\n*/\n\n{final_tf_code}"
            
        new_qa_fb.append(final_text)
        
    return {
        "qa_final_text": final_text, 
        "terraform_code": final_tf_code, 
        "retry_count": retry_count, 
        "qa_feedback": new_qa_fb, 
        "qa_security_warning": qa_security_warning,
        "phase": "qa_validation"
    }

def check_qa_status(state: GraphState) -> str:
    final_text = state.get("qa_final_text", "")
    retry_count = state.get("retry_count", 0)
    
    if "FAIL_SECURITY" in final_text or "PASS_SECURITY" not in final_text:
        if retry_count < 2:
            return "retry"
    return "pass"

def approval_node(state: GraphState):
    # Dummy node to wait for human approval before execution
    return {"phase": "awaiting_approval"}

async def tf_runner_node(state: GraphState):
    tf_code = state.get("terraform_code", "")
    cloud = state.get("selected_cloud", "AWS")
    
    # Always generate a unique job_id for each run so Firestore polling doesn't return old cached status
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    
    retry_count = state.get("sandbox_retry_count", 0)
    is_final_retry = retry_count >= 2
    
    status = "failed"
    sandbox_feedback = "Unknown error"
    
    await adispatch_custom_event("sandbox_log", {"log": f"🚀 Starting Sandbox Job (Attempt {retry_count + 1})... Job ID: {job_id}\n"})
    
    try:
        async for chunk in publish_job_and_stream_logs(job_id, tf_code, cloud, is_final_retry=is_final_retry):
            if isinstance(chunk, dict) and "status" in chunk:
                status = chunk["status"]
                sandbox_feedback = str(chunk.get("feedback", ""))
            else:
                clean_chunk = str(chunk).replace("data: ", "").replace("\\n\\n", "\\n")
                await adispatch_custom_event("sandbox_log", {"log": clean_chunk})
    except Exception as e:
        status = "failed"
        sandbox_feedback = f"Pub/Sub Exception: {str(e)}"
        
    if status == "success":
        await adispatch_custom_event("sandbox_log", {"log": "\n✅ Sandbox validation successful!\n"})
        return {"sandbox_feedback": "", "phase": "completed", "job_id": job_id}
    else:
        await adispatch_custom_event("sandbox_log", {"log": f"\n❌ Sandbox validation failed. Triggering Auto-Healing.\n"})
        return {"sandbox_feedback": str(sandbox_feedback), "phase": "sandbox_failed", "job_id": job_id}

def check_sandbox_status(state: GraphState) -> str:
    sandbox_retry_count = state.get("sandbox_retry_count", 0)
    if state.get("sandbox_feedback"):
        if sandbox_retry_count >= 2:  # Max 3 attempts (0, 1, 2) reached
            return "fail_permanently"
        return "retry"
    return "pass"

async def tf_final_failure_analysis_node(state: GraphState, config: RunnableConfig):
    tf_code = state.get("terraform_code", "")
    sandbox_feedback = state.get("sandbox_feedback", "")
    
    prompt = (
        f"The following Terraform code failed to provision after maximum retries:\n"
        f"```hcl\n{tf_code}\n```\n\n"
        f"Final Sandbox Error Logs:\n{sandbox_feedback}\n\n"
        f"Please analyze the failure and return the HCL code with your explanation and recommendations injected as comments at the top."
    )
    
    llm = get_llm()
    res_text = ""
    await adispatch_custom_event("sandbox_log", {"log": "\n🔎 Analyzing permanent failure cause...\n"})
    
    async for chunk in llm.astream([
        SystemMessage(content=TF_FINAL_FAILURE_PROMPT),
        HumanMessage(content=prompt)
    ], config):
        if isinstance(chunk.content, list):
            for block in chunk.content:
                if isinstance(block, dict) and block.get("type") == "text":
                    res_text += block.get("text", "")
                elif isinstance(block, str):
                    res_text += block
        else:
            res_text += str(chunk.content)
            
    extracted_tf = extract_hcl_safely(res_text)
    if extracted_tf:
        final_tf_code = extracted_tf
    else:
        final_tf_code = res_text
        
    return {"terraform_code": final_tf_code, "phase": "sandbox_failed_permanently", "qa_final_text": res_text}

async def tf_coder_sandbox_fix_node(state: GraphState, config: RunnableConfig):
    tf_code = state.get("terraform_code", "")
    sandbox_feedback = state.get("sandbox_feedback", "")
    sandbox_retry_count = state.get("sandbox_retry_count", 0) + 1
    
    prompt = (
        f"The following Terraform code failed to provision in the Sandbox:\n"
        f"```hcl\n{tf_code}\n```\n\n"
        f"Sandbox Error Logs:\n{sandbox_feedback}\n\n"
        f"Please analyze the error and output your response STRICTLY as a JSON object with a single key 'terraform_code' containing the full, corrected raw HCL string.\n"
        f"CRITICAL: Do NOT truncate the code. Provide the ENTIRE script including all existing resources untouched. Do not output markdown or conversational text outside the JSON."
    )
    
    llm = get_llm(GEMINI_PRO_MODEL)
    structured_llm = llm.with_structured_output(TerraformSandboxFix)
    
    await adispatch_custom_event("sandbox_log", {"log": "\n🤖 Analyzing and fixing Sandbox Syntax errors (Strict JSON Mode)...\n"})
    
    res_text = "Structured JSON Fixing..."
    try:
        res = await structured_llm.ainvoke([
            SystemMessage(content=TF_CODER_SANDBOX_FIX_SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ], config)
        final_tf_code = res.terraform_code if res and hasattr(res, 'terraform_code') else ""
        if not final_tf_code:
            raise ValueError("Structured LLM returned empty terraform_code")
    except Exception as e:
        await adispatch_custom_event("sandbox_log", {"log": f"\n❌ Strict output parsing failed: {str(e)}. Falling back to raw execution.\n"})
        # Fallback to standard invoke if Pydantic parsing completely crashes
        res_fallback = await llm.ainvoke([SystemMessage(content=TF_CODER_SANDBOX_FIX_SYSTEM_PROMPT), HumanMessage(content=prompt)], config)
        res_text = res_fallback.content
        extracted_tf = extract_hcl_safely(res_text)
        final_tf_code = extracted_tf if extracted_tf else res_text
        
    qa_display_text = f"Structured JSON Fixing...\n\n```hcl\n{final_tf_code}\n```"
        
    return {
        "terraform_code": final_tf_code, 
        "sandbox_feedback": "", 
        "phase": "sandbox_retrying", 
        "sandbox_retry_count": sandbox_retry_count, 
        "qa_final_text": qa_display_text
    }

def build_e2e_graph(memory=None):
    workflow = StateGraph(GraphState)
    
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("aws_architect", aws_architect_node)
    workflow.add_node("gcp_architect", gcp_architect_node)
    workflow.add_node("merge_architectures", merge_architectures_node)
    workflow.add_node("feedback_review", feedback_review_node)
    workflow.add_node("tf_coder", tf_coder_node)
    workflow.add_node("qa_validator", qa_validator_node)
    workflow.add_node("approval_node", approval_node)
    workflow.add_node("tf_runner", tf_runner_node)
    workflow.add_node("tf_coder_sandbox_fix", tf_coder_sandbox_fix_node)
    workflow.add_node("tf_final_failure_analysis", tf_final_failure_analysis_node)
    
    workflow.set_entry_point("orchestrator")
    
    workflow.add_edge("orchestrator", "aws_architect")
    workflow.add_edge("orchestrator", "gcp_architect")
    
    workflow.add_edge("aws_architect", "merge_architectures")
    workflow.add_edge("gcp_architect", "merge_architectures")
    
    workflow.add_edge("merge_architectures", "feedback_review")
    
    workflow.add_conditional_edges(
        "feedback_review",
        route_after_feedback,
        ["aws_architect", "gcp_architect", "tf_coder"]
    )
    
    workflow.add_edge("tf_coder", "qa_validator")
    
    workflow.add_conditional_edges(
        "qa_validator",
        check_qa_status,
        {
            "retry": "tf_coder",
            "pass": "approval_node"
        }
    )
    
    workflow.add_edge("approval_node", "tf_runner")
    
    workflow.add_conditional_edges(
        "tf_runner",
        check_sandbox_status,
        {
            "retry": "tf_coder_sandbox_fix",
            "pass": END,
            "fail_permanently": "tf_final_failure_analysis"
        }
    )
    workflow.add_edge("tf_coder_sandbox_fix", "tf_runner")
    workflow.add_edge("tf_final_failure_analysis", END)
    
    if memory is None:
        memory = MemorySaver()
        
    compiled_e2e_graph = workflow.compile(
        checkpointer=memory, 
        interrupt_before=["feedback_review", "approval_node"]
    )
    return compiled_e2e_graph

compiled_e2e_graph = build_e2e_graph()
