from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from xhtml2pdf import pisa
from io import BytesIO
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from common.decorators import kader_required
from common.access import visible_posyandu_queryset
from apps.posyandu.services import sync_kader_assignment

from .forms import PesertaForm
from .services import (
    VALID_STATUS_PESERTA,
    filter_peserta,
    peserta_accessible_to,
)


def _peserta_terjangkau(request):
    """Queryset peserta sesuai wilayah, sekaligus self-heal penugasan Kader legacy."""
    petugas = getattr(request.user, "petugas", None)
    if petugas is not None and petugas.level == "kader":
        sync_kader_assignment(petugas)
    return peserta_accessible_to(request.user)


def _posyandu_terjangkau(request):
    """Posyandu yang dapat dipilih petugas saat menambah/mengubah peserta."""
    return visible_posyandu_queryset(request.user).order_by("desa", "nama")


# =========================================================
# LIST PESERTA
# =========================================================
def _filter_peserta(request, status_peserta):
    """Satu sumber filter untuk halaman peserta, PDF, dan Excel."""
    return filter_peserta(
        _peserta_terjangkau(request),
        status_peserta=status_peserta,
        search=request.GET.get("search", ""),
        gender=request.GET.get("gender", ""),
        age=request.GET.get("age", ""),
    )


@login_required
@kader_required
def list_peserta(request, status_peserta):
    if status_peserta not in {"balita", "bumil"}:
        return render(request, "403.html", status=403)

    peserta = _filter_peserta(request, status_peserta)
    paginator = Paginator(peserta, 5)
    page_obj = paginator.get_page(request.GET.get("page"))

    petugas = getattr(request.user, "petugas", None)
    scope_posyandu = list(_posyandu_terjangkau(request))

    return render(request, "peserta/list.html", {
        "page_obj": page_obj,
        "status_peserta": status_peserta,
        "total_filtered": paginator.count,
        "scope_posyandu": scope_posyandu,
        "is_kader": bool(petugas and petugas.level == "kader"),
    })


def _peserta_export_title(status_peserta):
    return "Data Balita" if status_peserta == "balita" else "Data Ibu Hamil"


def _peserta_filter_text(request, status_peserta):
    parts = []
    search = (request.GET.get("search") or "").strip()
    gender = (request.GET.get("gender") or "").strip().upper()
    age = (request.GET.get("age") or "").strip()

    if search:
        parts.append(f'Pencarian: "{search}"')
    if status_peserta == "balita" and gender in {"L", "P"}:
        parts.append("Jenis kelamin: " + ("Laki-laki" if gender == "L" else "Perempuan"))

    age_labels = {
        "0-1": "0 - < 1 tahun",
        "1-3": "1 - < 3 tahun",
        "3-5": "3 - 5 tahun",
        "under-20": "< 20 tahun",
        "20-35": "20 - 35 tahun",
        "over-35": "> 35 tahun",
    }
    if age in age_labels:
        parts.append(f"Usia: {age_labels[age]}")

    return " | ".join(parts) or "Semua data"


def _peserta_export_filename(status_peserta, extension):
    label = _peserta_export_title(status_peserta)
    stamp = timezone.localdate().strftime("%Y%m%d")
    return f"{slugify(label)}_{stamp}.{extension}"


@login_required
@kader_required
def cetak_peserta_pdf(request, status_peserta):
    if status_peserta not in {"balita", "bumil"}:
        return render(request, "403.html", status=403)

    data = list(_filter_peserta(request, status_peserta))
    html = render_to_string("peserta/pdf_peserta.html", {
        "data": data,
        "status_peserta": status_peserta,
        "title": _peserta_export_title(status_peserta),
        "filter_text": _peserta_filter_text(request, status_peserta),
        "generated_at": timezone.localtime(),
        "total_data": len(data),
    })

    buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=buffer, encoding="utf-8")
    if result.err:
        return HttpResponse("Gagal membuat PDF laporan peserta.", status=500)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="{_peserta_export_filename(status_peserta, "pdf")}"'
    )
    return response


@login_required
@kader_required
def export_peserta_excel(request, status_peserta):
    if status_peserta not in {"balita", "bumil"}:
        return render(request, "403.html", status=403)

    data = list(_filter_peserta(request, status_peserta))
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data Peserta"
    ws.sheet_view.showGridLines = False

    if status_peserta == "balita":
        headers = [
            "No", "Nama Balita", "NIK", "JK", "Tanggal Lahir", "Usia",
            "Nama Ibu", "NIK Ibu", "Nama Ayah", "No. HP", "Posyandu", "Alamat",
        ]
    else:
        headers = [
            "No", "Nama Ibu Hamil", "NIK", "Tanggal Lahir", "Usia",
            "No. HP", "Posyandu", "Alamat",
        ]

    end_column = get_column_letter(len(headers))
    title = _peserta_export_title(status_peserta)
    filter_text = _peserta_filter_text(request, status_peserta)

    ws.merge_cells(f"A1:{end_column}1")
    ws["A1"] = f"LAPORAN {title.upper()}"
    ws["A1"].font = Font(bold=True, size=16)
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 26

    ws.merge_cells(f"A2:{end_column}2")
    ws["A2"] = (
        f"Filter: {filter_text} | Total: {len(data)} data | "
        f"Diekspor: {timezone.localtime().strftime('%d-%m-%Y %H:%M')} WIB"
    )
    ws["A2"].font = Font(italic=True, size=9, color="64748B")
    ws["A2"].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[2].height = 28

    header_row = 4
    thin = Side(style="thin", color="CBD5E1")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", fgColor="DCE6F1")

    for column_index, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=column_index, value=header)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[header_row].height = 24

    for no, p in enumerate(data, 1):
        if status_peserta == "balita":
            jk = (
                "L" if str(p.jenis_kelamin).lower().startswith("l")
                else "P" if str(p.jenis_kelamin).lower().startswith("p")
                else "-"
            )
            row = [
                no, p.nama_peserta, p.no_nik or "-", jk,
                p.tgl_lahir.strftime("%d-%m-%Y"), p.usia, p.nama_ibu or "-",
                p.nik_ibu or "-", p.nama_ayah or "-", p.no_hp or "-",
                p.posko.nama if p.posko else "-", p.alamat or "-",
            ]
        else:
            row = [
                no, p.nama_peserta, p.no_nik or "-",
                p.tgl_lahir.strftime("%d-%m-%Y"), f"{p.usia_tahun} tahun",
                p.no_hp or "-", p.posko.nama if p.posko else "-", p.alamat or "-",
            ]

        row_number = header_row + no
        for column_index, value in enumerate(row, start=1):
            cell = ws.cell(row=row_number, column=column_index, value=value)
            cell.border = border
            header = headers[column_index - 1]
            center_headers = {"No", "NIK", "JK", "Tanggal Lahir", "Usia", "NIK Ibu", "No. HP"}
            cell.alignment = Alignment(
                horizontal="center" if header in center_headers else "left",
                vertical="top",
                wrap_text=True,
            )
            # NIK dan nomor HP harus tetap dibaca sebagai teks oleh Excel.
            if header in {"NIK", "NIK Ibu", "No. HP"}:
                cell.number_format = "@"

    widths = {
        "No": 6, "Nama Balita": 22, "Nama Ibu Hamil": 24, "NIK": 19, "JK": 7,
        "Tanggal Lahir": 14, "Usia": 13, "Nama Ibu": 21, "NIK Ibu": 19,
        "Nama Ayah": 21, "No. HP": 16, "Posyandu": 22, "Alamat": 38,
    }
    for column_index, header in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(column_index)].width = widths.get(header, 18)

    ws.freeze_panes = f"A{header_row + 1}"
    ws.auto_filter.ref = f"A{header_row}:{end_column}{max(header_row, header_row + len(data))}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{header_row}:{header_row}"

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{_peserta_export_filename(status_peserta, "xlsx")}"'
    )
    return response


# =========================================================
# TAMBAH PESERTA
# =========================================================
@login_required
@kader_required
def tambah_peserta(request, status_peserta):

    if status_peserta not in VALID_STATUS_PESERTA:
        return render(request, "403.html", status=403)

    if request.method == "POST":

        form = PesertaForm(
            request.POST,
            posyandu_queryset=_posyandu_terjangkau(request),
            status_peserta=status_peserta,
        )

        if form.is_valid():

            obj = form.save(
                commit=False
            )

            obj.status_peserta = (
                status_peserta
            )

            obj.save()

            messages.success(
                request,
                "Peserta berhasil ditambahkan"
            )

            return redirect(
                "peserta:list",
                status_peserta=status_peserta
            )

    else:

        form = PesertaForm(
            posyandu_queryset=_posyandu_terjangkau(request),
            status_peserta=status_peserta,
        )


    return render(
        request,
        "peserta/create.html",
        {
            "form": form,
            "status_peserta": status_peserta
        }
    )


# =========================================================
# EDIT PESERTA
# =========================================================
@login_required
@kader_required
def edit_peserta(
    request,
    id,
    status_peserta
):

    peserta = get_object_or_404(
        _peserta_terjangkau(request),
        id=id,
        status_peserta=status_peserta
    )


    if request.method == "POST":

        form = PesertaForm(
            request.POST,
            instance=peserta,
            posyandu_queryset=_posyandu_terjangkau(request),
            status_peserta=status_peserta,
        )

        if form.is_valid():

            obj = form.save(
                commit=False
            )

            obj.status_peserta = (
                status_peserta
            )

            obj.save()

            messages.success(
                request,
                "Data peserta berhasil diperbarui"
            )

            return redirect(
                "peserta:list",
                status_peserta=status_peserta
            )

    else:

        form = PesertaForm(
            instance=peserta,
            posyandu_queryset=_posyandu_terjangkau(request),
            status_peserta=status_peserta,
        )


    return render(
        request,
        "peserta/edit.html",
        {
            "form": form,
            "status_peserta": status_peserta
        }
    )


# =========================================================
# DELETE PESERTA
# =========================================================
@login_required
@kader_required
@require_POST
def delete_peserta(request, id, status_peserta):
    peserta = get_object_or_404(
        _peserta_terjangkau(request),
        id=id,
        status_peserta=status_peserta,
    )
    if (
        peserta.pemeriksaan_balita.exists()
        or peserta.pemeriksaan_bumil.exists()
        or peserta.imunisasi.exists()
        or peserta.kehadiran.exists()
    ):
        messages.error(
            request,
            "Peserta tidak dapat dihapus karena sudah memiliki riwayat pelayanan. "
            "Pertahankan data untuk menjaga rekam pelayanan Posyandu.",
        )
        return redirect("peserta:list", status_peserta=status_peserta)

    peserta.delete()
    messages.success(request, "Data peserta berhasil dihapus")
    return redirect("peserta:list", status_peserta=status_peserta)
