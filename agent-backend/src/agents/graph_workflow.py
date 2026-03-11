from src.config import GEMINI_FLASH_MODEL
import json
from typing import TypedDict, List
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langgraph.graph import StateGraph, END

from src.agents.prompts import TF_CODER_SYSTEM_PROMPT, QA_VALIDATOR_SYSTEM_PROMPT
from src.agents.tools import tfsec_scan

class GraphState(TypedDict):
    user_requirement: str
    architecture_proposals: dict
    selected_cloud: str
    terraform_code: str
    qa_feedback: List[str]
    qa_final_text: str
    retry_count: int

async def tf_coder_node(state: GraphState):
    cloud = state.get("selected_cloud", "AWS")
    proposals = state.get("architecture_proposals", {})
    selected_arch = proposals.get(cloud, {})
    prev_code = state.get("terraform_code", "")
    feedback = state.get("qa_feedback", [])
    
    feedback_str = f"QA Feedback to incorporate:\n{feedback[-1]}" if feedback else "No feedback. Initial clean run."
    prev_code_str = f"Previous Generated Code that caused the error:\n```hcl\n{prev_code}\n```\n" if prev_code else ""
    
    prompt = (
        f"Target Cloud: {cloud}\nArchitecture Proposal: {json.dumps(selected_arch)}\n{prev_code_str}{feedback_str}\n\n"
        "CRITICAL Requirement: DO NOT output any generic notes. Return your response strictly as a JSON object with two keys: 'terraform_code' (string containing the raw HCL) and 'terraform_metadata' (dictionary containing any tags or settings)."
    )
    
    llm = ChatGoogleGenerativeAI(
        model=GEMINI_FLASH_MODEL, 
        temperature=0.1, 
        project="duper-project-1", 
        location="global", 
        client_options={"api_endpoint": "https://aiplatform.googleapis.com"}
    )
    llm.client._api_client._http_options.api_version = "v1"
    
    agent_executor = create_react_agent(llm, [], prompt=TF_CODER_SYSTEM_PROMPT)
    res = await agent_executor.ainvoke({"messages": [("user", prompt)]})
    
    final_text = res["messages"][-1].content
    
    # Try parsing JSON to extract terraform_code
    try:
        if "```json" in final_text:
            json_str = final_text.split("```json")[1].split("```")[0].strip()
        else:
            json_str = final_text.strip("` \n")
            if json_str.startswith("json"): json_str = json_str[4:].strip()
        parsed = json.loads(json_str)
        final_tf_code = parsed.get("terraform_code", "")
    except Exception as e:
        final_tf_code = f"// Fallback mocked code due to parse error\nresource \"example\" \"fallback\" {{}}"
        
    return {"terraform_code": final_tf_code}

async def qa_validator_node(state: GraphState):
    cloud = state.get("selected_cloud", "AWS")
    final_tf_code = state.get("terraform_code", "")
    
    qa_prompt = f"Review the following Terraform code. Run tfsec_scan on it. If it fails or you find issues, describe them in detail with ACTIONABLE corrections. Otherwise, output exactly 'PASS'.\n\n```hcl\n{final_tf_code}\n```"
    
    qa_llm = ChatGoogleGenerativeAI(
        model=GEMINI_FLASH_MODEL, 
        temperature=0.0, 
        project="duper-project-1", 
        location="global", 
        client_options={"api_endpoint": "https://aiplatform.googleapis.com"}
    )
    qa_llm.client._api_client._http_options.api_version = "v1"
    
    qa_agent_executor = create_react_agent(qa_llm, [tfsec_scan], prompt=QA_VALIDATOR_SYSTEM_PROMPT)
    res = await qa_agent_executor.ainvoke({"messages": [("user", qa_prompt)]})
    
    final_text = res["messages"][-1].content
    
    retry_count = state.get("retry_count", 0) + 1
    new_feedback = list(state.get("qa_feedback", []))
    
    if "CRITICAL" in final_text or "ERROR" in final_text or "FAIL" in final_text:
        new_feedback.append(final_text)
        
    return {"qa_final_text": final_text, "retry_count": retry_count, "qa_feedback": new_feedback}

def check_qa_status(state: GraphState) -> str:
    final_text = state.get("qa_final_text", "")
    retry_count = state.get("retry_count", 0)
    
    if "CRITICAL" in final_text or "ERROR" in final_text or "FAIL" in final_text:
        if retry_count < 3:
            return "retry"
    return "done"

# Compile Graph
workflow = StateGraph(GraphState)
workflow.add_node("tf_coder", tf_coder_node)
workflow.add_node("qa_validator", qa_validator_node)

workflow.set_entry_point("tf_coder")
workflow.add_edge("tf_coder", "qa_validator")
workflow.add_conditional_edges(
    "qa_validator",
    check_qa_status,
    {
        "retry": "tf_coder",
        "done": END
    }
)
compiled_graph = workflow.compile()
