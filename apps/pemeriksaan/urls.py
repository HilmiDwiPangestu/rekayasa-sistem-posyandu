from django.urls import path

from . import views

app_name = "pemeriksaan"

urlpatterns = [
    path("pemeriksaan/jadwal-pemeriksaan-<str:status_peserta>/", views.list_jadwal_pemeriksaan, name="list"),
    path("pemeriksaan/jadwal-pemeriksaan-<str:status_peserta>/list-peserta/<int:id_jadwal>/", views.list_peserta, name="list_peserta"),
    path("pemeriksaan/jadwal-pemeriksaan-<str:status_peserta>/list-peserta/<int:id_jadwal>/peserta/<int:id_peserta>/", views.periksa_peserta, name="periksa_peserta"),
    path("pemeriksaan/jadwal-pemeriksaan-<str:status_peserta>/list-peserta/<int:id_jadwal>/peserta/<int:id_peserta>/pemeriksaan/<int:id_periksa>/edit/", views.periksa_peserta, name="edit_pemeriksaan"),
    path("detail-deteksi-stunting/<int:id_periksa>/", views.detail_deteksi_stunting, name="detail_deteksi_stunting"),
    path("imunisasi/jadwal-Imunisasi-<str:status_peserta>/", views.imunisasi_jadwal, name="list_imunisasi"),
]
