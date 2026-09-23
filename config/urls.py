from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("", include("apps.peserta.urls")),
    path("", include("apps.pemeriksaan.urls")),
    path("", include("apps.laporan.urls")),
    path("", include("apps.posyandu.urls")),
]

handler403 = "django.views.defaults.permission_denied"
