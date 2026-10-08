"""Service presentasi/analisis untuk modul pemeriksaan."""

from apps.deteksi.services.who_services import koreksi_panjang_tinggi
from apps.laporan.helper.kms_standards import bbu_series, imtu_series, pbu_tbu_series

from .models import PemeriksaanBalita


def kms_gender_code(peserta) -> str:
    gender_text = str(getattr(peserta, "jenis_kelamin", "") or "").strip().lower()
    return "P" if gender_text.startswith("p") else "L"


def build_kms_payload(peserta) -> dict:
    """Bangun payload tiga grafik KMS: BB/U, PB/TB/U, dan IMT/U."""
    gender_code = kms_gender_code(peserta)
    riwayat = (
        PemeriksaanBalita.objects
        .filter(peserta=peserta)
        .order_by("usia_bulan", "tgl_pemeriksaan")
    )

    points = []
    for row in riwayat:
        if row.usia_bulan is None or not 0 <= row.usia_bulan <= 60:
            continue

        berat = float(row.berat_badan) if row.berat_badan is not None else None
        tinggi_input = float(row.tinggi_badan) if row.tinggi_badan is not None else None
        tinggi_who = tinggi_input

        # Grafik PB/TB-U dan IMT/U harus memakai nilai antropometri yang sama
        # dengan perhitungan Z-score WHO. Bila posisi ukur tidak sesuai kelompok
        # usia, WHO memerlukan koreksi 0,7 cm. Nilai input asli tetap disimpan
        # pada database dan ikut dikirim sebagai `tinggi_input` untuk audit.
        if tinggi_input is not None and getattr(row, "jenis_pengukuran", None):
            tinggi_who = koreksi_panjang_tinggi(
                nilai=tinggi_input,
                jenis_pengukuran=row.jenis_pengukuran,
                umur_hari=row.usia_hari,
                umur=row.usia_bulan,
            )

        imt = None
        if berat is not None and tinggi_who is not None and berat > 0 and tinggi_who > 0:
            tinggi_meter = tinggi_who / 100.0
            imt = round(berat / (tinggi_meter ** 2), 2)

        points.append({
            "bulan": int(row.usia_bulan),
            "berat": berat,
            "tinggi": round(float(tinggi_who), 2) if tinggi_who is not None else None,
            "tinggi_input": tinggi_input,
            "jenis_pengukuran": getattr(row, "jenis_pengukuran", None),
            "imt": imt,
            "tanggal": row.tgl_pemeriksaan.strftime("%d-%m-%Y"),
            "z_score": float(row.z_score) if row.z_score is not None else None,
            "status": row.get_status_gizi_display() if row.status_gizi else "-",
        })

    return {
        "gender": gender_code,
        "points": points,
        "bbu": bbu_series(gender_code),
        "pbu_tbu": pbu_tbu_series(gender_code),
        "imtu": imtu_series(gender_code),
    }


def z_score_valid(z_score) -> bool:
    """Z-score di luar -6..+6 dianggap perlu verifikasi antropometri."""
    if z_score is None:
        return False
    try:
        value = float(z_score)
    except (TypeError, ValueError):
        return False
    return -6 <= value <= 6


def rf_is_stunting(hasil_prediksi):
    if hasil_prediksi is None:
        return None
    value = str(hasil_prediksi).strip().lower()
    if value in {"stunting", "stunted"}:
        return True
    if value in {"normal", "tidak stunting", "not stunted", "non stunting"}:
        return False
    return None


def who_is_stunting(status_gizi):
    if not status_gizi:
        return None
    return status_gizi in {"stunting", "stunting_berat"}


def hitung_kesesuaian(z_score, status_gizi, hasil_prediksi) -> str:
    if not z_score_valid(z_score):
        return "Tidak Dapat Dinilai"

    who_stunting = who_is_stunting(status_gizi)
    rf_stunting = rf_is_stunting(hasil_prediksi)
    if who_stunting is None or rf_stunting is None:
        return "-"
    return "Sesuai" if who_stunting == rf_stunting else "Tidak Sesuai"


def format_probabilitas_stunting(value):
    """`prob_ml` disimpan sebagai persen 0-100; fungsi hanya memformat dua desimal."""
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return round(value, 2)
