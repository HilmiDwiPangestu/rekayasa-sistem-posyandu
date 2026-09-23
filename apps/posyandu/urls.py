from django.urls import path

from . import views

app_name = "posyandu"

urlpatterns = [
    path("list-jadwal/", views.list_jadwal, name="list_jadwal"),
    path("list-jadwal/tambah/", views.create, name="create"),
    path("list-jadwal/edit/<int:id_jadwal>/", views.edit_jadwal, name="edit"),
    path("list-jadwal/delete/<int:id>/", views.delete, name="delete"),
    path("master-data/data-kader/", views.daftar_petugas_kader, name="daftar_petugas_kader"),
    path("master-data/data-bidan/", views.daftar_bidan, name="daftar_bidan"),
    path("master-data/data-bidan/<int:pk>/cakupan-wilayah/", views.atur_cakupan_bidan, name="atur_cakupan_bidan"),
    path("master-data/data-petugas/<str:level>/export/pdf/", views.export_petugas_pdf, name="export_petugas_pdf"),
    path("master-data/data-petugas/<str:level>/export/excel/", views.export_petugas_excel, name="export_petugas_excel"),
    path("master-data/<int:pk>/edit/", views.edit_petugas, name="edit_petugas"),
    path("master-data/<int:pk>/delete/", views.delete_petugas, name="delete_petugas"),
    path("master-data/admin/", views.list_posyandu, name="list_posyandu"),
    path("master-data/admin/tambah/", views.create_posyandu, name="create_posyandu"),
    path("master-data/admin/export/pdf/", views.export_posyandu_pdf, name="export_posyandu_pdf"),
    path("master-data/admin/export/excel/", views.export_posyandu_excel, name="export_posyandu_excel"),
    path("master-data/admin/<int:id>/edit/", views.edit_posyandu, name="edit_posyandu"),
    path("master-data/admin/<int:id>/delete/", views.delete_posyandu, name="delete_posyandu"),
    path("jadwal-posyandu/", views.jadwal_posyandu_admin, name="jadwal_posyandu_admin"),
    path("jadwal-posyandu/jadwal/<int:id_jadwal>/detail/", views.detail_jadwal_admin, name="detail_jadwal_admin"),
    path("laporan/ibu-hamil/", views.laporan_bumil, name="laporan_bumil"),
    path("laporan/balita/", views.laporan_balita, name="laporan_balita"),
    path("laporan/admin/imunisasi/", views.laporan_imunisasi, name="laporan_imunisasi"),
    path("laporan/triwulan/", views.laporan_triwulan, name="laporan_triwulan"),
    path("laporan/semua-laporan", views.semua_laporan, name="semua_laporan"),
    path("laporan/ibu-hamil/excel/", views.export_bumil_excel, name="export_bumil_excel"),
    path("laporan/balita/excel/", views.export_balita_excel, name="export_balita_excel"),
    path("laporan/ibu-hamil/pdf/", views.cetak_bumil_pdf, name="cetak_bumil_pdf"),
    path("laporan/ibu-balita/pdf/", views.cetak_balita_pdf, name="cetak_balita_pdf"),
    path("laporan/imunisasi/pdf/", views.cetak_imunisasi_pdf, name="cetak_imunisasi_pdf"),
    path("laporan/imunisasi/<int:id_jadwal>/detail/", views.detail_laporan_imunisasi, name="detail_laporan_imunisasi"),
    path("petugas/buat-akun/<int:id>/", views.buat_akun_petugas, name="buat_akun_petugas"),
]
