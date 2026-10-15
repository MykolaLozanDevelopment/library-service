from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from books.models import Book
from borrowings.models import Borrowing

LIST_URL = reverse("borrowings:borrowing-list")


def detail_url(borrowing_id):
    return reverse("borrowings:borrowing-detail", args=[borrowing_id])


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


def sample_user(email="user@example.com"):
    return get_user_model().objects.create_user(
        email=email, password="pass12345"
    )


def sample_borrowing(user, book, **params):
    defaults = {
        "borrow_date": date(2026, 10, 1),
        "expected_return_date": date(2026, 10, 8),
        "user": user,
        "book": book,
    }
    defaults.update(params)
    return Borrowing.objects.create(**defaults)


class BorrowingModelTests(TestCase):
    def setUp(self):
        self.user = sample_user()
        self.book = sample_book()

    def test_str(self):
        borrowing = sample_borrowing(self.user, self.book)
        self.assertEqual(
            str(borrowing), "Dune borrowed by user@example.com"
        )

    def test_expected_return_must_be_after_borrow_date(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                sample_borrowing(
                    self.user,
                    self.book,
                    borrow_date=date(2026, 10, 10),
                    expected_return_date=date(2026, 10, 10),
                )

    def test_actual_return_cannot_be_before_borrow_date(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                sample_borrowing(
                    self.user,
                    self.book,
                    actual_return_date=date(2026, 9, 30),
                )

    def test_actual_return_date_is_optional(self):
        borrowing = sample_borrowing(self.user, self.book)
        self.assertIsNone(borrowing.actual_return_date)


class BorrowingApiTests(TestCase):
    def setUp(self):
        self.user = sample_user()
        self.book = sample_book()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_list_borrowings(self):
        sample_borrowing(self.user, self.book)
        sample_borrowing(
            self.user,
            self.book,
            borrow_date=date(2026, 10, 5),
            expected_return_date=date(2026, 10, 12),
        )
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_list_contains_detailed_book_info(self):
        sample_borrowing(self.user, self.book)
        response = self.client.get(LIST_URL)
        book_data = response.data[0]["book"]
        self.assertEqual(book_data["title"], "Dune")
        self.assertEqual(book_data["author"], "Frank Herbert")
        self.assertEqual(book_data["cover"], "HARD")
        self.assertEqual(book_data["daily_fee"], "1.50")

    def test_retrieve_borrowing(self):
        borrowing = sample_borrowing(self.user, self.book)
        response = self.client.get(detail_url(borrowing.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], borrowing.id)
        self.assertEqual(response.data["user"], self.user.id)
        self.assertEqual(response.data["book"]["title"], "Dune")
        self.assertIsNone(response.data["actual_return_date"])

    def test_retrieve_missing_borrowing_returns_404(self):
        response = self.client.get(detail_url(999))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_not_allowed_on_list_endpoint(self):
        response = self.client.post(LIST_URL, {})
        self.assertEqual(
            response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
