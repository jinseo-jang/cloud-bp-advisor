# Architecture Review: Enterprise Cloud Architecture Generation Agent

## User Review Required

> [!IMPORTANT]
> 리드 아키텍트로서 PRD 기반 대상 아키텍처를 검토한 결과, GKE gVisor를 사용한 보안 격리 등 엔터프라이즈 요구사항이 전반적으로 훌륭하게 설계되어 있습니다.
> 다만, 실제 **5-Agent 협력 패턴의 구현 복잡도와 클라우드 모범 사례(보안/비용/확장성)** 측면에서 다음 4가지 아키텍처 대안 및 구체화 방안을 제안합니다. 아래 내용에 대한 승인 혹은 수정 의견을 주시면 승인된 아키텍처를 기반으로 모노레포 생성(Step 2)을 시작하겠습니다.

### 1. 5-Agent 다중 협력 제어를 위한 오케스트레이션 프레임워크 명확화 (Backend)

- **Current**: GCP Agent Engine & ADK 사용 위주.
- **Limitation**: 5개 에이전트(Orchestrator, AWS, GCP, TF Coder, QA)가 서로 피드백 루프를 돌며 상태를 교환하는 과정에서, 단순 코드나 기본 ADK만으로는 핑퐁(예: QA의 반려 후 재작성) 및 복잡한 상태 관리를 제어하기 매우 까다롭습니다.
- **Proposal**: 코어 로직에 **LangGraph (Python)** 프레임워크 도입을 강력히 권장합니다.
- **Rationale**: 멀티 에이전트 워크플로우를 사이클 기반(Cyclic) 그래프로 제어하는 데 있어 현재 LangGraph 및 Python 생태계가 가장 성숙해 있으며, 상태 추적 및 Time-travel 디버깅에 압도적으로 유리합니다.

### 2. 실시간 터미널 로그 스트리밍 구조 개선 (통신)

- **Current**: 샌드박스에서 Pub/Sub 로그 발행 -> BFF 수신 -> WebSocket을 통해 클라이언트 전시.
- **Limitation**: GKE K8s 환경에서 여러 Pod으로 구성된 Next.js BFF가 WebSocket 세션을 일관되게 유지하고 스케일링하려면 Redis Pub/Sub 백엔드가 강제되어 인프라 복잡도가 크게 단기 상승합니다.
- **Proposal**: **Server-Sent Events (SSE)**를 활용하거나, 샌드박스 워커가 실행 로그를 **Firestore**에 직접 기록하고 클라이언트(Next.js 브라우저)가 Firestore Snapshot Listener를 통해 직접 구독(직결)하는 방식(보안 룰 적용)을 제안합니다.
- **Rationale**: 훨씬 구현이 간결하며 GKE L7 LB 환경에서 스케일링 이슈 스트레스 없이 완벽한 실시간 터미널 UI 구현이 가능합니다.

### 3. 세션 및 상태 관리를 위한 데이터베이스 추가 (Persistence)

- **Current**: Memory Bank, BigQuery, GCS 구성 (트랜잭션/관계형 저장소 부재).
- **Limitation**: BigQuery는 Audit 용도이며 Memory Bank는 주로 임베딩/RAG 컨텍스트 용도입니다. 사용자의 세션 기록, 채팅/아키텍처 스키마의 수정 반복 기록(History)을 안정적으로 저장할 공간이 명시적이지 않습니다.
- **Proposal**: BFF/Agent의 공통 상태 저장소로 **Cloud SQL (PostgreSQL)** 또는 **Firestore**를 모노레포 설정에 추가 구성해야 합니다. (기본적으로 Firestore 권장)

### 4. Vertex AI Search 기반 RAG 파이프라인을 위한 산출물 Meta-data 및 Ingestion 설계

- **Current**: 샌드박스 산출물을 GCS 짚파일로 저장하고, 향후 Vertex AI Search에서 RAG 소스로 사용한다고만 명시됨.
- **Limitation**: 단순 압축 파일이나 구조화되지 않은 Terraform 코드 텍스트만 저장할 경우, RAG Retrieval 단계에서 컨텍스트(사용된 클라우드 벤더, 서비스, 아키텍처 목적)를 정확히 검색하고 추출하기 어렵습니다.
- **Proposal**: 산출물 생성 시, 해당 아키텍처의 의도와 태그 정보를 담은 **구조화된 메타데이터(JSON/Frontmatter, 예: `cloud: AWS`, `cost_tier: medium` 등)를 Terraform 코드 및 Markdown 가이드라인에 필수 주입**하도록 강제합니다.
- **Rationale**: 샌드박스 테스트 통과 직후 GCS 업로드와 동시에, 이 메타데이터를 기반으로 **Vertex AI Search Datastore API 구조에 맞게 청킹(Chunking) 및 인덱싱(Ingestion)을 자동 호출**하는 Event-Driven 파이프라인(또는 Agent 내부 명시적 호출)을 모노레포 아키텍처 구조의 핵심으로 추가해야 진정한 RAG 시스템으로 동작할 수 있습니다.

## Proposed Changes

승인 즉시 각 서브 엔진(Orchestration, BFF, K8s 매니페스트 등)의 스캐폴딩 구조를 병렬 생성할 예정입니다.

---

## Phase 10: Feedback Loop & UX Improvements (User Requests)

> [!CAUTION]
> 사용자가 요청한 7가지 개선 사항을 반영하기 위한 아키텍처 및 로직 변경 계획입니다.

### 1. Mermaid Fallback UI 보강

- `frontend/src/components/Mermaid.tsx`의 에러 핸들러를 수정하여, Syntax Error 발생 시 사용자가 직접 원본 다이어그램 코드를 볼 수 있도록 `<pre><code>` 블록에 Raw Code를 노출합니다.

### 2 & 3. Architecture Modification Feedback Loop

- **UI 추가**: 제안된 아키텍처 리뷰 화면 하단에 `추가/수정 요청사항` 입력란(텍스트에어리어)을 배치합니다.
- **로직 추가**: 사용자가 피드백을 적어 전송하면, 기존 `Requirement`에 피드백을 덧붙여 `/api/v1/phase1/design`으로 다시 전송하고, 재생성된 2차 아키텍처 결과를 UI에 다시 오버라이드합니다.

### 4 & 5. Terraform Code Preview & Testing Notification

- **UI 흐름 분리**: 기존 UI는 `Select` 버튼 클릭 시 바로 `IMPLEMENTING` 상태로 넘어가서 샌드박스를 실행(Mock)했습니다. 이를 `TERRAFORM_GENERATING` -> `TERRAFORM_PREVIEW` 단계로 세분화합니다.
- **로직 설계**: `backend`의 `/api/v1/phase2/implement`가 호출되면 샌드박스를 당장 실행하지 않고 생성된 Terraform 코드만 리턴합니다.
- **UI 추가**: 반환된 Terraform 코드를 코드블록 에디터 뷰어에 보여주고, 하단에 **"해당 코드로 샌드박스 보안/배포 테스트 실행하기"** 버튼을 제공합니다. 클릭 시 알림 메시지와 함께 샌드박스 실행으로 넘어갑니다.

### 6 & 7. Real Sandbox Execution Log & Auto-Correction Loop

- **Streaming API**: Backend에 새로운 `GET /api/v1/phase3/execute?tf_code=...` (SSE 기반) 엔드포인트를 만들어 실제 서버의 `subprocess`로 워커(terraform_executor) 로그를 스트리밍합니다 (기존 Mock 로그 대체).
- **Feedback Loop**: 스트리밍 로그 도중 Terraform 실행 에러(Exit Code != 0)를 감지하면, 백엔드 또는 프론트엔드가 오류가 포함된 로그 스트링을 `QA Validator` -> `TF Coder`에게 `qa_feedback` 필드에 담아 넘기고 코드를 재작성하는 자동 재시도 루프 로직을 구현합니다.

### 8. Gemini 3.0 Pro Thinking Process (`include_thoughts`) 연동

- **설정 추가**: `ChatGoogleGenerativeAI` 클라이언트 옵션에 `thinking_level="high"` 및 `include_thoughts=True` 파라미터를 명시적으로 넘깁니다. (또는 모델 스펙에 맞게 `thinking_config={...}`로 전달)
- **추출 로직**: LLM의 Raw 응답 메시지 내에서 `<thought>` 혹은 `parts` 배열 안의 Thinking 영역 텍스트를 파싱하여 별도의 필드 `thoughts`로 추출합니다.

- [x] 프론트엔드 리팩토링: `ChatInterface`에서 동기 호출 후 Loading 스피너를 도는 대신, 백엔드 스트리밍에 연결하여 LLM이 출력하는 "생각 과정 (Thoughts)"과 JSON 조각들을 실시간 타자 치듯 화면에 뿌려주는 Streaming Text Box / Accordion 컴포넌트를 UI에 추가합니다.

## Phase 11: Full GCP Production Service Integration (PRD Alignment)

> [!CAUTION]
> 사용자가 PRD에 명시된 모든 클라우드 서비스를 동작 상태로 만들고 로컬에서 통합 테스트할 수 있도록 강하게 지시했습니다. 이를 위해 현재 Mock되거나 Synchronous로 동작하는 요소들을 Production-Ready 비동기 GCP 툴킷으로 전면 교체합니다.

### 1. Vertex AI Memory Bank 연동 (Agent Engine)

- **위치**: `agent-backend/src/main.py` 및 Agent Nodes.
- **방식**: `vertexai.Client().agent_engines` 인터페이스를 사용하여, 사용자의 히스토리 및 선호도를 Memory Bank에 `generate_memories`로 기록하고, 다음 설계 요청 시 `retrieve_memories`로 가져와 LangGraph System Prompt에 컨텍스트로 주입합니다.

### 2. Async Messaging 파이프라인 (Pub/Sub)

- **위치**: Backend `execute` 엔드포인트 및 `sandbox-worker` 구동부.
- **Limitation**: 현재 백엔드 API에서 샌드박스의 Terraform 코드를 직접 Synchronous하게 실행하는 구조입니다.
- **Proposal**: 백엔드는 Pub/Sub 토픽(`sandbox-jobs`)에 실행 요청(JSON)만 Publish 하고 200 OK를 즉시 반환하도록 완전 비동기화합니다. `sandbox-worker/worker_app.py` 데몬을 신규 작성하여, Pub/Sub을 Pull (Subscriber) 하여 백그라운드로 TF 루프를 돌도록 분리합니다.

### 3. 실시간 분산 로깅 (Firestore)

- **위치**: `sandbox-worker/logger.py` 및 Backend `stream` 엔드포인트.
- **구현**: 워커 파일에 주석 처리된 Firestore 연결 코드를 해제합니다. 워커는 진행 상태를 Firestore Document에 `ArrayUnion`으로 기록하고, 프론트엔드용 BFF는 Firestore의 `on_snapshot` 리스너를 통해 변경분을 SSE 덩어리로 전달하도록 백엔드 라우터를 수정합니다.

### 4. 산출물 패키징 및 보관 (GCS & BigQuery)

- **위치**: `sandbox-worker` Terraform 실행 성공 분기.
- **구현**: 샌드박스가 성공적으로 실행된 후, 생성된 Terraform 코드를 `.zip`으로 압축하여 GCP Cloud Storage 버킷에 업로드합니다. 또한 수행 내역을 BigQuery Audit 테이블 템플릿에 로깅하는 코드를 삽입합니다.

### 5. RAG 소스 인덱싱 (Vertex AI Search)

- **위치**: 워커 종료 전.
- **구현**: GCS에 업로드 완료된 후, 메타데이터와 함께 `google-cloud-discoveryengine` 라이브러리를 통해 Vertex AI Search 데이터스토어에 Import 문서를 쏘는 로직을 추가합니다.
