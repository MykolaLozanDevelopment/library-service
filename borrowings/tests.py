from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
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


def create_payload(book, days=7):
    return_date = timezone.localdate() + timedelta(days=days)
    return {
        "book": book.id,
        "expected_return_date": return_date.isoformat(),
    }


class UnauthenticatedBorrowingApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_list_requires_authentication(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_requires_authentication(self):
        book = sample_book()
        response = self.client.post(LIST_URL, create_payload(book))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Borrowing.objects.count(), 0)


class CreateBorrowingTests(TestCase):
    def setUp(self):
        self.user = sample_user()
        self.book = sample_book(inventory=2)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_create_borrowing(self):
        response = self.client.post(LIST_URL, create_payload(self.book))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        borrowing = Borrowing.objects.get()
        self.assertEqual(borrowing.book, self.book)
        self.assertEqual(borrowing.borrow_date, timezone.localdate())
        self.assertIsNone(borrowing.actual_return_date)

    def test_create_decreases_inventory(self):
        self.client.post(LIST_URL, create_payload(self.book))
        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 1)

    def test_create_attaches_current_user(self):
        other = sample_user("other@example.com")
        payload = {**create_payload(self.book), "user": other.id}
        response = self.client.post(LIST_URL, payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Borrowing.objects.get().user, self.user)

    def test_create_with_zero_inventory_rejected(self):
        book = sample_book(title="Emma", inventory=0)
        response = self.client.post(LIST_URL, create_payload(book))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Borrowing.objects.count(), 0)
        book.refresh_from_db()
        self.assertEqual(book.inventory, 0)

    def test_last_copy_cannot_be_borrowed_twice(self):
        book = sample_book(title="Emma", inventory=1)
        first = self.client.post(LIST_URL, create_payload(book))
        second = self.client.post(LIST_URL, create_payload(book))
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        book.refresh_from_db()
        self.assertEqual(book.inventory, 0)
        self.assertEqual(Borrowing.objects.count(), 1)

    def test_expected_return_date_today_rejected(self):
        response = self.client.post(
            LIST_URL, create_payload(self.book, days=0)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Borrowing.objects.count(), 0)

    def test_expected_return_date_in_past_rejected(self):
        response = self.client.post(
            LIST_URL, create_payload(self.book, days=-1)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 2)

    def test_nonexistent_book_rejected(self):
        payload = {**create_payload(self.book), "book": 999}
        response = self.client.post(LIST_URL, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_fields_rejected(self):
        response = self.client.post(LIST_URL, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
