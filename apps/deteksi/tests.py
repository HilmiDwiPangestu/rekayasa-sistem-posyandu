from django.test import SimpleTestCase

from .services.random_forest import (
    EXPECTED_FEATURE_COLUMNS,
    check_model_ready,
    encode_gender,
    get_model_info,
    normalize_gender,
    prediksi_stunting_rf,
    validate_input,
)
from .services.who_services import (
    kategori_tb_u,
    koreksi_panjang_tinggi,
    normalize_gender_who,
    validate_age_day,
    validate_age_month,
    validate_height,
)


class RandomForestServiceTests(SimpleTestCase):
    def test_encoding_gender_konsisten_dengan_training(self):
        self.assertEqual(normalize_gender("Perempuan"), "F")
        self.assertEqual(normalize_gender("Laki-Laki"), "M")
        self.assertEqual(encode_gender("Perempuan"), 0)
        self.assertEqual(encode_gender("Laki-Laki"), 1)

    def test_gender_tidak_valid_ditolak(self):
        with self.assertRaises(ValueError):
            normalize_gender("tidak diketahui")

    def test_input_di_luar_rentang_ditolak(self):
        with self.assertRaises(ValueError):
            validate_input(age_month=60, weight_kg=10, height_cm=80)
        with self.assertRaises(ValueError):
            validate_input(age_month=12, weight_kg=0.5, height_cm=80)
        with self.assertRaises(ValueError):
            validate_input(age_month=12, weight_kg=10, height_cm=150)

    def test_model_final_siap_digunakan(self):
        health = check_model_ready()
        self.assertTrue(health["ready"], health.get("message"))
        self.assertEqual(health["prediction_method"], "model.predict")
        self.assertFalse(health["uses_manual_threshold"])
        self.assertEqual(health["features"], EXPECTED_FEATURE_COLUMNS)

    def test_model_dapat_melakukan_prediksi(self):
        hasil = prediksi_stunting_rf(
            gender="Laki-Laki",
            age_month=24,
            weight_kg=10.5,
            height_cm=82.0,
        )
        self.assertIn(hasil["label"], (0, 1))
        self.assertIn(hasil["status"], ("Stunting", "Tidak Stunting"))
        self.assertEqual(hasil["prediction_method"], "model.predict")
        self.assertNotIn("threshold", hasil)
        self.assertGreaterEqual(hasil["probability_stunted"], 0)
        self.assertLessEqual(hasil["probability_stunted"], 1)
        total = hasil["probability_stunted"] + hasil["probability_not_stunted"]
        self.assertAlmostEqual(total, 1.0, places=6)

    def test_metadata_model_final_tersedia(self):
        info = get_model_info()
        metadata = info.get("metadata", {})
        self.assertEqual(info["prediction_method"], "model.predict")
        self.assertFalse(info["uses_manual_threshold"])
        self.assertIn("created_at_utc", metadata)
        self.assertEqual(metadata.get("python_library_sklearn_version"), "1.9.0")


class WHOServiceTests(SimpleTestCase):
    def test_normalisasi_gender(self):
        self.assertEqual(normalize_gender_who("Laki-Laki"), "L")
        self.assertEqual(normalize_gender_who("Perempuan"), "P")

    def test_validasi_usia_dan_tinggi(self):
        self.assertEqual(validate_age_day("183"), 183)
        self.assertEqual(validate_age_month("12"), 12)
        self.assertEqual(validate_height("80.5"), 80.5)
        with self.assertRaises(ValueError):
            validate_age_day(1857)
        with self.assertRaises(ValueError):
            validate_age_month(60)
        with self.assertRaises(ValueError):
            validate_height(20)

    def test_koreksi_posisi_pengukuran(self):
        self.assertAlmostEqual(
            koreksi_panjang_tinggi(umur_hari=365, nilai=75.0, jenis_pengukuran="berdiri"),
            75.7,
        )
        self.assertAlmostEqual(
            koreksi_panjang_tinggi(umur_hari=900, nilai=90.0, jenis_pengukuran="terlentang"),
            89.3,
        )

    def test_kategori_tb_u(self):
        self.assertEqual(kategori_tb_u(-3.5)["kode"], "stunting_berat")
        self.assertEqual(kategori_tb_u(-2.5)["kode"], "stunting")
        self.assertEqual(kategori_tb_u(0)["kode"], "normal")
        self.assertEqual(kategori_tb_u(3.5)["kode"], "tinggi")
