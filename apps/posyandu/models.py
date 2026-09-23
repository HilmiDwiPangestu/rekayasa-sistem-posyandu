from django.db import models
from django.utils import timezone

class Posyandu(models.Model):
    nama = models.CharField(max_length=100)
    desa = models.TextField(blank=True, null=True)
    alamat = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "posyandu"
        ordering = ["nama"]
        verbose_name = "Posyandu"
        verbose_name_plural = "Posyandu"

    def __str__(self):
        return self.nama
    

class PenugasanPetugas(models.Model):
    petugas = models.ForeignKey("accounts.Petugas", on_delete=models.CASCADE)
    posyandu = models.ForeignKey(Posyandu, on_delete=models.CASCADE)
    tanggal_daftar = models.DateField("Tanggal Daftar", default=timezone.localdate, editable=False)

    class Meta:
        db_table = "penugasan_Petugas"
        verbose_name = "Penugasan Petugas"
        verbose_name_plural = "Penugasan Petugas"
        ordering = ["-tanggal_daftar", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["petugas", "posyandu"],
                name="unique_penugasan_petugas_posyandu",
            ),
        ]

    def __str__(self):
        return f"{self.petugas} - {self.posyandu} ({self.tanggal_daftar:%d-%m-%Y})"

class JadwalKegiatan(models.Model):
    id_jadwal = models.AutoField(primary_key=True)
    tgl_kegiatan = models.DateField(verbose_name="Tanggal Kegiatan")
    jam_mulai = models.TimeField(verbose_name="Jam Mulai")
    jam_selesai = models.TimeField(verbose_name="Jam Selesai")

    # Workflow operasional yang benar-benar tersedia di aplikasi. Penimbangan,
    # pengukuran, Vitamin A dan obat cacing dicatat di Pemeriksaan Rutin.
    KEGIATAN = [
        ('Pemeriksaan Rutin', 'Pemeriksaan Rutin'),
        ('Imunisasi', 'Imunisasi'),
    ]

    jns_kegiatan = models.CharField(max_length=50, choices=KEGIATAN ,verbose_name="Jenis Kegiatan")
    
    posyandu = models.ForeignKey(Posyandu, on_delete=models.CASCADE, null=True)

    class Meta:
        db_table = "jadwal_kegiatan"
        ordering = ["-tgl_kegiatan"]
        verbose_name = "Jadwal Kegiatan"
        verbose_name_plural = "Jadwal Kegiatan"

    def __str__(self):
        return f"{self.jns_kegiatan} - {self.tgl_kegiatan}"

