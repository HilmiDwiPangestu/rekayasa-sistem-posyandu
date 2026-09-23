"""Satu command untuk menyiapkan seluruh data demo awal aplikasi Posyandu.

Pemakaian:
    python manage.py seed_data

Command ini bersifat idempotent untuk data demo yang dibuatnya sendiri dan
menyiapkan:
- Referensi WHO LFA/HFA harian (3.714 baris: laki-laki + perempuan)
- 12 Posyandu
- 2 Bidan non-login dengan pembagian cakupan 6 + 6 Posyandu
- 12 Kader non-login (akun dapat dibuat Admin dari UI)
- 4 Balita + 2 Ibu Hamil per Posyandu (72 peserta)
- 2 jadwal per Posyandu (riwayat + jadwal mendatang)

Akun Admin Kelurahan sengaja tidak dibuat otomatis demi keamanan. Gunakan
``python manage.py create_admin_kelurahan ...`` setelah seed jika diperlukan.
"""

from __future__ import annotations

import calendar
import csv
from datetime import date, time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from dateutil.relativedelta import relativedelta

from apps.accounts.models import Petugas
from apps.peserta.models import Peserta
from apps.posyandu.models import JadwalKegiatan, Posyandu
from apps.posyandu.services import ensure_single_assignment, set_bidan_coverage
from apps.referensi.models import WHOStandardPBU


POSYANDU_NAMES = [
    "Posyandu Anggrek",
    "Posyandu Dahlia",
    "Posyandu Flamboyan",
    "Posyandu Kenanga",
    "Posyandu Melati",
    "Posyandu Mawar",
    "Posyandu Nusa Indah",
    "Posyandu Sedap Malam",
    "Posyandu Teratai",
    "Posyandu Bougenville",
    "Posyandu Cempaka",
    "Posyandu Kamboja",
]

BALITA_NAMES = [
    ("Alya", "Perempuan"),
    ("Bagas", "Laki-Laki"),
    ("Citra", "Perempuan"),
    ("Daffa", "Laki-Laki"),
]

BUMIL_NAMES = ["Nabila", "Rina"]


def _safe_date(year: int, month: int, day: int) -> date:
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, max_day))


def _demo_nik(pos_index: int, kind: int, person_index: int) -> str:
    # 16 digit, deterministik, dan khusus data demo.
    return f"9901{pos_index:02d}{kind}{person_index:02d}0000000"


def _demo_phone(pos_index: int, kind: int, person_index: int) -> str:
    return f"0813{pos_index:02d}{kind}{person_index:02d}0000"


class Command(BaseCommand):
    help = "Menyiapkan seluruh data demo awal (WHO, master data, peserta, dan jadwal) dalam satu command."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Izinkan seed saat database sudah memiliki Posyandu non-demo. "
                "Tidak menghapus data lama; hanya menambah/memperbarui data demo."
            ),
        )
        parser.add_argument(
            "--kelurahan",
            default="Kelurahan Contoh",
            help="Nama kelurahan/desa untuk data demo (default: Kelurahan Contoh).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        kelurahan = (options.get("kelurahan") or "Kelurahan Contoh").strip()
        force = bool(options.get("force"))

        demo_names = set(POSYANDU_NAMES)
        existing_non_demo = Posyandu.objects.exclude(nama__in=demo_names).exists()
        if existing_non_demo and not force:
            raise CommandError(
                "Database sudah memiliki data Posyandu di luar data demo. "
                "Untuk mencegah data nyata tercampur, seed dibatalkan. "
                "Gunakan --force jika memang ingin menambahkan data demo tanpa menghapus data lama."
            )

        self.stdout.write(self.style.MIGRATE_HEADING("\n[1/5] Import referensi WHO"))
        who_count = self._seed_who()
        self.stdout.write(self.style.SUCCESS(f"Referensi WHO siap: {who_count} baris"))

        self.stdout.write(self.style.MIGRATE_HEADING("\n[2/5] Membuat 12 Posyandu"))
        posyandu_list = self._seed_posyandu(kelurahan)
        self.stdout.write(self.style.SUCCESS(f"Posyandu siap: {len(posyandu_list)}"))

        self.stdout.write(self.style.MIGRATE_HEADING("\n[3/5] Membuat data Bidan dan Kader"))
        bidan_count, kader_count = self._seed_petugas(posyandu_list)
        self.stdout.write(self.style.SUCCESS(f"Bidan siap: {bidan_count} | Kader siap: {kader_count}"))

        self.stdout.write(self.style.MIGRATE_HEADING("\n[4/5] Membuat peserta demo"))
        peserta_count = self._seed_peserta(posyandu_list, kelurahan)
        self.stdout.write(self.style.SUCCESS(f"Peserta demo siap: {peserta_count}"))

        self.stdout.write(self.style.MIGRATE_HEADING("\n[5/5] Membuat jadwal demo"))
        jadwal_count = self._seed_jadwal(posyandu_list)
        self.stdout.write(self.style.SUCCESS(f"Jadwal demo siap: {jadwal_count}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("SEED DATA SELESAI."))
        self.stdout.write("Ringkasan:")
        self.stdout.write(f"- Referensi WHO : {WHOStandardPBU.objects.count()}")
        self.stdout.write(f"- Posyandu      : {len(posyandu_list)} data demo")
        self.stdout.write(f"- Bidan         : {bidan_count} (non-login, cakupan 6 + 6)")
        self.stdout.write(f"- Kader         : {kader_count} (akun belum dibuat)")
        self.stdout.write(f"- Peserta       : {peserta_count} (48 balita + 24 ibu hamil)")
        self.stdout.write(f"- Jadwal        : {jadwal_count}")
        self.stdout.write("")
        self.stdout.write(
            "Jika belum memiliki Admin Kelurahan, buat dengan:\n"
            'python manage.py create_admin_kelurahan --username adminkelurahan --nama "Admin Kelurahan"'
        )

    def _seed_who(self) -> int:
        """Import ulang WHO expanded daily dari CSV hasil file acuan pengguna."""
        data_dir = Path(__file__).resolve().parents[3] / "referensi" / "data"
        files = [
            ("L", data_dir / "lfa_boys_z_exp.csv"),
            ("P", data_dir / "lfa_girls_z_exp.csv"),
        ]

        for _, file_path in files:
            if not file_path.exists():
                raise CommandError(f"File referensi WHO tidak ditemukan: {file_path}")

        # Hapus referensi bulanan/legacy agar satu-satunya sumber lookup adalah
        # tabel harian WHO expanded.
        WHOStandardPBU.objects.all().delete()

        objects = []
        for gender, file_path in files:
            seen_days = []
            with file_path.open(encoding="utf-8-sig", newline="") as csv_file:
                reader = csv.DictReader(csv_file, delimiter=";")
                for row in reader:
                    seen_days.append(int(row["Day"]))
                    m_value = float(str(row["M"]).replace(",", "."))
                    s_value = float(str(row["S"]).replace(",", "."))
                    objects.append(
                        WHOStandardPBU(
                            gender=gender,
                            day=int(row["Day"]),
                            month=None,
                            l_value=float(str(row["L"]).replace(",", ".")),
                            m_value=m_value,
                            s_value=s_value,
                            sd=m_value * s_value,
                            sd4neg=float(str(row["SD4neg"]).replace(",", ".")),
                            sd3neg=float(str(row["SD3neg"]).replace(",", ".")),
                            sd2neg=float(str(row["SD2neg"]).replace(",", ".")),
                            sd1neg=float(str(row["SD1neg"]).replace(",", ".")),
                            sd0=float(str(row["SD0"]).replace(",", ".")),
                            sd1=float(str(row["SD1"]).replace(",", ".")),
                            sd2=float(str(row["SD2"]).replace(",", ".")),
                            sd3=float(str(row["SD3"]).replace(",", ".")),
                            sd4=float(str(row["SD4"]).replace(",", ".")),
                            source="WHO LFA expanded daily",
                        )
                    )
            if seen_days != list(range(1857)):
                raise CommandError(
                    f"Referensi WHO {file_path.name} harus memiliki Day 0-1856 lengkap."
                )

        WHOStandardPBU.objects.bulk_create(objects, batch_size=500)
        return WHOStandardPBU.objects.count()

    def _seed_posyandu(self, kelurahan: str) -> list[Posyandu]:
        rows = []
        for index, name in enumerate(POSYANDU_NAMES, start=1):
            posyandu, _ = Posyandu.objects.update_or_create(
                nama=name,
                defaults={
                    "desa": kelurahan,
                    "alamat": f"Wilayah RW {index:02d}, {kelurahan}",
                },
            )
            rows.append(posyandu)
        return rows

    def _seed_petugas(self, posyandu_list: list[Posyandu]) -> tuple[int, int]:
        # Bidan adalah data penanggung jawab wilayah, BUKAN aktor login.
        bidan_a, _ = Petugas.objects.update_or_create(
            nama="Bidan Wilayah A",
            level="bidan",
            defaults={
                "user": None,
                "posyandu": posyandu_list[0],
                "no_telp": "081300000101",
                "alamat": "Wilayah kerja Posyandu 1-6",
            },
        )
        bidan_b, _ = Petugas.objects.update_or_create(
            nama="Bidan Wilayah B",
            level="bidan",
            defaults={
                "user": None,
                "posyandu": posyandu_list[6],
                "no_telp": "081300000102",
                "alamat": "Wilayah kerja Posyandu 7-12",
            },
        )
        set_bidan_coverage(bidan_a, [pos.pk for pos in posyandu_list[:6]])
        set_bidan_coverage(bidan_b, [pos.pk for pos in posyandu_list[6:]])

        kader_count = 0
        for index, pos in enumerate(posyandu_list, start=1):
            kader, _ = Petugas.objects.update_or_create(
                nama=f"Kader {pos.nama.replace('Posyandu ', '')}",
                level="kader",
                defaults={
                    "posyandu": pos,
                    "no_telp": f"08132000{index:04d}",
                    "alamat": pos.alamat,
                },
            )
            # Seed tidak mengubah akun Kader yang sudah dibuat Admin melalui UI.
            ensure_single_assignment(kader, pos)
            kader_count += 1

        return 2, kader_count

    def _seed_peserta(self, posyandu_list: list[Posyandu], kelurahan: str) -> int:
        today = date.today()
        total = 0

        for pos_index, pos in enumerate(posyandu_list, start=1):
            for person_index, (base_name, gender) in enumerate(BALITA_NAMES, start=1):
                umur_bulan = [6, 18, 36, 54][person_index - 1]
                lahir = today - relativedelta(months=umur_bulan)
                nik = _demo_nik(pos_index, 1, person_index)
                mother_nik = _demo_nik(pos_index, 3, person_index)

                Peserta.objects.update_or_create(
                    no_nik=nik,
                    defaults={
                        "posko": pos,
                        "nama_peserta": f"{base_name} {pos_index:02d}",
                        "tgl_lahir": lahir,
                        "alamat": f"Wilayah {pos.nama}, {kelurahan}",
                        "anak_ke": (person_index % 3) + 1,
                        "bb_lahir": 3.0 + (person_index * 0.05),
                        "tb_lahir": 48.0 + person_index,
                        "lila_lahir": 11.0 + (person_index * 0.1),
                        "no_hp": _demo_phone(pos_index, 1, person_index),
                        "nik_ibu": mother_nik,
                        "status_peserta": "balita",
                        "nama_ibu": f"Ibu {base_name} {pos_index:02d}",
                        "nama_ayah": f"Ayah {base_name} {pos_index:02d}",
                        "jenis_kelamin": gender,
                        "is_tamu": False,
                        "asal_posyandu": None,
                    },
                )
                total += 1

            for person_index, base_name in enumerate(BUMIL_NAMES, start=1):
                umur_tahun = [24, 32][person_index - 1]
                lahir = today - relativedelta(years=umur_tahun)
                nik = _demo_nik(pos_index, 2, person_index)

                Peserta.objects.update_or_create(
                    no_nik=nik,
                    defaults={
                        "posko": pos,
                        "nama_peserta": f"{base_name} {pos_index:02d}",
                        "tgl_lahir": lahir,
                        "alamat": f"Wilayah {pos.nama}, {kelurahan}",
                        "anak_ke": None,
                        "bb_lahir": None,
                        "tb_lahir": None,
                        "lila_lahir": None,
                        "no_hp": _demo_phone(pos_index, 2, person_index),
                        "nik_ibu": nik,
                        "status_peserta": "bumil",
                        "nama_ibu": f"{base_name} {pos_index:02d}",
                        "nama_ayah": f"Suami {base_name} {pos_index:02d}",
                        "jenis_kelamin": "Perempuan",
                        "is_tamu": False,
                        "asal_posyandu": None,
                    },
                )
                total += 1

        return total

    def _seed_jadwal(self, posyandu_list: list[Posyandu]) -> int:
        today = date.today()
        previous_month = today - relativedelta(months=1)
        next_month = today + relativedelta(months=1)
        history_date = _safe_date(previous_month.year, previous_month.month, 15)
        upcoming_date = _safe_date(next_month.year, next_month.month, 10)

        count = 0
        for pos in posyandu_list:
            for schedule_date, kind in [
                (history_date, "Pemeriksaan Rutin"),
                (upcoming_date, "Imunisasi"),
            ]:
                JadwalKegiatan.objects.update_or_create(
                    posyandu=pos,
                    tgl_kegiatan=schedule_date,
                    jns_kegiatan=kind,
                    defaults={
                        "jam_mulai": time(8, 0),
                        "jam_selesai": time(11, 0),
                    },
                )
                count += 1
        return count
