from django.urls import path

from . import views

app_name = "laporan"

urlpatterns = [
    path("laporan/rekap/", views.laporan_index, name="laporan_index"),
    path("laporan/detail-laporan/<int:id_jadwal>/", views.laporan_jadwal, name="laporan_jadwal"),
    path("laporan/", views.laporan_bulanan, name="laporan_bulanan"),
    path("laporan/imunisasi/", views.laporan_imunisasi_bulanan, name="laporan_imunisasi_bulanan"),
    path("triwulan/", views.laporan_triwulan, name="laporan_triwulan"),
    path("triwulan/export/pdf/", views.export_laporan_triwulan_pdf, name="export_laporan_triwulan_pdf"),
    path("laporan/kms/<int:id_peserta>/", views.laporan_kms, name="laporan_kms"),
    path("laporan/jadwal/<int:id_jadwal>/pdf/", views.export_laporan_jadwal_pdf, name="export_laporan_jadwal_pdf"),
    path("laporan/jadwal/<int:id_jadwal>/excel/", views.export_laporan_jadwal_excel, name="export_laporan_jadwal_excel"),
]
