from django.core.management.base import BaseCommand

from apps.accounts.models import Petugas
from apps.peserta.models import Peserta
from apps.posyandu.models import Posyandu
from apps.posyandu.services import sync_kader_assignment


class Command(BaseCommand):
    help = "Sinkronkan penugasan Kader dan tampilkan jumlah peserta pada tiap wilayah."

    def handle(self, *args, **options):
        self.stdout.write("Sinkronisasi akses Kader...")
        kaders = Petugas.objects.filter(level="kader").select_related("user", "posyandu").order_by("nama")

        if not kaders.exists():
            self.stdout.write(self.style.WARNING("Belum ada data Kader."))
            return

        for kader in kaders:
            sync_kader_assignment(kader)
            kader.refresh_from_db(fields=["posyandu"])
            username = kader.user.username if kader.user_id else "(belum punya akun)"
            pos_name = kader.posyandu.nama if kader.posyandu_id else "(belum ditugaskan)"
            balita = Peserta.objects.filter(posko_id=kader.posyandu_id, status_peserta="balita").count() if kader.posyandu_id else 0
            bumil = Peserta.objects.filter(posko_id=kader.posyandu_id, status_peserta="bumil").count() if kader.posyandu_id else 0
            self.stdout.write(f"- {kader.nama} | {username} | {pos_name} | Balita={balita} | Bumil={bumil}")

        self.stdout.write("\nRingkasan peserta per Posyandu:")
        for pos in Posyandu.objects.all().order_by("nama"):
            balita = Peserta.objects.filter(posko=pos, status_peserta="balita").count()
            bumil = Peserta.objects.filter(posko=pos, status_peserta="bumil").count()
            self.stdout.write(f"  {pos.pk}: {pos.nama} | Balita={balita} | Bumil={bumil}")

        unassigned = Peserta.objects.filter(posko__isnull=True).count()
        if unassigned:
            self.stdout.write(self.style.WARNING(
                f"Ditemukan {unassigned} peserta tanpa Posyandu (posko=NULL). Data ini tidak dapat ditampilkan ke Kader sampai ditetapkan Posyandunya oleh Admin."
            ))
        else:
            self.stdout.write(self.style.SUCCESS("Semua peserta sudah memiliki Posyandu."))

        self.stdout.write(self.style.SUCCESS("Sinkronisasi akses Kader selesai."))
