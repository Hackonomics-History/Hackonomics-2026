from django.urls import path

from .views import BusinessNewsRefreshView, BusinessNewsView, ChatStreamView

urlpatterns = [
    path("business-news/", BusinessNewsView.as_view(), name="business-news"),
    path(
        "business-news/refresh/",
        BusinessNewsRefreshView.as_view(),
        name="business-news-refresh",
    ),
    path("chat/stream/", ChatStreamView.as_view()),
]
