import os
import time
import datetime
from google.cloud import firestore
import vertexai

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_memory_bank_engine(client):
    engines = list(client.agent_engines.list())
    if not engines:
        return None
    return engines[0].api_resource.name

def watch_databases():
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'agent-backend'))
    from src.config import GCP_PROJECT_ID
    
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", GCP_PROJECT_ID)
    user_id = "default_user"
    
    # Initialize Clients
    db = firestore.Client(project=project, database="cloud-bp-db")
    vertex_client = vertexai.Client(project=project, location="us-central1")
    engine_name = get_memory_bank_engine(vertex_client)
    
    if not engine_name:
        print("❌ Cannot find Vertex AI Memory Bank engine.")
        return

    print(f"👁️ Starting Real-time Database Watcher for user: {user_id}")
    print("Press Ctrl+C to stop.")
    time.sleep(2)
    
    # Track previous state to highlight changes
    last_fs_count = -1
    last_vb_count = -1

    try:
        while True:
            # 1. Fetch Firestore (Short-term UI)
            docs = list(db.collection('chat_sessions').order_by('title').limit(5).stream())
            total_fs_messages = sum([len(d.to_dict().get('messages', [])) for d in docs])
            
            # 2. Fetch Vertex AI Memory Bank (Long-term Facts)
            memories = []
            total_vb_facts = 0
            vb_error = None
            try:
                memories = vertex_client.agent_engines.memories.retrieve(
                    name=engine_name,
                    scope={"user_id": user_id},
                    simple_retrieval_params={}
                )
                total_vb_facts = len(memories)
            except Exception as e:
                vb_error = str(e)
                # If there's a huge Java stacktrace, we just take the first part
                if len(vb_error) > 150:
                    vb_error = vb_error[:150] + "..."
            
            # Prepare UI
            clear_screen()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"🕒 Last Checked: {now}")
            print("="*60)
            
            # --- Panel 1: Firestore ---
            fs_status = "🟢 CHANGED!" if (last_fs_count != -1 and total_fs_messages != last_fs_count) else "⚪ IDLE"
            print(f"📘 [1] FIRESTORE (Short-term Raw Chat) | {fs_status}")
            print(f"    - Total Sessions Found (Top 5): {len(docs)}")
            print(f"    - Cumulative Messages Count: {total_fs_messages}")
            
            if docs:
                latest_doc = docs[-1].to_dict()
                msgs = latest_doc.get('messages', [])
                if msgs:
                    latest_msg = msgs[-1]
                    role = latest_msg.get('role', 'unknown')
                    content = str(latest_msg.get('content', ''))
                    print(f"    -> Latest msg [{role}]: {content[:50]}...")
            
            print("\n" + "="*60)
            
            # --- Panel 2: Memory Bank ---
            if vb_error:
                vb_status = "⚠️ API ERROR"
                print(f"🧠 [2] VERTEX AI MEMORY BANK (Long-term Facts) | {vb_status}")
                print(f"    - Error: GCP Backend Issue ({vb_error})")
            else:
                vb_status = "🔴 CHANGED (FACT EXTRACTED!)" if (last_vb_count != -1 and total_vb_facts != last_vb_count) else "⚪ IDLE"
                print(f"🧠 [2] VERTEX AI MEMORY BANK (Long-term Facts) | {vb_status}")
                print(f"    - Total Facts Extracted: {total_vb_facts}")
                
                if memories:
                    latest_mem = memories[-1]
                    fact = getattr(getattr(latest_mem, 'memory', None), 'fact', None)
                    if not fact:
                        fact = str(latest_mem).strip()
                    print(f"    -> Latest Fact: {fact}")
                
            print("="*60)
            
            last_fs_count = total_fs_messages
            last_vb_count = total_vb_facts
            
            # Wait before next poll
            time.sleep(3)
            
    except KeyboardInterrupt:
        print("\n⏹️ Watcher stopped by user.")
    except Exception as e:
        print(f"\n❌ Watcher crashed: {e}")

if __name__ == "__main__":
    watch_databases()
