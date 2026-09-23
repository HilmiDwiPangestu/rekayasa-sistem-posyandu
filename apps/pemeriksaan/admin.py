from django.contrib import admin
from .models import Imunisasi, Kehadiran, PemeriksaanBalita

# Register your models here.
admin.site.register(Imunisasi)
admin.site.register(Kehadiran)
admin.site.register(PemeriksaanBalita)
