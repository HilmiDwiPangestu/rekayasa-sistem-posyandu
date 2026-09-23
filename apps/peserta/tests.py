from datetime import date
from decimal import Decimal
from io import StringIO

from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.urls import reverse

from common.testing import make_petugas, make_peserta, make_posyandu
from apps.posyandu.models import PenugasanPetugas

from .forms import PesertaForm
from .models import Peserta
from .services import (
    filter_peserta,
    peserta_accessible_to,
    subtract_years,
)


class PesertaModelTests(TestCase):
    def test_usia_detail_dan_bulan_tidak_negatif(self):
        pos = make_posyandu()
        lahir = date.today() - relativedelta(years=2, months=3, days=5)
        peserta = Peserta.objects.create(
            posko=pos,
            nama_peserta="Balita Usia",
            tgl_lahir=lahir,
            alamat="Alamat",
            no_hp="081200000100",
            status_peserta="balita",
            jenis_kelamin="Perempuan",
        )
        expected = relativedelta(date.today(), lahir)
        self.assertEqual(peserta.usia_detail["tahun"], expected.years)
        self.assertEqual(peserta.usia_detail["bulan"], expected.months)
        self.assertEqual(peserta.usia_detail["hari"], expected.days)
        self.assertEqual(peserta.usia_bulan, expected.years * 12 + expected.months)

    def test_subtract_years_aman_untuk_29_februari(self):
        self.assertEqual(subtract_years(date(2024, 2, 29), 1), date(2023, 2, 28))

    def test_peserta_bukan_aktor_login(self):
        from django.core.exceptions import FieldDoesNotExist
        with self.assertRaises(FieldDoesNotExist):
            Peserta._meta.get_field("user")


class PesertaFormTests(TestCase):
    def setUp(self):
        self.pos = make_posyandu()
        self.base = {
            "nama_peserta": "Balita Form",
            "jenis_kelamin": "Perempuan",
            "tgl_lahir": "2024-01-01",
            "alamat": "Alamat",
            "no_hp": "081200000200",
            "is_tamu": "",
            "posko": self.pos.pk,
        }

    def test_peserta_tetap_wajib_posyandu(self):
        data = {**self.base, "posko": ""}
        form = PesertaForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("posko", form.errors)

    def test_peserta_tamu_wajib_asal_posyandu(self):
        data = {**self.base, "is_tamu": "on", "asal_posyandu": ""}
        form = PesertaForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("asal_posyandu", form.errors)

    def test_validasi_antropometri_lahir(self):
        data = {**self.base, "bb_lahir": Decimal("9.00")}
        form = PesertaForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("bb_lahir", form.errors)

    def test_form_menerima_posyandu_queryset_tanpa_error(self):
        form = PesertaForm(posyandu_queryset=type(self.pos).objects.filter(pk=self.pos.pk))
        self.assertEqual(list(form.fields["posko"].queryset), [self.pos])

    def test_bumil_hanya_perempuan(self):
        data = {**self.base, "jenis_kelamin": "Laki-Laki"}
        form = PesertaForm(data=data, status_peserta="bumil")
        self.assertFalse(form.is_valid())
        self.assertIn("jenis_kelamin", form.errors)


class PesertaServiceAndAccessTests(TestCase):
    def setUp(self):
        self.pos_a = make_posyandu("Pos A")
        self.pos_b = make_posyandu("Pos B")
        self.user, _ = make_petugas(username="kader-peserta", level="kader", posyandu=self.pos_a)
        self.a = make_peserta(posyandu=self.pos_a, nama="Peserta A", no_hp="081200000301")
        self.b = make_peserta(posyandu=self.pos_b, nama="Peserta B", no_hp="081200000302")

    def test_kader_hanya_melihat_posyandunya(self):
        qs = peserta_accessible_to(self.user)
        self.assertEqual(list(qs.order_by("pk")), [self.a])

    def test_penugasan_tambahan_tidak_mengubah_posyandu_operasional_kader(self):
        from datetime import date as _date

        PenugasanPetugas.objects.create(
            petugas=self.user.petugas,
            posyandu=self.pos_b,
            tanggal_daftar=_date.today(),
        )

        qs = peserta_accessible_to(self.user)
        self.assertEqual(set(qs.values_list("pk", flat=True)), {self.a.pk})

    def test_filter_search(self):
        qs = filter_peserta(Peserta.objects.all(), status_peserta="balita", search="Peserta A")
        self.assertEqual(list(qs), [self.a])

    def test_delete_hanya_post(self):
        self.client.force_login(self.user)
        url = reverse("peserta:delete", args=["balita", self.a.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(Peserta.objects.filter(pk=self.a.pk).exists())


class PesertaAdminCreateTests(TestCase):
    def test_admin_dilarang_menambah_peserta(self):
        pos = make_posyandu("Pos Pilihan Admin")
        admin, _ = make_petugas(username="admin-peserta-create", level="admin", posyandu=None)
        self.client.force_login(admin)
        response = self.client.post(reverse("peserta:create", args=["balita"]), {
            "nama_peserta": "Balita Admin",
            "jenis_kelamin": "Perempuan",
            "tgl_lahir": "2024-01-01",
            "alamat": "Alamat",
            "no_hp": "081211111111",
            "posko": pos.pk,
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Peserta.objects.filter(nama_peserta="Balita Admin").exists())


class KaderScopeRegressionTests(TestCase):
    def test_list_peserta_kader_menampilkan_data_posyandu_utamanya(self):
        pos = make_posyandu("Pos Scope Kader")
        user, petugas = make_petugas(username="kader-scope-reg", level="kader", posyandu=pos)
        peserta = make_peserta(posyandu=pos, nama="Balita Scope", no_hp="081299999901")
        self.client.force_login(user)
        response = self.client.get(reverse("peserta:list", args=["balita"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, peserta.nama_peserta)

    def test_empty_state_kader_menyebut_posyandu(self):
        pos = make_posyandu("Pos Tanpa Peserta")
        user, _ = make_petugas(username="kader-empty-reg", level="kader", posyandu=pos)
        self.client.force_login(user)
        response = self.client.get(reverse("peserta:list", args=["balita"]))
        self.assertContains(response, "Pos Tanpa Peserta")
