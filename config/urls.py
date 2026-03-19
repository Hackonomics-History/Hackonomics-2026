from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("", include("django_prometheus.urls")),
    path("admin/", admin.site.urls),
    # swagger
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/swagger/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/docs/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"
    ),
    # APIs
    path("api/auth/", include("authentication.presentation.urls")),
    path("api/account/", include("accounts.presentation.urls")),
    path("api/meta/", include("meta.presentation.urls")),
    path("api/exchange/", include("exchange.presentation.urls")),
    path("api/simulation/", include("simulation.presentation.urls")),
    path("api/calendar/", include("user_calendar.presentation.urls")),
    path("api/news/", include("news.presentation.urls")),
]
