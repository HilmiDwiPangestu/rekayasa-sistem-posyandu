from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Petugas
from apps.pemeriksaan.helper.imunisasi import get_dosis_otomatis, get_vaksin_rekomendasi_balita
from apps.pemeriksaan.forms import PemeriksaanBalitaForm, PemeriksaanBumilForm
from apps.pemeriksaan.models import Imunisasi, PemeriksaanBumil
from apps.peserta.models import Peserta
from apps.posyandu.models import JadwalKegiatan, Posyandu


class PemeriksaanServiceTests(TestCase):
    def setUp(self):
        self.posyandu = Posyandu.objects.create(nama="Pos Pemeriksaan")
        self.user = User.objects.create_user("kader-uji", password="aman-12345")
        Petugas.objects.create(
            user=self.user,
            nama="Kader Uji",
            level="kader",
            posyandu=self.posyandu,
        )
        self.bidan = Petugas.objects.create(
            nama="Bidan Otomatis",
            level="bidan",
            posyandu=self.posyandu,
        )
        self.peserta = Peserta.objects.create(
            posko=self.posyandu,
            nama_peserta="Balita Uji",
            tgl_lahir=date.today() - timedelta(days=95),
            alamat="Alamat",
            no_hp="080000000002",
            status_peserta="balita",
            jenis_kelamin="Laki-Laki",
        )
        self.jadwal = JadwalKegiatan.objects.create(
            tgl_kegiatan=date.today(),
            jam_mulai=time(8),
            jam_selesai=time(10),
            jns_kegiatan="Imunisasi",
            posyandu=self.posyandu,
        )

    def test_kader_dapat_membuka_daftar_peserta(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse(
            "pemeriksaan:list_peserta",
            args=["balita", self.jadwal.pk],
        ))
        self.assertEqual(response.status_code, 200)

    def test_form_balita_tidak_memiliki_input_bidan(self):
        form = PemeriksaanBalitaForm(peserta=self.peserta, jadwal=self.jadwal)
        self.assertNotIn("bidan_pelaksana", form.fields)

    def test_pemeriksaan_balita_menampilkan_bidan_otomatis_dari_posyandu(self):
        jadwal_rutin = JadwalKegiatan.objects.create(
            tgl_kegiatan=date.today(),
            jam_mulai=time(10),
            jam_selesai=time(12),
            jns_kegiatan="Pemeriksaan Rutin",
            posyandu=self.posyandu,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse(
            "pemeriksaan:periksa_peserta",
            args=["balita", jadwal_rutin.pk, self.peserta.pk],
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["bidan_otomatis"], self.bidan)
        self.assertNotIn("bidan_pelaksana", response.context["form"].fields)

    def test_form_bumil_tidak_memiliki_input_bidan(self):
        form = PemeriksaanBumilForm(jadwal=self.jadwal)
        self.assertNotIn("bidan_pelaksana", form.fields)

    def test_pemeriksaan_bumil_menampilkan_bidan_otomatis_dari_posyandu(self):
        peserta_bumil = Peserta.objects.create(
            posko=self.posyandu,
            nama_peserta="Ibu Hamil Uji",
            tgl_lahir=date.today() - timedelta(days=25 * 365),
            alamat="Alamat Bumil",
            no_hp="080000000003",
            status_peserta="bumil",
            jenis_kelamin="Perempuan",
        )
        jadwal_rutin = JadwalKegiatan.objects.create(
            tgl_kegiatan=date.today(),
            jam_mulai=time(10),
            jam_selesai=time(12),
            jns_kegiatan="Pemeriksaan Rutin",
            posyandu=self.posyandu,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse(
            "pemeriksaan:periksa_peserta",
            args=["bumil", jadwal_rutin.pk, peserta_bumil.pk],
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["bidan_otomatis"], self.bidan)
        self.assertNotIn("bidan_pelaksana", response.context["form"].fields)

    def test_post_bumil_mengabaikan_bidan_dari_browser_dan_memakai_bidan_otomatis(self):
        peserta_bumil = Peserta.objects.create(
            posko=self.posyandu,
            nama_peserta="Ibu Hamil POST",
            tgl_lahir=date.today() - timedelta(days=24 * 365),
            alamat="Alamat Bumil",
            no_hp="080000000004",
            status_peserta="bumil",
            jenis_kelamin="Perempuan",
        )
        jadwal_rutin = JadwalKegiatan.objects.create(
            tgl_kegiatan=date.today(),
            jam_mulai=time(10),
            jam_selesai=time(12),
            jns_kegiatan="Pemeriksaan Rutin",
            posyandu=self.posyandu,
        )
        pos_lain = Posyandu.objects.create(nama="Pos Lain")
        bidan_lain = Petugas.objects.create(
            nama="Bidan Manipulasi",
            level="bidan",
            posyandu=pos_lain,
        )

        self.client.force_login(self.user)
        response = self.client.post(
            reverse(
                "pemeriksaan:periksa_peserta",
                args=["bumil", jadwal_rutin.pk, peserta_bumil.pk],
            ),
            {
                "bidan_pelaksana": bidan_lain.pk,
                "usia_kehamilan": 20,
                "berat_badan": 55,
                "tinggi_badan": 155,
                "lila_bumil": 25,
                "tekanan_darah": "120/80",
                "tinggi_fundus": 20,
                "denyut_jantung_janin": 140,
                "hemoglobin": 12,
                "status_kehamilan": "normal",
                "keluhan": "",
                "catatan": "",
                "tujuan_rujukan": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        pemeriksaan = PemeriksaanBumil.objects.get(
            peserta=peserta_bumil,
            jadwal=jadwal_rutin,
        )
        self.assertEqual(pemeriksaan.bidan_pelaksana, self.bidan)
        self.assertNotEqual(pemeriksaan.bidan_pelaksana, bidan_lain)

    def test_rekomendasi_mencakup_vaksin_terlewat(self):
        rekomendasi = get_vaksin_rekomendasi_balita(self.peserta, date.today())
        self.assertIn("BCG", rekomendasi)
        self.assertIn("DPT-HB-Hib 1", rekomendasi)

    def test_form_imunisasi_mengirim_vaksin_yang_sudah_diberikan(self):
        Imunisasi.objects.create(
            peserta=self.peserta,
            petugas=self.user.petugas,
            jadwal=self.jadwal,
            jenis_vaksin="BCG",
            dosis="1",
            usia_saat_vaksin=3,
            tgl_pemberian=self.jadwal.tgl_kegiatan,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse(
            "pemeriksaan:periksa_peserta",
            args=["balita", self.jadwal.pk, self.peserta.pk],
        ))

        self.assertEqual(response.status_code, 200)
        self.assertIn("BCG", response.context["vaksin_sudah"])

    def test_dosis_otomatis_hanya_menggunakan_vaksin_aktif(self):
        self.assertEqual(get_dosis_otomatis("DPT-HB-Hib 3"), "3")
        self.assertEqual(get_dosis_otomatis("DPT-HB-Hib 4"), "4")
        self.assertEqual(get_dosis_otomatis("PCV 3"), "3")
        self.assertEqual(get_dosis_otomatis("Rotavirus 3"), "3")
        self.assertEqual(get_dosis_otomatis("IPV 2"), "2")
        self.assertEqual(get_dosis_otomatis("MR 2"), "2")
        self.assertIsNone(get_dosis_otomatis("DPT-HB-Hib Booster"))

    def test_detail_deteksi_stunting_tidak_error_karena_z_score_valid(self):
        from apps.pemeriksaan.models import PemeriksaanBalita

        pemeriksaan = PemeriksaanBalita.objects.create(
            peserta=self.peserta,
            petugas=self.user.petugas,
            jadwal=self.jadwal,
            berat_badan=8.5,
            tinggi_badan=72.0,
            z_score=-2.5,
            status_gizi="stunting",
            hsl_prediksi="Stunting",
            prob_ml=87.25,
        )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse(
                "pemeriksaan:detail_deteksi_stunting",
                args=[pemeriksaan.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["detail_data"]["z_score_valid"])
        self.assertEqual(
            response.context["detail_data"]["kesesuaian"],
            "Sesuai",
        )

    def test_vaksin_tidak_sesuai_jenis_peserta_ditolak(self):
        imunisasi = Imunisasi(
            peserta=self.peserta,
            petugas=self.user.petugas,
            jadwal=self.jadwal,
            jenis_vaksin="TT-1",
            dosis="1",
            usia_saat_vaksin=3,
        )
        with self.assertRaises(Exception):
            imunisasi.full_clean()


class PemeriksaanModelValidationTests(TestCase):
    def setUp(self):
        self.pos = Posyandu.objects.create(nama="Pos Validasi")
        self.user = User.objects.create_user("kader-validasi", password="aman-12345")
        self.petugas = Petugas.objects.create(
            user=self.user,
            nama="Kader Validasi",
            level="kader",
            posyandu=self.pos,
        )
        self.balita = Peserta.objects.create(
            posko=self.pos,
            nama_peserta="Balita Validasi",
            tgl_lahir=date.today() - timedelta(days=365),
            alamat="Alamat",
            no_hp="081230000001",
            status_peserta="balita",
            jenis_kelamin="Perempuan",
        )
        self.bumil = Peserta.objects.create(
            posko=self.pos,
            nama_peserta="Bumil Validasi",
            tgl_lahir=date.today() - timedelta(days=25 * 365),
            alamat="Alamat",
            no_hp="081230000002",
            status_peserta="bumil",
            jenis_kelamin="Perempuan",
        )
        self.jadwal = JadwalKegiatan.objects.create(
            tgl_kegiatan=date.today(),
            jam_mulai=time(8),
            jam_selesai=time(10),
            jns_kegiatan="Pemeriksaan Rutin",
            posyandu=self.pos,
        )

    def test_pemeriksaan_balita_menghitung_usia_bulan_dan_hari(self):
        from apps.pemeriksaan.models import PemeriksaanBalita

        obj = PemeriksaanBalita.objects.create(
            peserta=self.balita,
            petugas=self.petugas,
            jadwal=self.jadwal,
            berat_badan=8.0,
            tinggi_badan=70.0,
        )
        self.assertIsNotNone(obj.usia_bulan)
        self.assertGreaterEqual(obj.usia_bulan, 0)
        self.assertIsNotNone(obj.usia_hari)
        self.assertGreaterEqual(obj.usia_hari, 0)

    def test_pemeriksaan_bumil_menolak_peserta_balita(self):
        from apps.pemeriksaan.models import PemeriksaanBumil

        obj = PemeriksaanBumil(
            peserta=self.balita,
            petugas=self.petugas,
            jadwal=self.jadwal,
            usia_kehamilan=20,
            lila_bumil=25,
            tekanan_darah="120/80",
        )
        with self.assertRaises(Exception):
            obj.full_clean()

    def test_rujukan_bumil_wajib_memiliki_tujuan(self):
        from apps.pemeriksaan.models import PemeriksaanBumil

        obj = PemeriksaanBumil(
            peserta=self.bumil,
            petugas=self.petugas,
            jadwal=self.jadwal,
            usia_kehamilan=20,
            lila_bumil=25,
            tekanan_darah="120/80",
            perlu_rujukan=True,
            tujuan_rujukan="",
        )
        with self.assertRaises(Exception):
            obj.full_clean()


class PemeriksaanAnalysisServiceTests(TestCase):
    def test_validasi_z_score(self):
        from apps.pemeriksaan.services import z_score_valid

        self.assertTrue(z_score_valid(-2.5))
        self.assertTrue(z_score_valid(6))
        self.assertFalse(z_score_valid(6.1))
        self.assertFalse(z_score_valid(None))
        self.assertFalse(z_score_valid("bukan-angka"))

    def test_kesesuaian_who_dan_random_forest(self):
        from apps.pemeriksaan.services import hitung_kesesuaian

        self.assertEqual(hitung_kesesuaian(-2.5, "stunting", "Stunting"), "Sesuai")
        self.assertEqual(hitung_kesesuaian(-2.5, "stunting", "Tidak Stunting"), "Tidak Sesuai")
        self.assertEqual(hitung_kesesuaian(7, "stunting", "Stunting"), "Tidak Dapat Dinilai")

    def test_format_probabilitas_tidak_mengubah_skala(self):
        from apps.pemeriksaan.services import format_probabilitas_stunting

        self.assertEqual(format_probabilitas_stunting(67.219), 67.22)
        self.assertEqual(format_probabilitas_stunting(0), 0.0)
        self.assertIsNone(format_probabilitas_stunting(None))


class PemeriksaanJadwalUiRegressionTests(TestCase):
    def test_halaman_pemeriksaan_tidak_memiliki_aksi_edit_hapus_jadwal(self):
        from pathlib import Path
        from django.conf import settings

        template = (
            Path(settings.BASE_DIR) / "templates" / "pemeriksaan" / "list.html"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Edit Data Jadwal", template)
        self.assertNotIn("Hapus Data Jadwal", template)
        self.assertNotIn("openActionModal", template)
        self.assertIn("Cek Peserta", template)


class KaderOnlyOperationalRegressionTests(TestCase):
    def setUp(self):
        self.pos = Posyandu.objects.create(nama="Pos Role Operasional")
        self.admin_user = User.objects.create_user("admin-operasional", password="aman-12345")
        Petugas.objects.create(user=self.admin_user, nama="Admin Operasional", level="admin")
        self.kader_user = User.objects.create_user("kader-operasional", password="aman-12345")
        self.kader = Petugas.objects.create(
            user=self.kader_user, nama="Kader Operasional", level="kader", posyandu=self.pos
        )
        self.peserta = Peserta.objects.create(
            posko=self.pos, nama_peserta="Balita Operasional",
            tgl_lahir=date.today() - timedelta(days=365), alamat="Alamat",
            no_hp="081234560001", status_peserta="balita", jenis_kelamin="Perempuan",
        )
        self.jadwal = JadwalKegiatan.objects.create(
            tgl_kegiatan=date.today(), jam_mulai=time(8), jam_selesai=time(10),
            jns_kegiatan="Pemeriksaan Rutin", posyandu=self.pos,
        )

    def test_admin_dilarang_membuka_input_pemeriksaan(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse(
            "pemeriksaan:periksa_peserta",
            args=["balita", self.jadwal.pk, self.peserta.pk],
        ))
        self.assertEqual(response.status_code, 403)

    def test_kader_dapat_membuka_input_pemeriksaan(self):
        self.client.force_login(self.kader_user)
        response = self.client.get(reverse(
            "pemeriksaan:periksa_peserta",
            args=["balita", self.jadwal.pk, self.peserta.pk],
        ))
        self.assertEqual(response.status_code, 200)
