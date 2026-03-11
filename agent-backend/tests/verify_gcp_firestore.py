#!/usr/bin/env python3
import json
from google.cloud import firestore
import uuid

def main():
    print("🚀 [GCP Level Verification] Native Firestore (cloud-bp-db) 연동 라이브 테스트를 시작합니다.")
    
    # 1. Initialize Firestore Client targeting specific database
    project_id = "duper-project-1"
    database_id = "cloud-bp-db"
    try:
        db = firestore.Client(project=project_id, database=database_id)
        print(f"✅ GCP 연결 성공 (Project: {project_id}, Database: {database_id})")
    except Exception as e:
        print(f"❌ GCP 인증/연결 실패: {e}")
        return
        
    # 2. 고유 스레드 ID 생성
    thread_id = f"live_verification_{uuid.uuid4().hex[:8]}"
    
    # 3. Streamlit 앱에서 사용하는 것과 완벽히 동일한 데이터
    test_title = "[E2E 검증용] 실시간 클라우드 아키텍처 상담 (Native Firestore)"
    test_messages = [
        {"role": "user", "content": "안녕하세요! GCP Firestore의 네이티브 데이터베이스 저장 확인용 테스트입니다."},
        {"role": "assistant", "content": "네, 성공적으로 특정된 클라우드 데이터베이스에 영구 저장될 예정입니다. 나중에 콘솔에서 확인해보세요!"}
    ]
    
    print(f"\n📝 다음 데이터를 Firestore의 [chat_sessions] Collection에 저장합니다:")
    print(f"  - Document ID (Name): {thread_id}")
    print(f"  - Title: {test_title}")
    
    # 4. 데이터 쓰기 (Save to GCP Firestore)
    try:
        doc_ref = db.collection(u'chat_sessions').document(thread_id)
        doc_ref.set({
            u'title': test_title,
            u'messages': test_messages
        }, merge=True)
        print("✅ 데이터베이스 쓰기 성공!")
    except Exception as e:
        print(f"❌ 데이터베이스 쓰기 실패: {e}")
        return

    # 5. GCP Console에서 바로 확인할 수 있는 가이드 출력
    print("\n=======================================================")
    print("🎉 [GCP Cloud 콘솔에서 데이터 확인하기]")
    print(f"1. 브라우저에서 아래 링크로 변경된 저장 상태를 직접 확인해보세요:")
    print(f"   👉 https://console.cloud.google.com/firestore/databases/{database_id}/data/panel/chat_sessions/{thread_id}?project={project_id}")
    
    print("\n   (참고: 기존 E2E 단위 테스트 코드에서는 테스트 직후 tearDown() 블록에서")
    print("          임시 데이터를 자동 삭제(Clean-up)하도록 설계되어 있어")
    print("          콘솔에서 잔류 흔적을 육안으로 확인하기 어려웠습니다.")
    print("          이 스크립트는 영구 보존 모드로 작성하여 바로 직접 조회가 가능합니다.)")
    print("=======================================================\n")
    
    # 6. (검증용) 방금 저장한 데이터를 다시 Fetch
    try:
        read_doc = db.collection(u'chat_sessions').document(thread_id).get()
        if read_doc.exists:
            print("🔍 [시스템 교차 검증]: 저장된 데이터를 Fetch 해 온 결과:")
            print(json.dumps(read_doc.to_dict(), indent=2, ensure_ascii=False))
        else:
            print("⚠️ 문서를 찾을 수 없습니다.")
    except Exception as e:
        print(f"❌ Fetch 에러 발생: {e}")

if __name__ == '__main__':
    main()
