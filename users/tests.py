from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

CREATE_USER_URL = reverse("users:create")
TOKEN_URL = reverse("users:token_obtain_pair")
ME_URL = reverse("users:manage")

PAYLOAD = {
    "email": "test@example.com",
    "password": "testpass123",
    "first_name": "Test",
    "last_name": "User",
}


class UserManagerTests(TestCase):
    def test_create_user(self):
        user = get_user_model().objects.create_user(
            email="user@example.com", password="pass12345"
        )
        self.assertEqual(user.email, "user@example.com")
        self.assertTrue(user.check_password("pass12345"))
        self.assertFalse(user.is_staff)

    def test_create_user_without_email_raises(self):
        with self.assertRaises(ValueError):
            get_user_model().objects.create_user(email="", password="pass")

    def test_create_superuser(self):
        admin = get_user_model().objects.create_superuser(
            email="admin@example.com", password="pass12345"
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)


class PublicUserApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_user(self):
        response = self.client.post(CREATE_USER_URL, PAYLOAD)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("password", response.data)
        user = get_user_model().objects.get(email=PAYLOAD["email"])
        self.assertTrue(user.check_password(PAYLOAD["password"]))

    def test_register_cannot_set_is_staff(self):
        response = self.client.post(
            CREATE_USER_URL, {**PAYLOAD, "is_staff": True}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = get_user_model().objects.get(email=PAYLOAD["email"])
        self.assertFalse(user.is_staff)

    def test_register_duplicate_email_fails(self):
        get_user_model().objects.create_user(
            email=PAYLOAD["email"], password="pass12345"
        )
        response = self.client.post(CREATE_USER_URL, PAYLOAD)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_obtain_token(self):
        get_user_model().objects.create_user(
            email=PAYLOAD["email"], password=PAYLOAD["password"]
        )
        response = self.client.post(
            TOKEN_URL,
            {"email": PAYLOAD["email"], "password": PAYLOAD["password"]},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_obtain_token_wrong_password(self):
        get_user_model().objects.create_user(
            email=PAYLOAD["email"], password=PAYLOAD["password"]
        )
        response = self.client.post(
            TOKEN_URL, {"email": PAYLOAD["email"], "password": "wrong"}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_requires_authentication(self):
        response = self.client.get(ME_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authorize_header_is_used_for_jwt(self):
        get_user_model().objects.create_user(
            email=PAYLOAD["email"], password=PAYLOAD["password"]
        )
        token = self.client.post(
            TOKEN_URL,
            {"email": PAYLOAD["email"], "password": PAYLOAD["password"]},
        ).data["access"]

        ok = self.client.get(ME_URL, HTTP_AUTHORIZE=f"Bearer {token}")
        self.assertEqual(ok.status_code, status.HTTP_200_OK)

        default_header = self.client.get(
            ME_URL, HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        self.assertEqual(
            default_header.status_code, status.HTTP_401_UNAUTHORIZED
        )


class PrivateUserApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="me@example.com",
            password="pass12345",
            first_name="Me",
            last_name="Myself",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_retrieve_profile(self):
        response = self.client.get(ME_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "me@example.com")
        self.assertNotIn("password", response.data)

    def test_update_profile(self):
        response = self.client.patch(ME_URL, {"first_name": "New"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "New")

    def test_update_password_is_hashed(self):
        response = self.client.patch(ME_URL, {"password": "newpass123"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newpass123"))

    def test_cannot_make_self_staff(self):
        self.client.patch(ME_URL, {"is_staff": True})
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)
