from src.config import GEMINI_FLASH_MODEL, GCP_PROJECT_ID
import json
import os
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from src.state import GraphState
from src.agents.prompts import ORCHESTRATOR_SYSTEM_PROMPT
from src.memory import MemoryBank

class OrchestratorOutput(BaseModel):
    extracted_requirements: str = Field(description="Summary of core requirements")
    technical_constraints: dict = Field(description="Dictionary of constraints e.g. budget, region, compliance")
    target_audience: str = Field(description="Target audience or traffic expectations")

def orchestrator_node(state: GraphState) -> dict:
    """
    Step 1: Analyzes requirements, breaks down constraints, and prepares context
    for AWS & GCP architects.
    """
    req = state.get('user_requirement', '')
    print(f"[Orchestrator] Analyzing requirement: {req}")
    
    # Instantiate MemoryBank for user
    memory_bank = MemoryBank(user_id="default_user")
    user_memories = memory_bank.retrieve_memories()
    
    # Save current interaction to Memory Bank
    memory_bank.generate_memories(req)
    
    # Initialize Vertex AI with structured output capabilities
    llm = ChatGoogleGenerativeAI(model=GEMINI_FLASH_MODEL, temperature=0.1, project=os.environ.get("GOOGLE_CLOUD_PROJECT", GCP_PROJECT_ID), location="global", client_options={"api_endpoint": "https://aiplatform.googleapis.com"})
    llm.client._api_client._http_options.api_version = "v1"
    structured_llm = llm.with_structured_output(OrchestratorOutput)
    
    # Inject Memory into System Prompt
    system_prompt = f"{ORCHESTRATOR_SYSTEM_PROMPT}\n\n[Vertex AI Memory Bank Context: {user_memories}]"
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Requirement: {req}")
    ]
    
    try:
        parsed_result = structured_llm.invoke(messages)
        context_str = (
            f"Requirements: {parsed_result.extracted_requirements}\n"
            f"Constraints: {json.dumps(parsed_result.technical_constraints)}\n"
            f"Audience/Traffic: {parsed_result.target_audience}"
        )
    except Exception as e:
        print(f"[Orchestrator] Warning: LLM parsing failed. Fast fallback. {e}")
        context_str = f"Requirements: {req}"
        
    return {"user_requirement": context_str, "current_step": "orchestrator_done"}
