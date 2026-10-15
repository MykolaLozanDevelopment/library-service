from django.test import TestCase
from django.urls import reverse


class ApiDocsTests(TestCase):
    def get_schema(self):
        response = self.client.get(reverse("schema"), {"format": "json"})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_swagger_ui_available(self):
        response = self.client.get(reverse("swagger-ui"))
        self.assertEqual(response.status_code, 200)

    def test_redoc_available(self):
        response = self.client.get(reverse("redoc"))
        self.assertEqual(response.status_code, 200)

    def test_schema_contains_all_services(self):
        paths = self.get_schema()["paths"]
        for expected in (
            "/users/",
            "/users/token/",
            "/users/token/refresh/",
            "/users/me/",
            "/books/",
            "/books/{id}/",
            "/borrowings/",
            "/borrowings/{id}/",
            "/borrowings/{id}/return/",
        ):
            self.assertIn(expected, paths)

    def test_schema_documents_borrowing_filters(self):
        paths = self.get_schema()["paths"]
        params = {
            p["name"] for p in paths["/borrowings/"]["get"]["parameters"]
            }
        self.assertIn("is_active", params)
        self.assertIn("user_id", params)

    def test_schema_describes_return_endpoint(self):
        paths = self.get_schema()["paths"]
        operation = paths["/borrowings/{id}/return/"]["post"]
        self.assertEqual(operation["summary"], "Return a borrowing")

    def test_schema_describes_authentication(self):
        schema = self.get_schema()
        self.assertTrue(schema["components"]["securitySchemes"])
