from datetime import date, timedelta
from apps.pemeriksaan.models import PemeriksaanBalita, PemeriksaanBumil
from apps.peserta.models import Peserta
from apps.posyandu.models import Posyandu

from django.db.models import Count

DEFAULT_KECAMATAN = "Indramayu"
DEFAULT_PUSKESMAS = "Margadadi"


def get_rentang_triwulan(tahun, triwulan):
    """
    Mengembalikan (tanggal_mulai, tanggal_selesai) untuk triwulan tertentu.
    Triwulan 1: Jan-Mar, 2: Apr-Jun, 3: Jul-Sep, 4: Okt-Des
    """
    bulan_mulai = {1: 1, 2: 4, 3: 7, 4: 10}[triwulan]
    bulan_selesai = bulan_mulai + 2
 
    tanggal_mulai = date(tahun, bulan_mulai, 1)
    if bulan_selesai == 12:
        tanggal_selesai = date(tahun, 12, 31)
    else:
        tanggal_selesai = date(tahun, bulan_selesai + 1, 1) - timedelta(days=1)
 
    return tanggal_mulai, tanggal_selesai


 
BULAN_NAMA = {
    1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April',
    5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus',
    9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember',
}

def _ambil_parameter(request):
    try:
        tahun = int(request.GET.get('tahun', date.today().year))
    except (TypeError, ValueError):
        tahun = date.today().year
    try:
        triwulan = int(request.GET.get('triwulan', ((date.today().month - 1) // 3) + 1))
    except (TypeError, ValueError):
        triwulan = ((date.today().month - 1) // 3) + 1
    tahun = min(max(tahun, 2000), date.today().year + 1)
    triwulan = min(max(triwulan, 1), 4)
    return tahun, triwulan


def get_daftar_bulan_triwulan(tahun, triwulan):
    """
    Mengembalikan list 3 bulan dalam triwulan tsb, masing-masing berisi
    nomor bulan, nama bulan, tanggal awal & akhir bulan itu.
    """
    bulan_mulai = {1: 1, 2: 4, 3: 7, 4: 10}[triwulan]
    daftar = []
    for i in range(3):
        bulan = bulan_mulai + i
        awal = date(tahun, bulan, 1)
        if bulan == 12:
            akhir = date(tahun, 12, 31)
        else:
            akhir = date(tahun, bulan + 1, 1) - timedelta(days=1)
        daftar.append({
            'bulan': bulan,
            'nama': BULAN_NAMA[bulan],
            'awal': awal,
            'akhir': akhir,
        })
    return daftar


# ============================================================
# HELPER: bangun data pivot (peserta x 3 bulan)
# ============================================================
def build_pivot_balita(daftar_bulan, posyandu_ids=None):
    tanggal_awal_tw = daftar_bulan[0]['awal']
    tanggal_akhir_tw = daftar_bulan[-1]['akhir']
 
    pemeriksaan_qs = PemeriksaanBalita.objects.filter(
        tgl_pemeriksaan__date__range=(tanggal_awal_tw, tanggal_akhir_tw)
    ).select_related('peserta')
    if posyandu_ids is not None:
        pemeriksaan_qs = pemeriksaan_qs.filter(jadwal__posyandu_id__in=posyandu_ids)
 
    # peserta_ids = pemeriksaan_qs.values_list('peserta_id', flat=True).distinct()
    peserta_list = Peserta.objects.filter(status_peserta='balita').order_by('nama_peserta')
    if posyandu_ids is not None:
        peserta_list = peserta_list.filter(posko_id__in=posyandu_ids)
 
    data = []
    for peserta in peserta_list:
        baris = {'peserta': peserta, 'bulan': []}
        for b in daftar_bulan:
            hasil = (
                pemeriksaan_qs
                .filter(peserta=peserta, tgl_pemeriksaan__date__range=(b['awal'], b['akhir']))
                .order_by('-tgl_pemeriksaan')
                .first()
            )
            baris['bulan'].append(hasil)
        baris['ada_data'] = any(baris['bulan'])
        data.append(baris)
    return data


def build_pivot_bumil(daftar_bulan, posyandu_ids=None):
    tanggal_awal_tw = daftar_bulan[0]['awal']
    tanggal_akhir_tw = daftar_bulan[-1]['akhir']

    pemeriksaan_qs = PemeriksaanBumil.objects.filter(
        tgl_pemeriksaan__date__range=(tanggal_awal_tw, tanggal_akhir_tw)
    ).select_related('peserta')
    if posyandu_ids is not None:
        pemeriksaan_qs = pemeriksaan_qs.filter(jadwal__posyandu_id__in=posyandu_ids)

    # Jika ingin semua ibu hamil tampil
    peserta_list = Peserta.objects.filter(
        status_peserta='bumil'
    ).order_by('nama_peserta')
    if posyandu_ids is not None:
        peserta_list = peserta_list.filter(posko_id__in=posyandu_ids)

    data = []

    for peserta in peserta_list:
        baris = {
            'peserta': peserta,
            'bulan': []
        }

        for b in daftar_bulan:
            hasil = (
                pemeriksaan_qs
                .filter(
                    peserta=peserta,
                    tgl_pemeriksaan__date__range=(b['awal'], b['akhir'])
                )
                .order_by('-tgl_pemeriksaan')
                .first()
            )

            baris['bulan'].append(hasil)

        # Tambahkan ini
        baris['ada_data'] = any(baris['bulan'])

        data.append(baris)

    return data

# ============================================================
# HELPER: kumpulkan seluruh context (dipakai halaman, excel, pdf)
# ============================================================
def build_context_laporan_triwulan(tahun, triwulan, posyandu_ids=None):
    tanggal_mulai, tanggal_selesai = get_rentang_triwulan(tahun, triwulan)
    daftar_bulan = get_daftar_bulan_triwulan(tahun, triwulan)
 
    # ---------- BALITA ----------
    pemeriksaan_balita = PemeriksaanBalita.objects.filter(
        tgl_pemeriksaan__date__range=(tanggal_mulai, tanggal_selesai)
    ).select_related('peserta', 'petugas', 'jadwal')
    if posyandu_ids is not None:
        pemeriksaan_balita = pemeriksaan_balita.filter(jadwal__posyandu_id__in=posyandu_ids)
 
    total_pemeriksaan_balita = pemeriksaan_balita.count()
    balita_diperiksa = pemeriksaan_balita.values('peserta').distinct().count()
 
    distribusi_status_gizi_raw = (
        pemeriksaan_balita
        .values('status_gizi')
        .annotate(jumlah=Count('id_periksa'))
        .order_by('-jumlah')
    )
    label_status_gizi = dict(PemeriksaanBalita.STATUS_GIZI)
    distribusi_status_gizi = [
        {'label': label_status_gizi.get(i['status_gizi'], i['status_gizi']), 'jumlah': i['jumlah']}
        for i in distribusi_status_gizi_raw
    ]
    
    data_balita = build_pivot_balita(daftar_bulan, posyandu_ids)
    
    
 
    # ---------- BUMIL ----------
    pemeriksaan_bumil = PemeriksaanBumil.objects.filter(
        tgl_pemeriksaan__date__range=(tanggal_mulai, tanggal_selesai)
    ).select_related('peserta', 'petugas', 'jadwal')
    if posyandu_ids is not None:
        pemeriksaan_bumil = pemeriksaan_bumil.filter(jadwal__posyandu_id__in=posyandu_ids)
 
    total_pemeriksaan_bumil = pemeriksaan_bumil.count()
    bumil_diperiksa = pemeriksaan_bumil.values('peserta').distinct().count()
    total_perlu_rujukan = pemeriksaan_bumil.filter(perlu_rujukan=True).count()
 
    distribusi_status_kehamilan_raw = (
        pemeriksaan_bumil
        .values('status_kehamilan')
        .annotate(jumlah=Count('id_periksa'))
        .order_by('-jumlah')
    )
    label_status_kehamilan = dict(PemeriksaanBumil.STATUS_KEHAMILAN)
    distribusi_status_kehamilan = [
        {'label': label_status_kehamilan.get(i['status_kehamilan'], i['status_kehamilan']), 'jumlah': i['jumlah']}
        for i in distribusi_status_kehamilan_raw
    ]
 
    data_bumil = build_pivot_bumil(daftar_bulan, posyandu_ids)
 
    daftar_triwulan = [
        (1, 'Triwulan I (Jan - Mar)'),
        (2, 'Triwulan II (Apr - Jun)'),
        (3, 'Triwulan III (Jul - Sep)'),
        (4, 'Triwulan IV (Okt - Des)'),
    ]
    tahun_sekarang = date.today().year
    daftar_tahun = range(tahun_sekarang - 4, tahun_sekarang + 1)
    
    
    # jumlah kolom tiap bulan
    colspan_bulan = 4

    # total colspan jika data kosong
    jumlah_bulan = len(daftar_bulan)
    colspan_triwulan = colspan_bulan * jumlah_bulan
    colspan_total = 10 + colspan_triwulan

    posyandu_qs = Posyandu.objects.all().order_by("nama")
    if posyandu_ids is not None:
        posyandu_qs = posyandu_qs.filter(pk__in=posyandu_ids)

    posyandu_nama = ", ".join(posyandu_qs.values_list("nama", flat=True)) or "-"
    desa_values = [
        value.strip()
        for value in posyandu_qs.values_list("desa", flat=True)
        if value and value.strip()
    ]
    desa_nama = ", ".join(dict.fromkeys(desa_values)) or "-"
    
    return {
        'tahun': tahun,
        'triwulan': triwulan,
        'triwulan_label': dict(daftar_triwulan).get(triwulan, ''),
        'tanggal_mulai': tanggal_mulai,
        'tanggal_selesai': tanggal_selesai,
        'daftar_triwulan': daftar_triwulan,
        'daftar_tahun': daftar_tahun,
        'daftar_bulan': daftar_bulan,
 
        # Balita
        'total_pemeriksaan_balita': total_pemeriksaan_balita,
        'balita_diperiksa': balita_diperiksa,
        'distribusi_status_gizi': distribusi_status_gizi,
        'data_balita': data_balita,
 
        # Bumil
        'total_pemeriksaan_bumil': total_pemeriksaan_bumil,
        'bumil_diperiksa': bumil_diperiksa,
        'total_perlu_rujukan': total_perlu_rujukan,
        'distribusi_status_kehamilan': distribusi_status_kehamilan,
        'data_bumil': data_bumil,
        
        'colspan_bulan': colspan_bulan,
        'colspan_total': colspan_total,
        'colspan_triwulan': colspan_triwulan,

        # Metadata identitas laporan. Kecamatan dan Puskesmas sebelumnya
        # ditulis langsung di template; sekarang dipusatkan di helper.
        'kecamatan': DEFAULT_KECAMATAN,
        'puskesmas_nama': DEFAULT_PUSKESMAS,
        'desa_nama': desa_nama,
        'posyandu_nama': posyandu_nama,
    }
