from io import StringIO

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.deteksi.services.who_services import get_lms_values

from .models import WHOStandardPBU


class WHOStandardPBUModelTests(TestCase):
    def _create(self, **overrides):
        values = dict(
            gender="L", day=365, month=None, l_value=1.0, m_value=75.0, s_value=0.04, sd=3.0,
            sd4neg=63.0, sd3neg=66.0, sd2neg=69.0, sd1neg=72.0, sd0=75.0,
            sd1=78.0, sd2=81.0, sd3=84.0, sd4=87.0, source="WHO LFA expanded daily",
        )
        values.update(overrides)
        return WHOStandardPBU.objects.create(**values)

    def test_string_representation(self):
        obj = self._create()
        self.assertIn("365 hari", str(obj))

    def test_gender_hari_harus_unik(self):
        self._create()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create()

    def test_lms_dapat_diambil_oleh_service_who(self):
        obj = self._create()
        self.assertEqual(get_lms_values(obj), (1.0, 75.0, 0.04))


class WHODailyReferenceCalculationTests(TestCase):
    def test_perempuan_usia_183_hari_panjang_60_cm_stunting(self):
        from apps.deteksi.services.who_services import hitung_status_antropometri

        WHOStandardPBU.objects.create(
            gender="P",
            day=183,
            month=None,
            l_value=1.0,
            m_value=65.751,
            s_value=0.03448,
            sd=65.751 * 0.03448,
            sd4neg=56.683,
            sd3neg=58.950,
            sd2neg=61.217,
            sd1neg=63.484,
            sd0=65.751,
            sd1=68.018,
            sd2=70.285,
            sd3=72.552,
            sd4=74.819,
            source="WHO LFA expanded daily",
        )

        hasil = hitung_status_antropometri(
            umur_hari=183,
            jk="Perempuan",
            tinggi_badan=60.0,
        )
        self.assertAlmostEqual(hasil["z_score"], -2.5367, places=4)
        self.assertEqual(hasil["kode"], "stunting")
        self.assertEqual(hasil["kategori"], "Pendek")
        self.assertTrue(hasil["stunting"])

    def test_berdiri_di_bawah_24_bulan_dikoreksi_tambah_07_cm(self):
        from apps.deteksi.services.who_services import hitung_status_antropometri

        WHOStandardPBU.objects.create(
            gender="L", day=575, month=None, l_value=1.0, m_value=83.136,
            s_value=0.03306, sd=83.136 * 0.03306,
            sd4neg=72.142, sd3neg=74.891, sd2neg=77.639, sd1neg=80.388,
            sd0=83.136, sd1=85.884, sd2=88.633, sd3=91.381, sd4=94.130,
            source="WHO LFA expanded daily",
        )

        hasil = hitung_status_antropometri(
            umur_hari=575,
            jk="Laki-Laki",
            tinggi_badan=100.0,
            jenis_pengukuran="tinggi",
        )
        self.assertAlmostEqual(hasil["z_score"], 6.3905, places=4)

    def test_terlentang_mulai_24_bulan_dikoreksi_kurang_07_cm(self):
        from apps.deteksi.services.who_services import hitung_status_antropometri

        WHOStandardPBU.objects.create(
            gender="L", day=731, month=None, l_value=1.0, m_value=87.1303,
            s_value=0.03508, sd=87.1303 * 0.03508,
            sd4neg=74.904, sd3neg=77.961, sd2neg=81.017, sd1neg=84.074,
            sd0=87.130, sd1=90.187, sd2=93.243, sd3=96.300, sd4=99.356,
            source="WHO LFA expanded daily",
        )

        hasil = hitung_status_antropometri(
            umur_hari=731,
            jk="Laki-Laki",
            tinggi_badan=88.0,
            jenis_pengukuran="panjang",
        )
        # 88.0 cm terlentang -> 87.3 cm tinggi untuk referensi >=24 bulan.
        expected = ((87.3 / 87.1303) - 1.0) / 0.03508
        self.assertAlmostEqual(hasil["z_score"], expected, places=4)
