import os
from typing import Optional, List, Dict, Any

from src.config import GEMINI_FLASH_MODEL, GCP_PROJECT_ID

try:
    import vertexai
    # To use preview memory bank features if available
    # from vertexai.preview import reasoning_engines
except ImportError:
    vertexai = None

_AGENT_ENGINE_NAME: Optional[str] = None

class MemoryBank:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.project = os.environ.get("GOOGLE_CLOUD_PROJECT", GCP_PROJECT_ID)
        self.location = "us-central1" # memory bank list/create requires us-central1
        
        try:
            import vertexai
            self.client = vertexai.Client(project=self.project, location=self.location)
            
            global _AGENT_ENGINE_NAME
            if not _AGENT_ENGINE_NAME:
                engines = list(self.client.agent_engines.list())
                if engines:
                    _AGENT_ENGINE_NAME = engines[0].api_resource.name
                else:
                    new_engine = self.client.agent_engines.create(display_name="cloud_bp_memory_bank")
                    _AGENT_ENGINE_NAME = new_engine.api_resource.name
                    
            self.agent_engine_name = _AGENT_ENGINE_NAME
        except Exception as e:
            print(f"[Memory Bank] Vertex AI Initialization Error: {e}")
            self.client = None

    def retrieve_memories(self) -> str:
        """
        Retrieves user preferences and history from the Vertex AI Agent Engine Memory Bank.
        """
        if getattr(self, 'client', None) and getattr(self, 'agent_engine_name', None):
            try:
                memories = self.client.agent_engines.memories.retrieve(
                    name=self.agent_engine_name,
                    scope={"user_id": self.user_id},
                    simple_retrieval_params={}
                )
                memory_facts = [
                    m.memory.fact for m in memories
                    if hasattr(m, 'memory') and hasattr(m.memory, 'fact')
                ]
                if memory_facts:
                    print(f"[Memory Bank] Retrieved {len(memory_facts)} memories for user: {self.user_id}")
                    return " | ".join(str(f) for f in memory_facts)
            except Exception as e:
                err_msg = str(e)
                print(f"[Memory Bank] Vertex Retrieve Error: {err_msg[:150]}... (Backend Error)")
                
        print(f"[Memory Bank] Fallback retrieval for user: {self.user_id}")
        return "User prefers secure, highly-available, and strictly compliant architectures."

    def generate_memories(self, new_context: str):
        """
        Stores new interactions or preferences back to the Vertex AI Agent Engine Memory Bank.
        """
        print(f"[Memory Bank] Generating memory for user {self.user_id}: {new_context[:100]}...")
        if getattr(self, 'client', None) and getattr(self, 'agent_engine_name', None):
            try:
                self.client.agent_engines.memories.create(
                    name=self.agent_engine_name,
                    fact=new_context,
                    scope={"user_id": self.user_id}
                )
                print(f"[Memory Bank] Succesfully sent via SDK: {new_context[:50]}...")
            except Exception as e:
                err_msg = str(e)
                print(f"[Memory Bank] Vertex Update Error: {err_msg[:150]}... (Backend Error)")

from google.cloud import firestore
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

_FIRESTORE_CLIENT: Optional[firestore.Client] = None

def backup_to_firestore(thread_id: str, messages: List[Any]) -> None:
    """Backups a list of messages (or dicts) to Firestore."""
    global _FIRESTORE_CLIENT
    try:
        if _FIRESTORE_CLIENT is None:
            _FIRESTORE_CLIENT = firestore.Client(
                project=os.environ.get("GOOGLE_CLOUD_PROJECT", GCP_PROJECT_ID), 
                database="cloud-bp-db"
            )
        db = _FIRESTORE_CLIENT
        
        title = "새 아키텍처 설계"
        serialized = []
        for msg in messages:
            if hasattr(msg, 'type') and hasattr(msg, 'content'):
                serialized.append({"role": msg.type, "content": msg.content})
            elif isinstance(msg, dict):
                serialized.append(msg)
            else:
                serialized.append({"role": "unknown", "content": str(msg)})
                
        # Find first user message for title
        for m in serialized:
            if m.get("role") == "user":
                title = str(m.get("content", ""))[:30] + "..."
                break
                
        doc_ref = db.collection('chat_sessions').document(thread_id)
        # We only want to set title if it doesn't exist, or just overwrite it with the same initial user message.
        doc_ref.set({'messages': serialized, 'title': title, 'last_updated': firestore.SERVER_TIMESTAMP}, merge=True)
    except Exception as e:
        print(f"[Memory Orchestration] Firestore backup failed: {e}")

async def extract_and_store_facts(user_id: str, state: Dict[str, Any]) -> None:
    """Summarizes LangGraph state and stores facts in MemoryBank."""
    try:
        llm = ChatGoogleGenerativeAI(
            model=GEMINI_FLASH_MODEL, 
            temperature=0.1, 
            project=os.environ.get("GOOGLE_CLOUD_PROJECT", GCP_PROJECT_ID), 
            location="global",
            client_options={"api_endpoint": "https://aiplatform.googleapis.com"}
        )
        llm.client._api_client._http_options.api_version = "v1"
        
        prompt = (
            "You are an AI Memory Summarizer. Extract the holistic project outcome from this state. "
            "Return a strictly formatted JSON array composed of independent strings. "
            "CRITICAL: Each string in the array represents a single distinct memory 'fact' and MUST be strictly UNDER 1800 characters! "
            "Instead of generating one massive paragraph, break down the facts into 1-4 distinct array elements such as:\n"
            "[\n"
            "  \"User originally requested a secure, enterprise-grade Serverless Architecture for GCP.\",\n"
            "  \"System proposed GKE with gVisor boundaries, Cloud Armor, and Cloud SQL. Selected Cloud was GCP.\",\n"
            "  \"Terraform code compilation was attempted. Example resources used include `google_container_node_pool` with `sandbox_config`.\",\n"
            "  \"Final Outcome: The deployment failed with INVALID_ARGUMENT related to data structures.\"\n"
            "]\n"
            "DO NOT include markdown block characters. ONLY output the valid JSON array."
        )
        
        # Safely extract and truncate massive fields
        extracted_state = {}
        for key in ['user_requirement', 'selected_cloud', 'architecture_proposals', 'terraform_code', 'qa_feedback', 'sandbox_feedback']:
            val = state.get(key, "")
            if key == 'architecture_proposals' and isinstance(val, dict):
                selected = state.get("selected_cloud", "")
                if selected and selected in val:
                    arch_text = str(val[selected])
                    extracted_state['architecture_proposal'] = arch_text[:1000] + "...(truncated)" if len(arch_text) > 1000 else arch_text
                continue
                
            if isinstance(val, str):
                if key == 'terraform_code':
                    extracted_state[key] = val[:500] + "...(truncated)" if len(val) > 500 else val
                elif key == 'sandbox_feedback' or key == 'qa_feedback':
                    extracted_state[key] = val[:1000] + "...(truncated)" if len(val) > 1000 else val
                else:
                    extracted_state[key] = val
            elif val is not None:
                extracted_state[key] = str(val)[:500]

        state_str = json.dumps(extracted_state, ensure_ascii=False)
        
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"State:\n{state_str}")
        ]
        
        res = await llm.ainvoke(messages)
        
        fact_content = res.content
        if isinstance(fact_content, list):
            fact = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in fact_content).strip()
        else:
            fact = str(fact_content).strip()
        
        if fact:
            bank = MemoryBank(user_id=user_id)
            bank.generate_memories(fact)
            
    except Exception as e:
        err_msg = str(e)
        print(f"[Memory Orchestration] Extraction failed: {err_msg[:150]}...")
