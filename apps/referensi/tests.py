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
