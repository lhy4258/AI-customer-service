import unittest

from fastapi.testclient import TestClient

from app.api.deps import get_customer_service
from app.main import create_app
from app.services.demo_data import build_demo_service


class KnowledgeApiTests(unittest.TestCase):
    def setUp(self):
        self.service = build_demo_service()
        self.service.embedding_client.embed = lambda _text: None
        self.app = create_app()
        self.app.dependency_overrides[get_customer_service] = lambda: self.service
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_upload_knowledge_document_and_list_documents(self):
        response = self.client.post(
            "/api/v1/customer-service/admin/knowledge/upload",
            json={
                "file_name": "train-sample.txt",
                "source": "support-upload",
                "content": "1\t买 二份 有没有 少点 呀\t亲亲 已经 是 优惠价 了 呢\n",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["file_name"], "train-sample.txt")
        self.assertEqual(payload["status"], "processing")
        self.assertEqual(payload["chunk_count"], 0)

        documents = self.client.get("/api/v1/customer-service/admin/knowledge/documents").json()
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["file_name"], "train-sample.txt")
        self.assertEqual(documents[0]["status"], "ready")
        self.assertEqual(documents[0]["chunk_count"], 1)

    def test_cancel_processing_document_before_delete(self):
        document = self.service.create_knowledge_document("slow.txt", "support-upload")

        cancel_response = self.client.post(f"/api/v1/customer-service/admin/knowledge/documents/{document.id}/cancel")

        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.json()["status"], "canceled")

        delete_response = self.client.delete(f"/api/v1/customer-service/admin/knowledge/documents/{document.id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(self.service.list_knowledge_documents(), [])


if __name__ == "__main__":
    unittest.main()
