from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.db import transaction

from dateutil.relativedelta import relativedelta

from apps.pemeriksaan.models import PelayananBalita
from apps.peserta.models import Peserta


# ============================================================
# PERIODE PELAYANAN POSYANDU
# ============================================================

BULAN_PELAYANAN = {
    2: "Februari",
    8: "Agustus",
}


# ============================================================
# KONVERSI TANGGAL
# ============================================================

def _to_date(value):

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    return None


# ============================================================
# TANGGAL PELAYANAN
# ============================================================

def get_tanggal_pelayanan(jadwal):

    tanggal = _to_date(
        getattr(
            jadwal,
            "tgl_kegiatan",
            None
        )
    )

    if tanggal is None:

        raise ValidationError(
            "Tanggal kegiatan Posyandu tidak tersedia."
        )

    return tanggal


# ============================================================
# HITUNG USIA BULAN
# ============================================================

def hitung_usia_bulan(
    peserta,
    tanggal
):

    if not peserta.tgl_lahir:
        return None

    if peserta.tgl_lahir > tanggal:
        return None

    selisih = relativedelta(
        tanggal,
        peserta.tgl_lahir
    )

    return (
        selisih.years * 12
        + selisih.months
    )


# ============================================================
# RIWAYAT PELAYANAN PADA PERIODE YANG SAMA
# ============================================================

def _get_riwayat_periode(
    peserta,
    jenis_layanan,
    tanggal,
    pemeriksaan=None
):

    queryset = (
        PelayananBalita.objects
        .filter(
            pemeriksaan__peserta=peserta,
            jenis_layanan=jenis_layanan,

            tanggal_pemberian__year=(
                tanggal.year
            ),

            tanggal_pemberian__month=(
                tanggal.month
            ),
        )
        .select_related(
            "pemeriksaan"
        )
        .order_by(
            "tanggal_pemberian"
        )
    )


    # Digunakan jika suatu saat pemeriksaan diedit.
    if (
        pemeriksaan is not None
        and pemeriksaan.pk
    ):

        queryset = queryset.exclude(
            pemeriksaan=pemeriksaan
        )


    return queryset.first()


# ============================================================
# ATURAN VITAMIN A
# ============================================================

def _get_vitamin_a_by_age(
    usia_bulan
):

    if usia_bulan is None:
        return None


    # ========================================================
    # 6 - 11 BULAN
    # ========================================================

    if 6 <= usia_bulan <= 11:

        return {
            "jenis": "biru",
            "jenis_display": "Vitamin A Biru",
            "dosis": "100.000 SI",
        }


    # ========================================================
    # 12 - 59 BULAN
    # ========================================================

    if 12 <= usia_bulan <= 59:

        return {
            "jenis": "merah",
            "jenis_display": "Vitamin A Merah",
            "dosis": "200.000 SI",
        }


    return None


# ============================================================
# ATURAN OBAT CACING
# ============================================================

def _get_obat_cacing_by_age(
    usia_bulan
):

    if usia_bulan is None:
        return None


    # ========================================================
    # 12 - 23 BULAN
    # ========================================================

    if 12 <= usia_bulan <= 23:

        return {
            "nama_obat": "Albendazole",
            "dosis": "200 mg",
            "keterangan_dosis": (
                "1/2 tablet Albendazole 400 mg"
            ),
        }


    # ========================================================
    # 24 - 59 BULAN
    # ========================================================

    if 24 <= usia_bulan <= 59:

        return {
            "nama_obat": "Albendazole",
            "dosis": "400 mg",
            "keterangan_dosis": (
                "1 tablet Albendazole 400 mg"
            ),
        }


    return None


# ============================================================
# STATUS PELAYANAN BALITA
# ============================================================

def get_status_pelayanan_balita(
    peserta,
    jadwal,
    pemeriksaan=None
):

    tanggal = get_tanggal_pelayanan(
        jadwal
    )


    usia_bulan = hitung_usia_bulan(
        peserta,
        tanggal
    )


    # ========================================================
    # PERIODE
    # ========================================================

    periode_aktif = (
        tanggal.month
        in BULAN_PELAYANAN
    )


    nama_periode = (
        BULAN_PELAYANAN.get(
            tanggal.month
        )
    )


    # ========================================================
    # ATURAN BERDASARKAN UMUR
    # ========================================================

    vitamin_info = (
        _get_vitamin_a_by_age(
            usia_bulan
        )
    )


    obat_info = (
        _get_obat_cacing_by_age(
            usia_bulan
        )
    )


    # ========================================================
    # CEK RIWAYAT
    # ========================================================

    vitamin_record = (
        _get_riwayat_periode(
            peserta=peserta,
            jenis_layanan="vitamin_a",
            tanggal=tanggal,
            pemeriksaan=pemeriksaan,
        )
    )


    obat_record = (
        _get_riwayat_periode(
            peserta=peserta,
            jenis_layanan="obat_cacing",
            tanggal=tanggal,
            pemeriksaan=pemeriksaan,
        )
    )


    # ========================================================
    # VITAMIN A
    # ========================================================

    vitamin_a_boleh = (
        periode_aktif
        and vitamin_info is not None
        and vitamin_record is None
    )


    # ========================================================
    # OBAT CACING
    # ========================================================

    obat_cacing_boleh = (
        periode_aktif
        and obat_info is not None
        and obat_record is None
    )


    # ========================================================
    # ALASAN VITAMIN A
    # ========================================================

    if not periode_aktif:

        vitamin_a_alasan = (
            "Pemberian Vitamin A dilakukan "
            "pada bulan Februari dan Agustus."
        )

    elif usia_bulan is None:

        vitamin_a_alasan = (
            "Usia balita tidak dapat dihitung."
        )

    elif usia_bulan < 6:

        vitamin_a_alasan = (
            "Vitamin A belum diberikan karena "
            "usia balita masih di bawah 6 bulan."
        )

    elif usia_bulan > 59:

        vitamin_a_alasan = (
            "Balita sudah berada di luar "
            "rentang usia sasaran Vitamin A."
        )

    elif vitamin_record:

        vitamin_a_alasan = (
            "Vitamin A sudah diberikan "
            "pada periode ini."
        )

    else:

        vitamin_a_alasan = None


    # ========================================================
    # ALASAN OBAT CACING
    # ========================================================

    if not periode_aktif:

        obat_cacing_alasan = (
            "Pemberian obat cacing dilakukan "
            "pada bulan Februari dan Agustus."
        )

    elif usia_bulan is None:

        obat_cacing_alasan = (
            "Usia balita tidak dapat dihitung."
        )

    elif usia_bulan < 12:

        obat_cacing_alasan = (
            "Obat cacing belum diberikan karena "
            "usia balita masih di bawah 12 bulan."
        )

    elif usia_bulan > 59:

        obat_cacing_alasan = (
            "Balita sudah berada di luar "
            "rentang usia sasaran modul balita."
        )

    elif obat_record:

        obat_cacing_alasan = (
            "Obat cacing sudah diberikan "
            "pada periode ini."
        )

    else:

        obat_cacing_alasan = None


    return {

        # ====================================================
        # PERIODE
        # ====================================================

        "tanggal": tanggal,

        "bulan": tanggal.month,

        "tahun": tanggal.year,

        "nama_periode": (
            nama_periode
        ),

        "periode_aktif": (
            periode_aktif
        ),


        # ====================================================
        # USIA
        # ====================================================

        "usia_bulan": (
            usia_bulan
        ),


        # ====================================================
        # VITAMIN A
        # ====================================================

        "vitamin_a_boleh": (
            vitamin_a_boleh
        ),

        "vitamin_a_sudah": (
            vitamin_record is not None
        ),

        "vitamin_a_tanggal": (
            vitamin_record.tanggal_pemberian
            if vitamin_record
            else None
        ),

        "vitamin_a_jenis": (
            vitamin_info["jenis"]
            if vitamin_info
            else None
        ),

        "vitamin_a_jenis_display": (
            vitamin_info["jenis_display"]
            if vitamin_info
            else None
        ),

        "vitamin_a_dosis": (
            vitamin_info["dosis"]
            if vitamin_info
            else None
        ),

        "vitamin_a_alasan": (
            vitamin_a_alasan
        ),


        # ====================================================
        # OBAT CACING
        # ====================================================

        "obat_cacing_boleh": (
            obat_cacing_boleh
        ),

        "obat_cacing_sudah": (
            obat_record is not None
        ),

        "obat_cacing_tanggal": (
            obat_record.tanggal_pemberian
            if obat_record
            else None
        ),

        "obat_cacing_nama": (
            obat_info["nama_obat"]
            if obat_info
            else None
        ),

        "obat_cacing_dosis": (
            obat_info["dosis"]
            if obat_info
            else None
        ),

        "obat_cacing_keterangan_dosis": (
            obat_info["keterangan_dosis"]
            if obat_info
            else None
        ),

        "obat_cacing_alasan": (
            obat_cacing_alasan
        ),
    }


# ============================================================
# SIMPAN PELAYANAN
# ============================================================

def simpan_pelayanan_balita(
    pemeriksaan,
    cleaned_data
):

    peserta = pemeriksaan.peserta
    jadwal = pemeriksaan.jadwal


    vitamin_a = cleaned_data.get(
        "vitamin_a",
        False
    )


    obat_cacing = cleaned_data.get(
        "obat_cacing",
        False
    )


    # Tidak ada pelayanan yang dipilih.
    if not vitamin_a and not obat_cacing:
        return []


    with transaction.atomic():

        # ====================================================
        # LOCK PESERTA
        # ====================================================

        Peserta.objects.select_for_update().get(
            pk=peserta.pk
        )


        # Status dihitung ulang dari database.
        status = (
            get_status_pelayanan_balita(
                peserta=peserta,
                jadwal=jadwal,
                pemeriksaan=pemeriksaan,
            )
        )


        berhasil = []


        # ====================================================
        # VITAMIN A
        # ====================================================

        if vitamin_a:

            if not status["vitamin_a_boleh"]:

                raise ValidationError(
                    status["vitamin_a_alasan"]
                    or
                    "Vitamin A tidak dapat diberikan."
                )


            PelayananBalita.objects.update_or_create(

                pemeriksaan=pemeriksaan,

                jenis_layanan="vitamin_a",

                defaults={

                    "tanggal_pemberian":
                        status["tanggal"],

                    "jenis_vitamin_a":
                        status["vitamin_a_jenis"],

                    "nama_obat":
                        None,

                    "dosis":
                        status["vitamin_a_dosis"],

                    "catatan":
                        cleaned_data.get(
                            "catatan_vitamin_a",
                            ""
                        ),
                }
            )


            berhasil.append(
                "Vitamin A"
            )


        # ====================================================
        # OBAT CACING
        # ====================================================

        if obat_cacing:

            if not status["obat_cacing_boleh"]:

                raise ValidationError(
                    status["obat_cacing_alasan"]
                    or
                    "Obat cacing tidak dapat diberikan."
                )


            PelayananBalita.objects.update_or_create(

                pemeriksaan=pemeriksaan,

                jenis_layanan="obat_cacing",

                defaults={

                    "tanggal_pemberian":
                        status["tanggal"],

                    "jenis_vitamin_a":
                        None,

                    "nama_obat":
                        status["obat_cacing_nama"],

                    "dosis":
                        status["obat_cacing_dosis"],

                    "catatan":
                        cleaned_data.get(
                            "catatan_obat_cacing",
                            ""
                        ),
                }
            )


            berhasil.append(
                "Obat Cacing"
            )


        return berhasil