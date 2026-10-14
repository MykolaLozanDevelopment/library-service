from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from books.models import Book

LIST_URL = reverse("books:book-list")


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


class BookApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_create_book(self):
        payload = {
            "title": "Emma",
            "author": "Jane Austen",
            "cover": "SOFT",
            "inventory": 3,
            "daily_fee": "0.99",
        }
        response = self.client.post(LIST_URL, payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Book.objects.count(), 1)

    def test_list_books(self):
        sample_book(title="Dune")
        sample_book(title="Emma", author="Jane Austen")
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_retrieve_book(self):
        book = sample_book()
        response = self.client.get(detail_url(book.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Dune")

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
        response = self.client.post(
            LIST_URL,
            {
                "title": "X",
                "author": "Y",
                "cover": "PAPER",
                "inventory": 1,
                "daily_fee": "1.00",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_negative_inventory_rejected(self):
        response = self.client.post(
            LIST_URL,
            {
                "title": "X",
                "author": "Y",
                "cover": "HARD",
                "inventory": -1,
                "daily_fee": "1.00",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
