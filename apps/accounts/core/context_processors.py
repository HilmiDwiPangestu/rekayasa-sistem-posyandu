from urllib.parse import unquote

from django.urls import NoReverseMatch, reverse


LABELS = {
    "setting": "Pengaturan Akun",
    "register": "Tambah Akun Pengguna",
    "tambah_petugas": "Tambah Petugas",
    "list": "Daftar Data",
    "create": "Tambah Data",
    "edit": "Ubah Data",
    "delete": "Hapus Data",
    "list_peserta": "Daftar Peserta",
    "periksa_peserta": "Pemeriksaan Peserta",
    "detail_deteksi_stunting": "Detail Deteksi Stunting",
    "list_imunisasi": "Jadwal Imunisasi",
    "list_jadwal": "Jadwal Kegiatan",
    "daftar_petugas_kader": "Data Kader",
    "daftar_bidan": "Data Bidan",
    "atur_cakupan_bidan": "Cakupan Wilayah Bidan",
    "edit_petugas": "Ubah Petugas",
    "delete_petugas": "Hapus Petugas",
    "buat_akun_petugas": "Buat Akun Kader",
    "list_posyandu": "Data Posyandu",
    "create_posyandu": "Tambah Posyandu",
    "edit_posyandu": "Ubah Posyandu",
    "delete_posyandu": "Hapus Posyandu",
    "jadwal_posyandu_admin": "Jadwal Posyandu",
    "detail_jadwal_admin": "Detail Jadwal",
    "laporan_index": "Rekap Laporan",
    "laporan_jadwal": "Detail Laporan Jadwal",
    "laporan_bulanan": "Laporan Bulanan",
    "laporan_imunisasi_bulanan": "Laporan Imunisasi",
    "laporan_kms": "Kartu Menuju Sehat",
    "laporan_triwulan": "Laporan Triwulan",
    "laporan_bumil": "Laporan Ibu Hamil",
    "laporan_balita": "Laporan Balita",
    "laporan_imunisasi": "Laporan Imunisasi",
    "semua_laporan": "Semua Laporan",
    "detail_laporan_imunisasi": "Detail Laporan Imunisasi",
}


def _safe_reverse(name, **kwargs):
    try:
        return reverse(name, kwargs=kwargs or None)
    except NoReverseMatch:
        return None


def _peserta_label(status):
    return "Data Ibu Hamil" if status == "bumil" else "Data Balita"


def breadcrumbs(request):
    """Breadcrumb berbasis nama URL sehingga label stabil dan tautan tidak 404."""
    match = request.resolver_match
    if not match or match.namespace == "dashboard" or match.url_name == "login":
        return {"django_breadcrumbs": []}

    namespace = match.namespace
    url_name = match.url_name or ""
    kwargs = match.kwargs
    items = []

    if namespace == "peserta":
        status = kwargs.get("status_peserta", "balita")
        items.append({
            "name": _peserta_label(status),
            "url": _safe_reverse("peserta:list", status_peserta=status),
        })
    elif namespace == "pemeriksaan":
        status = kwargs.get("status_peserta", "balita")
        label = "Pemeriksaan Ibu Hamil" if status == "bumil" else "Pemeriksaan Balita"
        route = "pemeriksaan:list_imunisasi" if url_name == "list_imunisasi" else "pemeriksaan:list"
        items.append({
            "name": "Imunisasi" if route.endswith("list_imunisasi") else label,
            "url": _safe_reverse(route, status_peserta=status),
        })
        if url_name in {"periksa_peserta"}:
            items.append({
                "name": "Daftar Peserta",
                "url": _safe_reverse(
                    "pemeriksaan:list_peserta",
                    status_peserta=status,
                    id_jadwal=kwargs.get("id_jadwal"),
                ),
            })
    elif namespace == "posyandu":
        parent_map = {
            "create": ("Jadwal Kegiatan", "posyandu:list_jadwal"),
            "edit": ("Jadwal Kegiatan", "posyandu:list_jadwal"),
            "delete": ("Jadwal Kegiatan", "posyandu:list_jadwal"),
            "create_posyandu": ("Data Posyandu", "posyandu:list_posyandu"),
            "edit_posyandu": ("Data Posyandu", "posyandu:list_posyandu"),
            "delete_posyandu": ("Data Posyandu", "posyandu:list_posyandu"),
            "edit_petugas": ("Data Petugas", "posyandu:daftar_petugas_kader"),
            "atur_cakupan_bidan": ("Data Bidan", "posyandu:daftar_bidan"),
            "delete_petugas": ("Data Petugas", "posyandu:daftar_petugas_kader"),
            "buat_akun_petugas": ("Data Petugas", "posyandu:daftar_petugas_kader"),
            "detail_jadwal_admin": ("Jadwal Posyandu", "posyandu:jadwal_posyandu_admin"),
            "detail_laporan_imunisasi": ("Laporan Imunisasi", "posyandu:laporan_imunisasi"),
        }
        if url_name in parent_map:
            label, route = parent_map[url_name]
            items.append({"name": label, "url": _safe_reverse(route)})

    label = LABELS.get(url_name)
    if not label:
        label = unquote(url_name).replace("_", " ").title()

    if not items or items[-1]["name"] != label:
        items.append({"name": label, "url": None})
    else:
        items[-1]["url"] = None

    return {"django_breadcrumbs": items}
