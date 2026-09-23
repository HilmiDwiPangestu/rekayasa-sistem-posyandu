from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from common.testing import make_petugas, make_posyandu

from .models import Petugas
from .services import PetugasAccountError, create_petugas_account, normalize_phone_username


class PetugasModelTests(TestCase):
    def test_kader_wajib_memiliki_posyandu(self):
        user = User.objects.create_user("kader-tanpa-pos", password="aman-12345")
        with self.assertRaises(ValidationError):
            Petugas.objects.create(user=user, nama="Kader", level="kader")

    def test_admin_boleh_tanpa_posyandu(self):
        user = User.objects.create_user("admin-model", password="aman-12345")
        petugas = Petugas.objects.create(user=user, nama="Admin", level="admin")
        self.assertIsNone(petugas.posyandu)

    def test_bidan_tetap_memiliki_posyandu_utama(self):
        with self.assertRaises(ValidationError):
            Petugas.objects.create(nama="Bidan", level="bidan")

    def test_bidan_tidak_boleh_memiliki_akun_user(self):
        posyandu = make_posyandu("Pos Bidan Non Login")
        user = User.objects.create_user("bidan-tidak-boleh-login", password="aman-12345")
        with self.assertRaises(ValidationError):
            Petugas.objects.create(
                user=user,
                nama="Bidan Non Login",
                level="bidan",
                posyandu=posyandu,
            )


class PetugasAccountServiceTests(TestCase):
    def setUp(self):
        self.posyandu = make_posyandu()
        self.petugas = Petugas.objects.create(
            nama="Kader Baru",
            level="kader",
            posyandu=self.posyandu,
            no_telp="0812-3456 7890",
        )

    def test_normalisasi_nomor_telepon(self):
        self.assertEqual(normalize_phone_username("0812-3456 7890"), "081234567890")

    def test_buat_akun_menghubungkan_user_ke_petugas(self):
        result = create_petugas_account(self.petugas)
        self.petugas.refresh_from_db()
        self.assertEqual(result.username, "081234567890")
        self.assertEqual(self.petugas.user_id, result.user.id)
        self.assertTrue(result.user.check_password(result.temporary_password))

    def test_buat_akun_manual_menggunakan_username_dan_password_admin(self):
        result = create_petugas_account(
            self.petugas,
            username="kader.melati",
            password="SandiKader!2026",
        )
        self.petugas.refresh_from_db()
        self.assertEqual(result.username, "kader.melati")
        self.assertFalse(result.username_generated)
        self.assertFalse(result.password_generated)
        self.assertTrue(result.user.check_password("SandiKader!2026"))

    def test_username_manual_password_kosong_menghasilkan_password_otomatis(self):
        result = create_petugas_account(
            self.petugas,
            username="kader.manual",
        )
        self.assertEqual(result.username, "kader.manual")
        self.assertFalse(result.username_generated)
        self.assertTrue(result.password_generated)
        self.assertTrue(result.user.check_password(result.temporary_password))

    def test_akun_kedua_ditolak(self):
        create_petugas_account(self.petugas)
        self.petugas.refresh_from_db()
        with self.assertRaises(PetugasAccountError):
            create_petugas_account(self.petugas)

    def test_buat_akun_bidan_ditolak(self):
        posyandu = make_posyandu("Pos Bidan Service")
        bidan = Petugas.objects.create(
            nama="Bidan Service",
            level="bidan",
            posyandu=posyandu,
            no_telp="081255500001",
        )
        with self.assertRaises(PetugasAccountError):
            create_petugas_account(bidan)


class AccountViewTests(TestCase):
    def test_login_valid_masuk_dashboard(self):
        user, _ = make_petugas(username="kader-login", level="kader")
        response = self.client.post(reverse("accounts:login"), {
            "username": user.username,
            "password": "aman-12345",
        })
        self.assertRedirects(response, reverse("dashboard:index"))

    def test_logout_hanya_post(self):
        user, _ = make_petugas(username="kader-logout", level="kader")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))

    def test_register_hanya_admin(self):
        kader, _ = make_petugas(username="kader-register", level="kader")
        self.client.force_login(kader)
        self.assertEqual(self.client.get(reverse("accounts:register")).status_code, 403)

    def test_halaman_register_responsif_dan_tidak_memakai_width_tetap(self):
        admin, _ = make_petugas(username="admin-register-responsive", level="admin", posyandu=None)
        self.client.force_login(admin)
        response = self.client.get(reverse("accounts:register"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'max-w-2xl')
        self.assertContains(response, 'grid-cols-1')
        self.assertNotContains(response, 'width: 400px')
        self.assertNotContains(response, 'option value="bidan"')
        self.assertContains(response, 'Buat akun login Kader')


    def test_user_tanpa_profil_aktor_ditolak_login(self):
        User.objects.create_user("user-nonaktor", password="aman-12345")
        response = self.client.post(reverse("accounts:login"), {
            "username": "user-nonaktor",
            "password": "aman-12345",
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "hanya dapat diakses oleh Admin Kelurahan dan Kader")

    def test_database_menolak_relasi_user_ke_bidan(self):
        posyandu = make_posyandu("Pos Bidan Constraint")
        user = User.objects.create_user("bidan-constraint", password="aman-12345")
        bidan = Petugas.objects.create(
            nama="Bidan Constraint",
            level="bidan",
            posyandu=posyandu,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Petugas.objects.filter(pk=bidan.pk).update(user=user)

    def test_register_admin_baru_ditolak_dari_ui(self):
        admin, _ = make_petugas(username="admin-register-admin", level="admin", posyandu=None)
        pos = make_posyandu("Pos Register Admin")
        self.client.force_login(admin)
        response = self.client.post(reverse("accounts:register"), {
            "username": "admin-baru-terlarang",
            "password": "SandiKuat!2026",
            "password2": "SandiKuat!2026",
            "nama": "Admin Baru",
            "alamat": "Alamat",
            "no_telp": "081266600009",
            "level": "admin",
            "posyandu": str(pos.pk),
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(username="admin-baru-terlarang").exists())

    def test_register_bidan_ditolak_karena_bukan_aktor_login(self):
        admin, _ = make_petugas(username="admin-register-bidan", level="admin", posyandu=None)
        self.client.force_login(admin)
        response = self.client.post(reverse("accounts:register"), {
            "username": "akun-bidan-terlarang",
            "password": "SandiKuat!2026",
            "password2": "SandiKuat!2026",
            "nama": "Bidan Tanpa Login",
            "alamat": "Alamat",
            "no_telp": "081266600001",
            "level": "bidan",
            "posyandu": "",
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(username="akun-bidan-terlarang").exists())

    def test_register_kader_tanpa_posyandu_tidak_membuat_user_yatim(self):
        admin, _ = make_petugas(username="admin-register", level="admin", posyandu=None)
        self.client.force_login(admin)
        response = self.client.post(reverse("accounts:register"), {
            "username": "calon-kader",
            "password": "SandiKuat!2026",
            "password2": "SandiKuat!2026",
            "nama": "Calon Kader",
            "alamat": "Alamat",
            "no_telp": "081299999999",
            "level": "kader",
            "posyandu": "",
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(username="calon-kader").exists())


class RoleDecoratorTests(TestCase):
    def test_kader_ditolak_pada_view_admin(self):
        from django.http import HttpResponse
        from django.test import RequestFactory
        from common.decorators import admin_required

        user, _ = make_petugas(username="kader-decorator", level="kader")
        request = RequestFactory().get("/dummy/")
        request.user = user

        @admin_required
        def protected_view(request):
            return HttpResponse("ok")

        response = protected_view(request)
        self.assertEqual(response.status_code, 403)

    def test_admin_diizinkan_pada_view_admin(self):
        from django.http import HttpResponse
        from django.test import RequestFactory
        from common.decorators import admin_required

        user, _ = make_petugas(username="admin-decorator", level="admin", posyandu=None)
        request = RequestFactory().get("/dummy/")
        request.user = user

        @admin_required
        def protected_view(request):
            return HttpResponse("ok")

        response = protected_view(request)
        self.assertEqual(response.status_code, 200)

    def test_bidan_ditolak_pada_view_operasional(self):
        from types import SimpleNamespace
        from django.http import HttpResponse
        from django.test import RequestFactory
        from common.decorators import petugas_required

        pos = make_posyandu("Pos Bidan Decorator")
        bidan = Petugas.objects.create(nama="Bidan Non Aktor", level="bidan", posyandu=pos)
        request = RequestFactory().get("/dummy/")
        request.user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            petugas=bidan,
        )

        @petugas_required
        def protected_view(request):
            return HttpResponse("ok")

        response = protected_view(request)
        self.assertEqual(response.status_code, 403)


class AccountSettingsTests(TestCase):
    def test_setting_fallback_menampilkan_posyandu_petugas(self):
        posyandu = make_posyandu(name="Posyandu Fallback")
        user, _ = make_petugas(
            username="kader-setting-fallback",
            level="kader",
            posyandu=posyandu,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:setting"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Posyandu Fallback")

    def test_update_setting_tidak_dapat_memindahkan_posyandu_sendiri(self):
        posyandu_awal = make_posyandu(name="Posyandu Awal")
        posyandu_lain = make_posyandu(name="Posyandu Lain")
        user, petugas = make_petugas(
            username="kader-setting-posyandu",
            level="kader",
            posyandu=posyandu_awal,
        )
        self.client.force_login(user)

        response = self.client.post(reverse("accounts:updateSetting"), {
            "nama": petugas.nama,
            "username": user.username,
            "no_telp": petugas.no_telp,
            "alamat": petugas.alamat or "",
            "posyandu": str(posyandu_lain.pk),
        })

        self.assertEqual(response.status_code, 302)
        petugas.refresh_from_db()
        self.assertEqual(petugas.posyandu_id, posyandu_awal.pk)

    def test_update_setting_hanya_post(self):
        user, _ = make_petugas(username="kader-setting", level="kader")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("accounts:updateSetting")).status_code, 405)

    def test_username_dapat_diubah_dan_harus_unik(self):
        user, petugas = make_petugas(username="kader-setting-edit", level="kader")
        User.objects.create_user("username-terpakai", password="aman-12345")
        self.client.force_login(user)

        response = self.client.post(reverse("accounts:updateSetting"), {
            "nama": petugas.nama,
            "username": "kader-baru",
            "no_telp": petugas.no_telp,
            "alamat": petugas.alamat or "",
        })
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.username, "kader-baru")

        response = self.client.post(reverse("accounts:updateSetting"), {
            "nama": petugas.nama,
            "username": "username-terpakai",
            "no_telp": petugas.no_telp,
            "alamat": petugas.alamat or "",
        })
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.username, "kader-baru")


class TambahBidanCakupanTests(TestCase):
    def test_tambah_bidan_dapat_memilih_beberapa_posyandu(self):
        from apps.posyandu.models import PenugasanPetugas, Posyandu

        admin, _ = make_petugas(username="admin-tambah-bidan", level="admin", posyandu=None)
        pos1 = Posyandu.objects.create(nama="Pos Bidan 1", desa="Kelurahan A")
        pos2 = Posyandu.objects.create(nama="Pos Bidan 2", desa="Kelurahan A")
        self.client.force_login(admin)

        response = self.client.post(reverse("accounts:tambah_petugas", args=["bidan"]), {
            "nama": "Bidan Wilayah",
            "alamat": "Alamat",
            "no_telp": "081200099991",
            "cakupan_posyandu": [pos1.pk, pos2.pk],
        })

        self.assertEqual(response.status_code, 302)
        bidan = Petugas.objects.get(nama="Bidan Wilayah")
        active_ids = set(
            PenugasanPetugas.objects.filter(
                petugas=bidan,
            ).values_list("posyandu_id", flat=True)
        )
        self.assertEqual(active_ids, {pos1.pk, pos2.pk})
        self.assertIn(bidan.posyandu_id, active_ids)

    def test_tambah_bidan_tanpa_cakupan_ditolak(self):
        admin, _ = make_petugas(username="admin-bidan-tanpa-cakupan", level="admin", posyandu=None)
        self.client.force_login(admin)

        response = self.client.post(reverse("accounts:tambah_petugas", args=["bidan"]), {
            "nama": "Bidan Tanpa Wilayah",
            "alamat": "Alamat",
            "no_telp": "081200099992",
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Petugas.objects.filter(nama="Bidan Tanpa Wilayah").exists())


class AdminKelurahanSeparationTests(TestCase):
    def test_superuser_teknis_ditolak_login_aplikasi(self):
        User.objects.create_superuser(
            username="teknis-login",
            email="teknis@example.com",
            password="aman-12345",
        )
        response = self.client.post(reverse("accounts:login"), {
            "username": "teknis-login",
            "password": "aman-12345",
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "Akun teknis Django")

    def test_admin_kelurahan_adalah_user_biasa(self):
        user, petugas = make_petugas(
            username="admin-biasa",
            level="admin",
            posyandu=None,
        )
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(petugas.can_login)

    def test_command_create_admin_kelurahan_membuat_user_non_staff(self):
        from django.core.management import call_command

        call_command(
            "create_admin_kelurahan",
            username="admin-command",
            nama="Admin Command",
            password="SandiKuat!2026",
        )
        user = User.objects.get(username="admin-command")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.petugas.level, "admin")
        self.assertTrue(user.petugas.can_login)


class KaderAccountAssignmentRegressionTests(TestCase):
    def test_buat_akun_kader_mensinkronkan_penugasan_posyandu(self):
        from apps.posyandu.models import PenugasanPetugas
        from common.testing import make_posyandu
        from .models import Petugas
        from .services import create_petugas_account

        pos = make_posyandu("Pos Akun Scope")
        kader = Petugas.objects.create(
            nama="Kader Akun Scope", level="kader", posyandu=pos, no_telp="081277779999"
        )
        create_petugas_account(kader, username="kader-akun-scope")
        self.assertTrue(PenugasanPetugas.objects.filter(
            petugas=kader, posyandu=pos
        ).exists())
