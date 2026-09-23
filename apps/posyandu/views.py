from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from datetime import date
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from common.decorators import kader_required
from common.access import visible_posyandu_queryset
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
from django.http import HttpResponse
from xhtml2pdf import pisa
from io import BytesIO
from pypdf import PdfReader, PdfWriter
from django.template.loader import get_template
from django.utils.dateparse import parse_date
from datetime import timedelta
from django.utils import timezone
from django.utils.text import slugify
from collections import OrderedDict, defaultdict
from django.db.models import Count, Max

from apps.pemeriksaan.models import Kehadiran


# DECORATOR
from common.decorators import admin_required


# IMPORT DARI APPS TERSENDIRI
from .models import JadwalKegiatan, Posyandu
from django.views.decorators.http import require_POST
from .forms import UserEditForm, PetugasEditForm, PosyanduForm
from apps.accounts.models import Petugas
from apps.accounts.services import PetugasAccountError, create_petugas_account
from .forms import JadwalKegiatanForm, PosyanduEditForm
from .services import (
    BidanCoverageError,
    active_bidan_owner_map,
    bidan_coverage_ids,
    decorate_bidan_coverage,
    ensure_single_assignment,
    set_bidan_coverage,
    sync_kader_assignment,
)
from apps.pemeriksaan.models import Imunisasi, PemeriksaanBalita, PemeriksaanBumil
from apps.peserta.models import Peserta

from apps.laporan.helper.utils import build_context_laporan_triwulan, _ambil_parameter
from .exporters import master_excel_response, master_pdf_response


# =========================
# LIST JADWAL
# =========================

def _posyandu_queryset_petugas(request):
    return visible_posyandu_queryset(request.user)


def _posyandu_tugas_kader(request):
    """Posyandu operasional Kader yang sedang login.

    Kader pada sistem ini memiliki satu tempat tugas aktif. Nilai ini menjadi
    sumber tunggal untuk pembuatan dan perubahan jadwal sehingga lokasi tidak
    berasal dari input browser.
    """
    petugas = getattr(request.user, "petugas", None)
    if petugas is None or petugas.level != "kader":
        return None
    return sync_kader_assignment(petugas) or petugas.posyandu


@login_required
@kader_required
def list_jadwal(request):
    status_filter = request.GET.get('status', 'mendatang')
    today = timezone.localdate()

    has_imunisasi = Imunisasi.objects.filter(jadwal_id=OuterRef('pk'))
    has_periksa_balita = PemeriksaanBalita.objects.filter(jadwal_id=OuterRef('pk'))
    has_periksa_bumil = PemeriksaanBumil.objects.filter(jadwal_id=OuterRef('pk'))

    # Ambil base query
    jadwal_qs = JadwalKegiatan.objects.select_related("posyandu").annotate(
        ada_transaksi=Exists(has_imunisasi) | Exists(has_periksa_balita) | Exists(has_periksa_bumil)
    )
    jadwal_qs = jadwal_qs.filter(posyandu__in=_posyandu_queryset_petugas(request))

    search = (request.GET.get("search") or "").strip()
    kegiatan = (request.GET.get("kegiatan") or "").strip()
    if search:
        jadwal_qs = jadwal_qs.filter(
            Q(posyandu__nama__icontains=search)
            | Q(jns_kegiatan__icontains=search)
        )
    valid_kegiatan = {value for value, _label in JadwalKegiatan.KEGIATAN}
    if kegiatan in valid_kegiatan:
        jadwal_qs = jadwal_qs.filter(jns_kegiatan=kegiatan)
    else:
        kegiatan = ""

    if status_filter == 'riwayat':
        jadwal = jadwal_qs.filter(
            tgl_kegiatan__lt=today
        ).order_by('-tgl_kegiatan', '-jam_mulai', '-id_jadwal')
    else:
        jadwal = jadwal_qs.filter(
            tgl_kegiatan__gte=today
        ).order_by('tgl_kegiatan', 'jam_mulai', 'id_jadwal')

    # Batasi 10 data per halaman agar query super ringan
    paginator = Paginator(jadwal, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "posyandu/list.html", {
        "page_obj": page_obj,
        "status_filter": status_filter,
        "search": search,
        "kegiatan": kegiatan,
    })


# =========================
# CREATE JADWAL
# =========================
@login_required
@kader_required
def create(request):
    posyandu_otomatis = _posyandu_tugas_kader(request)
    if posyandu_otomatis is None:
        messages.error(
            request,
            "Tempat tugas Kader belum ditetapkan. Hubungi Admin Kelurahan untuk mengatur Posyandu Kader.",
        )
        return redirect("posyandu:list_jadwal")

    if request.method == "POST":
        form = JadwalKegiatanForm(request.POST)

        if form.is_valid():
            jadwal = form.save(commit=False)
            # Lokasi selalu mengikuti tempat tugas Kader. Abaikan nilai Posyandu
            # apa pun yang mungkin disisipkan pada POST dari browser.
            jadwal.posyandu = posyandu_otomatis
            jadwal.save()

            messages.success(
                request,
                f"Jadwal kegiatan berhasil ditambahkan untuk {posyandu_otomatis.nama}.",
            )
            return redirect("posyandu:list_jadwal")
    else:
        form = JadwalKegiatanForm()

    return render(request, "posyandu/create.html", {
        "form": form,
        "posyandu_otomatis": posyandu_otomatis,
    })


# =========================
# EDIT JADWAL
# =========================
@login_required
@kader_required
def edit_jadwal(request, id_jadwal):
    posyandu_otomatis = _posyandu_tugas_kader(request)
    if posyandu_otomatis is None:
        messages.error(
            request,
            "Tempat tugas Kader belum ditetapkan. Hubungi Admin Kelurahan untuk mengatur Posyandu Kader.",
        )
        return redirect("posyandu:list_jadwal")

    # Kader hanya dapat mengubah jadwal pada Posyandu tempat tugasnya.
    jadwal = get_object_or_404(
        JadwalKegiatan,
        id_jadwal=id_jadwal,
        posyandu=posyandu_otomatis,
    )

    if request.method == 'POST':
        form = JadwalKegiatanForm(request.POST, instance=jadwal)
        if form.is_valid():
            jadwal_baru = form.save(commit=False)
            jadwal_baru.posyandu = posyandu_otomatis
            jadwal_baru.save()
            messages.success(
                request,
                f"Jadwal {jadwal_baru.jns_kegiatan} berhasil diperbarui untuk {posyandu_otomatis.nama}!",
            )
            return redirect('posyandu:list_jadwal')
    else:
        form = JadwalKegiatanForm(instance=jadwal)

    context = {
        'form': form,
        'jadwal': jadwal,
        'posyandu_otomatis': posyandu_otomatis,
    }
    return render(request, 'posyandu/edit.html', context)


# =========================
# DELETE JADWAL
# =========================
@login_required
@kader_required
@require_POST
def delete(request, id):
    jadwal = get_object_or_404(
        JadwalKegiatan,
        id_jadwal=id,
        posyandu__in=_posyandu_queryset_petugas(request),
    )
    if (
        jadwal.pemeriksaan_balita.exists()
        or jadwal.pemeriksaan_bumil.exists()
        or jadwal.imunisasi.exists()
        or jadwal.kehadiran.exists()
    ):
        messages.error(
            request,
            "Jadwal tidak dapat dihapus karena sudah memiliki riwayat pelayanan. "
            "Gunakan riwayat jadwal sebagai arsip pelayanan Posyandu.",
        )
        return redirect("posyandu:list_jadwal")

    jadwal.delete()
    messages.success(request, "Jadwal berhasil dihapus")
    return redirect("posyandu:list_jadwal")





# =========================
# BAGIAN AKTOR ADMIN
# =========================

@login_required
@admin_required
def daftar_petugas_kader(request):
    search = request.GET.get("search", "").strip()
    petugas_queryset = _master_petugas_items("kader", search)
    paginator = Paginator(petugas_queryset, 5)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "posyandu/petugas_list.html", {
        "page_obj": page_obj,
        "list_posyandu": Posyandu.objects.all().order_by("desa", "nama"),
        "level_petugas": "kader",
        "search": search,
    })


@login_required
@admin_required
def daftar_bidan(request):
    search = request.GET.get("search", "").strip()
    petugas_items = _master_petugas_items("bidan", search)
    paginator = Paginator(petugas_items, 5)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "posyandu/petugas_list.html", {
        "page_obj": page_obj,
        "level_petugas": "bidan",
        "search": search,
    })


def _master_petugas_items(level, search=""):
    if level not in {"kader", "bidan"}:
        return []

    queryset = (
        Petugas.objects
        .filter(level=level)
        .select_related("posyandu", "user")
        .order_by("nama", "pk")
    )

    if level == "kader":
        if search:
            queryset = queryset.filter(
                Q(nama__icontains=search)
                | Q(no_telp__icontains=search)
                | Q(alamat__icontains=search)
                | Q(posyandu__nama__icontains=search)
                | Q(posyandu__desa__icontains=search)
            )
        return queryset

    items = decorate_bidan_coverage(queryset)
    if not search:
        return items

    key = search.lower()
    return [
        item for item in items
        if key in " ".join([
            item.nama or "",
            item.no_telp or "",
            item.alamat or "",
            item.cakupan_search or "",
        ]).lower()
    ]


def _petugas_export_table(level, search=""):
    items = list(_master_petugas_items(level, search))

    if level == "bidan":
        headers = [
            "No", "Nama Bidan", "Posyandu Utama", "Cakupan Wilayah",
            "Jumlah Posyandu", "No. Telepon", "Alamat", "Status Akun",
        ]
        rows = []
        for index, ptg in enumerate(items, start=1):
            coverage = getattr(ptg, "cakupan_nama", "") or "-"
            rows.append([
                index,
                ptg.nama,
                ptg.posyandu.nama if ptg.posyandu else "-",
                coverage,
                getattr(ptg, "cakupan_count", 0),
                ptg.no_telp or "-",
                ptg.alamat or "-",
                "Non-login",
            ])
        return "Master Data Bidan", headers, rows

    headers = [
        "No", "Nama Kader", "Posyandu", "Kelurahan/Desa",
        "No. Telepon", "Alamat", "Username", "Status Akun",
    ]
    rows = []
    for index, ptg in enumerate(items, start=1):
        rows.append([
            index,
            ptg.nama,
            ptg.posyandu.nama if ptg.posyandu else "-",
            ptg.posyandu.desa if ptg.posyandu and ptg.posyandu.desa else "-",
            ptg.no_telp or "-",
            ptg.alamat or "-",
            ptg.user.username if ptg.user else "-",
            "Aktif" if ptg.can_login else "Belum memiliki akun",
        ])
    return "Master Data Kader", headers, rows


@login_required
@admin_required
def export_petugas_excel(request, level):
    if level not in {"kader", "bidan"}:
        return render(request, "403.html", status=403)
    search = request.GET.get("search", "").strip()
    title, headers, rows = _petugas_export_table(level, search)
    return master_excel_response(
        title=title,
        headers=headers,
        rows=rows,
        filter_text=search,
    )


@login_required
@admin_required
def export_petugas_pdf(request, level):
    if level not in {"kader", "bidan"}:
        return render(request, "403.html", status=403)
    search = request.GET.get("search", "").strip()
    title, headers, rows = _petugas_export_table(level, search)
    return master_pdf_response(
        title=title,
        headers=headers,
        rows=rows,
        filter_text=search,
    )


@login_required
@admin_required
def atur_cakupan_bidan(request, pk):
    bidan = get_object_or_404(
        Petugas.objects.select_related("posyandu"),
        pk=pk,
        level="bidan",
    )

    if request.method == "POST":
        selected_ids = request.POST.getlist("cakupan_posyandu")
        try:
            set_bidan_coverage(bidan, selected_ids)
        except BidanCoverageError as error:
            messages.error(request, str(error))
        else:
            messages.success(
                request,
                f"Cakupan wilayah kerja {bidan.nama} berhasil diperbarui.",
            )
            return redirect("posyandu:daftar_bidan")

    current_ids = bidan_coverage_ids(bidan)
    owner_map = active_bidan_owner_map(exclude_bidan=bidan)

    grouped = OrderedDict()
    for posyandu in Posyandu.objects.all().order_by("desa", "nama"):
        posyandu.is_selected = posyandu.pk in current_ids
        posyandu.bidan_lain = owner_map.get(posyandu.pk)
        group_name = posyandu.desa or "Kelurahan / Desa belum diisi"
        grouped.setdefault(group_name, []).append(posyandu)

    return render(request, "posyandu/bidan_cakupan.html", {
        "bidan": bidan,
        "wilayah_groups": list(grouped.items()),
        "current_ids": current_ids,
        "total_cakupan": len(current_ids),
    })
    

@login_required
@admin_required
@transaction.atomic
def edit_petugas(request, pk):
    # petugas yang akan diedit
    petugas = get_object_or_404(Petugas, pk=pk)
    user = petugas.user
    
    if request.method == 'POST':
        user_form = UserEditForm(request.POST, instance=user) if (user and petugas.level in Petugas.LOGIN_LEVELS) else None
        petugas_form = PetugasEditForm(request.POST, instance=petugas)
        
        if petugas_form.is_valid() and (user_form.is_valid() if user_form else True):
            try:
                if user_form:
                    user_form.save()
                updated_petugas = petugas_form.save()
                if updated_petugas.level == "admin":
                    updated_petugas.posyandu = None
                    updated_petugas.save(update_fields=["posyandu"])
                    ensure_single_assignment(updated_petugas, None)
                elif updated_petugas.level == "kader":
                    ensure_single_assignment(updated_petugas, updated_petugas.posyandu)
                # Bidan tidak memiliki akun login. Posyandu utamanya dan seluruh
                # cakupannya diubah melalui halaman Atur Cakupan Wilayah.
                messages.success(request, f"Data petugas {petugas.nama} berhasil diperbarui!")
                return redirect(
                    'posyandu:daftar_petugas_kader'
                    if petugas.level == 'kader' else 'posyandu:daftar_bidan'
                )
            except BidanCoverageError as error:
                messages.error(request, str(error))
            except ValidationError as e:
                messages.error(request, e.messages[0])
    else:
        user_form = UserEditForm(instance=user) if (user and petugas.level in Petugas.LOGIN_LEVELS) else None
        petugas_form = PetugasEditForm(instance=petugas)
        
    return render(request, 'posyandu/petugas_edit.html', {
        'petugas_form': petugas_form,
        'user_form': user_form,
        'petugas': petugas
    })

    
@login_required
@admin_required
@require_POST
def delete_petugas(request, pk):
    petugas = get_object_or_404(Petugas, pk=pk)
    tujuan = (
        "posyandu:daftar_petugas_kader"
        if petugas.level == "kader"
        else "posyandu:daftar_bidan"
    )
    nama_petugas = petugas.nama

    # Data petugas yang sudah tercatat pada pelayanan dipertahankan untuk
    # menjaga jejak penanggung jawab/pencatat pada riwayat kesehatan.
    memiliki_riwayat = (
        petugas.pemeriksaan_balita.exists()
        or petugas.pemeriksaan_bumil.exists()
        or petugas.imunisasi.exists()
        or petugas.pemeriksaan_balita_sebagai_bidan.exists()
        or petugas.pemeriksaan_bumil_sebagai_bidan.exists()
        or petugas.imunisasi_sebagai_bidan.exists()
    )
    if memiliki_riwayat:
        messages.error(
            request,
            f"{nama_petugas} tidak dapat dihapus karena sudah tercatat pada riwayat pelayanan.",
        )
        return redirect(tujuan)

    if petugas.user:
        petugas.user.delete()
    else:
        petugas.delete()
    messages.success(request, f"Petugas {nama_petugas} sukses dihapus dari sistem.")
    return redirect(tujuan)


    

@login_required
@admin_required
@require_POST
def buat_akun_petugas(request, id):
    petugas = get_object_or_404(Petugas, id=id)
    tujuan = (
        "posyandu:daftar_petugas_kader"
        if petugas.level == "kader"
        else "posyandu:daftar_bidan"
    )

    if petugas.level != "kader":
        messages.error(
            request,
            "Bidan tidak memiliki akses login. Akun petugas hanya dibuat untuk Kader.",
        )
        return redirect(tujuan)

    username = (request.POST.get("username") or "").strip()
    password = request.POST.get("password") or ""
    password_confirm = request.POST.get("password_confirm") or ""

    # Jika Admin memilih password manual, konfirmasi wajib sama. Jika kedua
    # kolom password dibiarkan kosong, service akan membuat password otomatis.
    if password or password_confirm:
        if not password:
            messages.error(
                request,
                "Isi password manual atau kosongkan kedua kolom password untuk generate otomatis.",
            )
            return redirect(tujuan)
        if password != password_confirm:
            messages.error(request, "Konfirmasi password tidak sama dengan password.")
            return redirect(tujuan)

    try:
        result = create_petugas_account(
            petugas,
            username=username or None,
            password=password or None,
        )
    except PetugasAccountError as error:
        messages.error(request, str(error))
    else:
        mode_username = "otomatis" if result.username_generated else "manual"
        mode_password = "otomatis" if result.password_generated else "manual"
        messages.success(
            request,
            f"Akun login untuk {petugas.nama} berhasil dibuat. "
            f"Username ({mode_username}): {result.username} | "
            f"Password ({mode_password}): {result.temporary_password}. "
            "Simpan kredensial ini sebelum menutup notifikasi.",
        )

    return redirect(tujuan)


@admin_required
def detail_jadwal_admin(request, id_jadwal):

    # =========================================================
    # AMBIL DATA JADWAL
    # =========================================================
    jadwal = get_object_or_404(
        JadwalKegiatan.objects.select_related("posyandu"),
        id_jadwal=id_jadwal
    )

    sekarang = timezone.localtime()
    tanggal_sekarang = sekarang.date()
    jam_sekarang = sekarang.time().replace(tzinfo=None)

    # =========================================================
    # MENENTUKAN STATUS JADWAL
    # =========================================================
    if jadwal.tgl_kegiatan > tanggal_sekarang:

        status_jadwal = "mendatang"
        status_label = "Belum Dilaksanakan"
        status_deskripsi = (
            "Kegiatan belum dilaksanakan karena tanggal "
            "pelaksanaan masih akan datang."
        )

    elif jadwal.tgl_kegiatan < tanggal_sekarang:

        status_jadwal = "selesai"
        status_label = "Sudah Dilaksanakan"
        status_deskripsi = (
            "Kegiatan telah selesai dilaksanakan karena tanggal "
            "pelaksanaan sudah terlewati."
        )

    else:

        # Jadwal dilaksanakan hari ini
        if (
            jadwal.jam_mulai
            and jam_sekarang < jadwal.jam_mulai
        ):

            status_jadwal = "mendatang"
            status_label = "Belum Dilaksanakan"
            status_deskripsi = (
                "Kegiatan dijadwalkan hari ini, tetapi waktu "
                "pelaksanaannya belum dimulai."
            )

        elif (
            jadwal.jam_selesai
            and jam_sekarang > jadwal.jam_selesai
        ):

            status_jadwal = "selesai"
            status_label = "Sudah Dilaksanakan"
            status_deskripsi = (
                "Kegiatan telah selesai dilaksanakan pada hari ini."
            )

        else:

            status_jadwal = "berlangsung"
            status_label = "Sedang Berlangsung"
            status_deskripsi = (
                "Kegiatan sedang berlangsung sesuai jadwal "
                "yang telah ditentukan."
            )

    # =========================================================
    # SELURUH PESERTA DALAM POSKO
    # =========================================================
    # Tidak difilter berdasarkan status_peserta agar seluruh
    # balita, ibu hamil, tamu, dan kategori lain tetap muncul.
    peserta_queryset = (
        Peserta.objects
        .filter(posko_id=jadwal.posyandu_id)
        .select_related("posko")
        .order_by(
            "status_peserta",
            "nama_peserta"
        )
    )

    # =========================================================
    # DATA KEHADIRAN PADA JADWAL TERSEBUT
    # =========================================================
    data_kehadiran = (
        Kehadiran.objects
        .filter(
            jadwal_id=jadwal.id_jadwal
        )
        .select_related(
            "peserta",
            "jadwal"
        )
    )

    # Membuat mapping agar pencarian kehadiran tidak
    # melakukan query database berulang kali.
    kehadiran_map = {
        kehadiran.peserta_id: kehadiran
        for kehadiran in data_kehadiran
    }

    # =========================================================
    # GABUNGKAN PESERTA DAN DATA KEHADIRAN
    # =========================================================
    semua_peserta = []

    for peserta in peserta_queryset:

        kehadiran = kehadiran_map.get(peserta.pk)

        if kehadiran:
            status_database = kehadiran.status_kehadiran
            data_kehadiran_tersimpan = True
        else:
            status_database = None
            data_kehadiran_tersimpan = False

        # =====================================================
        # MENENTUKAN STATUS KEHADIRAN YANG DITAMPILKAN
        # =====================================================
        if status_database == "hadir":

            status_kode = "hadir"
            status_label_peserta = "Hadir"

        elif status_database == "izin":

            status_kode = "izin"
            status_label_peserta = "Izin"

        else:

            # Status database "tidak" atau belum mempunyai
            # data kehadiran.
            if status_jadwal == "selesai":

                status_kode = "tidak"
                status_label_peserta = "Tidak Hadir"

            else:

                status_kode = "belum"
                status_label_peserta = "Belum Hadir"

        # =====================================================
        # LABEL KATEGORI PESERTA
        # =====================================================
        kategori_kode = (
            peserta.status_peserta.lower()
            if peserta.status_peserta
            else "lainnya"
        )

        get_kategori_display = getattr(
            peserta,
            "get_status_peserta_display",
            None
        )

        if callable(get_kategori_display):
            kategori_label = get_kategori_display()
        else:
            kategori_label = (
                peserta.status_peserta
                or "Kategori Lain"
            )

        # =====================================================
        # LABEL JENIS KELAMIN
        # =====================================================
        get_jk_display = getattr(
            peserta,
            "get_jenis_kelamin_display",
            None
        )

        if callable(get_jk_display):
            jenis_kelamin_label = get_jk_display()
        else:
            jenis_kelamin_label = (
                peserta.jenis_kelamin
                or "-"
            )

        # =====================================================
        # NOMOR IDENTITAS
        # =====================================================
        nomor_identitas = (
            peserta.no_nik
            or peserta.nik_ibu
            or "-"
        )

        semua_peserta.append({
            "peserta": peserta,
            "kehadiran": kehadiran,

            "kategori_kode": kategori_kode,
            "kategori_label": kategori_label,

            "jenis_kelamin_label": jenis_kelamin_label,
            "nomor_identitas": nomor_identitas,

            "status_kode": status_kode,
            "status_label": status_label_peserta,

            "data_kehadiran_tersimpan": (
                data_kehadiran_tersimpan
            ),
        })

    # =========================================================
    # STATISTIK KESELURUHAN PESERTA
    # =========================================================
    total_peserta = len(semua_peserta)

    total_hadir = sum(
        1
        for item in semua_peserta
        if item["status_kode"] == "hadir"
    )

    total_izin = sum(
        1
        for item in semua_peserta
        if item["status_kode"] == "izin"
    )

    total_tidak_hadir = sum(
        1
        for item in semua_peserta
        if item["status_kode"] == "tidak"
    )

    total_belum_hadir = sum(
        1
        for item in semua_peserta
        if item["status_kode"] == "belum"
    )

    if status_jadwal == "selesai":
        total_belum_atau_tidak = total_tidak_hadir
    else:
        total_belum_atau_tidak = total_belum_hadir

    if total_peserta > 0:
        persentase_kehadiran = round(
            total_hadir / total_peserta * 100,
            1
        )
    else:
        persentase_kehadiran = 0

    # =========================================================
    # STATISTIK KATEGORI PESERTA
    # =========================================================
    total_balita = sum(
        1
        for item in semua_peserta
        if item["kategori_kode"] == "balita"
    )

    total_bumil = sum(
        1
        for item in semua_peserta
        if item["kategori_kode"] == "bumil"
    )

    total_kategori_lain = (
        total_peserta
        - total_balita
        - total_bumil
    )

    # =========================================================
    # STATISTIK KEHADIRAN BALITA
    # =========================================================
    total_balita_hadir = sum(
        1
        for item in semua_peserta
        if (
            item["kategori_kode"] == "balita"
            and item["status_kode"] == "hadir"
        )
    )

    total_balita_izin = sum(
        1
        for item in semua_peserta
        if (
            item["kategori_kode"] == "balita"
            and item["status_kode"] == "izin"
        )
    )

    total_balita_tidak = sum(
        1
        for item in semua_peserta
        if (
            item["kategori_kode"] == "balita"
            and item["status_kode"] in ["tidak", "belum"]
        )
    )

    # =========================================================
    # STATISTIK KEHADIRAN IBU HAMIL
    # =========================================================
    total_bumil_hadir = sum(
        1
        for item in semua_peserta
        if (
            item["kategori_kode"] == "bumil"
            and item["status_kode"] == "hadir"
        )
    )

    total_bumil_izin = sum(
        1
        for item in semua_peserta
        if (
            item["kategori_kode"] == "bumil"
            and item["status_kode"] == "izin"
        )
    )

    total_bumil_tidak = sum(
        1
        for item in semua_peserta
        if (
            item["kategori_kode"] == "bumil"
            and item["status_kode"] in ["tidak", "belum"]
        )
    )

    # =========================================================
    # CONTEXT
    # =========================================================
    context = {
        "jadwal": jadwal,

        # Status jadwal
        "status_jadwal": status_jadwal,
        "status_label": status_label,
        "status_deskripsi": status_deskripsi,

        # Daftar peserta
        "semua_peserta": semua_peserta,

        # Statistik umum
        "total_peserta": total_peserta,
        "total_hadir": total_hadir,
        "total_izin": total_izin,
        "total_tidak_hadir": total_tidak_hadir,
        "total_belum_hadir": total_belum_hadir,
        "total_belum_atau_tidak": total_belum_atau_tidak,
        "persentase_kehadiran": persentase_kehadiran,

        # Statistik kategori
        "total_balita": total_balita,
        "total_bumil": total_bumil,
        "total_kategori_lain": total_kategori_lain,

        # Statistik balita
        "total_balita_hadir": total_balita_hadir,
        "total_balita_izin": total_balita_izin,
        "total_balita_tidak": total_balita_tidak,

        # Statistik ibu hamil
        "total_bumil_hadir": total_bumil_hadir,
        "total_bumil_izin": total_bumil_izin,
        "total_bumil_tidak": total_bumil_tidak,
    }

    return render(
        request,
        "posyandu/detail_jadwal_admin.html",
        context
    )


@admin_required
def jadwal_posyandu_admin(request):
    """Monitoring jadwal Admin dengan aturan status yang sama dengan Kader.

    Admin tetap melihat seluruh Posyandu, tetapi default halaman hanya menampilkan
    jadwal mendatang dan diurutkan dari tanggal terdekat. Dengan begitu sebuah
    jadwal pada Posyandu tertentu muncul dengan urutan/status yang sama ketika
    dibuka oleh Kader Posyandu tersebut.
    """
    petugas = getattr(request.user, "petugas", None)
    if not petugas or petugas.level != "admin":
        return render(request, "403.html", status=403)

    today = timezone.localdate()
    search = (request.GET.get("search") or "").strip()
    status_filter = (request.GET.get("status") or "mendatang").strip().lower()
    if status_filter not in {"mendatang", "riwayat"}:
        status_filter = "mendatang"

    posyandu_param = (request.GET.get("posyandu") or "").strip()
    selected_posyandu = None
    if posyandu_param.isdigit():
        selected_posyandu = Posyandu.objects.filter(pk=int(posyandu_param)).first()

    # Satu base-query dipakai untuk kartu ringkasan dan daftar agar angka tidak
    # berbeda dengan hasil filter yang sedang dilihat Admin.
    base_qs = JadwalKegiatan.objects.select_related("posyandu")
    if selected_posyandu is not None:
        base_qs = base_qs.filter(posyandu=selected_posyandu)
    if search:
        base_qs = base_qs.filter(
            Q(posyandu__nama__icontains=search)
            | Q(jns_kegiatan__icontains=search)
        )

    total_mendatang = base_qs.filter(tgl_kegiatan__gte=today).count()
    total_selesai = base_qs.filter(tgl_kegiatan__lt=today).count()

    if status_filter == "riwayat":
        jadwal_admin = base_qs.filter(tgl_kegiatan__lt=today).order_by(
            "-tgl_kegiatan", "-jam_mulai", "-id_jadwal"
        )
    else:
        jadwal_admin = base_qs.filter(tgl_kegiatan__gte=today).order_by(
            "tgl_kegiatan", "jam_mulai", "id_jadwal"
        )

    # Samakan ukuran halaman dengan daftar Jadwal Kader.
    paginator = Paginator(jadwal_admin, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Tampilkan Kader yang menerima jadwal tersebut. Bila kosong, Admin langsung
    # tahu bahwa jadwal belum dapat muncul pada akun Kader mana pun.
    page_posyandu_ids = {item.posyandu_id for item in page_obj.object_list if item.posyandu_id}
    kader_by_posyandu = defaultdict(list)
    if page_posyandu_ids:
        for kader in (
            Petugas.objects.filter(level="kader", posyandu_id__in=page_posyandu_ids)
            .select_related("posyandu")
            .order_by("nama")
        ):
            kader_by_posyandu[kader.posyandu_id].append(kader.nama)

    for jadwal in page_obj.object_list:
        jadwal.kader_penerima = kader_by_posyandu.get(jadwal.posyandu_id, [])

    return render(request, "posyandu/jadwal_admin.html", {
        "petugas": petugas,
        "page_obj": page_obj,
        "today": today,
        "total_semua": total_mendatang + total_selesai,
        "total_mendatang": total_mendatang,
        "total_selesai": total_selesai,
        "search": search,
        "status_filter": status_filter,
        "daftar_posyandu": Posyandu.objects.all().order_by("desa", "nama"),
        "selected_posyandu": selected_posyandu,
        "selected_posyandu_id": selected_posyandu.pk if selected_posyandu else "",
    })

    
    
@login_required
@admin_required
def list_posyandu(request):
    search = request.GET.get("search", "").strip()
    posyandu_list = _master_posyandu_queryset(search)

    paginator = Paginator(posyandu_list, 5)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "posyandu/list_posyandu.html", {
        "page_obj": page_obj,
        "search": search,
    })


def _master_posyandu_queryset(search=""):
    queryset = (
        Posyandu.objects
        .annotate(
            jumlah_kader=Count(
                "petugas",
                filter=Q(petugas__level="kader"),
                distinct=True,
            )
        )
        .order_by("desa", "nama", "pk")
    )
    if search:
        queryset = queryset.filter(
            Q(nama__icontains=search)
            | Q(desa__icontains=search)
            | Q(alamat__icontains=search)
        )
    return queryset


def _posyandu_export_table(search=""):
    owner_map = active_bidan_owner_map()
    items = list(_master_posyandu_queryset(search))
    headers = [
        "No", "Nama Posyandu", "Kelurahan/Desa", "Alamat",
        "Jumlah Kader", "Bidan Penanggung Jawab",
    ]
    rows = [
        [
            index,
            pos.nama,
            pos.desa or "-",
            pos.alamat or "-",
            pos.jumlah_kader,
            owner_map.get(pos.pk, "Belum ditetapkan"),
        ]
        for index, pos in enumerate(items, start=1)
    ]
    return "Master Data Posyandu", headers, rows


@login_required
@admin_required
def export_posyandu_excel(request):
    search = request.GET.get("search", "").strip()
    title, headers, rows = _posyandu_export_table(search)
    return master_excel_response(
        title=title,
        headers=headers,
        rows=rows,
        filter_text=search,
    )


@login_required
@admin_required
def export_posyandu_pdf(request):
    search = request.GET.get("search", "").strip()
    title, headers, rows = _posyandu_export_table(search)
    return master_pdf_response(
        title=title,
        headers=headers,
        rows=rows,
        filter_text=search,
    )


# =========================
# CREATE POSYANDU
# =========================
@login_required
@admin_required
def create_posyandu(request):

    if request.method == "POST":

        form = PosyanduForm(request.POST)

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "data posyandu berhasil ditambahkan"
            )

            return redirect("posyandu:list_posyandu")

    else:
        form = PosyanduForm()

    return render(request, "posyandu/create_posyandu.html", {
        "form": form
    })


# =========================
# EDIT DATA POSYANDU
# =========================
@login_required
@admin_required
def edit_posyandu(request, id):
    # Mencari jadwal berdasarkan primary key kustom: id_jadwal
    posyandu = get_object_or_404(Posyandu, id=id)
    
    if request.method == 'POST':
        form = PosyanduEditForm(request.POST, instance=posyandu)
        
        if form.is_valid():
            form.save()
            messages.success(request, f"data {posyandu.nama} berhasil diperbarui!")
            # Silakan sesuaikan nama URL list jadwal kamu di sini
            return redirect('posyandu:list_posyandu') 
    else:
        form = PosyanduEditForm(instance=posyandu)
        
    context = {
        'form': form,
        'posyandu': posyandu,
    }
    return render(request, 'posyandu/posyandu_edit.html', context)

# =========================
# DELETE JADWAL
# =========================
@login_required
@admin_required
@require_POST
def delete_posyandu(request, id):
    posyandu = get_object_or_404(Posyandu, id=id)

    # Master Posyandu yang sudah dipakai oleh data operasional tidak boleh
    # dihapus agar riwayat pelayanan dan pelaporan tetap utuh.
    has_history = (
        posyandu.peserta_set.exists()
        or posyandu.jadwalkegiatan_set.exists()
        or posyandu.petugas.exists()
        or posyandu.penugasanpetugas_set.exists()
    )
    if has_history:
        messages.error(
            request,
            "Posyandu tidak dapat dihapus karena sudah digunakan oleh data peserta, "
            "jadwal, petugas, atau penugasan. Nonaktifkan/ubah data terkait terlebih dahulu."
        )
        return redirect("posyandu:list_posyandu")

    posyandu.delete()
    messages.success(request, "Data posyandu berhasil dihapus")
    return redirect("posyandu:list_posyandu")


    

# =========================================================
# HELPER FILTER LAPORAN IBU HAMIL
# =========================================================
def _parse_rentang_tanggal(request):
    awal_value = request.GET.get("tanggal_awal", "").strip()
    akhir_value = request.GET.get("tanggal_akhir", "").strip()
    awal = parse_date(awal_value) if awal_value else None
    akhir = parse_date(akhir_value) if akhir_value else None
    if awal and akhir and awal > akhir:
        awal, akhir = akhir, awal
    return awal, akhir


def filter_data_laporan_bumil(request):
    """
    Digunakan untuk memfilter data laporan pemeriksaan ibu hamil.

    Filter yang tersedia:
    1. Pencarian nama peserta
    2. Periode pemeriksaan
    3. Rentang tanggal khusus
    4. Status kehamilan
    5. Petugas pemeriksaan
    """

    keyword = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    petugas_id = request.GET.get("petugas", "").strip()

    periode_parameter = request.GET.get("periode")
    tanggal_awal_value = request.GET.get("tanggal_awal", "").strip()
    tanggal_akhir_value = request.GET.get("tanggal_akhir", "").strip()

    # Mendukung URL filter lama yang hanya menggunakan tanggal.
    if periode_parameter is None and (
        tanggal_awal_value or tanggal_akhir_value
    ):
        periode = "custom"
    else:
        periode = periode_parameter or "semua"

    periode_valid = {
        "semua",
        "hari_ini",
        "7_hari",
        "bulan_ini",
        "tahun_ini",
        "custom",
    }

    if periode not in periode_valid:
        periode = "semua"

    status_valid = {
        "normal",
        "resiko",
        "anemia",
        "kek",
    }

    if status not in status_valid:
        status = ""

    # Validasi ID petugas.
    selected_petugas_id = None

    if petugas_id.isdigit():
        selected_petugas_id = int(petugas_id)
    else:
        petugas_id = ""

    hari_ini = timezone.localdate()

    tanggal_awal = None
    tanggal_akhir = None

    # =====================================================
    # FILTER PERIODE
    # =====================================================
    if periode == "hari_ini":
        tanggal_awal = hari_ini
        tanggal_akhir = hari_ini

    elif periode == "7_hari":
        tanggal_awal = hari_ini - timedelta(days=6)
        tanggal_akhir = hari_ini

    elif periode == "bulan_ini":
        tanggal_awal = hari_ini.replace(day=1)
        tanggal_akhir = hari_ini

    elif periode == "tahun_ini":
        tanggal_awal = hari_ini.replace(
            month=1,
            day=1
        )
        tanggal_akhir = hari_ini

    elif periode == "custom":
        if tanggal_awal_value:
            tanggal_awal = parse_date(tanggal_awal_value)

        if tanggal_akhir_value:
            tanggal_akhir = parse_date(tanggal_akhir_value)

    else:
        tanggal_awal = None
        tanggal_akhir = None
        tanggal_awal_value = ""
        tanggal_akhir_value = ""

    # Jika tanggal awal lebih besar dari tanggal akhir,
    # posisi tanggal ditukar secara otomatis.
    if (
        tanggal_awal
        and tanggal_akhir
        and tanggal_awal > tanggal_akhir
    ):
        tanggal_awal, tanggal_akhir = (
            tanggal_akhir,
            tanggal_awal,
        )

    # Perbarui value input tanggal.
    if tanggal_awal:
        tanggal_awal_value = tanggal_awal.isoformat()

    if tanggal_akhir:
        tanggal_akhir_value = tanggal_akhir.isoformat()

    # =====================================================
    # QUERYSET DASAR
    # =====================================================
    data = (
        PemeriksaanBumil.objects
        .select_related(
            "peserta",
            "petugas",
            "jadwal",
        )
        .order_by("-tgl_pemeriksaan")
    )

    # =====================================================
    # PENCARIAN NAMA IBU HAMIL
    # =====================================================
    if keyword:
        data = data.filter(
            peserta__nama_peserta__icontains=keyword
        )

    # =====================================================
    # FILTER STATUS KEHAMILAN
    # =====================================================
    if status:
        data = data.filter(
            status_kehamilan=status
        )

    # =====================================================
    # FILTER PETUGAS
    # =====================================================
    if selected_petugas_id:
        data = data.filter(
            petugas_id=selected_petugas_id
        )

    # =====================================================
    # FILTER TANGGAL
    # =====================================================
    if tanggal_awal:
        data = data.filter(
            tgl_pemeriksaan__date__gte=tanggal_awal
        )

    if tanggal_akhir:
        data = data.filter(
            tgl_pemeriksaan__date__lte=tanggal_akhir
        )

    # Label untuk ditampilkan pada halaman.
    periode_labels = {
        "semua": "Semua periode",
        "hari_ini": "Hari ini",
        "7_hari": "7 hari terakhir",
        "bulan_ini": "Bulan ini",
        "tahun_ini": "Tahun ini",
        "custom": "Rentang tanggal khusus",
    }

    status_labels = {
        "normal": "Normal",
        "resiko": "Risiko Tinggi",
        "anemia": "Anemia",
        "kek": "KEK",
    }

    if tanggal_awal and tanggal_akhir:
        rentang_label = (
            f"{tanggal_awal.strftime('%d-%m-%Y')} "
            f"sampai {tanggal_akhir.strftime('%d-%m-%Y')}"
        )

    elif tanggal_awal:
        rentang_label = (
            f"Mulai {tanggal_awal.strftime('%d-%m-%Y')}"
        )

    elif tanggal_akhir:
        rentang_label = (
            f"Sampai {tanggal_akhir.strftime('%d-%m-%Y')}"
        )

    else:
        rentang_label = "Semua tanggal pemeriksaan"

    filter_state = {
        "keyword": keyword,
        "status": status,
        "status_label": status_labels.get(status, ""),
        "petugas_id": petugas_id,
        "selected_petugas_id": selected_petugas_id,
        "periode": periode,
        "periode_label": periode_labels.get(
            periode,
            "Semua periode"
        ),
        "tanggal_awal": tanggal_awal_value,
        "tanggal_akhir": tanggal_akhir_value,
        "rentang_label": rentang_label,
    }

    return data, filter_state


# =========================================================
# LAPORAN IBU HAMIL
# =========================================================
@login_required
@admin_required
def laporan_bumil(request):
    data, filter_state = filter_data_laporan_bumil(
        request
    )

    # =====================================================
    # STATISTIK BERDASARKAN HASIL FILTER
    # =====================================================
    total_data = data.count()

    total_normal = data.filter(
        status_kehamilan="normal"
    ).count()

    total_resiko = data.filter(
        status_kehamilan="resiko"
    ).count()

    total_anemia = data.filter(
        status_kehamilan="anemia"
    ).count()

    total_kek = data.filter(
        status_kehamilan="kek"
    ).count()

    # =====================================================
    # DAFTAR PETUGAS UNTUK DROPDOWN
    # =====================================================
    petugas_ids = (
        PemeriksaanBumil.objects
        .exclude(petugas_id__isnull=True)
        .values_list(
            "petugas_id",
            flat=True
        )
        .distinct()
    )

    petugas_options = list(
        Petugas.objects.filter(
            pk__in=petugas_ids
        )
    )

    # Mengurutkan berdasarkan hasil __str__ model Petugas.
    petugas_options.sort(
        key=lambda item: str(item).lower()
    )

    selected_petugas_label = ""

    if filter_state["selected_petugas_id"]:
        selected_petugas = next(
            (
                petugas
                for petugas in petugas_options
                if petugas.pk
                == filter_state["selected_petugas_id"]
            ),
            None
        )

        if selected_petugas:
            selected_petugas_label = str(
                selected_petugas
            )

    # =====================================================
    # JUMLAH FILTER AKTIF
    # =====================================================
    active_filter_count = sum([
        bool(filter_state["keyword"]),
        bool(filter_state["status"]),
        bool(filter_state["selected_petugas_id"]),
        filter_state["periode"] != "semua",
    ])

    # =====================================================
    # PAGINATION
    # =====================================================
    paginator = Paginator(data, 10)

    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Menghilangkan parameter page agar dapat digunakan
    # pada navigasi pagination, Excel, dan PDF.
    query_params = request.GET.copy()
    query_params.pop("page", None)
    query_string = query_params.urlencode()

    context = {
        "data": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,

        "petugas_options": petugas_options,
        "selected_petugas_label": selected_petugas_label,

        "total_data": total_data,
        "total_normal": total_normal,
        "total_resiko": total_resiko,
        "total_anemia": total_anemia,
        "total_kek": total_kek,

        "active_filter_count": active_filter_count,
        "query_string": query_string,

        **filter_state,
    }

    return render(
        request,
        "posyandu/laporan_admin/laporan_bumil.html",
        context
    )
    
BULAN_INDONESIA = [
    (1, "Januari"),
    (2, "Februari"),
    (3, "Maret"),
    (4, "April"),
    (5, "Mei"),
    (6, "Juni"),
    (7, "Juli"),
    (8, "Agustus"),
    (9, "September"),
    (10, "Oktober"),
    (11, "November"),
    (12, "Desember"),
]


def _filter_laporan_balita_admin(request):
    """Kembalikan queryset dan state filter Bulan/Tahun/Posyandu."""
    today = timezone.localdate()
    bulan_label_map = dict(BULAN_INDONESIA)

    try:
        bulan = int(request.GET.get("bulan", today.month))
    except (TypeError, ValueError):
        bulan = today.month
    if bulan not in bulan_label_map:
        bulan = today.month

    try:
        tahun = int(request.GET.get("tahun", today.year))
    except (TypeError, ValueError):
        tahun = today.year
    if tahun < 2000 or tahun > today.year + 5:
        tahun = today.year

    daftar_posyandu = list(Posyandu.objects.all().order_by("nama"))
    posyandu_id_raw = request.GET.get("posyandu", "").strip()
    selected_posyandu = None
    if posyandu_id_raw:
        try:
            posyandu_id = int(posyandu_id_raw)
        except (TypeError, ValueError):
            posyandu_id = None
        if posyandu_id is not None:
            selected_posyandu = next(
                (item for item in daftar_posyandu if item.pk == posyandu_id),
                None,
            )

    data = (
        PemeriksaanBalita.objects
        .select_related("peserta", "petugas", "jadwal", "jadwal__posyandu")
        .filter(
            tgl_pemeriksaan__year=tahun,
            tgl_pemeriksaan__month=bulan,
        )
        .order_by("-tgl_pemeriksaan", "peserta__nama_peserta")
    )
    if selected_posyandu is not None:
        data = data.filter(jadwal__posyandu=selected_posyandu)

    tahun_data = set(
        PemeriksaanBalita.objects
        .values_list("tgl_pemeriksaan__year", flat=True)
        .distinct()
    )
    tahun_data.discard(None)
    tahun_data.add(today.year)
    tahun_data.add(tahun)
    tahun_options = sorted(tahun_data, reverse=True)

    from urllib.parse import urlencode
    query_params = {"bulan": bulan, "tahun": tahun}
    if selected_posyandu is not None:
        query_params["posyandu"] = selected_posyandu.pk

    bulan_label = bulan_label_map[bulan]
    state = {
        "bulan": bulan,
        "bulan_label": bulan_label,
        "bulan_options": BULAN_INDONESIA,
        "tahun": tahun,
        "tahun_options": tahun_options,
        "daftar_posyandu": daftar_posyandu,
        "selected_posyandu": selected_posyandu,
        "selected_posyandu_id": selected_posyandu.pk if selected_posyandu else None,
        "posyandu_label": selected_posyandu.nama if selected_posyandu else "Semua Posyandu",
        "periode_label": f"{bulan_label} {tahun}",
        "query_string": urlencode(query_params),
    }
    return data, state


@login_required
@admin_required
def laporan_balita(request):
    """Laporan balita Admin Kelurahan: Bulan, Tahun, dan Posyandu."""
    data, filter_state = _filter_laporan_balita_admin(request)

    context = {
        "data": data,
        "total_data": data.count(),
        "total_normal": data.filter(status_gizi="normal").count(),
        "total_stunting": data.filter(
            status_gizi__in=["stunting", "stunting_berat"]
        ).count(),
        **filter_state,
    }
    return render(
        request,
        "posyandu/laporan_admin/laporan_balita.html",
        context,
    )

# =========================================================
# LAPORAN IMUNISASI - DAFTAR JADWAL
# =========================================================
@login_required
@admin_required
def laporan_imunisasi(request):
    """Laporan imunisasi Admin: Bulan, Tahun, dan Posyandu."""
    today = timezone.localdate()
    bulan_label_map = dict(BULAN_INDONESIA)

    try:
        bulan = int(request.GET.get("bulan", today.month))
    except (TypeError, ValueError):
        bulan = today.month
    if bulan not in bulan_label_map:
        bulan = today.month

    try:
        tahun = int(request.GET.get("tahun", today.year))
    except (TypeError, ValueError):
        tahun = today.year
    if tahun < 2000 or tahun > today.year + 5:
        tahun = today.year

    daftar_posyandu = list(Posyandu.objects.all().order_by("nama"))
    selected_posyandu = None
    posyandu_raw = request.GET.get("posyandu", "").strip()
    if posyandu_raw:
        try:
            posyandu_id = int(posyandu_raw)
        except (TypeError, ValueError):
            posyandu_id = None
        if posyandu_id is not None:
            selected_posyandu = next(
                (item for item in daftar_posyandu if item.pk == posyandu_id),
                None,
            )

    queryset = (
        JadwalKegiatan.objects
        .filter(
            jns_kegiatan="Imunisasi",
            tgl_kegiatan__year=tahun,
            tgl_kegiatan__month=bulan,
        )
        .select_related("posyandu")
        .annotate(
            total_pemberian=Count("imunisasi", distinct=True),
            total_peserta_divaksin=Count("imunisasi__peserta", distinct=True),
            total_balita_divaksin=Count(
                "imunisasi__peserta",
                filter=Q(imunisasi__peserta__status_peserta="balita"),
                distinct=True,
            ),
            total_bumil_divaksin=Count(
                "imunisasi__peserta",
                filter=Q(imunisasi__peserta__status_peserta="bumil"),
                distinct=True,
            ),
            tanggal_pemberian_terakhir=Max("imunisasi__tgl_pemberian"),
        )
    )

    if selected_posyandu is not None:
        queryset = queryset.filter(posyandu=selected_posyandu)

    data = list(queryset.order_by("-tgl_kegiatan", "-id_jadwal"))

    hari_ini = timezone.localdate()
    for jadwal in data:
        if jadwal.tgl_kegiatan > hari_ini:
            jadwal.status_laporan = "mendatang"
            jadwal.status_label = "Mendatang"
        elif jadwal.tgl_kegiatan == hari_ini:
            jadwal.status_laporan = "hari_ini"
            jadwal.status_label = "Hari Ini"
        else:
            jadwal.status_laporan = "selesai"
            jadwal.status_label = "Selesai"

    tahun_data = set(
        JadwalKegiatan.objects
        .filter(jns_kegiatan="Imunisasi")
        .values_list("tgl_kegiatan__year", flat=True)
        .distinct()
    )
    tahun_data.discard(None)
    tahun_data.update({today.year, tahun})

    total_jadwal = len(data)
    total_jadwal_berisi = sum(1 for jadwal in data if jadwal.total_pemberian > 0)

    context = {
        "data": data,
        "bulan": bulan,
        "bulan_label": bulan_label_map[bulan],
        "bulan_options": BULAN_INDONESIA,
        "tahun": tahun,
        "tahun_options": sorted(tahun_data, reverse=True),
        "daftar_posyandu": daftar_posyandu,
        "selected_posyandu": selected_posyandu,
        "selected_posyandu_id": selected_posyandu.pk if selected_posyandu else None,
        "posyandu_label": selected_posyandu.nama if selected_posyandu else "Semua Posyandu",
        "periode_label": f"{bulan_label_map[bulan]} {tahun}",
        "total_jadwal": total_jadwal,
        "total_jadwal_berisi": total_jadwal_berisi,
        "total_jadwal_kosong": total_jadwal - total_jadwal_berisi,
        "total_pemberian": sum(jadwal.total_pemberian for jadwal in data),
    }

    return render(
        request,
        "posyandu/laporan_admin/laporan_imunisasi.html",
        context,
    )


# =========================================================
# FUNGSI BANTU DETAIL IMUNISASI PER JADWAL
# =========================================================
# =========================================================
# FUNGSI BANTU DETAIL IMUNISASI PER JADWAL
# =========================================================
def susun_detail_imunisasi_jadwal(jadwal):

    # =====================================================
    # DATA IMUNISASI PADA JADWAL
    # =====================================================
    data_imunisasi = (
        Imunisasi.objects
        .filter(jadwal=jadwal)
        .select_related(
            "peserta",
            "petugas",
            "jadwal",
            "jadwal__posyandu",
        )
        .order_by(
            "peserta__status_peserta",
            "peserta__nama_peserta",
            "id_imunisasi",
        )
    )

    # Menyimpan semua vaksin berdasarkan ID peserta
    imunisasi_per_peserta = defaultdict(list)

    for imunisasi in data_imunisasi:
        imunisasi_per_peserta[
            imunisasi.peserta_id
        ].append(imunisasi)

    # =====================================================
    # SEMUA PESERTA DALAM POSKO JADWAL
    # =====================================================
    peserta_queryset = (
        Peserta.objects
        .filter(
            posko_id=jadwal.posyandu_id,
            status_peserta__in=[
                "balita",
                "bumil",
            ],
        )
        .select_related("posko")
        .order_by(
            "status_peserta",
            "nama_peserta",
        )
    )

    daftar_peserta = []

    total_sudah = 0
    total_belum = 0
    total_pemberian = 0
    total_balita = 0
    total_bumil = 0

    for peserta in peserta_queryset:

        daftar_vaksin = imunisasi_per_peserta.get(
            peserta.pk,
            []
        )

        sudah_divaksin = bool(daftar_vaksin)

        if peserta.status_peserta == "balita":
            total_balita += 1

        elif peserta.status_peserta == "bumil":
            total_bumil += 1

        if sudah_divaksin:
            total_sudah += 1
        else:
            total_belum += 1

        total_pemberian += len(daftar_vaksin)

        # Mengambil tanggal pemberian terakhir
        tanggal_terakhir = None

        if daftar_vaksin:
            tanggal_terakhir = max(
                vaksin.tgl_pemberian
                for vaksin in daftar_vaksin
            )

        daftar_peserta.append({
            "peserta": peserta,
            "daftar_vaksin": daftar_vaksin,
            "sudah_divaksin": sudah_divaksin,
            "jumlah_vaksin": len(daftar_vaksin),
            "tanggal_terakhir": tanggal_terakhir,
        })

    return {
        "jadwal": jadwal,
        "daftar_peserta": daftar_peserta,

        "total_peserta": len(daftar_peserta),
        "total_balita": total_balita,
        "total_bumil": total_bumil,
        "total_sudah": total_sudah,
        "total_belum": total_belum,
        "total_pemberian": total_pemberian,
    }


# =========================================================
# DETAIL LAPORAN IMUNISASI
# =========================================================
@login_required
@admin_required
def detail_laporan_imunisasi(request, id_jadwal):

    jadwal = get_object_or_404(
        JadwalKegiatan.objects.select_related(
            "posyandu"
        ),
        id_jadwal=id_jadwal
    )

    context = susun_detail_imunisasi_jadwal(
        jadwal
    )

    return render(
        request,
        "posyandu/laporan_admin/detail_laporan_imunisasi.html",
        context,
    )



@login_required
@admin_required
def laporan_triwulan(request):
    """Laporan triwulan khusus Admin Kelurahan.

    Halaman tetap menampilkan satu Posyandu pada satu waktu. Admin dapat
    memilih Posyandu dari filter, berpindah dengan tombol sebelumnya/berikutnya,
    mengunduh PDF Posyandu yang sedang dipilih, atau mengunduh seluruh Posyandu
    menjadi satu file PDF (setiap Posyandu dimulai pada halaman baru).
    """
    tahun, triwulan = _ambil_parameter(request)

    daftar_posyandu = list(Posyandu.objects.all().order_by("nama"))
    selected_posyandu = None
    selected_index = 0

    selected_raw = request.GET.get("posyandu", "").strip()
    try:
        selected_id = int(selected_raw) if selected_raw else None
    except (TypeError, ValueError):
        selected_id = None

    if selected_id is not None:
        for index, posyandu in enumerate(daftar_posyandu):
            if posyandu.pk == selected_id:
                selected_posyandu = posyandu
                selected_index = index
                break

    # Kompatibilitas dengan navigasi pos_page dari versi sebelumnya.
    if selected_posyandu is None and daftar_posyandu:
        try:
            requested_page = max(1, int(request.GET.get("pos_page", 1)))
        except (TypeError, ValueError):
            requested_page = 1
        selected_index = min(requested_page - 1, len(daftar_posyandu) - 1)
        selected_posyandu = daftar_posyandu[selected_index]

    paginator_posyandu = Paginator(daftar_posyandu, 1)
    posyandu_page = paginator_posyandu.get_page(
        selected_index + 1 if daftar_posyandu else 1
    )

    posyandu_ids = [selected_posyandu.pk] if selected_posyandu else []
    context = build_context_laporan_triwulan(tahun, triwulan, posyandu_ids)

    paginator_balita = Paginator(context['data_balita'], 5)
    context['data_balita'] = paginator_balita.get_page(
        request.GET.get('page_balita', 1)
    )

    paginator_bumil = Paginator(context['data_bumil'], 10)
    context['data_bumil'] = paginator_bumil.get_page(
        request.GET.get('page_bumil', 1)
    )

    context.update({
        'posyandu_page': posyandu_page,
        'selected_posyandu': selected_posyandu,
        'selected_posyandu_id': selected_posyandu.pk if selected_posyandu else None,
        'daftar_posyandu_filter': daftar_posyandu,
        'jumlah_posyandu_admin': len(daftar_posyandu),
    })

    return render(request, 'posyandu/laporan_admin/laporan_triwulan.html', context)

@login_required
@admin_required
def semua_laporan (request):
    
    return render (request, 'posyandu/laporan_admin/semua_laporan.html')


#PDF LAPORAN 
@login_required
@admin_required
def export_balita_excel(request):
    """Export Excel laporan balita mengikuti filter Bulan/Tahun/Posyandu."""
    data, filter_state = _filter_laporan_balita_admin(request)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Laporan Balita"

    ws.merge_cells("A1:J1")
    ws["A1"] = "LAPORAN PEMERIKSAAN BALITA"
    ws["A1"].font = Font(size=14, bold=True, color="FFFFFF")
    ws["A1"].alignment = Alignment(horizontal="center")
    ws["A1"].fill = PatternFill(
        start_color="2845D6",
        end_color="2845D6",
        fill_type="solid",
    )

    ws.merge_cells("A2:J2")
    ws["A2"] = (
        f"Periode: {filter_state['periode_label']} | "
        f"Posyandu: {filter_state['posyandu_label']}"
    )
    ws["A2"].alignment = Alignment(horizontal="center")
    ws["A2"].font = Font(italic=True, color="475569")

    headers = [
        "No",
        "Nama Balita",
        "Posyandu",
        "Usia (Bulan)",
        "Berat Badan (kg)",
        "Tinggi Badan (cm)",
        "LiLA (cm)",
        "Status Gizi",
        "Petugas",
        "Tanggal Pemeriksaan",
    ]
    header_fill = PatternFill(
        start_color="E8EDFF",
        end_color="E8EDFF",
        fill_type="solid",
    )
    for col_num, header in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=col_num, value=header)
        cell.font = Font(bold=True, color="1E293B")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for row_num, item in enumerate(data, start=5):
        values = [
            row_num - 4,
            item.peserta.nama_peserta,
            item.jadwal.posyandu.nama if item.jadwal and item.jadwal.posyandu else "-",
            item.usia_bulan,
            item.berat_badan,
            item.tinggi_badan,
            item.lila_balita,
            item.get_status_gizi_display(),
            item.petugas_nama,
            timezone.localtime(item.tgl_pemeriksaan).strftime("%d-%m-%Y"),
        ]
        for col_num, value in enumerate(values, start=1):
            cell = ws.cell(row=row_num, column=col_num, value=value)
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    widths = [8, 26, 24, 13, 18, 19, 13, 18, 22, 20]
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(index)].width = width

    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A4:J{max(ws.max_row, 4)}"

    filename = (
        f"Laporan_Balita_{filter_state['tahun']}_"
        f"{filter_state['bulan']:02d}.xlsx"
    )
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required
@admin_required
def export_bumil_excel(request):
    tanggal_awal, tanggal_akhir = _parse_rentang_tanggal(request)

    data = PemeriksaanBumil.objects.select_related(
        'peserta',
        'petugas'
    )

    if tanggal_awal:
        data = data.filter(
            tgl_pemeriksaan__date__gte=tanggal_awal
        )

    if tanggal_akhir:
        data = data.filter(
            tgl_pemeriksaan__date__lte=tanggal_akhir
        )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Laporan Ibu Hamil"

    # Judul
    ws.merge_cells('A1:I1')
    ws['A1'] = "LAPORAN PEMERIKSAAN IBU HAMIL"
    ws['A1'].font = Font(size=14, bold=True)
    ws['A1'].alignment = Alignment(horizontal='center')

    # Header
    headers = [
        "No",
        "Nama Ibu Hamil",
        "Usia Kehamilan",
        "Berat Badan",
        "LILA",
        "Tekanan Darah",
        "Status",
        "Petugas",
        "Tanggal"
    ]

    header_fill = PatternFill(
        start_color="D9EAD3",
        end_color="D9EAD3",
        fill_type="solid"
    )

    for col_num, header in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col_num)
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = header_fill

    row = 4

    for no, item in enumerate(data, start=1):

        ws.cell(row=row, column=1).value = no
        ws.cell(row=row, column=2).value = item.peserta.nama_peserta
        ws.cell(row=row, column=3).value = item.usia_kehamilan
        ws.cell(row=row, column=4).value = item.berat_badan
        ws.cell(row=row, column=5).value = item.lila_bumil
        ws.cell(row=row, column=6).value = item.tekanan_darah
        ws.cell(row=row, column=7).value = item.get_status_kehamilan_display()
        ws.cell(row=row, column=8).value = item.petugas_nama
        ws.cell(row=row, column=9).value = item.tgl_pemeriksaan.strftime("%d-%m-%Y")

        row += 1

    # Auto Width
    for column_index, column in enumerate(ws.columns, start=1):
        length = max(
            len(str(cell.value)) if cell.value else 0
            for cell in column
        )
        ws.column_dimensions[openpyxl.utils.get_column_letter(column_index)].width = length + 5

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    response[
        'Content-Disposition'
    ] = 'attachment; filename=Laporan_Ibu_Hamil.xlsx'

    wb.save(response)

    return response

@login_required
@admin_required
def cetak_bumil_pdf(request):
    tanggal_awal, tanggal_akhir = _parse_rentang_tanggal(request)

    data = PemeriksaanBumil.objects.select_related(
        'peserta',
        'petugas',
        'jadwal',
        'jadwal__posyandu'
    )

    if tanggal_awal:
        data = data.filter(
            tgl_pemeriksaan__date__gte=tanggal_awal
        )

    if tanggal_akhir:
        data = data.filter(
            tgl_pemeriksaan__date__lte=tanggal_akhir
        )
    
    jadwal = None
    tanggal_pemeriksaan = None

    if data.exists():
        jadwal = data.first().jadwal
        tanggal_pemeriksaan = data.first().tgl_pemeriksaan

    template = get_template(
        'posyandu/laporan_admin/pdf/laporan_bumil.html'
    )

    html = template.render({
        'data': data,
        'jadwal': jadwal,
        'tanggal_awal': tanggal_awal,
        'tanggal_akhir': tanggal_akhir,
        'tanggal_pemeriksaan': tanggal_pemeriksaan
    })

    result = BytesIO()

    pisa_status = pisa.CreatePDF(
        html,
        dest=result
    )

    if pisa_status.err:
        return HttpResponse(
            'Terjadi kesalahan saat membuat PDF'
        )

    response = HttpResponse(
        result.getvalue(),
        content_type='application/pdf'
    )

    response[
        'Content-Disposition'
    ] = 'inline; filename="laporan_bumil.pdf"'

    return response

@login_required
@admin_required
def cetak_balita_pdf(request):
    """Cetak PDF laporan balita mengikuti filter Bulan/Tahun/Posyandu."""
    pemeriksaan_qs, filter_state = _filter_laporan_balita_admin(request)

    peserta_map = OrderedDict()
    for pemeriksaan in pemeriksaan_qs.order_by(
        "peserta__nama_peserta",
        "tgl_pemeriksaan",
    ):
        peserta = peserta_map.setdefault(
            pemeriksaan.peserta_id,
            pemeriksaan.peserta,
        )
        if not hasattr(peserta, "riwayat_periksa"):
            peserta.riwayat_periksa = []
        peserta.riwayat_periksa.append(pemeriksaan)
    data_peserta = list(peserta_map.values())

    jadwal = pemeriksaan_qs.first().jadwal if pemeriksaan_qs.exists() else None

    template = get_template(
        "posyandu/laporan_admin/pdf/pdf_laporan_balita.html"
    )
    html = template.render({
        "data_peserta": data_peserta,
        "status_peserta": "balita",
        "jadwal": jadwal,
        "bulan": filter_state["bulan"],
        "bulan_label": filter_state["bulan_label"],
        "tahun": filter_state["tahun"],
        "periode_label": filter_state["periode_label"],
        "posyandu_nama": filter_state["posyandu_label"],
    })

    result = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=result)
    if pisa_status.err:
        return HttpResponse(
            "Terjadi kesalahan saat membuat PDF",
            status=500,
        )

    response = HttpResponse(
        result.getvalue(),
        content_type="application/pdf",
    )
    response["Content-Disposition"] = (
        f'inline; filename="laporan_balita_{filter_state["tahun"]}_'
        f'{filter_state["bulan"]:02d}.pdf"'
    )
    return response


# =========================================================
# UNDUH PDF IMUNISASI PER JADWAL
# =========================================================
def _resolve_imunisasi_period(request):
    """Validasi filter bulan/tahun laporan imunisasi Admin."""
    today = timezone.localdate()
    bulan_map = dict(BULAN_INDONESIA)

    try:
        bulan = int(request.GET.get("bulan", today.month))
    except (TypeError, ValueError):
        bulan = today.month
    if bulan not in bulan_map:
        bulan = today.month

    try:
        tahun = int(request.GET.get("tahun", today.year))
    except (TypeError, ValueError):
        tahun = today.year
    if tahun < 2000 or tahun > today.year + 5:
        tahun = today.year

    return bulan, tahun, bulan_map[bulan]


def _build_imunisasi_pdf_context(
    *,
    posyandu,
    status_peserta,
    bulan,
    tahun,
    jadwal_id=None,
):
    """Bangun satu laporan imunisasi untuk satu Posyandu."""
    peserta_qs = (
        Peserta.objects
        .filter(status_peserta=status_peserta, posko=posyandu)
        .select_related("posko")
        .order_by("nama_peserta")
    )

    jadwal_qs = JadwalKegiatan.objects.filter(
        jns_kegiatan="Imunisasi",
        posyandu=posyandu,
    )

    if jadwal_id is not None:
        jadwal_qs = jadwal_qs.filter(pk=jadwal_id)
        jadwal = jadwal_qs.first()
        periode_label = (
            jadwal.tgl_kegiatan.strftime("%d-%m-%Y")
            if jadwal
            else f"{dict(BULAN_INDONESIA)[bulan]} {tahun}"
        )
    else:
        jadwal_qs = jadwal_qs.filter(
            tgl_kegiatan__year=tahun,
            tgl_kegiatan__month=bulan,
        )
        jadwal = jadwal_qs.order_by("tgl_kegiatan", "id_jadwal").first()
        periode_label = f"{dict(BULAN_INDONESIA)[bulan]} {tahun}"

    data_peserta = []
    for peserta in peserta_qs:
        imunisasi_qs = (
            Imunisasi.objects
            .filter(
                peserta=peserta,
                jadwal__posyandu=posyandu,
            )
            .select_related("petugas", "jadwal", "jadwal__posyandu")
            .order_by("tgl_pemberian", "id_imunisasi")
        )

        if jadwal_id is not None:
            imunisasi_qs = imunisasi_qs.filter(jadwal_id=jadwal_id)
        else:
            imunisasi_qs = imunisasi_qs.filter(
                jadwal__tgl_kegiatan__year=tahun,
                jadwal__tgl_kegiatan__month=bulan,
            )

        peserta.hadir = imunisasi_qs.exists()
        peserta.vaksin_list = list(
            imunisasi_qs.values_list("jenis_vaksin", flat=True)
        )
        peserta.riwayat_imunisasi = imunisasi_qs

        if peserta.hadir:
            terakhir = imunisasi_qs.last()
            if status_peserta == "balita":
                peserta.usia_saat_vaksin = terakhir.usia_vaksin_display
            else:
                peserta.usia_saat_vaksin = terakhir.usia_kehamilan
            peserta.petugas_imunisasi = terakhir.petugas
            peserta.jadwal_imunisasi = terakhir.jadwal
        else:
            peserta.usia_saat_vaksin = "-"
            peserta.petugas_imunisasi = None
            peserta.jadwal_imunisasi = None

        data_peserta.append(peserta)

    return {
        "data_peserta": data_peserta,
        "status_peserta": status_peserta,
        "jadwal": jadwal,
        "posyandu": posyandu,
        "posyandu_nama": posyandu.nama,
        "bulan": bulan,
        "tahun": tahun,
        "periode_label": periode_label,
    }


def _render_imunisasi_pdf_buffer(context):
    """Render satu Posyandu menjadi buffer PDF."""
    template = get_template(
        "posyandu/laporan_admin/pdf/pdf_laporan_imunisasi.html"
    )
    html = template.render(context)
    buffer = BytesIO()
    status = pisa.CreatePDF(html, dest=buffer)
    if status.err:
        buffer.close()
        raise RuntimeError("Gagal membuat PDF laporan imunisasi.")
    buffer.seek(0)
    return buffer


# =========================================================
# UNDUH PDF LAPORAN IMUNISASI ADMIN
# =========================================================
@login_required
@admin_required
def cetak_imunisasi_pdf(request):
    """
    Export laporan imunisasi Admin.

    scope=selected -> satu Posyandu terpilih.
    scope=all      -> seluruh Posyandu dalam satu PDF; tiap Posyandu
                      selalu dimulai sebagai dokumen/halaman baru.
    id_jadwal      -> kompatibilitas tombol Unduh per jadwal.
    """
    status_peserta = request.GET.get("status_peserta", "balita").strip().lower()
    if status_peserta not in {"balita", "bumil"}:
        status_peserta = "balita"

    bulan, tahun, _ = _resolve_imunisasi_period(request)
    scope = request.GET.get("scope", "all").strip().lower()
    if scope not in {"selected", "all"}:
        scope = "all"

    jadwal_id_raw = request.GET.get("id_jadwal", "").strip()
    try:
        jadwal_id = int(jadwal_id_raw) if jadwal_id_raw else None
    except (TypeError, ValueError):
        jadwal_id = None

    daftar_posyandu = list(Posyandu.objects.all().order_by("nama"))
    posyandu_map = {item.pk: item for item in daftar_posyandu}

    # Tombol Unduh pada satu jadwal selalu hanya mencetak Posyandu jadwal itu.
    if jadwal_id is not None:
        jadwal_obj = get_object_or_404(
            JadwalKegiatan.objects.select_related("posyandu"),
            pk=jadwal_id,
            jns_kegiatan="Imunisasi",
        )
        bulan = jadwal_obj.tgl_kegiatan.month
        tahun = jadwal_obj.tgl_kegiatan.year
        export_posyandu = [jadwal_obj.posyandu]
        scope = "selected"
    elif scope == "all":
        export_posyandu = daftar_posyandu
    else:
        selected_raw = request.GET.get("posyandu", "").strip()
        try:
            selected_id = int(selected_raw) if selected_raw else None
        except (TypeError, ValueError):
            selected_id = None

        selected = posyandu_map.get(selected_id)
        if selected is None:
            return HttpResponse(
                "Silakan pilih Posyandu terlebih dahulu untuk mengunduh laporan terpilih.",
                status=400,
                content_type="text/plain; charset=utf-8",
            )
        export_posyandu = [selected]

    if not export_posyandu:
        return HttpResponse(
            "Belum ada data Posyandu yang dapat diekspor.",
            status=404,
            content_type="text/plain; charset=utf-8",
        )

    writer = PdfWriter()
    buffers = []

    try:
        for posyandu in export_posyandu:
            context = _build_imunisasi_pdf_context(
                posyandu=posyandu,
                status_peserta=status_peserta,
                bulan=bulan,
                tahun=tahun,
                jadwal_id=jadwal_id,
            )
            pdf_buffer = _render_imunisasi_pdf_buffer(context)
            buffers.append(pdf_buffer)

            reader = PdfReader(pdf_buffer)
            for page in reader.pages:
                writer.add_page(page)

        output = BytesIO()
        writer.write(output)
        output.seek(0)
    except Exception:
        return HttpResponse(
            "Terjadi kesalahan saat membuat PDF laporan imunisasi.",
            status=500,
            content_type="text/plain; charset=utf-8",
        )
    finally:
        for buffer in buffers:
            buffer.close()

    jenis = "ibu_hamil" if status_peserta == "bumil" else "balita"
    if jadwal_id is not None:
        pos_slug = slugify(export_posyandu[0].nama) or "posyandu"
        filename = f"laporan_imunisasi_{jenis}_{pos_slug}_{tahun}_{bulan:02d}.pdf"
    elif scope == "all":
        filename = f"laporan_imunisasi_{jenis}_semua_posyandu_{tahun}_{bulan:02d}.pdf"
    else:
        pos_slug = slugify(export_posyandu[0].nama) or "posyandu"
        filename = f"laporan_imunisasi_{jenis}_{pos_slug}_{tahun}_{bulan:02d}.pdf"

    response = HttpResponse(output.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
