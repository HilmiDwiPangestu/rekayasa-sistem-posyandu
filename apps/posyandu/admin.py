from django.contrib import admin

from .models import JadwalKegiatan, PenugasanPetugas, Posyandu


@admin.register(PenugasanPetugas)
class PenugasanPetugasAdmin(admin.ModelAdmin):
    list_display = ("petugas", "posyandu", "tanggal_daftar")
    list_filter = ("tanggal_daftar", "posyandu")
    search_fields = ("petugas__nama", "posyandu__nama")
    ordering = ("-tanggal_daftar", "-pk")


admin.site.register(Posyandu)
admin.site.register(JadwalKegiatan)
