<role>
너는 에이전트 및 클라우드 아키텍처 설계 및 개발 전문가
</role>

<context>
- 사용자가 특정 목적의 서비스를 위하여 클라우드 아키텍처 설계 및 해당 클라우드 아키텍처 배포 코드(terraform)를 요청하면,
- 에이전트는 이 요청을 입수하여 gcp 아키텍처 모범 사례에 맞춰 아키텍처를 구성 설계를 제안하고 이를 배포하는 terraform 코드를 제공한다.
- 이 terraform 코드는, 사용자에게 제공되기전 에이전트가 미리 샌드박스 환경에서 배포를 실험, 문제 없이 동작함을 사전에 테스트 완료 해야하며, 사용자가 이 코드 사용시 에러나 문제 없이 정상적으로 동작해야만 한다.
- 사용자와 agent 간 interfactions은 자연어 대화로 이루어지며 이를 위한 인터페이스 UI를 제공한다
- 사용자가 원하는 아키텍처를 설계하기 위한 대화 과정에서, 사용자가 놓치고 있는 보안, 비용, 성능, 운영, 확장성, 가용성, 재해복구, 규정 준수, 데이터 프라이버시, 모니터링, 로깅, 알림, 자동화, CI/CD, 테스트, 문서화, 교육, 지원 등 엔터프라이즈 클라우드 아키텍처 관점에서 필요한 모든 사항들을 에이전트가 짚어주고, 사용자의 요구사항을 반영하여 최적의 아키텍처를 설계하도록 돕는다.
- 사용자가 비교 선택할 수 있도록 클라우드 제공자는 aws, gcp에 한정하며 각각 모두 클라우드 제공자의 모범 사례에 맞춰 아키텍처를 구성 설계를 제안하고 이를 배포하는 terraform 코드를 제공한다.
- 에이전트의 최종 결과물은:
  - terraform code
  - 아키텍처 다이어그램
  - 비용 예측
  - 보안 점검
  - 성능 예측
  - 배포 가이드
  - 운영 가이드
  - 테스트 가이드
  - 문서화
  - 교육 자료
- 사용자가 최종 Accept하면 에이전트의 최종 결과물은 사용자가 다운로드 받을 수 있도록 제공되어야 한다.
- 에이전트의 결과물은 GCS cloud storage와 big query에 저장되어야 한다. 향후 이 데이터는 vertex ai search를 통해 저장/인덱싱되어 모범 사례 아키텍처로 재활용 될수 있도록 한다.
- 사용자의 인터랙선 context 및 session 정보는 적절한 데이터스토리지를 선택하여 저장하며 유실이 없도록 한다. 또한 이 데이터는 보안 및 규정 준수를 위해 적절한 접근 제어 및 암호화가 적용되어야 한다.
- 에이전트는 개발 stack
  - agent dev framework
    - adk
  - agent backend
    - gcp agent engine
  - agent long-term memory
    - gcp memory banck
  - agent output assets storage
    - google cloud storage
  - user interactions logging
    - big query
  -  asset search
    - vertex ai search
</context>

<task>
- 이상의 에이전트를 claude code 또는 antigravity에게 개발을 요청하기 위한 탄탄한 PRD 문서를 작성하라 
- 이 에이전트 개발시 고려해야 하는 중요한 사항들이 모두 담겨 있어야 하며 모범 사례 엔터프라이즈 서비스 아키텍처 관점에서 필요한 모든 것들을 포함할 것
</task>

<instructions>
1. brain storming
  - PRD 문서에 포함되어야 하는 내용들을 브레인스토밍 할것
  - 사용자 입력한 요구사항 뿐 아니라 엔터프라이즈 클라우드 아키텍처 관점에서 필요한, 사용자가 놓치고 있는 부분까지 모두 포함할 것
2. initial forward analysis
  - Think step by step  and don't suggest the answer at this stage
3. backward analysis
  - after initial forward analysis, workbackward the end to come up with the answer
4. final answer
  - after backward analysis, suggest the answer
</instructions>
