from django.urls import include, path
from rest_framework import routers

from books.views import BookViewSet

router = routers.SimpleRouter()
router.register("", BookViewSet)

urlpatterns = [path("", include(router.urls))]

app_name = "books"
