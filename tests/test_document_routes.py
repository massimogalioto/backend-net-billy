import unittest

import main
from fastapi import FastAPI
from fastapi.testclient import TestClient
from upload_pdf import router as upload_router


class DocumentRouteTests(unittest.TestCase):
    def test_only_pdf_document_extraction_routes_are_active(self):
        paths = {route.path for route in main.app.routes if hasattr(route, "path")}
        for included in (route for route in main.app.routes if hasattr(route, "original_router")):
            paths.update(route.path for route in included.original_router.routes if hasattr(route, "path"))
        self.assertIn("/upload-cte", paths)
        self.assertIn("/upload-bolletta", paths)
        self.assertNotIn("/analizza-cte", paths)
        self.assertNotIn("/analizza-bolletta", paths)
        self.assertNotIn("/estrai-testo-pdf", paths)

    def test_pdf_document_routes_require_authenticated_session(self):
        app = FastAPI()
        app.include_router(upload_router)
        client = TestClient(app)
        for path in ("/upload-cte", "/upload-bolletta"):
            with self.subTest(path=path):
                response = client.post(path, files={"file": ("document.pdf", b"%PDF-test", "application/pdf")})
                self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
