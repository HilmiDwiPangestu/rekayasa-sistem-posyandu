from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("setting/", views.settings_page, name="setting"),
    path("setting/update/", views.update_settings, name="updateSetting"),
    path("petugas/tambah/<str:level_petugas>/", views.tambah_petugas, name="tambah_petugas"),
]
