import streamlit as st
import asyncio
import os
import sys
import uuid
import json

# Force unbuffered stdout for container environments
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.agents.e2e_workflow import build_e2e_graph

@st.cache_resource
def get_compiled_graph():
    return build_e2e_graph()

compiled_e2e_graph = get_compiled_graph()
from dotenv import load_dotenv

# Load .env for LangSmith (LANGCHAIN_TRACING_V2=true, LANGCHAIN_API_KEY, LANGCHAIN_PROJECT)
load_dotenv()

from google.cloud import firestore

st.set_page_config(page_title="Cloud BP Advisor", page_icon="☁️", layout="wide")

try:
    # Use explicitly created Firestore Database
    db = firestore.Client(database="cloud-bp-db")
except Exception as e:
    print(f"[Firestore] Initialization Error: {e}")
    db = None

def load_sessions():
    if not db:
        return {}
    try:
        sessions_ref = db.collection(u'chat_sessions')
        docs = sessions_ref.order_by(u'last_updated', direction=firestore.Query.DESCENDING).stream()
        sessions = {}
        for doc in docs:
            sessions[doc.id] = doc.to_dict()
        return sessions
    except Exception as e:
        print(f"[Firestore Load Error] {e}")
        return {}

def save_sessions(sessions):
    """Fallback local dump. Not used directly in Firestore flow, kept for compatibility if needed."""
    pass

from src.memory import backup_to_firestore, extract_and_store_facts
import threading

def sync_chat_session():
    # Helper to run firestore backup in background without blocking or async loop cancellation
    tid = st.session_state.thread_id
    if not st.session_state.messages:
        return
    try:
        # Shallow copy the list to avoid mutations from the main Streamlit thread
        msgs_copy = list(st.session_state.messages)
        threading.Thread(target=backup_to_firestore, args=(tid, msgs_copy), daemon=True).start()
    except Exception as e:
        print(f"[Firestore Thread Error] {e}")

with st.sidebar:
    st.title("💬 과거 대화 기록")
    if st.button("➕ 새로운 대화 시작하기", use_container_width=True):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.persisted_snapshots = set()
        st.rerun()
        
    st.divider()
    sessions = load_sessions()
    for tid, sdata in sessions.items():
        if st.button(sdata.get("title", "새 대화"), key=f"btn_{tid}", use_container_width=True):
            st.session_state.thread_id = tid
            st.session_state.messages = sdata.get("messages", [])
            st.session_state.persisted_snapshots = set()
            st.rerun()

st.title("☁️ Cloud BP Advisor (LangGraph E2E)")
st.caption("사용자 지시에 따른 완벽한 StateGraph 기반 단일 통합 UI")

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []
    # Try restoring if it already exists
    curr_sess = load_sessions().get(st.session_state.thread_id)
    if curr_sess:
        st.session_state.messages = curr_sess.get("messages", [])

config = {"configurable": {"thread_id": st.session_state.thread_id}}

if "persisted_snapshots" not in st.session_state:
    st.session_state.persisted_snapshots = set()

def display_chat():
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.write(msg["content"])
        elif msg.get("type") == "proposals":
            with st.chat_message("assistant"):
                feedback_ctx = msg.get("feedback_context")
                if feedback_ctx:
                    st.info(f"💡 **방안 재설계 완료 - 사용자의 수정 요청 내역 반영됨:**\n\n> {feedback_ctx}")
                else:
                    st.write("요청해주신 아키텍처 초안 설계가 완료되었습니다. 아래 2가지 클라우드 제안을 검토해주세요.")
                    
                proposals = msg["content"]
                
                import streamlit.components.v1 as components
                import re
                
                def render_mermaid(code: str):
                    # Sanitize common LLM Mermaid syntax errors (e.g. unescaped parentheses in Node names)
                    # NodeName[Label (Parens)] -> NodeName["Label (Parens)"]
                    code = re.sub(r'([A-Za-z0-9_]+)\[([^"\]]*?[()][^"\]]*?)\]', r'\1["\2"]', code)
                    
                    # Escape the code block slightly to inject properly into HTML
                    safe_code = code.replace('`', '\\`')
                    components.html(
                        f"""
                        <div id="mermaid-container" class="mermaid" style="width: 100%; height: 100%; font-family: sans-serif;">
                            {code}
                        </div>
                        <script type="module">
                            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
                            mermaid.initialize({{ 
                                startOnLoad: false, 
                                theme: 'default',
                                securityLevel: 'loose',
                                flowchart: {{ useMaxWidth: true, htmlLabels: true }}
                            }});
                            
                            async function renderDiagram() {{
                                const element = document.getElementById('mermaid-container');
                                try {{
                                    await mermaid.run({{ nodes: [element] }});
                                }} catch (err) {{
                                    console.error("Mermaid syntax error:", err);
                                    element.innerHTML = `<div style="padding:15px; background:#f8f9fa; color:#212529; border: 1px solid #dee2e6; border-radius:8px; font-family:monospace; white-space:pre-wrap; font-size:12px;">${safe_code}</div>`;
                                }}
                            }}
                            renderDiagram();
                        </script>
                        """,
                        height=400,
                        scrolling=True
                    )

                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("☁️ AWS Architecture 제안")
                    aws = proposals.get("AWS", {})
                    if aws:
                        st.markdown(f"**💰 예상 비용:** {aws.get('cost', 'N/A')}")
                        st.markdown(f"**📝 설명:** {aws.get('desc', 'N/A')}")
                        st.markdown("**📊 아키텍처 다이어그램:**")
                        render_mermaid(aws.get('diagram', ''))
                        with st.expander("✅ Well-Architected 심층 분석 보기", expanded=False):
                            st.markdown(aws.get('well_architected_analysis', 'N/A'))
                    else:
                        st.error("AWS 제안이 누락되었습니다.")

                with col2:
                    st.subheader("☁️ GCP Architecture 제안")
                    gcp = proposals.get("GCP", {})
                    if gcp:
                        st.markdown(f"**💰 예상 비용:** {gcp.get('cost', 'N/A')}")
                        st.markdown(f"**📝 설명:** {gcp.get('desc', 'N/A')}")
                        st.markdown("**📊 아키텍처 다이어그램:**")
                        render_mermaid(gcp.get('diagram', ''))
                        with st.expander("✅ Well-Architected 심층 분석 보기", expanded=False):
                            st.markdown(gcp.get('well_architected_analysis', 'N/A'))
                    else:
                        st.error("GCP 제안이 누락되었습니다.")
        elif msg.get("type") == "tf_code":
            with st.chat_message("assistant"):
                st.success("🎉 **과거 기록**: 테라폼 코드 생성 완료")
                with st.expander("최종 검증된 테라폼 코드 보기", expanded=False):
                    st.code(msg["content"], language="hcl")
        elif msg.get("type") == "final_success_code":
            with st.chat_message("assistant"):
                st.success("✅ **[프로비저닝 성공]** 모든 샌드박스 검증 및 배포가 완료되었습니다!")
                st.code(msg["content"], language="hcl")
        elif msg.get("type") == "final_failed_code":
            with st.chat_message("assistant"):
                st.error("🚨 **[최종 실패]** 재시도 최대 횟수 초과. AI가 원인을 분석하여 코드 상단에 주석으로 기록했습니다.")
                st.code(msg["content"], language="hcl")
        else:
            # Parse retry count from node name if available (e.g. "tf_coder (1차 시도)")
            node_label = msg.get('node', 'assistant')
            retry_tag = f" ({msg.get('retry_count', 1)}차 시도)" if msg.get("retry_count", 0) > 1 else ""
            
            with st.expander(f"⚙️ Agent Log: {node_label}{retry_tag}"):
                if msg.get("is_sandbox_log"):
                    st.code(msg["content"])
                else:
                    st.markdown(msg["content"])

async def run_graph(initial_state=None):
    # Dictionaries to track elements for each parallel node
    # Dictionaries to track elements for each parallel node
    node_ui_boxes = {}
    node_buffers = {}
    node_retry_counts = {} # Track retry attempts per node type
    sandbox_log_buffer = ""
    
    with st.chat_message("assistant"):
        st.markdown("🔄 **그래프 실행 시작...**")
        status_box = st.empty()
        # Create a container where parallel node outputs will flexibly stack
        streams_container = st.container()
        
        try:
            async for event in compiled_e2e_graph.astream_events(initial_state, config, version="v2"):
                event_type = event["event"]
                node_name = event.get("name", "")
                tags = event.get("tags", [])
                
                # Identify which node this stream event belongs to using LangGraph tags
                node_owner = None
                valid_nodes = ["orchestrator", "aws_architect", "gcp_architect", "tf_coder", "qa_validator", "tf_runner", "tf_coder_sandbox_fix"]
                for n in valid_nodes:
                    if f"langgraph:node:{n}" in tags or node_name == n:
                        node_owner = n
                        break

                # Initialize UI for this node if we haven't yet
                if node_owner and node_owner not in node_ui_boxes:
                    node_retry_counts[node_owner] = node_retry_counts.get(node_owner, 0) + 1
                    current_retry = node_retry_counts[node_owner]
                    retry_label = f" ({current_retry}차 시도)" if current_retry > 1 else ""
                    
                    print(f"\n\n🟢 [LangGraph] Starting Agent: {node_owner} ...", flush=True)
                    with streams_container:
                        st.markdown(f"🟢 **[{node_owner}]** 실행 중...{retry_label}")
                        node_ui_boxes[node_owner] = st.empty()
                        node_buffers[node_owner] = ""
                        if node_owner == "tf_runner":
                            sandbox_log_buffer = ""
                
                # Custom Sandbox Logs Stream
                if event_type == "on_custom_event" and event.get("name") == "sandbox_log":
                    chunk_text = event["data"]["log"]
                    print(chunk_text, end="", flush=True)
                    sandbox_log_buffer += chunk_text
                    if "tf_runner" in node_ui_boxes:
                        node_ui_boxes["tf_runner"].code(sandbox_log_buffer)
                    continue

                if event_type == "on_chat_model_stream" and node_owner:
                    chunk = event["data"]["chunk"].content
                    if isinstance(chunk, list):
                        chunk = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in chunk if b)
                    elif not isinstance(chunk, str):
                        chunk = str(chunk)
                        
                    if chunk:
                        print(chunk, end="", flush=True)
                        node_buffers[node_owner] += chunk
                        node_ui_boxes[node_owner].markdown(node_buffers[node_owner])
                
                # Fallback for synchronous LLM calls that don't emit stream chunks
                if event_type == "on_chat_model_end" and node_owner:
                    final_msg = event["data"].get("output", "")
                    if hasattr(final_msg, "content"):
                        final_text = final_msg.content
                    elif isinstance(final_msg, dict) and "output" in final_msg:
                        final_text = final_msg.get("output", "")
                    else:
                        final_text = str(final_msg)
                        
                    if not node_buffers.get(node_owner) and final_text:
                        node_buffers[node_owner] = final_text
                        node_ui_boxes[node_owner].markdown(node_buffers[node_owner])
                
                if event_type == "on_tool_start":
                    print(f"\n🛠️ [LangGraph] Tool Triggered: {node_name}", flush=True)
                    status_box.warning(f"🛠️ **Tool Triggred**: `{node_name}` 검사 시도중...")
                    
                if event_type == "on_chain_end" and node_name in valid_nodes:
                    print(f"\n🔴 [LangGraph] {node_name} Execution Completed.", flush=True)
                    status_box.success(f"🔴 **[{node_name}]** 완료.")
                    
                    # 🚨 BULLETPROOF FALLBACK 🚨 
                    # If streaming failed or was swallowed by nested agents, extract the exact result from the final state payload!
                    if not node_buffers.get(node_name):
                        final_output = event.get("data", {}).get("output", {})
                        if isinstance(final_output, dict):
                            salvaged = ""
                            if node_name == "orchestrator":
                                salvaged = str(final_output.get("user_requirement", ""))
                            elif node_name in ["aws_architect", "gcp_architect"]:
                                salvaged = json.dumps(final_output.get("architecture_proposals", {}), ensure_ascii=False, indent=2)
                            elif node_name == "tf_coder":
                                salvaged = f"```hcl\n{final_output.get('terraform_code', '')}\n```"
                            elif node_name in ["qa_validator", "tf_coder_sandbox_fix"] and final_output.get("qa_final_text"):
                                salvaged = str(final_output.get("qa_final_text", ""))
                                
                            if salvaged:
                                node_buffers[node_name] = salvaged
                                if node_name in node_ui_boxes:
                                    node_ui_boxes[node_name].markdown(node_buffers[node_name])
                                    
                    # Persist message
                    content_to_save = sandbox_log_buffer if node_name == "tf_runner" else node_buffers.get(node_name, "")
                    current_retry = node_retry_counts.get(node_name, 1)
                    retry_label = f" ({current_retry}차 시도)" if current_retry > 1 else ""
                    
                    is_sandbox = (node_name == "tf_runner")
                    # Persist message immediately to session state
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "node": node_name, 
                        "content": content_to_save, 
                        "is_sandbox_log": is_sandbox,
                        "retry_count": current_retry
                    })
                    sync_chat_session()
                    
                    if node_name in node_ui_boxes:
                        # Replace the live streaming empty box with a clean collapsed expander before looping or rerunning
                        with node_ui_boxes[node_name].container():
                            with st.expander(f"⚙️ Agent Log: {node_name}{retry_label} (완료)", expanded=False):
                                if is_sandbox:
                                    st.code(content_to_save)
                                else:
                                    st.code(content_to_save, language="markdown")
                        del node_ui_boxes[node_name] # Ensure a fresh box is created if graph loops back

        except asyncio.CancelledError:
            error_msg = "Graph Execution Cancelled (asyncio.CancelledError) - 이는 보통 2개의 설계 에이전트(AWS, GCP)가 병렬 실행될 때 하나가 429 API 쿼터 초과 연쇄 에러로 강제 취소되면서 발생합니다."
            st.error(error_msg)
            st.session_state.messages.append({
                "role": "assistant", 
                "node": "system_error", 
                "content": f"🚨 **[시스템 오류]** {error_msg}",
                "is_sandbox_log": False,
                "retry_count": 1
            })
            sync_chat_session()
        except Exception as e:
            error_msg = f"Graph Error: {str(e)}"
            st.error(error_msg)
            
            # Refined guidance based on error type
            advice = "잠시 후 다시 시도해주세요."
            if any(k in error_msg.lower() for k in ["quota", "exhausted", "429", "limit"]):
                advice = "1~2분 정도 대기하여 Gemini API Quota가 갱신된 후 프롬프트를 다시 시도해주세요."
            elif "name 'os' is not defined" in error_msg.lower():
                advice = "백엔드 코드에 정의되지 않은 변수(os)가 사용되었습니다. 개발팀의 조치가 필요합니다."
            elif "auth" in error_msg.lower() or "permission" in error_msg.lower():
                advice = "GCP 권한 또는 인증 관련 오류가 발생했습니다. 서비스 계정 설정을 확인해주세요."

            st.session_state.messages.append({
                "role": "assistant", 
                "node": "system_error", 
                "content": f"🚨 **[시스템 오류]** 실행 중 예기치 못한 에러가 발생하여 LangGraph 스트리밍이 중단되었습니다.\n\n```text\n{error_msg}\n```\n\n(조치 방법: {advice})",
                "is_sandbox_log": False,
                "retry_count": 1
            })
            sync_chat_session()
        current_state = compiled_e2e_graph.get_state(config)
        next_node = getattr(current_state, "next", [])
        snapshot_id = getattr(current_state.config.get("configurable", {}), "get", lambda x: "")("checkpoint_id") or "fallback"
        
        if snapshot_id not in st.session_state.persisted_snapshots:
            if "feedback_review" in next_node:
                msg = {
                    "role": "assistant", "type": "proposals", 
                    "content": current_state.values.get("architecture_proposals", {})
                }
                feedback_val = current_state.values.get("user_feedback", "")
                if feedback_val:
                    msg["feedback_context"] = feedback_val
                st.session_state.messages.append(msg)
            elif "approval_node" in next_node:
                st.session_state.messages.append({
                    "role": "assistant", "type": "tf_code", 
                    "content": current_state.values.get("terraform_code", "")
                })
            elif not next_node and current_state.values:
                phase = current_state.values.get("phase")
                
                final_code = current_state.values.get("terraform_code", "")
                qa_warning = current_state.values.get("qa_security_warning", "")
                if qa_warning and qa_warning not in final_code:
                    final_code = f"/*\n{qa_warning}\n*/\n\n{final_code}"
                    
                if phase == "completed":
                    st.session_state.messages.append({
                        "role": "assistant", "type": "final_success_code", 
                        "content": final_code
                    })
                    # Background fact extraction to Memory Bank
                    try:
                        await extract_and_store_facts("default_user", current_state.values)
                    except Exception as e:
                        print(f"[Memory Bank Extraction Error] {e}")
                elif phase == "sandbox_failed_permanently":
                    st.session_state.messages.append({
                        "role": "assistant", "type": "final_failed_code", 
                        "content": final_code
                    })
                    # Background fact extraction to Memory Bank
                    try:
                        await extract_and_store_facts("default_user", current_state.values)
                    except Exception as e:
                        print(f"[Memory Bank Extraction Error] {e}")
                    
            st.session_state.persisted_snapshots.add(snapshot_id)
            sync_chat_session()
            
    st.rerun()

# 1. Show existing chat
display_chat()

# Get current state
try:
    current_state = compiled_e2e_graph.get_state(config)
    next_node = current_state.next
    graph_values = current_state.values
except Exception as e:
    st.error(f"State Recovery Error: {str(e)}")
    next_node = []
    graph_values = {}

# Debugging State Visibility Check
if not next_node and graph_values.get("architecture_proposals") and not graph_values.get("terraform_code"):
    st.error(f"🚨 DEBUG MODE: Graph crashed or unexpectedly finished. next_node is empty!")
    st.json({"next_node_raw": list(next_node), "available_keys": list(graph_values.keys())})

# --- AUTO-RESUME ABORTED EXECUTIONS ---
HITL_NODES = ["feedback_review", "approval_node"]
is_hitl_wait = any(node in next_node for node in HITL_NODES)

if next_node and not is_hitl_wait:
    st.warning("⚠️ **진행 중단됨**: 에이전트 작업이 백그라운드에서 대기 상태입니다.")
    if st.button("▶️ 멈춘 지점부터 작업 계속하기", use_container_width=True):
        with st.spinner("작업을 다시 시작합니다..."):
            asyncio.run(run_graph(None))
            st.rerun()

elif not next_node and not graph_values.get("terraform_code") and st.session_state.messages:
    last_msg = st.session_state.messages[-1]
    if last_msg["role"] == "user" and len(st.session_state.messages) == 1:
        st.warning("⚠️ **진행 중단됨**: 초안 설계 요청 후 작업이 강제 종료되었습니다.")
        if st.button("▶️ 처음부터 작업 다시 시작하기", use_container_width=True):
            with st.spinner("작업을 다시 시작합니다..."):
                asyncio.run(run_graph({"user_requirement": last_msg["content"]}))
                st.rerun()

# 2. Main Logic UI Placeholders
ui_placeholder = st.empty()

# Determine state for Human In The Loop Forms
if "feedback_review" in next_node:
    with ui_placeholder.container():
        st.info("✋ **Human In The Loop**: 아키텍처 초안이 산출되었습니다. 채팅창을 확인 후 아래 옵션을 선택하세요.")
        proposals = graph_values.get("architecture_proposals", {})
        
        if proposals.get("AWS", {}).get("error"):
            st.error(f"⚠️ [AWS 에러] {proposals['AWS']['error']}")
        if proposals.get("GCP", {}).get("error"):
            st.error(f"⚠️ [GCP 에러] {proposals['GCP']['error']}")
            
        with st.form("human_review_form"):
            st.write("### ⚙️ 진행 옵션 (추가 요청 반영)")
            selected_cloud = st.selectbox("구축할 클라우드를 선택하세요:", ["AWS", "GCP", "재설계 요청 (수정)"])
            user_feedback = st.text_area("수정 요청사항 (없으면 비워두세요. 작성 시 아키텍처 재설계 루프를 탑니다.)", placeholder="예: 데이터베이스를 무조건 Private Subnet에 배치해주세요.")
            
            if st.form_submit_button("확정 및 다음 단계 진행"):
                unselected_cloud = "GCP" if selected_cloud == "AWS" else "AWS"
                pruning_payload = {
                    "architecture_proposals": {unselected_cloud: None},
                    "user_requirement": "Context Wiped to prevent TF Coder hallucination."
                }
                
                if selected_cloud == "재설계 요청 (수정)":
                    compiled_e2e_graph.update_state(config, {"selected_cloud": "", "user_feedback": user_feedback}, as_node="feedback_review")
                else:
                    payload = {"selected_cloud": selected_cloud, "user_feedback": user_feedback}
                    payload.update(pruning_payload) # Inject Pruning Logic
                    compiled_e2e_graph.update_state(config, payload, as_node="feedback_review")
                asyncio.run(run_graph(None))

elif "approval_node" in next_node:
    with ui_placeholder.container():
        st.success("🎉 테라폼 코드가 성공적으로 생성 및 자체 검증(QA)되었습니다!")
        retry_count = graph_values.get("retry_count", 0)
        qa_final_text = graph_values.get("qa_final_text", "")
        
        if retry_count >= 3 and "FAIL_SECURITY" in str(qa_final_text):
            st.warning("⚠️ **[경고]** 테라폼 코드가 최대 자체 치유 횟수(3회)를 초과하여 보안/QA 검증을 완벽히 통과하지 못한 상태로 중단되었습니다.")
            st.error("이 코드에는 보안 취약점이나 문법 오류가 포함되어 있을 수 있습니다. 신중하게 검토 후 샌드박스 배포를 승인해주세요.")
            st.warning("✋ **사용자 강제 승인 대기중**: 위험을 감수하고 코드를 샌드박스 환경에 실제 배포하시겠습니까?")
        else:
            st.warning("✋ **사용자 승인 대기중**: 코드를 샌드박스 환경에 실제 배포하시겠습니까?")
        with st.form("approval_form"):
            if st.form_submit_button("🚀 승인 및 샌드박스 프로비저닝 실행"):
                compiled_e2e_graph.update_state(config, {"phase": "executing"}, as_node="approval_node")
                asyncio.run(run_graph(None))

elif not next_node and graph_values.get("terraform_code"):
    with ui_placeholder.container():
        st.success("✅ 전체 파이프라인 처리가 완료되었습니다.")
        
        # -------------------------------------------------------------
        # Architecture Download Feature
        # -------------------------------------------------------------
        import datetime
        selected_cloud = graph_values.get("selected_cloud", "Unknown")
        final_code = graph_values.get("terraform_code", "")
        qa_warning = graph_values.get("qa_security_warning", "")
        if qa_warning and qa_warning not in final_code:
            final_code = f"/*\n{qa_warning}\n*/\n\n{final_code}"
            
        proposals = graph_values.get("architecture_proposals", {})
        selected_arch = proposals.get(selected_cloud, {})
        
        md_content = f"# {selected_cloud} Architecture Proposal\n\n"
        md_content += f"## 📝 Description\n{selected_arch.get('desc', 'N/A')}\n\n"
        md_content += f"## 💰 Estimated Cost\n{selected_arch.get('cost', 'N/A')}\n\n"
        md_content += f"## 📊 Architecture Diagram\n```mermaid\n{selected_arch.get('diagram', '')}\n```\n\n"
        md_content += f"## ✅ Well-Architected Analysis\n{selected_arch.get('well_architected_analysis', 'N/A')}\n\n"
        md_content += f"## 💻 Auto-generated Terraform Code\n```hcl\n{final_code}\n```\n"
        
        today_date = datetime.date.today().strftime("%Y%m%d")
        session_short = st.session_state.thread_id.split("-")[0] if "-" in st.session_state.thread_id else st.session_state.thread_id[:8]
        file_name = f"{session_short}_{today_date}_{selected_cloud}_architecture_proposal.md"
        
        try:
            from google.cloud import storage
            import google.auth
            from google.auth.transport.requests import Request
            
            storage_client = storage.Client()
            bucket_name = os.environ.get("GCS_ARCHIVE_BUCKET", "cloud-bp-archives")
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(f"exports/{file_name}")
            blob.upload_from_string(md_content, content_type="text/markdown")
            
            # Generate Presigned URL using IAM Impersonation of the Compute Engine SA
            credentials, _ = google.auth.default()
            credentials.refresh(Request())
            sa_email = "743441901636-compute@developer.gserviceaccount.com"
            url = blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(days=1),
                method="GET",
                service_account_email=sa_email,
                access_token=credentials.token
            )

            st.success("✅ 파일 렌더링 및 클라우드 아카이빙 성공")
            st.markdown(f"### ⬇️ [최종 아키텍처 및 코딩 파일 별도 열기 (.md)]({url})")
            st.caption("보안이 적용된 Presigned URL 링크입니다. (안전하게 24시간 동안 유효합니다)")
            
            # Unconditionally provide a local download button as well for convenience
            st.download_button(
                label="⬇️ 즉시 로컬로 다운로드 (.md)",
                data=md_content,
                file_name=file_name,
                mime="text/markdown"
            )
        except Exception as e:
            print(f"[GCS Upload Error] {e}")
            # Fallback to local download button if GCP permissions fail
            st.download_button(
                label="⬇️ 최종 아키텍처 및 테라폼 코드 다운로드 (.md)",
                data=md_content,
                file_name=file_name,
                mime="text/markdown"
            )

# 3. Always render Chat Input so it doesn't disappear
is_graph_running_or_paused = bool(next_node)
prompt = st.chat_input("원하시는 클라우드 인프라 요구사항을 입력하세요 (예: 고가용성 멀티티어 웹 앱)", disabled=is_graph_running_or_paused)

if prompt:
    # 즉각적인 UX 피드백: 그래프가 도는 동안 사용자의 입력이 사라져 보이지 않도록 바로 화면에 선단위 렌더링
    with st.chat_message("user"):
        st.write(prompt)
        
    start_msg = st.chat_message("assistant")
    with start_msg:
        with st.spinner("🧠 메인 오케스트레이터 분석 중... 잠시만 기다려주세요"):
            # If starting a new requirement after existing pipeline finished
            if not next_node and graph_values.get("terraform_code"):
                st.session_state.thread_id = str(uuid.uuid4())
                st.session_state.messages = [{"role": "user", "content": prompt}]
                config = {"configurable": {"thread_id": st.session_state.thread_id}}
                sync_chat_session()
                asyncio.run(run_graph({"user_requirement": prompt}))
            else:
                st.session_state.messages.append({"role": "user", "content": prompt})
                sync_chat_session()
                asyncio.run(run_graph({"user_requirement": prompt}))

sync_chat_session()
