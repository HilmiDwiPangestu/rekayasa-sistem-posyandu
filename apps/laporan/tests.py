from datetime import date
from io import BytesIO
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Petugas
from apps.peserta.models import Peserta
from apps.posyandu.models import Posyandu


class LaporanAccessTests(TestCase):
    def setUp(self):
        self.pos_a = Posyandu.objects.create(nama="Pos A")
        self.pos_b = Posyandu.objects.create(nama="Pos B")
        self.user = User.objects.create_user("kader-laporan", password="aman-12345")
        self.petugas = Petugas.objects.create(
            user=self.user,
            nama="Kader Laporan",
            level="kader",
            posyandu=self.pos_a,
        )
        Peserta.objects.create(
            posko=self.pos_b,
            nama_peserta="Data Pos Lain",
            tgl_lahir=date(2024, 1, 1),
            alamat="Alamat",
            no_hp="080000000001",
            status_peserta="balita",
            jenis_kelamin="Laki-Laki",
        )

    def test_laporan_wajib_login(self):
        response = self.client.get(reverse("laporan:laporan_bulanan"))
        self.assertEqual(response.status_code, 302)

    def test_laporan_hanya_memuat_posyandu_petugas(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("laporan:laporan_index"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_balita"], 0)

    def test_filter_periode_tidak_valid_tidak_menyebabkan_error(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("laporan:laporan_bulanan"),
            {"bulan": "99", "tahun": "tidak-valid"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["bulan"], 12)


class LaporanHelperTests(TestCase):
    def test_context_triwulan_memuat_identitas_posyandu(self):
        from apps.laporan.helper.utils import build_context_laporan_triwulan

        posyandu = Posyandu.objects.create(
            nama="Pos Mawar",
            desa="Lemahmekar",
        )
        context = build_context_laporan_triwulan(2026, 3, [posyandu.pk])

        self.assertEqual(context["kecamatan"], "Indramayu")
        self.assertEqual(context["puskesmas_nama"], "Margadadi")
        self.assertEqual(context["desa_nama"], "Lemahmekar")
        self.assertEqual(context["posyandu_nama"], "Pos Mawar")

    def test_rentang_triwulan(self):
        from apps.laporan.helper.utils import get_daftar_bulan_triwulan, get_rentang_triwulan

        awal, akhir = get_rentang_triwulan(2026, 3)
        self.assertEqual(awal, date(2026, 7, 1))
        self.assertEqual(akhir, date(2026, 9, 30))

        bulan = get_daftar_bulan_triwulan(2026, 4)
        self.assertEqual([item["bulan"] for item in bulan], [10, 11, 12])
        self.assertEqual(bulan[-1]["akhir"], date(2026, 12, 31))


class LaporanAdminKelurahanTests(TestCase):
    def test_admin_kelurahan_melihat_seluruh_posyandu(self):
        pos_a = Posyandu.objects.create(nama="Pos Laporan A")
        pos_b = Posyandu.objects.create(nama="Pos Laporan B")
        user = User.objects.create_user("admin-laporan", password="aman-12345")
        Petugas.objects.create(user=user, nama="Admin Laporan", level="admin")

        for index, pos in enumerate((pos_a, pos_b), start=1):
            Peserta.objects.create(
                posko=pos,
                nama_peserta=f"Balita Laporan {index}",
                tgl_lahir=date(2024, 1, index),
                alamat="Alamat",
                no_hp=f"08120002000{index}",
                status_peserta="balita",
                jenis_kelamin="Perempuan",
            )

        self.client.force_login(user)
        response = self.client.get(reverse("laporan:laporan_index"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_balita"], 2)


class LaporanTriwulanFilterAdminTests(TestCase):
    def test_admin_triwulan_dapat_memilih_satu_posyandu(self):
        pos_a = Posyandu.objects.create(nama="Pos Triwulan A")
        pos_b = Posyandu.objects.create(nama="Pos Triwulan B")
        user = User.objects.create_user("admin-triwulan-filter", password="aman-12345")
        Petugas.objects.create(user=user, nama="Admin Triwulan", level="admin")

        self.client.force_login(user)
        response = self.client.get(
            reverse("laporan:laporan_triwulan"),
            {"tahun": 2026, "triwulan": 3, "posyandu": pos_b.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_admin_kelurahan"])
        self.assertEqual(response.context["selected_posyandu_id"], pos_b.pk)
        self.assertEqual(response.context["posyandu_nama"], pos_b.nama)
        self.assertEqual(
            [item.pk for item in response.context["daftar_posyandu_filter"]],
            [pos_a.pk, pos_b.pk],
        )

    def test_admin_triwulan_default_memilih_posyandu_pertama(self):
        pos_b = Posyandu.objects.create(nama="Pos Triwulan B")
        pos_a = Posyandu.objects.create(nama="Pos Triwulan A")
        user = User.objects.create_user("admin-triwulan-default", password="aman-12345")
        Petugas.objects.create(user=user, nama="Admin Default", level="admin")

        self.client.force_login(user)
        response = self.client.get(
            reverse("laporan:laporan_triwulan"),
            {"tahun": 2026, "triwulan": 3},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_posyandu_id"], pos_a.pk)
        self.assertEqual(response.context["posyandu_nama"], pos_a.nama)


class LaporanTriwulanPdfAdminTests(TestCase):
    @staticmethod
    def _pdf_satu_halaman(*args, **kwargs):
        output = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=842, height=595)
        writer.write(output)
        output.seek(0)
        return output

    def setUp(self):
        self.pos_a = Posyandu.objects.create(nama="Pos PDF A")
        self.pos_b = Posyandu.objects.create(nama="Pos PDF B")
        self.user = User.objects.create_user(
            "admin-triwulan-pdf",
            password="aman-12345",
        )
        Petugas.objects.create(
            user=self.user,
            nama="Admin PDF",
            level="admin",
        )
        self.client.force_login(self.user)

    @patch(
        "apps.laporan.views._render_pdf_triwulan_satu_posyandu",
        side_effect=_pdf_satu_halaman.__func__,
    )
    def test_admin_download_posyandu_terpilih_hanya_satu_posyandu(self, mocked_render):
        response = self.client.get(
            reverse("laporan:export_laporan_triwulan_pdf"),
            {
                "tahun": 2026,
                "triwulan": 3,
                "jenis": "balita",
                "scope": "selected",
                "posyandu": self.pos_b.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(mocked_render.call_count, 1)
        self.assertEqual(len(PdfReader(BytesIO(response.content)).pages), 1)
        self.assertIn("pos-pdf-b", response["Content-Disposition"])

    @patch(
        "apps.laporan.views._render_pdf_triwulan_satu_posyandu",
        side_effect=_pdf_satu_halaman.__func__,
    )
    def test_admin_download_semua_posyandu_menjadi_satu_pdf(self, mocked_render):
        response = self.client.get(
            reverse("laporan:export_laporan_triwulan_pdf"),
            {
                "tahun": 2026,
                "triwulan": 3,
                "jenis": "balita",
                "scope": "all",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(mocked_render.call_count, 2)
        self.assertEqual(len(PdfReader(BytesIO(response.content)).pages), 2)
        self.assertIn("semua_posyandu", response["Content-Disposition"])
