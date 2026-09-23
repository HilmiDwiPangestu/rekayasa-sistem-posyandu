from django.contrib.auth.models import User
from django.db import models
from django.core.exceptions import ValidationError


class Petugas(models.Model):
    # Hanya Admin Kelurahan dan Kader yang merupakan aktor login.
    # Bidan tetap disimpan sebagai data master/penanggung jawab wilayah,
    # tetapi tidak mempunyai akun autentikasi.
    LOGIN_LEVELS = frozenset({"admin", "kader"})

    LEVEL_CHOICES = [
        ('kader', 'Kader'),
        ('bidan', 'Bidan'),
        ('admin', 'Admin'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='petugas'
    )

    nama = models.CharField(max_length=100)
    alamat = models.TextField(blank=True, null=True)
    no_telp = models.CharField(max_length=15, blank=True, null=True)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES)

    posyandu = models.ForeignKey(
        'posyandu.Posyandu',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='petugas'
    )

    def clean(self):
        # Kader dan Bidan tetap mempunyai Posyandu utama. Bidan bukan
        # aktor login; cakupan tambahannya disimpan di PenugasanPetugas.
        if self.level in {"kader", "bidan"} and not self.posyandu:
            raise ValidationError("Kader/Bidan harus memiliki posyandu utama")

        if self.level == "bidan" and self.user_id:
            raise ValidationError("Bidan merupakan data penanggung jawab wilayah dan tidak memiliki akun login.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def can_login(self):
        """Hanya akun aplikasi biasa untuk Admin Kelurahan/Kader yang boleh login.

        Akun staff/superuser Django dipisahkan sebagai akun teknis untuk /admin/.
        """
        if self.level not in self.LOGIN_LEVELS or self.user_id is None:
            return False
        return bool(
            self.user.is_active
            and not self.user.is_staff
            and not self.user.is_superuser
        )

    class Meta:
        db_table = "petugas"
        ordering = ["nama"]
        constraints = [
            models.CheckConstraint(
                condition=(~models.Q(level="bidan") | models.Q(user__isnull=True)),
                name="petugas_bidan_tanpa_akun",
            ),
        ]

    def __str__(self):
        return f"{self.nama} ({self.level})"