from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Petugas
from apps.posyandu.models import Posyandu


class DashboardAccessTests(TestCase):
    def test_pengguna_belum_login_diarahkan_ke_login(self):
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_kader_dapat_membuka_dashboard_posyandu(self):
        posyandu = Posyandu.objects.create(nama="Posyandu Melati")
        user = User.objects.create_user(username="kader", password="aman-12345")
        Petugas.objects.create(
            user=user,
            nama="Kader Uji",
            level="kader",
            posyandu=posyandu,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["posyandu"], posyandu)

    def test_admin_kelurahan_dapat_membuka_dashboard_seluruh_posyandu(self):
        Posyandu.objects.create(nama="Pos A")
        Posyandu.objects.create(nama="Pos B")
        user = User.objects.create_user(username="admin-kelurahan", password="aman-12345")
        Petugas.objects.create(user=user, nama="Admin Kelurahan", level="admin")
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_posyandu"], 2)

    def test_dashboard_memakai_layout_responsif_global(self):
        posyandu = Posyandu.objects.create(nama="Posyandu Responsif")
        user = User.objects.create_user(username="kader-responsive", password="aman-12345")
        Petugas.objects.create(
            user=user,
            nama="Kader Responsif",
            level="kader",
            posyandu=posyandu,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="appShell"')
        self.assertContains(response, 'id="appScroller"')
        self.assertContains(response, 'id="scrollTopBtn"')
        self.assertContains(response, 'css/responsive-overrides.css')

class DashboardBidanPenanggungJawabTests(TestCase):
    def test_kader_melihat_bidan_penanggung_jawab_tanpa_akun_login(self):
        from datetime import date
        from apps.posyandu.models import PenugasanPetugas

        pos = Posyandu.objects.create(nama="Pos Cakupan Bidan")
        kader_user = User.objects.create_user("kader-cakupan-bidan", password="aman-12345")
        Petugas.objects.create(user=kader_user, nama="Kader Cakupan", level="kader", posyandu=pos)
        bidan = Petugas.objects.create(
            nama="Bidan Penanggung Jawab",
            level="bidan",
            posyandu=pos,
            no_telp="081277700001",
        )
        PenugasanPetugas.objects.create(
            petugas=bidan,
            posyandu=pos,
            tanggal_daftar=date.today(),
        )

        self.client.force_login(kader_user)
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bidan Penanggung Jawab")
        self.assertContains(response, "081277700001")
        self.assertIsNone(bidan.user_id)



class DashboardRoleSeparationTests(TestCase):
    def test_dashboard_admin_dan_kader_memakai_tampilan_berbeda(self):
        pos = Posyandu.objects.create(nama="Pos Dashboard Beda")
        admin_user = User.objects.create_user("admin-beda", password="aman-12345")
        Petugas.objects.create(user=admin_user, nama="Admin Beda", level="admin")
        kader_user = User.objects.create_user("kader-beda", password="aman-12345")
        Petugas.objects.create(user=kader_user, nama="Kader Beda", level="kader", posyandu=pos)

        self.client.force_login(admin_user)
        admin_response = self.client.get(reverse("dashboard:index"))
        self.assertContains(admin_response, 'data-dashboard-role="admin"')
        self.assertContains(admin_response, "Dashboard Admin Kelurahan")
        self.assertNotContains(admin_response, 'data-dashboard-role="kader"')

        self.client.force_login(kader_user)
        kader_response = self.client.get(reverse("dashboard:index"))
        self.assertContains(kader_response, 'data-dashboard-role="kader"')
        self.assertContains(kader_response, "Dashboard Kader")
        self.assertNotContains(kader_response, 'data-dashboard-role="admin"')

    def test_superuser_teknis_tidak_masuk_dashboard_operasional(self):
        user = User.objects.create_superuser(
            username="teknis-dashboard",
            email="teknis@example.com",
            password="aman-12345",
        )
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 403)


class DashboardJadwalSinkronTests(TestCase):
    def test_dashboard_kader_tidak_memotong_jadwal_mendatang_pada_lima_data(self):
        from datetime import timedelta, time
        from django.utils import timezone
        from apps.posyandu.models import JadwalKegiatan

        pos = Posyandu.objects.create(nama="Pos Dashboard Sinkron")
        user = User.objects.create_user("kader-dashboard-sinkron", password="aman-12345")
        Petugas.objects.create(
            user=user,
            nama="Kader Dashboard Sinkron",
            level="kader",
            posyandu=pos,
        )
        today = timezone.localdate()
        jadwal_ids = []
        for index in range(1, 8):
            jadwal = JadwalKegiatan.objects.create(
                tgl_kegiatan=today + timedelta(days=index),
                jam_mulai=time(8),
                jam_selesai=time(10),
                jns_kegiatan="Pemeriksaan Rutin",
                posyandu=pos,
            )
            jadwal_ids.append(jadwal.pk)

        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 200)
        visible_ids = [item.pk for item in response.context["jadwal_mendatang"]]
        self.assertEqual(visible_ids, jadwal_ids)
