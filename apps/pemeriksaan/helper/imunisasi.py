from dateutil.relativedelta import relativedelta
from django.utils import timezone

from apps.pemeriksaan.models import Imunisasi
from .constant import JADWAL_VAKSIN_BALITA


BALITA_DOSIS = {
    "HB-0": "1",
    "BCG": "1",
    "bOPV 1": "1",
    "bOPV 2": "2",
    "bOPV 3": "3",
    "bOPV 4": "4",
    "DPT-HB-Hib 1": "1",
    "DPT-HB-Hib 2": "2",
    "DPT-HB-Hib 3": "3",
    "DPT-HB-Hib 4": "4",
    "PCV 1": "1",
    "PCV 2": "2",
    "PCV 3": "3",
    "Rotavirus 1": "1",
    "Rotavirus 2": "2",
    "Rotavirus 3": "3",
    "IPV 1": "1",
    "IPV 2": "2",
    "MR 1": "1",
    "MR 2": "2",
    "JE": "1",
}


BUMIL_DOSIS = {
    "TT-1": "1",
    "TT-2": "2",
    "TT-3": "3",
    "TT-4": "4",
    "TT-5": "5",
}


# ==========================================================
# REKOMENDASI IMUNISASI BALITA
# ==========================================================

def get_vaksin_rekomendasi_balita(peserta, tanggal=None):

    tanggal = tanggal or timezone.localdate()
    selisih = relativedelta(tanggal, peserta.tgl_lahir)
    umur_bulan = max(0, selisih.years * 12 + selisih.months)
    umur_hari = max(0, (tanggal - peserta.tgl_lahir).days)

    vaksin_sudah = set(
        Imunisasi.objects.filter(
            peserta=peserta
        ).values_list(
            "jenis_vaksin",
            flat=True
        )
    )

    rekomendasi = []
    
    # =============================
    # Bayi baru lahir (0–24 jam)
    # =============================
    if umur_hari <= 1:
        for vaksin in JADWAL_VAKSIN_BALITA["0-24jam"]:
            if vaksin not in vaksin_sudah:
                rekomendasi.append(vaksin)

        return rekomendasi
    
    # Tampilkan seluruh vaksin yang sudah jatuh tempo tetapi belum diberikan,
    # bukan hanya vaksin pada kelompok umur terakhir.
    for usia in sorted(k for k in JADWAL_VAKSIN_BALITA if isinstance(k, int)):
        if usia > umur_bulan:
            break
        for vaksin in JADWAL_VAKSIN_BALITA[usia]:
            if vaksin not in vaksin_sudah and vaksin not in rekomendasi:
                rekomendasi.append(vaksin)

    return rekomendasi


# ==========================================================
# DOSIS OTOMATIS
# ==========================================================

def get_dosis_otomatis(jenis_vaksin):

    mapping = {
        **BALITA_DOSIS,
        **BUMIL_DOSIS,
    }

    return mapping.get(jenis_vaksin)


# ==========================================================
# REKOMENDASI IMUNISASI IBU HAMIL
# ==========================================================

def get_vaksin_rekomendasi_bumil(peserta, tanggal=None):

    riwayat = (
        Imunisasi.objects.filter(
            peserta=peserta,
            jenis_vaksin__startswith="TT"
        )
        .order_by("-tgl_pemberian")
    )

    # Belum pernah imunisasi
    if not riwayat.exists():
        return ["TT-1"]

    terakhir = riwayat.first()

    hari_ini = tanggal or timezone.localdate()

    # Td1 -> Td2 (minimal 4 minggu)
    if terakhir.jenis_vaksin == "TT-1":
        if hari_ini >= terakhir.tgl_pemberian + relativedelta(weeks=4):
            return ["TT-2"]
        return []

    # Td2 -> Td3 (minimal 6 bulan)
    elif terakhir.jenis_vaksin == "TT-2":
        if hari_ini >= terakhir.tgl_pemberian + relativedelta(months=6):
            return ["TT-3"]
        return []

    # Td3 -> Td4 (minimal 1 tahun)
    elif terakhir.jenis_vaksin == "TT-3":
        if hari_ini >= terakhir.tgl_pemberian + relativedelta(years=1):
            return ["TT-4"]
        return []

    # Td4 -> Td5 (minimal 1 tahun)
    elif terakhir.jenis_vaksin == "TT-4":
        if hari_ini >= terakhir.tgl_pemberian + relativedelta(years=1):
            return ["TT-5"]
        return []

    # Sudah Td5
    return []
