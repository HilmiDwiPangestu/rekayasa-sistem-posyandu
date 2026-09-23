from django.db import models
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from datetime import datetime
import re

from dateutil.relativedelta import relativedelta

from apps.accounts.models import Petugas
from apps.peserta.models import Peserta
from apps.posyandu.models import JadwalKegiatan


# =========================================================
# PEMERIKSAAN BALITA
# =========================================================
class PemeriksaanBalita(models.Model):

    # Kategori PB/U atau TB/U. Kode stunting dipertahankan untuk
    # kompatibilitas analisis biner Random Forest, sedangkan label mengikuti
    # kategori antropometri: Sangat Pendek, Pendek, Normal, dan Tinggi.
    STATUS_GIZI = [
        ('stunting_berat', 'Sangat Pendek'),
        ('stunting', 'Pendek'),
        ('normal', 'Normal'),
        ('tinggi', 'Tinggi'),
    ]

    id_periksa = models.AutoField(primary_key=True)

    peserta = models.ForeignKey(
        Peserta,
        on_delete=models.PROTECT,
        related_name='pemeriksaan_balita'
    )

    petugas = models.ForeignKey(
        Petugas,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pemeriksaan_balita'
    )

    bidan_pelaksana = models.ForeignKey(
        Petugas,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pemeriksaan_balita_sebagai_bidan',
        limit_choices_to={'level': 'bidan'},
        help_text='Bidan/tenaga kesehatan pendamping pelayanan',
    )

    jadwal = models.ForeignKey(
        JadwalKegiatan,
        on_delete=models.PROTECT,
        related_name='pemeriksaan_balita'
    )

    tgl_pemeriksaan = models.DateTimeField(
        default=timezone.now
    )

    # =====================================================
    # ANTROPOMETRI
    # =====================================================
    usia_bulan = models.IntegerField(
        null=True,
        blank=True,
        editable=False,
        help_text="Usia bulan penuh untuk fitur Random Forest dan laporan",
    )

    usia_hari = models.IntegerField(
        null=True,
        blank=True,
        editable=False,
        help_text="Usia eksak dalam hari untuk lookup referensi WHO daily",
    )

    berat_badan = models.FloatField(
        null=True,
        blank=True,
        help_text="Berat badan dalam kilogram"
    )

    tinggi_badan = models.FloatField(
        null=True,
        blank=True,
        help_text="Panjang/Tinggi badan dalam sentimeter"
    )

    lila_balita = models.FloatField(
        null=True,
        blank=True,
        help_text="Lingkar lengan atas balita dalam sentimeter"
    )

    lingkar_kepala = models.FloatField(
        null=True,
        blank=True,
        help_text="Lingkar kepala balita dalam sentimeter"
    )

    # =====================================================
    # WHO + HASIL RANDOM FOREST
    # =====================================================
    z_score = models.FloatField(
        null=True,
        blank=True
    )

    status_gizi = models.CharField(
        max_length=30,
        choices=STATUS_GIZI,
        default='normal',
        editable=False
    )

    hsl_prediksi = models.CharField(
        max_length=30,
        null=True,
        blank=True
    )

    prob_ml = models.FloatField(
        null=True,
        blank=True
    )

    catatan = models.TextField(
        null=True,
        blank=True
    )

    # =====================================================
    # META
    # =====================================================
    class Meta:
        db_table = "pemeriksaan_balita"
        ordering = ['-tgl_pemeriksaan']
        verbose_name = "Pemeriksaan Balita"
        verbose_name_plural = "Pemeriksaan Balita"
        constraints = [
            models.UniqueConstraint(
                fields=['peserta', 'jadwal'],
                name='unique_pemeriksaan_balita_peserta_jadwal',
            )
        ]

    def __str__(self):
        return (
            f"{self.peserta.nama_peserta} - "
            f"{self.tgl_pemeriksaan:%d-%m-%Y}"
        )

    # =====================================================
    # PROPERTY
    # =====================================================
    @property
    def petugas_nama(self):
        return self.petugas.nama if self.petugas else "-"

    # =====================================================
    # VALIDASI
    # =====================================================
    def clean(self):

        super().clean()

        if self.petugas and self.petugas.level != 'kader':
            raise ValidationError(
                "Pemeriksaan hanya dapat dicatat oleh Kader."
            )
        if self.bidan_pelaksana_id:
            if self.bidan_pelaksana.level != 'bidan':
                raise ValidationError({'bidan_pelaksana': 'Pelaksana harus merupakan data Bidan.'})
            from common.access import active_posyandu_ids
            if self.jadwal_id and self.jadwal.posyandu_id not in active_posyandu_ids(self.bidan_pelaksana):
                raise ValidationError({'bidan_pelaksana': 'Bidan tidak termasuk cakupan Posyandu pada jadwal ini.'})
        if self.peserta_id and self.peserta.status_peserta != "balita":
            raise ValidationError("Pemeriksaan balita hanya untuk peserta balita.")
        if (
            self.peserta_id and self.jadwal_id
            and self.peserta.posko_id != self.jadwal.posyandu_id
        ):
            raise ValidationError("Peserta dan jadwal harus berasal dari Posyandu yang sama.")

    # =====================================================
    # SAVE
    # =====================================================
    def save(self, *args, **kwargs):

        # Tanggal pelayanan mengikuti jadwal Posyandu, sedangkan waktu input
        # tetap tercatat melalui log/audit aplikasi. Hal ini mencegah usia
        # antropometri berubah hanya karena data dimasukkan beberapa hari kemudian.
        if self.jadwal_id and self.jadwal.tgl_kegiatan:
            # Tanggal pemeriksaan selalu mengikuti tanggal pelayanan pada
            # jadwal, termasuk saat mengedit record lama. Ini penting karena
            # lookup WHO daily bergantung pada usia eksak di hari pelayanan.
            jam = self.jadwal.jam_mulai or datetime.min.time()
            value = datetime.combine(self.jadwal.tgl_kegiatan, jam)
            self.tgl_pemeriksaan = timezone.make_aware(value) if timezone.is_naive(value) else value

        # =================================================
        # HITUNG USIA BERDASARKAN TANGGAL PEMERIKSAAN
        # =================================================
        if (
            self.peserta
            and self.peserta.tgl_lahir
            and self.tgl_pemeriksaan
        ):

            # Jika DateTimeField
            if hasattr(self.tgl_pemeriksaan, "date"):
                tanggal_periksa = self.tgl_pemeriksaan.date()
            else:
                tanggal_periksa = self.tgl_pemeriksaan

            if tanggal_periksa < self.peserta.tgl_lahir:
                raise ValidationError(
                    "Tanggal pemeriksaan tidak boleh lebih awal dari tanggal lahir peserta."
                )

            # WHO daily memakai usia eksak dalam hari. Random Forest tetap
            # menggunakan usia bulan penuh agar konsisten dengan fitur training.
            self.usia_hari = (
                tanggal_periksa - self.peserta.tgl_lahir
            ).days

            selisih = relativedelta(
                tanggal_periksa,
                self.peserta.tgl_lahir
            )

            self.usia_bulan = (
                (selisih.years * 12)
                + selisih.months
            )

        # =================================================
        # CATATAN:
        #
        # Z-Score, status gizi, hasil prediksi Random Forest
        # dan probabilitas ML tetap dihitung dari views melalui
        # apps.deteksi.services.random_forest.
        # =================================================

        self.full_clean()
        super().save(*args, **kwargs)

    # =====================================================
    # SERIALIZER STYLE
    # =====================================================


# =========================================================
# PELAYANAN BALITA
# VITAMIN A DAN OBAT CACING
# =========================================================
class PelayananBalita(models.Model):

    JENIS_LAYANAN = [
        ('vitamin_a', 'Vitamin A'),
        ('obat_cacing', 'Obat Cacing'),
    ]

    JENIS_VITAMIN_A = [
        ('biru', 'Vitamin A Biru'),
        ('merah', 'Vitamin A Merah'),
    ]

    id_pelayanan = models.AutoField(
        primary_key=True
    )

    # =====================================================
    # TERHUBUNG DENGAN PEMERIKSAAN
    # =====================================================
    pemeriksaan = models.ForeignKey(
        PemeriksaanBalita,
        on_delete=models.CASCADE,
        related_name='pelayanan_balita'
    )

    # =====================================================
    # JENIS PELAYANAN
    # =====================================================
    jenis_layanan = models.CharField(
        max_length=30,
        choices=JENIS_LAYANAN
    )

    tanggal_pemberian = models.DateField(
        default=timezone.now
    )

    # =====================================================
    # KHUSUS VITAMIN A
    # =====================================================
    jenis_vitamin_a = models.CharField(
        max_length=20,
        choices=JENIS_VITAMIN_A,
        null=True,
        blank=True
    )

    # =====================================================
    # KHUSUS OBAT CACING
    # =====================================================
    nama_obat = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    dosis = models.CharField(
        max_length=50,
        null=True,
        blank=True
    )

    # =====================================================
    # CATATAN
    # =====================================================
    catatan = models.TextField(
        null=True,
        blank=True
    )

    # =====================================================
    # META
    # =====================================================
    class Meta:
        db_table = "pelayanan_balita"

        ordering = [
            '-tanggal_pemberian'
        ]

        verbose_name = "Pelayanan Balita"
        verbose_name_plural = "Pelayanan Balita"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'pemeriksaan',
                    'jenis_layanan'
                ],
                name='unique_pelayanan_per_pemeriksaan'
            )
        ]

    def __str__(self):

        return (
            f"{self.pemeriksaan.peserta.nama_peserta} - "
            f"{self.get_jenis_layanan_display()}"
        )

    # =====================================================
    # PROPERTY
    # =====================================================
    @property
    def peserta(self):
        return self.pemeriksaan.peserta

    @property
    def petugas(self):
        return self.pemeriksaan.petugas

    @property
    def jadwal(self):
        return self.pemeriksaan.jadwal

    # =====================================================
    # VALIDASI
    # =====================================================
    def clean(self):

        super().clean()

        # =================================================
        # VITAMIN A
        # =================================================
        if self.jenis_layanan == 'vitamin_a':

            if not self.jenis_vitamin_a:
                raise ValidationError({
                    'jenis_vitamin_a':
                        'Jenis Vitamin A harus dipilih.'
                })

            # Kosongkan atribut obat cacing
            self.nama_obat = None
            self.dosis = None

        # =================================================
        # OBAT CACING
        # =================================================
        elif self.jenis_layanan == 'obat_cacing':

            # Vitamin A tidak diperlukan
            self.jenis_vitamin_a = None

    # =====================================================
    # SERIALIZER STYLE
    # =====================================================


# =========================================================
# KEHADIRAN
# =========================================================
class Kehadiran(models.Model):

    STATUS_KEHADIRAN = [
        ('hadir', 'Hadir'),
        ('tidak', 'Tidak Hadir'),
        ('izin', 'Izin'),
    ]

    id_kehadiran = models.AutoField(
        primary_key=True
    )

    peserta = models.ForeignKey(
        Peserta,
        on_delete=models.PROTECT,
        related_name='kehadiran'
    )

    jadwal = models.ForeignKey(
        JadwalKegiatan,
        on_delete=models.PROTECT,
        related_name='kehadiran'
    )

    status_kehadiran = models.CharField(
        max_length=20,
        choices=STATUS_KEHADIRAN,
        default='tidak'
    )

    class Meta:
        db_table = "kehadiran"
        ordering = ["jadwal"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'peserta',
                    'jadwal'
                ],
                name='unique_kehadiran_peserta_jadwal'
            )
        ]

    def __str__(self):

        return (
            f"{self.peserta.nama_peserta} - "
            f"{self.status_kehadiran}"
        )



# =========================================================
# IMUNISASI
# =========================================================
class Imunisasi(models.Model):

    # =====================================================
    # PILIHAN VAKSIN BALITA
    # =====================================================
    VAKSIN_BALITA = [
        ('HB-0', 'Hepatitis B (HB-0)'),
        ('BCG', 'BCG'),
        ('bOPV 1', 'Polio Tetes (bOPV) 1'),
        ('bOPV 2', 'Polio Tetes (bOPV) 2'),
        ('bOPV 3', 'Polio Tetes (bOPV) 3'),
        ('bOPV 4', 'Polio Tetes (bOPV) 4'),
        ('DPT-HB-Hib 1', 'DPT-HB-Hib 1'),
        ('DPT-HB-Hib 2', 'DPT-HB-Hib 2'),
        ('DPT-HB-Hib 3', 'DPT-HB-Hib 3'),
        ('DPT-HB-Hib 4', 'DPT-HB-Hib 4'),
        ('PCV 1', 'PCV 1'),
        ('PCV 2', 'PCV 2'),
        ('PCV 3', 'PCV 3'),
        ('Rotavirus 1', 'Rotavirus 1'),
        ('Rotavirus 2', 'Rotavirus 2'),
        ('Rotavirus 3', 'Rotavirus 3'),
        ('IPV 1', 'Polio Suntik (IPV) 1'),
        ('IPV 2', 'Polio Suntik (IPV) 2'),
        ('MR 1', 'Campak Rubela (MR) 1'),
        ('MR 2', 'Campak Rubela (MR) 2'),
        ('JE', 'Japanese Encephalitis (wilayah endemis)'),
    ]

    # =====================================================
    # PILIHAN VAKSIN IBU HAMIL
    # =====================================================
    VAKSIN_BUMIL = [
        (
            'TT-1',
            'TT-1 (Tetanus Toksoid)'
        ),

        (
            'TT-2',
            'TT-2 (Tetanus Toksoid)'
        ),

        (
            'TT-3',
            'TT-3 (Tetanus Toksoid)'
        ),

        (
            'TT-4',
            'TT-4 (Tetanus Toksoid)'
        ),

        (
            'TT-5',
            'TT-5 (Tetanus Toksoid)'
        ),
    ]

    VAKSIN_CHOICES = (
        VAKSIN_BALITA
        + VAKSIN_BUMIL
    )

    # =====================================================
    # FIELD
    # =====================================================
    id_imunisasi = models.AutoField(
        primary_key=True
    )

    peserta = models.ForeignKey(
        Peserta,
        on_delete=models.PROTECT,
        related_name='imunisasi'
    )

    petugas = models.ForeignKey(
        Petugas,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='imunisasi'
    )

    bidan_pelaksana = models.ForeignKey(
        Petugas,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='imunisasi_sebagai_bidan',
        limit_choices_to={'level': 'bidan'},
        help_text='Bidan/tenaga kesehatan pelaksana imunisasi',
    )

    jadwal = models.ForeignKey(
        JadwalKegiatan,
        on_delete=models.PROTECT,
        related_name='imunisasi'
    )

    jenis_vaksin = models.CharField(
        max_length=50,
        choices=VAKSIN_CHOICES
    )

    dosis = models.CharField(
        max_length=20,
        choices=[
            ('1', 'Dosis 1'),
            ('2', 'Dosis 2'),
            ('3', 'Dosis 3'),
            ('4', 'Dosis 4'),
            ('5', 'Dosis 5'),
            ('Booster', 'Booster'),
        ],
        default='1',
        blank=True,
        null=True
    )

    usia_saat_vaksin = models.IntegerField(
        help_text="Usia dalam bulan (balita)",
        blank=True,
        null=True
    )

    usia_kehamilan = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        help_text="Usia kehamilan dalam minggu"
    )

    tgl_pemberian = models.DateField(
        default=timezone.now
    )

    lokasi = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    catatan = models.TextField(
        blank=True,
        null=True
    )

    class Meta:
        db_table = "imunisasi"

        verbose_name = "Data Imunisasi"
        verbose_name_plural = "Data Imunisasi"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'peserta',
                    'jadwal',
                    'jenis_vaksin'
                ],
                name='unique_imunisasi_peserta_jadwal_vaksin'
            )
        ]

    def __str__(self):

        return (
            f"{self.peserta.nama_peserta} - "
            f"{self.jenis_vaksin}"
        )

    def clean(self):
        super().clean()

        if self.petugas_id and self.petugas.level != "kader":
            raise ValidationError("Imunisasi hanya dapat dicatat oleh Kader.")

        if self.bidan_pelaksana_id:
            if self.bidan_pelaksana.level != "bidan":
                raise ValidationError({"bidan_pelaksana": "Pelaksana harus merupakan data Bidan."})
            from common.access import active_posyandu_ids
            if self.jadwal_id and self.jadwal.posyandu_id not in active_posyandu_ids(self.bidan_pelaksana):
                raise ValidationError({"bidan_pelaksana": "Bidan tidak termasuk cakupan Posyandu pada jadwal ini."})

        if self.peserta_id and self.jadwal_id:
            if self.peserta.posko_id != self.jadwal.posyandu_id:
                raise ValidationError(
                    "Peserta dan jadwal harus berasal dari Posyandu yang sama."
                )
            if self.jadwal.jns_kegiatan != "Imunisasi":
                raise ValidationError("Imunisasi hanya dapat dicatat pada jadwal imunisasi.")

        pilihan = dict(
            self.VAKSIN_BALITA if self.is_balita else self.VAKSIN_BUMIL
        ) if self.peserta_id else {}
        if self.peserta_id and self.jenis_vaksin not in pilihan:
            raise ValidationError({"jenis_vaksin": "Vaksin tidak sesuai jenis peserta."})

        if self.peserta_id:
            if self.is_balita:
                self.usia_kehamilan = None
            elif self.is_bumil:
                self.usia_saat_vaksin = None
                if not self.usia_kehamilan or not 1 <= self.usia_kehamilan <= 45:
                    raise ValidationError({
                        "usia_kehamilan": "Usia kehamilan harus antara 1–45 minggu."
                    })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    # =====================================================
    # HELPER JENIS PESERTA
    # =====================================================
    @property
    def is_balita(self):

        return (
            self.peserta.status_peserta
            == "balita"
        )

    @property
    def is_bumil(self):

        return (
            self.peserta.status_peserta
            == "bumil"
        )

    # =====================================================
    # FORMAT USIA VAKSIN
    # =====================================================
    @property
    def usia_vaksin_display(self):

        if self.is_bumil:

            if self.usia_kehamilan is None:
                return "-"

            return (
                f"{self.usia_kehamilan} Minggu"
            )

        if self.jenis_vaksin == "HB-0":
            return "0-24 Jam"

        if self.usia_saat_vaksin is None:
            return "-"

        return (
            f"{self.usia_saat_vaksin} Bulan"
        )


# =========================================================
# PEMERIKSAAN IBU HAMIL
# =========================================================
class PemeriksaanBumil(models.Model):

    STATUS_KEHAMILAN = [
        ('normal', 'Normal'),
        ('resiko', 'Risiko Tinggi'),
        ('anemia', 'Anemia'),
        ('kek', 'KEK'),
    ]

    id_periksa = models.AutoField(
        primary_key=True
    )

    peserta = models.ForeignKey(
        Peserta,
        on_delete=models.PROTECT,
        related_name='pemeriksaan_bumil'
    )

    petugas = models.ForeignKey(
        Petugas,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pemeriksaan_bumil'
    )

    bidan_pelaksana = models.ForeignKey(
        Petugas,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pemeriksaan_bumil_sebagai_bidan',
        limit_choices_to={'level': 'bidan'},
        help_text='Bidan/tenaga kesehatan pendamping pemeriksaan',
    )

    jadwal = models.ForeignKey(
        JadwalKegiatan,
        on_delete=models.PROTECT,
        related_name="pemeriksaan_bumil"
    )

    tgl_pemeriksaan = models.DateTimeField(
        default=timezone.now
    )

    # =====================================================
    # DATA KEHAMILAN
    # =====================================================
    usia_kehamilan = models.IntegerField(
        help_text="Usia kehamilan dalam minggu"
    )

    berat_badan = models.FloatField(
        help_text="Kg",
        null=True,
        blank=True
    )

    tinggi_badan = models.FloatField(
        help_text="Cm",
        null=True,
        blank=True
    )

    lila_bumil = models.FloatField(
        help_text="Lingkar Lengan Atas"
    )

    tekanan_darah = models.CharField(
        max_length=20,
        help_text="Contoh: 120/80"
    )

    tinggi_fundus = models.FloatField(
        null=True,
        blank=True,
        help_text="Cm"
    )

    denyut_jantung_janin = models.IntegerField(
        null=True,
        blank=True,
        help_text="DJJ"
    )

    hemoglobin = models.FloatField(
        null=True,
        blank=True,
        help_text="Hb"
    )

    # =====================================================
    # HASIL PEMERIKSAAN
    # =====================================================
    status_kehamilan = models.CharField(
        max_length=30,
        choices=STATUS_KEHAMILAN,
        default='normal'
    )

    # =====================================================
    # KELUHAN
    # =====================================================
    keluhan = models.TextField(
        null=True,
        blank=True
    )

    catatan = models.TextField(
        null=True,
        blank=True
    )

    # =====================================================
    # RUJUKAN
    # =====================================================
    perlu_rujukan = models.BooleanField(
        default=False
    )

    tujuan_rujukan = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    class Meta:
        db_table = "pemeriksaan_bumil"
        ordering = ['-tgl_pemeriksaan']

        verbose_name = "Pemeriksaan Ibu Hamil"
        verbose_name_plural = "Pemeriksaan Ibu Hamil"
        constraints = [
            models.UniqueConstraint(
                fields=['peserta', 'jadwal'],
                name='unique_pemeriksaan_bumil_peserta_jadwal',
            )
        ]

    def __str__(self):

        return (
            f"{self.peserta.nama_peserta} - "
            f"Bumil"
        )

    def clean(self):
        super().clean()

        if self.petugas_id and self.petugas.level != "kader":
            raise ValidationError("Pemeriksaan ibu hamil hanya dapat dicatat oleh Kader.")

        if self.bidan_pelaksana_id:
            if self.bidan_pelaksana.level != "bidan":
                raise ValidationError({"bidan_pelaksana": "Pelaksana harus merupakan data Bidan."})
            from common.access import active_posyandu_ids
            if self.jadwal_id and self.jadwal.posyandu_id not in active_posyandu_ids(self.bidan_pelaksana):
                raise ValidationError({"bidan_pelaksana": "Bidan tidak termasuk cakupan Posyandu pada jadwal ini."})

        if self.peserta_id and self.peserta.status_peserta != "bumil":
            raise ValidationError("Pemeriksaan ibu hamil hanya untuk peserta ibu hamil.")
        if (
            self.peserta_id and self.jadwal_id
            and self.peserta.posko_id != self.jadwal.posyandu_id
        ):
            raise ValidationError("Peserta dan jadwal harus berasal dari Posyandu yang sama.")
        if not 1 <= self.usia_kehamilan <= 45:
            raise ValidationError({
                "usia_kehamilan": "Usia kehamilan harus antara 1–45 minggu."
            })
        tekanan = (self.tekanan_darah or "").strip()
        match = re.fullmatch(r"(\d{2,3})\s*/\s*(\d{2,3})", tekanan)
        if not match:
            raise ValidationError({
                "tekanan_darah": "Tekanan darah harus menggunakan format sistolik/diastolik, contoh 120/80."
            })
        sistolik, diastolik = map(int, match.groups())
        if not (60 <= sistolik <= 250 and 30 <= diastolik <= 150):
            raise ValidationError({"tekanan_darah": "Nilai tekanan darah di luar rentang input yang wajar."})

        # LiLA < 23,5 cm ditandai otomatis sebagai KEK agar status tidak
        # hanya bergantung pada pilihan manual Kader.
        if self.lila_bumil is not None and self.lila_bumil < 23.5 and self.status_kehamilan == 'normal':
            self.status_kehamilan = 'kek'
        if self.perlu_rujukan and not self.tujuan_rujukan:
            raise ValidationError({
                "tujuan_rujukan": "Tujuan rujukan wajib diisi jika perlu rujukan."
            })

    def save(self, *args, **kwargs):
        if self._state.adding and self.jadwal_id and self.jadwal.tgl_kegiatan:
            jam = self.jadwal.jam_mulai or datetime.min.time()
            value = datetime.combine(self.jadwal.tgl_kegiatan, jam)
            self.tgl_pemeriksaan = timezone.make_aware(value) if timezone.is_naive(value) else value
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def sistolik(self):
        match = re.fullmatch(r"(\d{2,3})\s*/\s*(\d{2,3})", (self.tekanan_darah or "").strip())
        return int(match.group(1)) if match else None

    @property
    def diastolik(self):
        match = re.fullmatch(r"(\d{2,3})\s*/\s*(\d{2,3})", (self.tekanan_darah or "").strip())
        return int(match.group(2)) if match else None

    @property
    def tekanan_darah_tinggi(self):
        return bool(
            self.sistolik is not None
            and self.diastolik is not None
            and (self.sistolik >= 140 or self.diastolik >= 90)
        )

    # =====================================================
    # PROPERTY
    # =====================================================
    @property
    def petugas_nama(self):

        return (
            self.petugas.nama
            if self.petugas
            else "-"
        )


# =========================================================
# FUNGSI BANTU KEHADIRAN OTOMATIS
# =========================================================
def tandai_peserta_hadir(instance):
    """
    Membuat atau memperbarui data kehadiran peserta
    menjadi hadir ketika peserta menerima pelayanan
    pada suatu jadwal kegiatan.

    Digunakan oleh:
    1. PemeriksaanBalita
    2. PemeriksaanBumil
    3. Imunisasi
    """

    peserta_id = getattr(
        instance,
        "peserta_id",
        None
    )

    jadwal_id = getattr(
        instance,
        "jadwal_id",
        None
    )

    # Pemeriksaan/pelayanan tidak dapat dicatat
    # sebagai kehadiran apabila peserta atau
    # jadwal tidak tersedia.
    if not peserta_id or not jadwal_id:
        return

    Kehadiran.objects.update_or_create(
        peserta_id=peserta_id,
        jadwal_id=jadwal_id,
        defaults={
            "status_kehadiran": "hadir"
        }
    )


# =========================================================
# SIGNAL PEMERIKSAAN BALITA
# =========================================================
@receiver(
    post_save,
    sender=PemeriksaanBalita,
    dispatch_uid="otomatis_absen_pemeriksaan_balita"
)
def otomatis_absen_balita(
    sender,
    instance,
    created,
    **kwargs
):
    """
    Peserta otomatis dinyatakan hadir ketika
    data pemeriksaan balita dibuat atau diperbarui.
    """

    tandai_peserta_hadir(instance)


# =========================================================
# SIGNAL PEMERIKSAAN IBU HAMIL
# =========================================================
@receiver(
    post_save,
    sender=PemeriksaanBumil,
    dispatch_uid="otomatis_absen_pemeriksaan_bumil"
)
def otomatis_absen_bumil(
    sender,
    instance,
    created,
    **kwargs
):
    """
    Peserta otomatis dinyatakan hadir ketika
    pemeriksaan ibu hamil dibuat atau diperbarui.
    """

    tandai_peserta_hadir(instance)


# =========================================================
# SIGNAL IMUNISASI
# =========================================================
@receiver(
    post_save,
    sender=Imunisasi,
    dispatch_uid="otomatis_absen_imunisasi"
)
def otomatis_absen_imunisasi(
    sender,
    instance,
    created,
    **kwargs
):
    """
    Peserta otomatis dinyatakan hadir ketika
    data imunisasi dibuat atau diperbarui.
    """

    tandai_peserta_hadir(instance)
