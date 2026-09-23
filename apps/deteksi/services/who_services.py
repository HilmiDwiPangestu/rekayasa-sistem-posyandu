"""Perhitungan PB/U atau TB/U berbasis referensi WHO harian.

Referensi yang dipakai project ini berasal dari dua tabel WHO expanded yang
menggunakan umur dalam hari (Day 0-1856):
- LFA_boys_z_exp
- LFA_girls_z_exp

WHO dipakai sebagai ground truth/pembanding antropometri. Random Forest tetap
merupakan proses terpisah dan tetap menerima fitur usia dalam bulan sesuai
model training.
"""

from __future__ import annotations

import math

from apps.referensi.models import WHOStandardPBU


WHO_MIN_DAY = 0
WHO_MAX_DAY = 1856
WHO_HEIGHT_TRANSITION_DAY = 731


def normalize_gender_who(jk):
    if jk is None:
        raise ValueError("Jenis kelamin tidak boleh kosong.")

    value = str(jk).strip().upper().replace("_", " ")
    if value in {"L", "M", "MALE", "LAKI-LAKI", "LAKI LAKI", "LAKILAKI"}:
        return "L"
    if value in {"P", "F", "FEMALE", "PEREMPUAN"}:
        return "P"
    raise ValueError(f"Jenis kelamin tidak valid: {value}")


def validate_age_day(umur_hari):
    """Validasi usia untuk lookup WHO daily expanded table."""
    try:
        value = int(umur_hari)
    except (TypeError, ValueError) as error:
        raise ValueError("Umur WHO harus berupa angka dalam hari.") from error

    if not WHO_MIN_DAY <= value <= WHO_MAX_DAY:
        raise ValueError(
            f"Umur untuk referensi WHO harus berada pada rentang "
            f"{WHO_MIN_DAY}-{WHO_MAX_DAY} hari."
        )
    return value


def validate_age_month(umur):
    """Kompatibilitas helper lama/tes RF; bukan lookup referensi WHO baru."""
    try:
        value = int(umur)
    except (TypeError, ValueError) as error:
        raise ValueError("Umur harus berupa angka dalam bulan.") from error
    if not 0 <= value <= 59:
        raise ValueError("Umur balita harus berada pada rentang 0-59 bulan.")
    return value


def validate_height(tinggi_badan):
    try:
        value = float(tinggi_badan)
    except (TypeError, ValueError) as error:
        raise ValueError("Panjang/tinggi badan harus berupa angka.") from error

    if not 40 <= value <= 130:
        raise ValueError(
            "Panjang/tinggi badan berada di luar rentang pemeriksaan 40-130 cm."
        )
    return value


def koreksi_panjang_tinggi(
    *,
    nilai,
    jenis_pengukuran=None,
    umur_hari=None,
    umur=None,
):
    """Koreksi 0,7 cm bila metode ukur tidak sesuai kelompok usia.

    Referensi daily beralih dari length ke height pada Day 731. ``umur`` dalam
    bulan masih diterima untuk kompatibilitas pemanggilan lama, tetapi kode
    baru sebaiknya mengirim ``umur_hari``.
    """
    if jenis_pengukuran is None:
        return nilai

    if umur_hari is None:
        if umur is None:
            raise ValueError("umur_hari wajib diisi untuk koreksi pengukuran.")
        # Hanya jalur kompatibilitas tes/kode lama.
        umur_hari = 0 if int(umur) <= 0 else int(round(float(umur) * 30.4375))

    umur_hari = int(umur_hari)
    jenis = str(jenis_pengukuran).strip().lower()

    if umur_hari < WHO_HEIGHT_TRANSITION_DAY:
        if jenis in {"tinggi", "berdiri", "height"}:
            return nilai + 0.7
    else:
        if jenis in {"panjang", "terlentang", "length"}:
            return nilai - 0.7
    return nilai


def get_lms_values(reference):
    """Ambil parameter LMS dari object referensi WHO."""
    if reference is None:
        return None

    def pick(*names):
        for name in names:
            value = getattr(reference, name, None)
            if value is not None:
                return value
        return None

    L = pick("l_value", "L", "l")
    M = pick("m_value", "M", "m")
    S = pick("s_value", "S", "s")
    if L is None or M is None or S is None:
        return None
    return float(L), float(M), float(S)


def hitung_z_score_lms(*, nilai, L, M, S):
    """Hitung Z-score dengan metode LMS WHO."""
    nilai = float(nilai)
    L = float(L)
    M = float(M)
    S = float(S)

    if nilai <= 0 or M <= 0 or S <= 0:
        raise ValueError("Parameter LMS atau nilai antropometri tidak valid.")

    if math.isclose(L, 0.0, abs_tol=1e-12):
        return math.log(nilai / M) / S
    return (((nilai / M) ** L) - 1.0) / (L * S)


def get_who_reference(*, umur_hari, jk):
    """Ambil satu baris referensi WHO berdasarkan usia eksak dan gender."""
    day = validate_age_day(umur_hari)
    gender = normalize_gender_who(jk)
    return (
        WHOStandardPBU.objects
        .filter(gender=gender, day=day)
        .first()
    )


def hitung_z_score_who(
    *,
    umur_hari,
    jk,
    tinggi_badan,
    jenis_pengukuran=None,
):
    """Hitung Z-score PB/U atau TB/U dari tabel WHO berbasis hari."""
    day = validate_age_day(umur_hari)
    gender = normalize_gender_who(jk)
    nilai = validate_height(tinggi_badan)
    nilai = koreksi_panjang_tinggi(
        umur_hari=day,
        nilai=nilai,
        jenis_pengukuran=jenis_pengukuran,
    )

    reference = (
        WHOStandardPBU.objects
        .filter(gender=gender, day=day)
        .first()
    )
    if reference is None:
        return None

    lms = get_lms_values(reference)
    if lms is None:
        return None
    L, M, S = lms
    return round(float(hitung_z_score_lms(nilai=nilai, L=L, M=M, S=S)), 4)


def kategori_tb_u(z_score):
    """Kategori PB/U atau TB/U menurut batas Z-score WHO/Permenkes."""
    if z_score is None:
        return {"kode": None, "label": "Tidak dapat dihitung", "stunting": None}

    value = float(z_score)
    if value < -3:
        return {"kode": "stunting_berat", "label": "Sangat Pendek", "stunting": True}
    if value < -2:
        return {"kode": "stunting", "label": "Pendek", "stunting": True}
    if value <= 3:
        return {"kode": "normal", "label": "Normal", "stunting": False}
    return {"kode": "tinggi", "label": "Tinggi", "stunting": False}


def hitung_status_antropometri(
    *,
    umur_hari,
    jk,
    tinggi_badan,
    jenis_pengukuran=None,
):
    """Hasil lengkap antropometri WHO untuk satu pemeriksaan."""
    day = validate_age_day(umur_hari)
    gender = normalize_gender_who(jk)
    reference = (
        WHOStandardPBU.objects
        .filter(gender=gender, day=day)
        .first()
    )

    z_score = hitung_z_score_who(
        umur_hari=day,
        jk=gender,
        tinggi_badan=tinggi_badan,
        jenis_pengukuran=jenis_pengukuran,
    )
    kategori = kategori_tb_u(z_score)

    return {
        "z_score": z_score,
        "kode": kategori["kode"],
        "kategori": kategori["label"],
        "stunting": kategori["stunting"],
        "umur_hari": day,
        "gender_who": gender,
        "reference_day": reference.day if reference else None,
        "l_value": float(reference.l_value) if reference else None,
        "m_value": float(reference.m_value) if reference else None,
        "s_value": float(reference.s_value) if reference else None,
        "sd3neg": float(reference.sd3neg) if reference else None,
        "sd2neg": float(reference.sd2neg) if reference else None,
        "sd0": float(reference.sd0) if reference else None,
        "sd2": float(reference.sd2) if reference else None,
        "sd3": float(reference.sd3) if reference else None,
        "source": reference.source if reference else None,
    }
