from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from books.models import Book
from borrowings.messages import build_borrowing_message
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
        patcher = patch("borrowings.views.send_telegram_message")
        patcher.start()
        self.addCleanup(patcher.stop)

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


def returned_ids(response):
    return {item["id"] for item in response.data}


class BorrowingFilteringTests(TestCase):
    def setUp(self):
        self.user = sample_user()
        self.other = sample_user("other@example.com")
        self.book = sample_book(inventory=10)
        self.own_active = sample_borrowing(self.user, self.book)
        self.own_returned = sample_borrowing(
            self.user,
            self.book,
            actual_return_date=date(2026, 10, 3),
        )
        self.foreign_active = sample_borrowing(self.other, self.book)
        self.client = APIClient()


class UserBorrowingFilteringTests(BorrowingFilteringTests):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.user)

    def test_user_sees_only_own_borrowings(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            returned_ids(response),
            {self.own_active.id, self.own_returned.id},
        )

    def test_user_cannot_retrieve_foreign_borrowing(self):
        response = self.client.get(detail_url(self.foreign_active.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_id_param_ignored_for_non_admin(self):
        response = self.client.get(LIST_URL, {"user_id": self.other.id})
        self.assertEqual(
            returned_ids(response),
            {self.own_active.id, self.own_returned.id},
        )

    def test_is_active_true_returns_only_not_returned(self):
        response = self.client.get(LIST_URL, {"is_active": "true"})
        self.assertEqual(returned_ids(response), {self.own_active.id})

    def test_is_active_false_returns_only_returned(self):
        response = self.client.get(LIST_URL, {"is_active": "false"})
        self.assertEqual(returned_ids(response), {self.own_returned.id})

    def test_is_active_accepts_numeric_values(self):
        active = self.client.get(LIST_URL, {"is_active": "1"})
        returned = self.client.get(LIST_URL, {"is_active": "0"})
        self.assertEqual(returned_ids(active), {self.own_active.id})
        self.assertEqual(returned_ids(returned), {self.own_returned.id})

    def test_is_active_invalid_value_rejected(self):
        response = self.client.get(LIST_URL, {"is_active": "maybe"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AdminBorrowingFilteringTests(BorrowingFilteringTests):
    def setUp(self):
        super().setUp()
        self.admin = get_user_model().objects.create_superuser(
            email="admin@example.com", password="pass12345"
        )
        self.client.force_authenticate(self.admin)

    def test_admin_sees_all_borrowings(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            returned_ids(response),
            {
                self.own_active.id,
                self.own_returned.id,
                self.foreign_active.id,
            },
        )

    def test_admin_filters_by_user_id(self):
        response = self.client.get(LIST_URL, {"user_id": self.other.id})
        self.assertEqual(returned_ids(response), {self.foreign_active.id})

    def test_admin_user_id_without_borrowings_returns_empty(self):
        response = self.client.get(LIST_URL, {"user_id": self.admin.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_admin_invalid_user_id_rejected(self):
        response = self.client.get(LIST_URL, {"user_id": "abc"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_combines_user_id_and_is_active(self):
        response = self.client.get(
            LIST_URL, {"user_id": self.user.id, "is_active": "true"}
        )
        self.assertEqual(returned_ids(response), {self.own_active.id})

    def test_admin_can_retrieve_any_borrowing(self):
        response = self.client.get(detail_url(self.foreign_active.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)


def return_url(borrowing_id):
    return reverse("borrowings:borrowing-return", args=[borrowing_id])


class ReturnBorrowingTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.user = sample_user()
        self.other = sample_user("other@example.com")
        self.book = sample_book(inventory=3)
        self.borrowing = sample_borrowing(
            self.user,
            self.book,
            borrow_date=self.today - timedelta(days=2),
            expected_return_date=self.today + timedelta(days=5),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_return_sets_actual_return_date(self):
        response = self.client.post(return_url(self.borrowing.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.borrowing.refresh_from_db()
        self.assertEqual(self.borrowing.actual_return_date, self.today)

    def test_return_increases_inventory(self):
        self.client.post(return_url(self.borrowing.id))
        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 4)

    def test_return_response_contains_updated_borrowing(self):
        response = self.client.post(return_url(self.borrowing.id))
        self.assertEqual(response.data["id"], self.borrowing.id)
        self.assertEqual(
            response.data["actual_return_date"], self.today.isoformat()
        )
        self.assertEqual(response.data["book"]["inventory"], 4)

    def test_cannot_return_twice(self):
        first = self.client.post(return_url(self.borrowing.id))
        second = self.client.post(return_url(self.borrowing.id))
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 4)

    def test_returned_borrowing_is_not_active(self):
        self.client.post(return_url(self.borrowing.id))
        response = self.client.get(LIST_URL, {"is_active": "true"})
        self.assertEqual(response.data, [])

    def test_return_requires_authentication(self):
        client = APIClient()
        response = client.post(return_url(self.borrowing.id))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_cannot_return_foreign_borrowing(self):
        foreign = sample_borrowing(
            self.other,
            self.book,
            borrow_date=self.today - timedelta(days=1),
            expected_return_date=self.today + timedelta(days=6),
        )
        response = self.client.post(return_url(foreign.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        foreign.refresh_from_db()
        self.assertIsNone(foreign.actual_return_date)
        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 3)

    def test_admin_can_return_any_borrowing(self):
        admin = get_user_model().objects.create_superuser(
            email="admin@example.com", password="pass12345"
        )
        client = APIClient()
        client.force_authenticate(admin)
        response = client.post(return_url(self.borrowing.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.borrowing.refresh_from_db()
        self.assertEqual(self.borrowing.actual_return_date, self.today)

    def test_return_missing_borrowing_returns_404(self):
        response = self.client.post(return_url(999))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_return_not_allowed_with_get(self):
        response = self.client.get(return_url(self.borrowing.id))
        self.assertEqual(
            response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )


class BorrowingMessageTests(TestCase):
    def test_message_contains_borrowing_details(self):
        borrowing = sample_borrowing(sample_user(), sample_book())
        message = build_borrowing_message(borrowing)

        self.assertIn(f"#{borrowing.id}", message)
        self.assertIn("user@example.com", message)
        self.assertIn("Dune", message)
        self.assertIn("Frank Herbert", message)
        self.assertIn("2026-10-01", message)
        self.assertIn("2026-10-08", message)


class BorrowingNotificationTests(TestCase):
    def setUp(self):
        self.user = sample_user()
        self.book = sample_book(inventory=2)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        patcher = patch("borrowings.views.send_telegram_message")
        self.mock_send = patcher.start()
        self.addCleanup(patcher.stop)

    def test_notification_sent_on_create(self):
        response = self.client.post(LIST_URL, create_payload(self.book))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.mock_send.assert_called_once()
        text = self.mock_send.call_args.args[0]
        borrowing = Borrowing.objects.get()
        self.assertIn(f"#{borrowing.id}", text)
        self.assertIn(self.user.email, text)
        self.assertIn("Dune", text)
        self.assertIn(borrowing.expected_return_date.isoformat(), text)

    def test_no_notification_when_creation_fails(self):
        book = sample_book(title="Emma", inventory=0)
        response = self.client.post(LIST_URL, create_payload(book))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.mock_send.assert_not_called()

    def test_borrowing_created_even_if_notification_fails(self):
        self.mock_send.return_value = False
        response = self.client.post(LIST_URL, create_payload(self.book))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Borrowing.objects.count(), 1)
