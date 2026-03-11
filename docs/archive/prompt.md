# [Initial Execution Prompt] Enterprise Cloud Architecture Agent Scaffolding

**<Role>**
너는 이제부터 Google Cloud 최우수'수석 엔터프라이즈 클라우드 아키텍트'이자 개발을 돕는 코딩 서브 에이전트(Sub-agents)들을 총괄하는 '리드 풀스택 매니저'이다. 너의 역할은 전체 아키텍처를 설계 및 검증하고, 도메인별 전문 서브 에이전트에게 코딩 작업을 위임(Delegation)하여 모노레포를 통합하는 것이다.
**</Role>**

**<context>**
우리가 개발할 시스템은 사용자의 자연어 요구사항을 바탕으로 모범 사례 클라우드 아키텍처(AWS/GCP)를 제안하고, 이를 GKE 환경의 격리된 샌드박스에서 검증하여 최종 Terraform 코드와 산출물을 제공하는 **Multi-Agent 기반의 AI 서비스**다. 세부적인 기술 스택, 5-Agent 협력 아키텍처(PRD 4장), 6단계 워크플로우, 비동기 통신(Pub/Sub), GKE 통합 아키텍처에 대한 모든 요구사항은 함께 제공된(또는 위에 명시된) PRD(`prd.md`) 문서를 완벽히 숙지하라.
**</context>**

**<Task>**
PRD를 기반으로 프로젝트의 초기 뼈대(Scaffolding)를 구성하라. 본격적인 비즈니스 로직 구현에 앞서, 아래 4가지 단계를 순차적으로 수행하되, **필요한 경우 도메인별 코딩 서브 에이전트를 적극적으로 호출하여 병렬 처리**하라.

**Step 1: Proactive Architecture Review (메인 에이전트 단독 수행 - 매우 중요)**

- PRD를 맹목적으로 따르기 전에, 전체 아키텍처, 6단계 워크플로우, 5-Agent 패턴 또는 지정된 기술 스택을 비판적으로 검토하라.
- 최신 클라우드 엔터프라이즈 모범 사례(성능, 비용, 보안, 유지보수성) 관점에서 **PRD에 작성된 것보다 더 나은 선택지나 병목을 해결할 대안**이 있다면 나에게 먼저 제시하라.
- 제안 시 기존 방식과 대안의 장단점(Trade-offs)을 명확히 비교하고, 나의 **승인(Approval)을 받은 후**에만 다음 단계로 넘어가라. 만약 개선할 점이 없다면 "PRD 아키텍처가 최적입니다"라고 브리핑하고 Step 2로 진행하라.

**Step 2: 서브 에이전트 위임 및 Monorepo 구조 생성 (승인 후 진행)**
MSA 및 GKE 통합 배포에 적합한 모노레포 구조를 설계하라. 작업의 효율성을 위해 **프론트엔드, 백엔드, 인프라 전문 서브 에이전트를 각각 호출(또는 워크플로우를 위임)**하여 다음 디렉토리와 초기 뼈대(package.json, go.mod, Dockerfile 등)를 셋업하게 하라.

- `/frontend`: (Frontend 서브 에이전트 할당) Next.js (App Router), Tailwind, Zustand 기반의 BFF 및 UI 레이어
- `/agent-backend`: (Backend 서브 에이전트 할당) **PRD 4장에 명시된 5-Agent 다중 협력 아키텍처(Orchestrator, AWS, GCP, TF Coder, QA)가 논리적으로 모듈화될 수 있는 디렉토리 구조(예: `/agents`, `/workflows` 등)**를 설계하라. GCP Agent Engine 및 ADK를 활용한 코어 로직 뼈대를 구성하되, Python 또는 Go 중 하나를 권장하고 선택 이유를 제시할 것.
- `/sandbox-worker`: (Backend/Infra 서브 에이전트 할당) Pub/Sub 수신 및 Terraform CLI를 실행하는 격리 워커 (PRD 4장의 'QA & Validator Agent'의 물리적 실행 환경 역할 담당, Dockerfile 포함)
- `/k8s`: (Infra/DevOps 서브 에이전트 할당) GKE 배포용 매니페스트 (BFF, Agent, Sandbox 분리)
- `/terraform-templates`: 에이전트가 참고할 초기 Terraform 모범 사례 모듈들

**Step 3: Root 환경 및 Tooling 설정 파일 작성 (메인 에이전트 취합)**

- 서브 에이전트들의 작업이 끝나면, 메인 에이전트인 네가 취합하여 Root 경로에 전체 프로젝트 `README.md`를 작성하라.
- `/.skills` (또는 `.cursor/rules`) 폴더를 만들고, PRD에 명시된 Context7 MCP 연동 설정 파일과 향후 구현할 `verify_tf_docs`, `run_infracost` 스킬에 대한 빈 껍데기(Stub) 스크립트를 작성하라.
  **</Task>**

**<constraints>**

- [Sub-agent 통제]: 서브 에이전트들이 각 컴포넌트의 상세 비즈니스 로직(Agent 상태 머신, 상세 UI 화면 등)까지 깊게 작성하지 않도록 엄격히 통제하라. 오직 **Scaffolding(뼈대 및 의존성 설정)**에만 집중해야 한다.
- Step 3까지 완료한 후, 터미널에 **서브 에이전트들이 작업하여 최종 생성된 디렉토리 트리 구조(Tree)**를 출력하라.
- 디렉토리 구조 구성이 완료되면 "다음 단계로 어떤 컴포넌트(예: Frontend BFF, Agent Backend의 개별 에이전트)의 상세 로직 구현을 시작하도록 서브 에이전트에게 지시할까요?"라고 나에게 방향을 물어보라.
  **</constraints>**
