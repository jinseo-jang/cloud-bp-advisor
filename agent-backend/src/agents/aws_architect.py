from src.config import GEMINI_FLASH_MODEL, GCP_PROJECT_ID
import json
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from src.state import GraphState
from src.agents.prompts import AWS_ARCHITECT_SYSTEM_PROMPT

async def aws_architect_stream(state: GraphState):
    """
    Step 2-a: Designs an AWS-specific architecture (Diagram, Cost, Security etc)
    Yields streaming thought events, then the final proposal dict.
    Simplified to use native Gemini Google Search Grounding.
    """
    req = state.get('user_requirement', '')
    
    llm = ChatGoogleGenerativeAI(
        model=GEMINI_FLASH_MODEL, 
        temperature=0.1, 
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", GCP_PROJECT_ID), 
        location="global", 
        client_options={"api_endpoint": "https://aiplatform.googleapis.com"},
        model_kwargs={"tools": [{"googleSearch": {}}]}
    )
    llm.client._api_client._http_options.api_version = "v1"
    
    try:
        final_text = ""
        # Native grounding + streaming thoughts (if supported by model)
        async for chunk in llm.astream([("system", AWS_ARCHITECT_SYSTEM_PROMPT), ("user", f"Design strictly as JSON. Requirement:\n{req}")]):
            if not chunk.content: continue
            if isinstance(chunk.content, str):
                final_text += chunk.content
                yield {"type": "stream", "cloud": "AWS", "chunk": chunk.content}
            elif isinstance(chunk.content, list):
                s = "".join(str(m.get("text", "")) if isinstance(m, dict) else str(m) for m in chunk.content)
                final_text += s
                yield {"type": "stream", "cloud": "AWS", "chunk": s}
            
        final_text = str(final_text)

        # Parse final result
        thoughts = ""
        if "<thought>" in final_text and "</thought>" in final_text:
            thoughts = final_text.split("<thought>")[1].split("</thought>")[0].strip()
            final_text = final_text.replace(f"<thought>{thoughts}</thought>", "")
            
        if "```json" in final_text:
            json_str = final_text.split("```json")[1].split("```")[0].strip()
        else:
            json_str = final_text.strip("` \n")
            if json_str.startswith("json"): json_str = json_str[4:].strip()
            
        proposal = json.loads(json_str)
        proposal["thoughts"] = thoughts
    except Exception as e:
        print(f"[AWS Architect] LLM evaluation error: {e}. Falling back to default.")
        proposal = {
            "desc": "Falling back due to JSON parsing error.",
            "diagram": "graph TD;\n  AWS_ALB-->AWS_EKS;\n  AWS_EKS-->AWS_RDS",
            "cost": "$450/month (Fallback)",
            "well_architected_analysis": "Error parsing Well-Architected analysis from the backend.",
            "thoughts": "Error occurred during thinking."
        }
    
    current_proposals = state.get("architecture_proposals") or {}
    current_proposals["AWS"] = proposal
    
    yield {
        "type": "final",
        "cloud": "AWS",
        "state_update": {
            "architecture_proposals": current_proposals, 
        }
    }

def aws_architect_node(state: GraphState) -> dict:
    """
    Synchronous fallback for graph execution (unused in streaming UI).
    """
    req = state.get('user_requirement', '')
    llm = ChatGoogleGenerativeAI(
        model=GEMINI_FLASH_MODEL, 
        temperature=0.1, 
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", GCP_PROJECT_ID), 
        location="global", 
        client_options={"api_endpoint": "https://aiplatform.googleapis.com"},
        model_kwargs={"tools": [{"googleSearch": {}}]}
    )
    llm.client._api_client._http_options.api_version = "v1"
    
    try:
        result = llm.invoke([("system", AWS_ARCHITECT_SYSTEM_PROMPT), ("user", f"Design strictly as JSON. Requirement:\n{req}")])
        final_text = result.content
        if isinstance(final_text, list):
            final_text = "".join(str(m.get("text", "")) if isinstance(m, dict) else str(m) for m in final_text)
            
        thoughts = ""
        if "<thought>" in final_text and "</thought>" in final_text:
            thoughts = final_text.split("<thought>")[1].split("</thought>")[0].strip()
            final_text = final_text.replace(f"<thought>{thoughts}</thought>", "")
            
        if "```json" in final_text:
            json_str = final_text.split("```json")[1].split("```")[0].strip()
        else:
            json_str = final_text.strip("` \n")
            if json_str.startswith("json"): json_str = json_str[4:].strip()
            
        proposal = json.loads(json_str)
        proposal["thoughts"] = thoughts
    except Exception as e:
        proposal = {
            "desc": "Falling back due to JSON parsing error.",
            "diagram": "graph TD;\n  AWS_ALB-->AWS_EKS;\n  AWS_EKS-->AWS_RDS",
            "cost": "$450/month (Fallback)",
            "well_architected_analysis": "Error parsing Well-Architected analysis from the backend.",
            "thoughts": "Error occurred during thinking."
        }
    
    current_proposals = state.get("architecture_proposals") or {}
    current_proposals["AWS"] = proposal
    return {
        "architecture_proposals": current_proposals, 
        "current_step": "aws_done"
    }
