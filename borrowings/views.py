from rest_framework import mixins, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from borrowings.models import Borrowing
from borrowings.serializers import (
    BorrowingCreateSerializer,
    BorrowingSerializer,
)

TRUE_VALUES = ("true", "1")
FALSE_VALUES = ("false", "0")


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
        serializer.save(user=self.request.user)
