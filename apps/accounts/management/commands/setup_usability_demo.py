"""Siapkan dua akun demo bersama untuk pengujian usability langsung.

Desain pengujian:
- 1 akun Kader dipakai bersama oleh responden R01-R34.
- 1 akun Admin Kelurahan dipakai bersama oleh responden R35-R36.
- Semua login tetap mempunyai session browser/perangkat masing-masing.
- Data operasional dibedakan dengan kode responden Rxx agar pengujian serentak
  tidak memakai objek yang sama.

Pemakaian:
    python manage.py setup_usability_demo --reset
    python manage.py setup_usability_demo
    python manage.py setup_usability_demo --remove
    python manage.py setup_usability_demo --kader-password "PasswordKader" --admin-password "PasswordAdmin"
"""

from __future__ import annotations

import os
from datetime import time

from dateutil.relativedelta import relativedelta
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Petugas
from apps.pemeriksaan.models import (
    Imunisasi,
    Kehadiran,
    PemeriksaanBalita,
    PemeriksaanBumil,
)
from apps.peserta.models import Peserta
from apps.posyandu.models import JadwalKegiatan, PenugasanPetugas, Posyandu
from apps.posyandu.services import ensure_single_assignment, set_bidan_coverage


USERNAME_KADER = "kader"
USERNAME_ADMIN = "kelurahan"
POSYANDU_NAME = "Posyandu Demo Usability Bersama"
POSYANDU_PREFIX = "Posyandu Demo Usability"
BIDAN_NAME = "Bidan Demo Usability"
BIDAN_PREFIX = "Bidan Demo Usability"
DEFAULT_KADER_PASSWORD = os.getenv("USABILITY_KADER_PASSWORD", "kader123")
DEFAULT_ADMIN_PASSWORD = os.getenv("USABILITY_ADMIN_PASSWORD", "kelurahan123")
RESPONDEN_KADER = 34


def _nik(index: int) -> str:
    """NIK dummy 16 digit, unik untuk data acuan R01-R34."""
    return f"990901{index:02d}00000000"


def _phone(index: int) -> str:
    return f"08990000{index:04d}"


class Command(BaseCommand):
    help = (
        "Membuat dua akun demo bersama untuk usability: 1 Kader untuk R01-R34 "
        "dan 1 Admin Kelurahan untuk R35-R36."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--kader-password",
            default=DEFAULT_KADER_PASSWORD,
            help=(
                "Password akun Kader. Default berasal dari environment "
                "USABILITY_KADER_PASSWORD atau 'kader123'."
            ),
        )
        parser.add_argument(
            "--admin-password",
            default=DEFAULT_ADMIN_PASSWORD,
            help=(
                "Password akun Admin Kelurahan. Default berasal dari environment "
                "USABILITY_ADMIN_PASSWORD atau 'kelurahan123'."
            ),
        )
        parser.add_argument(
            "--password",
            default=None,
            help=(
                "Kompatibilitas versi lama: jika diisi, password ini digunakan "
                "untuk kedua akun demo."
            ),
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Hapus seluruh data demo usability lama, lalu buat ulang dua akun bersama.",
        )
        parser.add_argument(
            "--remove",
            action="store_true",
            help="Hapus seluruh akun dan workspace demo usability tanpa membuat ulang.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        shared_password = options.get("password")
        kader_password = shared_password or options["kader_password"] or DEFAULT_KADER_PASSWORD
        admin_password = shared_password or options["admin_password"] or DEFAULT_ADMIN_PASSWORD
        if len(kader_password) < 8 or len(admin_password) < 8:
            raise CommandError("Password demo minimal 8 karakter.")

        if options["reset"] or options["remove"]:
            self._remove_demo_data()
            if options["remove"]:
                self.stdout.write(self.style.SUCCESS("Data demo usability berhasil dihapus."))
                return

        posyandu = self._setup_shared_posyandu()
        self._setup_shared_bidan(posyandu)
        self._setup_kader(posyandu, kader_password)
        self._setup_admin(admin_password)
        jadwal = self._setup_reference_data(posyandu)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("DUA AKUN DEMO USABILITY SIAP DIGUNAKAN BERSAMAAN."))
        self.stdout.write("")
        self.stdout.write("Kader R01-R34")
        self.stdout.write(f"  Username : {USERNAME_KADER}")
        self.stdout.write(f"  Password : {kader_password}")
        self.stdout.write("")
        self.stdout.write("Admin R35-R36")
        self.stdout.write(f"  Username : {USERNAME_ADMIN}")
        self.stdout.write(f"  Password : {admin_password}")
        self.stdout.write("")
        self.stdout.write(
            f"Jadwal acuan pemeriksaan bersama: {jadwal.tgl_kegiatan:%d-%m-%Y}, "
            f"{jadwal.jam_mulai:%H:%M}-{jadwal.jam_selesai:%H:%M}."
        )
        self.stdout.write(
            "Data acuan Kader tersedia sebagai Balita Demo R01 sampai Balita Demo R34. "
            "Gunakan kolom pencarian untuk membuka data sesuai kode responden."
        )
        self.stdout.write(
            "Saat MENAMBAHKAN data baru, selalu sertakan kode Rxx pada nama data agar hasil "
            "antar-responden tetap dapat dibedakan."
        )

    def _setup_shared_posyandu(self) -> Posyandu:
        posyandu, _ = Posyandu.objects.update_or_create(
            nama=POSYANDU_NAME,
            defaults={
                "desa": "Wilayah Pengujian Usability",
                "alamat": "Lokasi Demo Pengujian Usability",
            },
        )
        return posyandu

    def _setup_shared_bidan(self, posyandu: Posyandu) -> Petugas:
        bidan, _ = Petugas.objects.update_or_create(
            nama=BIDAN_NAME,
            level="bidan",
            defaults={
                "user": None,
                "posyandu": posyandu,
                "alamat": "Wilayah Pengujian Usability",
                "no_telp": "088800000001",
            },
        )
        if bidan.user_id:
            bidan.user = None
        bidan.posyandu = posyandu
        bidan.alamat = "Wilayah Pengujian Usability"
        bidan.no_telp = "088800000001"
        bidan.save()
        set_bidan_coverage(bidan, [posyandu.pk])
        return bidan

    def _setup_kader(self, posyandu: Posyandu, password: str) -> Petugas:
        user, _ = User.objects.get_or_create(username=USERNAME_KADER)
        user.first_name = "Kader Demo Bersama"
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.set_password(password)
        user.save()

        petugas, _ = Petugas.objects.get_or_create(
            user=user,
            defaults={
                "nama": "Kader Demo Bersama",
                "level": "kader",
                "posyandu": posyandu,
            },
        )
        petugas.nama = "Kader Demo Bersama"
        petugas.level = "kader"
        petugas.posyandu = posyandu
        petugas.alamat = "Wilayah Pengujian Usability"
        petugas.no_telp = "089900000001"
        petugas.save()
        ensure_single_assignment(petugas, posyandu)
        return petugas

    def _setup_admin(self, password: str) -> Petugas:
        user, _ = User.objects.get_or_create(username=USERNAME_ADMIN)
        user.first_name = "Admin Demo Bersama"
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.set_password(password)
        user.save()

        petugas, _ = Petugas.objects.get_or_create(
            user=user,
            defaults={
                "nama": "Admin Demo Bersama",
                "level": "admin",
                "posyandu": None,
            },
        )
        PenugasanPetugas.objects.filter(petugas=petugas).delete()
        petugas.nama = "Admin Demo Bersama"
        petugas.level = "admin"
        petugas.posyandu = None
        petugas.alamat = "Kantor Kelurahan - Data Demo"
        petugas.no_telp = "087700000001"
        petugas.save()
        return petugas

    def _setup_reference_data(self, posyandu: Posyandu) -> JadwalKegiatan:
        """Data acuan membuat tugas pemeriksaan tidak bergantung pada keberhasilan T2/T3.

        R01-R34 tetap diminta menambah data sendiri untuk tugas input. Data acuan hanya
        dipakai pada tugas pemeriksaan agar kegagalan input sebelumnya tidak membuat
        seluruh tugas berikutnya otomatis gagal.
        """
        today = timezone.localdate()

        jadwal, _ = JadwalKegiatan.objects.update_or_create(
            posyandu=posyandu,
            tgl_kegiatan=today,
            jns_kegiatan="Pemeriksaan Rutin",
            jam_mulai=time(6, 30),
            defaults={"jam_selesai": time(7, 30)},
        )

        for index in range(1, RESPONDEN_KADER + 1):
            birth_balita = today - relativedelta(months=24 + (index % 12))
            Peserta.objects.update_or_create(
                no_nik=_nik(index),
                defaults={
                    "posko": posyandu,
                    "nama_peserta": f"Balita Demo R{index:02d}",
                    "tgl_lahir": birth_balita,
                    "alamat": f"Alamat Demo R{index:02d}",
                    "anak_ke": 1,
                    "bb_lahir": 3.20,
                    "tb_lahir": 49.00,
                    "lila_lahir": 11.50,
                    "no_hp": _phone(index),
                    "nik_ibu": f"990902{index:02d}00000000",
                    "status_peserta": "balita",
                    "nama_ibu": f"Ibu Demo R{index:02d}",
                    "nama_ayah": f"Ayah Demo R{index:02d}",
                    "jenis_kelamin": "Laki-Laki" if index % 2 else "Perempuan",
                    "is_tamu": False,
                    "asal_posyandu": None,
                },
            )

        return jadwal

    def _remove_demo_data(self) -> None:
        # Mendukung pembersihan versi lama (34+2 akun) sekaligus versi dua akun.
        demo_posyandu = Posyandu.objects.filter(nama__startswith=POSYANDU_PREFIX)
        demo_posyandu_ids = list(demo_posyandu.values_list("pk", flat=True))

        if demo_posyandu_ids:
            demo_jadwal = JadwalKegiatan.objects.filter(posyandu_id__in=demo_posyandu_ids)
            PemeriksaanBalita.objects.filter(jadwal__in=demo_jadwal).delete()
            PemeriksaanBumil.objects.filter(jadwal__in=demo_jadwal).delete()
            Imunisasi.objects.filter(jadwal__in=demo_jadwal).delete()
            Kehadiran.objects.filter(jadwal__in=demo_jadwal).delete()
            Peserta.objects.filter(posko_id__in=demo_posyandu_ids).delete()
            demo_jadwal.delete()

        # Bersihkan akun demo versi lama dan akun demo dua-role versi sekarang.
        User.objects.filter(username__startswith="demo_kader").delete()
        User.objects.filter(username__startswith="demo_admin").delete()
        User.objects.filter(username__in=[USERNAME_KADER, USERNAME_ADMIN]).delete()

        demo_bidans = Petugas.objects.filter(
            level="bidan",
            nama__startswith=BIDAN_PREFIX,
        )
        PenugasanPetugas.objects.filter(petugas__in=demo_bidans).delete()
        demo_bidans.delete()

        if demo_posyandu_ids:
            PenugasanPetugas.objects.filter(posyandu_id__in=demo_posyandu_ids).delete()
            Posyandu.objects.filter(pk__in=demo_posyandu_ids).delete()
