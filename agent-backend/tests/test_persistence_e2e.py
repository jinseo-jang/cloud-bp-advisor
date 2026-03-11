import unittest
from google.cloud import firestore
import uuid
import sys
import os

# Ensure src modules can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.memory import MemoryBank

class TestPersistenceE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.db = firestore.Client(database="cloud-bp-db")
        except Exception as e:
            raise unittest.SkipTest(f"Skipping tests because Firestore initialization failed: {e}")
            
        cls.test_user_id = f"test_user_e2e_{uuid.uuid4().hex[:8]}"
        cls.test_thread_id = f"test_thread_e2e_{uuid.uuid4().hex[:8]}"
        
    def test_01_memory_bank_operations(self):
        print(f"\\n[Test 1] Testing Vertex AI Agent Engine Memory Bank for user: {self.test_user_id}")
        
        # 1. Initialize
        mb = MemoryBank(user_id=self.test_user_id)
        
        # 2. Assert initial empty or default state
        initial_mem = mb.retrieve_memories()
        self.assertIn("secure, highly-available", initial_mem, "Initial memory should return the fallback message if not found")
        
        # 3. Generate a new context
        test_context = "User requires test_driven_development compliance in all architectures."
        mb.generate_memories(test_context)
        
        # 4. Give Vertex AI a brief moment
        import time
        time.sleep(3.0)
        
        # 5. Retrieve again, should include the new context
        updated_mem = mb.retrieve_memories()
        self.assertIn(test_context, updated_mem, "The newly generated context must be retrieved from Vertex Agent Engine Memory Bank")
        print("✅ Vertex AI MemoryBank integration test passed.")

    def test_02_chat_session_storage(self):
        print(f"\\n[Test 2] Testing Chat Session Persistence (Firestore cloud-bp-db) for thread: {self.test_thread_id}")
        
        # Streamlit append replication logic
        test_title = "E2E Automated Design Request"
        test_messages = [
            {"role": "user", "content": "I want a scalable architecture mock."},
            {"role": "assistant", "content": "Mock Architecture provided.", "type": "final_failed_code"}
        ]
        
        try:
            doc_ref = self.db.collection(u'chat_sessions').document(self.test_thread_id)
            doc_ref.set({
                u'title': test_title,
                u'messages': test_messages
            }, merge=True)
        except Exception as e:
            self.fail(f"Failed to write chat session to Firestore: {e}")
            
        # Give Firestore a brief moment to process
        import time
        time.sleep(1.0)
        
        # Attempt to load it back
        try:
            read_doc = self.db.collection(u'chat_sessions').document(self.test_thread_id).get()
            self.assertTrue(read_doc.exists, "The written chat session document must exist")
            
            data = read_doc.to_dict()
            self.assertEqual(data.get("title"), test_title, "Title should match")
            
            read_messages = data.get("messages", [])
            self.assertEqual(len(read_messages), 2, "Should have 2 messages")
            self.assertEqual(read_messages[0]["content"], "I want a scalable architecture mock.")
            
            print("✅ Chat Session (Firestore logic) integration test passed.")
        except Exception as e:
            self.fail(f"Failed to read chat session from Firestore: {e}")

    @classmethod
    def tearDownClass(cls):
        print("\\n[Clean Up] Removing mock data...")
        # 1. Clean Memory Bank (Try best-effort deletion if client allows)
        try:
            mb = MemoryBank(user_id=cls.test_user_id)
            if getattr(mb, 'client', None) and getattr(mb, 'agent_engine_name', None):
                memories = mb.client.agent_engines.memories.retrieve(
                    name=mb.agent_engine_name,
                    scope={"user_id": cls.test_user_id},
                    simple_retrieval_params={}
                )
                for mem in memories:
                    # Attempt to delete the specific memory object
                    if hasattr(mem, 'name'):
                        mb.client.agent_engines.memories.delete(name=mem.name)
            print(f"Cleaned MemoryBank docs for: {cls.test_user_id}")
        except Exception as e:
            print(f"Warning: Failed to cleanup Vertex AI MemoryBank doc: {e}. (This is non-critical)")
            
        # 2. Clean Chat Session
        try:
            cls.db.collection(u'chat_sessions').document(cls.test_thread_id).delete()
            print(f"Deleted Chat Session doc: {cls.test_thread_id}")
        except Exception as e:
            print(f"Warning: Failed to cleanup Firestore Chat Session doc: {e}")

if __name__ == '__main__':
    unittest.main()
