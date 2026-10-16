from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
)

from books.models import Book
from borrowings.messages import build_borrowing_message
from borrowings.models import Borrowing
from borrowings.serializers import (
    BorrowingCreateSerializer,
    BorrowingSerializer,
)
from notifications.telegram import send_telegram_message

TRUE_VALUES = ("true", "1")
FALSE_VALUES = ("false", "0")


@extend_schema_view(
    list=extend_schema(
        summary="List borrowings",
        description=(
            "Regular users see only their own borrowings. "
            "Admins see all borrowings, or only one user's when "
            "`user_id` is given."
        ),
        parameters=[
            OpenApiParameter(
                "is_active",
                OpenApiTypes.BOOL,
                description=(
                    "`true` - not returned yet, "
                    "`false` - already returned."
                ),
            ),
            OpenApiParameter(
                "user_id",
                OpenApiTypes.INT,
                description="Admins only: filter by user id.",
            ),
        ],
    ),
    retrieve=extend_schema(
        summary="Get borrowing details",
        description="Regular users can open only their own borrowings.",
    ),
    create=extend_schema(
        summary="Create a borrowing",
        description=(
            "Borrows a book for the current user: decreases the book "
            "inventory by 1 and sends a Telegram notification. "
            "Fails if the inventory is 0 or the expected return date "
            "is not after today."
        ),
    ),
)
class BorrowingViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Borrowing.objects.select_related("book", "user")
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        if not user.is_staff:
            queryset = queryset.filter(user=user)

        if self.action != "list":
            return queryset

        params = self.request.query_params

        if user.is_staff:
            user_id = params.get("user_id")
            if user_id:
                if not user_id.isdigit():
                    raise ValidationError(
                        {"user_id": "Must be an integer."}
                    )
                queryset = queryset.filter(user_id=int(user_id))

        is_active = params.get("is_active")
        if is_active:
            value = is_active.lower()
            if value in TRUE_VALUES:
                queryset = queryset.filter(actual_return_date__isnull=True)
            elif value in FALSE_VALUES:
                queryset = queryset.filter(actual_return_date__isnull=False)
            else:
                raise ValidationError({"is_active": "Use true or false."})

        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return BorrowingCreateSerializer
        return BorrowingSerializer

    def perform_create(self, serializer):
        borrowing = serializer.save(user=self.request.user)
        send_telegram_message(build_borrowing_message(borrowing))

    @extend_schema(
        summary="Return a borrowing",
        description=(
            "Sets the actual return date to today and increases the "
            "book inventory by 1. A borrowing cannot be returned twice."
        ),
        request=None,
        responses=BorrowingSerializer,
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="return",
        url_name="return",
    )
    def return_borrowing(self, request, pk=None):
        """Set the actual return date and give the book back to stock."""
        borrowing = self.get_object()

        with transaction.atomic():
            borrowing = Borrowing.objects.select_for_update().get(
                pk=borrowing.pk
            )
            if borrowing.actual_return_date is not None:
                raise ValidationError(
                    {"detail": "This borrowing has already been returned."}
                )

            book = Book.objects.select_for_update().get(
                pk=borrowing.book_id
            )
            book.inventory += 1
            book.save(update_fields=["inventory"])

            borrowing.actual_return_date = timezone.localdate()
            borrowing.save(update_fields=["actual_return_date"])
            borrowing.book = book

        return Response(BorrowingSerializer(borrowing).data)
