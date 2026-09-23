from django.urls import path

from . import views

app_name = "peserta"

urlpatterns = [
    path("data-<str:status_peserta>/", views.list_peserta, name="list"),
    path("data-<str:status_peserta>/cetak/pdf/", views.cetak_peserta_pdf, name="cetak_pdf"),
    path("data-<str:status_peserta>/export/excel/", views.export_peserta_excel, name="export_excel"),
    path("data-<str:status_peserta>/Tambah/", views.tambah_peserta, name="create"),
    path("data-<str:status_peserta>/edit/<int:id>/", views.edit_peserta, name="edit"),
    path("data-<str:status_peserta>/delete/<int:id>/", views.delete_peserta, name="delete"),
]
