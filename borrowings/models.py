from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from books.models import Book


class Borrowing(models.Model):
    borrow_date = models.DateField(default=timezone.localdate)
    expected_return_date = models.DateField()
    actual_return_date = models.DateField(null=True, blank=True)
    book = models.ForeignKey(
        Book, on_delete=models.CASCADE, related_name="borrowings"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="borrowings",
    )

    class Meta:
        ordering = ["-borrow_date", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(expected_return_date__gt=F("borrow_date")),
                name="expected_return_after_borrow_date",
            ),
            models.CheckConstraint(
                condition=(
                    Q(actual_return_date__isnull=True)
                    | Q(actual_return_date__gte=F("borrow_date"))
                ),
                name="actual_return_not_before_borrow_date",
            ),
        ]

    def __str__(self):
        return f"{self.book.title} borrowed by {self.user.email}"
