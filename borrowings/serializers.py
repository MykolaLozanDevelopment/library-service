from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from books.models import Book
from books.serializers import BookSerializer
from borrowings.models import Borrowing


class BorrowingSerializer(serializers.ModelSerializer):
    book = BookSerializer(read_only=True)

    class Meta:
        model = Borrowing
        fields = (
            "id",
            "borrow_date",
            "expected_return_date",
            "actual_return_date",
            "book",
            "user",
        )
        read_only_fields = fields


class BorrowingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Borrowing
        fields = ("id", "borrow_date", "expected_return_date", "book")
        read_only_fields = ("id", "borrow_date")

    def validate_book(self, book):
        if book.inventory < 1:
            raise serializers.ValidationError(
                "This book is not available: inventory is 0."
            )
        return book

    def validate_expected_return_date(self, value):
        if value <= timezone.localdate():
            raise serializers.ValidationError(
                "Expected return date must be after today."
            )
        return value

    def create(self, validated_data):
        with transaction.atomic():
            book = Book.objects.select_for_update().get(
                pk=validated_data["book"].pk
            )
            if book.inventory < 1:
                raise serializers.ValidationError(
                    {"book": "This book is not available: inventory is 0."}
                )
            book.inventory -= 1
            book.save(update_fields=["inventory"])
            validated_data["book"] = book
            return super().create(validated_data)
