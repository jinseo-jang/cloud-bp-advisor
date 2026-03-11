# Cloud BP Advisor - Testing & Debugging Guide

이 문서는 Streamlit 기반 백엔드와 GKE 샌드박스 워커로 구성된 Cloud BP Advisor 시스템의 테스트 및 디버깅 가이드입니다.

## 1. Local Testing (Backend & UI)

로컬에서 에이전트 로직과 Streamlit UI를 테스트하는 방법입니다.

### 1.1. 환경 설정
GCP 인증 및 시크릿 설정을 확인합니다.
```bash
gcloud auth application-default login
```
`.env` 파일에 `GOOGLE_CLOUD_PROJECT`, `GCP_PROJECT_ID` 등이 올바르게 설정되어야 합니다.

### 1.2. Streamlit UI 실행
`agent-backend` 디렉토리에서 UI를 실행합니다.
```bash
cd agent-backend
uv pip install -r requirements.txt
uv run streamlit run streamlit_app.py
```
접속 주소: `http://localhost:8501`

---

## 2. Sandbox Worker Testing

샌드박스 워커는 GKE에서 동작하지만, 로컬에서도 메시지 처리를 테스트할 수 있습니다.

### 2.1. 로컬 워커 구동
GKE에 배포하기 전 워커 로직(`worker_app.py`)을 로컬에서 실행하여 Pub/Sub 메시지 수신을 확인합니다.
```bash
cd sandbox-worker
uv pip install -r requirements.txt
export GOOGLE_CLOUD_PROJECT="your-project-id"
python src/worker_app.py
```

### 2.2. GKE 샌드박스 로그 확인
배포된 워커의 동작 상태와 하트비트를 확인합니다.
```bash
kubectl logs -f -l app=sandbox-worker -n cloud-bp-advisor
```

### 2.3. Fast-track 재배포
워커 코드(REST API 연동 등) 수정 후 빠르게 GKE에 반영할 때 사용합니다.
```bash
chmod +x ./scripts/deploy_sandbox.sh
./scripts/deploy_sandbox.sh
```

---

## 3. Automated E2E Testing

시스템의 전체적인 헬스체크를 위해 제공되는 스크립트입니다. GKE 워커와 Cloud Run 백엔드의 가용성을 점검합니다.

```bash
chmod +x tests/e2e_test.sh
./tests/e2e_test.sh
```

---

## 4. Troubleshooting (디버깅 팁)

### 3.1. REST vs gRPC (gVisor 환경)
GKE Sandbox(gVisor) 환경에서는 gRPC 통신이 불안정할 수 있습니다. 샌드박스 내부 통신이 끊긴다면 `worker_app.py`와 `logger.py`가 **REST(HTTP/1.1)** 방식으로 동작하는지 확인하십시오.

### 3.2. Firestore 로그 누락
`logger.py`의 `stream_log` 함수에서 Firestore REST API 호출 시 400 에러가 발생한다면, URL 엔드포인트가 특정 문서가 아닌 `documents:commit` 레벨인지 확인하십시오.

### 3.3. API Quota (Gemini)
에이전트 호출이 잦을 경우 Gemini API Quota 에러가 발생할 수 있습니다. `async_stream.py`의 딜레이 설정을 조정하거나 할당량을 확인하십시오.
