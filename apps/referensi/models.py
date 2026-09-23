from django.db import models


class WHOStandardPBU(models.Model):
    """Referensi WHO Length/Height-for-Age (LFA/HFA) berbasis usia harian.

    Nama model ``WHOStandardPBU`` dipertahankan agar kompatibel dengan kode dan
    migration lama project. Data aktif berasal dari tabel WHO expanded
    ``LFA_boys_z_exp`` dan ``LFA_girls_z_exp`` yang menggunakan ``Day``.
    """

    GENDER_CHOICES = [
        ("L", "Laki-laki"),
        ("P", "Perempuan"),
    ]

    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)

    # Referensi baru memakai umur eksak dalam hari. Kolom month dipertahankan
    # nullable hanya untuk kompatibilitas database versi lama; lookup WHO tidak
    # lagi menggunakannya.
    day = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Umur dalam hari sesuai tabel WHO expanded (0-1856)",
    )
    month = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Kolom kompatibilitas data WHO bulanan lama",
    )

    # Parameter LMS WHO.
    l_value = models.FloatField()
    m_value = models.FloatField()
    s_value = models.FloatField()

    # SD ~ M*S untuk tabel LFA (L=1). Dipertahankan untuk kompatibilitas kode
    # lama dan kebutuhan inspeksi, bukan sebagai sumber utama perhitungan.
    sd = models.FloatField()

    # Garis standar dari file WHO expanded.
    sd4neg = models.FloatField(null=True, blank=True)
    sd3neg = models.FloatField()
    sd2neg = models.FloatField()
    sd1neg = models.FloatField()
    sd0 = models.FloatField()
    sd1 = models.FloatField()
    sd2 = models.FloatField()
    sd3 = models.FloatField()
    sd4 = models.FloatField(null=True, blank=True)

    source = models.CharField(
        max_length=64,
        default="WHO LFA expanded daily",
        help_text="Sumber referensi antropometri",
    )

    class Meta:
        db_table = "who_standard_pbu"
        ordering = ["gender", "day"]
        constraints = [
            models.UniqueConstraint(
                fields=["gender", "day"],
                name="unique_pbu_gender_day",
            )
        ]

    def __str__(self):
        if self.day is not None:
            return f"{self.get_gender_display()} - {self.day} hari"
        if self.month is not None:
            return f"{self.get_gender_display()} - {self.month} bulan (legacy)"
        return self.get_gender_display()
