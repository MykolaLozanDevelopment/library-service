from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from books.models import Book

LIST_URL = reverse("books:book-list")

PAYLOAD = {
    "title": "Emma",
    "author": "Jane Austen",
    "cover": "SOFT",
    "inventory": 3,
    "daily_fee": "0.99",
}


def detail_url(book_id):
    return reverse("books:book-detail", args=[book_id])


def sample_book(**params):
    defaults = {
        "title": "Dune",
        "author": "Frank Herbert",
        "cover": "HARD",
        "inventory": 5,
        "daily_fee": "1.50",
    }
    defaults.update(params)
    return Book.objects.create(**defaults)


class BookModelTests(TestCase):
    def test_str(self):
        book = sample_book()
        self.assertEqual(str(book), "Dune (Frank Herbert)")


class PublicBookApiTests(TestCase):
    """Unauthenticated users: read-only access."""

    def setUp(self):
        self.client = APIClient()

    def test_list_books_allowed(self):
        sample_book(title="Dune")
        sample_book(title="Emma", author="Jane Austen")
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_retrieve_book_allowed(self):
        book = sample_book()
        response = self.client.get(detail_url(book.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Dune")

    def test_create_book_unauthorized(self):
        response = self.client.post(LIST_URL, PAYLOAD)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Book.objects.count(), 0)

    def test_update_book_unauthorized(self):
        book = sample_book()
        response = self.client.patch(detail_url(book.id), {"inventory": 10})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_delete_book_unauthorized(self):
        book = sample_book()
        response = self.client.delete(detail_url(book.id))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(Book.objects.filter(id=book.id).exists())


class UserBookApiTests(TestCase):
    """Authenticated non-admin users: read-only access."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="user@example.com", password="pass12345"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_list_books_allowed(self):
        sample_book()
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_book_forbidden(self):
        response = self.client.post(LIST_URL, PAYLOAD)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Book.objects.count(), 0)

    def test_update_book_forbidden(self):
        book = sample_book()
        response = self.client.patch(detail_url(book.id), {"inventory": 10})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        book.refresh_from_db()
        self.assertEqual(book.inventory, 5)

    def test_delete_book_forbidden(self):
        book = sample_book()
        response = self.client.delete(detail_url(book.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Book.objects.filter(id=book.id).exists())


class AdminBookApiTests(TestCase):
    """Admin users: full CRUD access."""

    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            email="admin@example.com", password="pass12345"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_create_book(self):
        response = self.client.post(LIST_URL, PAYLOAD)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Book.objects.count(), 1)

    def test_update_book_inventory(self):
        book = sample_book()
        response = self.client.patch(detail_url(book.id), {"inventory": 10})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        book.refresh_from_db()
        self.assertEqual(book.inventory, 10)

    def test_delete_book(self):
        book = sample_book()
        response = self.client.delete(detail_url(book.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Book.objects.filter(id=book.id).exists())

    def test_invalid_cover_rejected(self):
        response = self.client.post(LIST_URL, {**PAYLOAD, "cover": "PAPER"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_negative_inventory_rejected(self):
        response = self.client.post(LIST_URL, {**PAYLOAD, "inventory": -1})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
