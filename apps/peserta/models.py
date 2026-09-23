from django.db import models
from datetime import date
from dateutil.relativedelta import relativedelta

from apps.posyandu.models import Posyandu


class Peserta(models.Model):
    STATUS_CHOICES = [
        ('bumil', 'Ibu Hamil'),
        ('balita', 'Balita'),
    ]

    JENIS_KELAMIN = [
        ('Laki-Laki', 'Laki-Laki'),
        ('Perempuan', 'Perempuan'),
    ]

    posko = models.ForeignKey(
        Posyandu,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    nama_peserta = models.CharField(max_length=50)

    tgl_lahir = models.DateField()

    alamat = models.TextField()
    
    anak_ke = models.PositiveIntegerField(null=True, blank=True)
    
    bb_lahir = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Berat Badan Lahir (Kg)"
    )

    tb_lahir = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Panjang Badan Lahir (Cm)"
    )
    
    lila_lahir = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Lingkar Lengan Lahir (Cm)"
    )

    no_hp = models.CharField(max_length=15)

    nik_ibu = models.CharField(
        null=True,
        blank=True,
        max_length=16
    )
    
    no_nik = models.CharField(null=True, blank=True, max_length=16)

    status_peserta = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES
    )

    nama_ibu = models.CharField(
        verbose_name="Nama Ibu",
        blank=True,
        null=True,
        max_length=100,
        )
    
    nama_ayah = models.CharField(
        verbose_name="Nama Ayah",
        max_length=100,
        blank=True,
        null=True
    )

    jenis_kelamin = models.CharField(
        max_length=20,
        choices=JENIS_KELAMIN,
        null=True,
        blank=True
    )

    is_tamu = models.BooleanField(default=False)

    asal_posyandu = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    class Meta:
        db_table = "peserta"
        ordering = ["-nama_peserta"]

    def __str__(self):
        return self.nama_peserta

    # =========================
    # HITUNG USIA DETAIL
    # =========================
    @property
    def usia_detail(self):
        delta = relativedelta(date.today(), self.tgl_lahir)
        return {
            "tahun": max(delta.years, 0),
            "bulan": max(delta.months, 0),
            "hari": max(delta.days, 0),
        }

    # =========================
    # FORMAT USIA
    # =========================
    @property
    def usia(self):
        usia = self.usia_detail

        tahun = usia["tahun"]
        bulan = usia["bulan"]

        # Untuk balita
        if tahun < 5:
            return f"{tahun} th {bulan} bln"

        # Untuk usia >= 5 tahun
        return f"{tahun} tahun"
    
    # =========================
    # FORMAT USIA HARI
    # =========================
    @property
    def usia_hari(self):
        return (date.today() - self.tgl_lahir).days

    # =========================
    # TOTAL BULAN
    # =========================
    @property
    def usia_bulan(self):
        delta = relativedelta(date.today(), self.tgl_lahir)
        return max((delta.years * 12) + delta.months, 0)

    # =========================
    # FORMAT USIA BUMIL
    # =========================
    @property
    def usia_tahun(self):
        return self.usia_detail["tahun"]
