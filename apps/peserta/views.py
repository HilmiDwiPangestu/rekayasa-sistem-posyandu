from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa
import openpyxl
from openpyxl.styles import Font, Alignment

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


@login_required
@kader_required
def cetak_peserta_pdf(request, status_peserta):
    if status_peserta not in {"balita", "bumil"}:
        return render(request, "403.html", status=403)

    data = _filter_peserta(request, status_peserta)
    html = render_to_string("peserta/pdf_peserta.html", {
        "data": data,
        "status_peserta": status_peserta,
        "search": request.GET.get("search", ""),
        "gender": request.GET.get("gender", ""),
        "age": request.GET.get("age", ""),
    })
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="data_{status_peserta}.pdf"'
    result = pisa.CreatePDF(html, dest=response, encoding="utf-8")
    if result.err:
        return HttpResponse("Gagal membuat PDF laporan peserta.", status=500)
    return response


@login_required
@kader_required
def export_peserta_excel(request, status_peserta):
    if status_peserta not in {"balita", "bumil"}:
        return render(request, "403.html", status=403)

    data = _filter_peserta(request, status_peserta)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data Peserta"

    if status_peserta == "balita":
        headers = ["No", "Nama Balita", "NIK", "JK", "Tanggal Lahir", "Usia", "Nama Ibu", "NIK Ibu", "Nama Ayah", "No. HP", "Posyandu", "Alamat"]
    else:
        headers = ["No", "Nama Ibu Hamil", "NIK", "Tanggal Lahir", "Usia", "No. HP", "Posyandu", "Alamat"]

    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for no, p in enumerate(data, 1):
        if status_peserta == "balita":
            jk = "L" if str(p.jenis_kelamin).lower().startswith("l") else ("P" if str(p.jenis_kelamin).lower().startswith("p") else "-")
            row = [no, p.nama_peserta, p.no_nik or "-", jk, p.tgl_lahir.strftime("%d-%m-%Y"), p.usia, p.nama_ibu or "-", p.nik_ibu or "-", p.nama_ayah or "-", p.no_hp or "-", p.posko.nama if p.posko else "-", p.alamat or "-"]
        else:
            row = [no, p.nama_peserta, p.no_nik or "-", p.tgl_lahir.strftime("%d-%m-%Y"), f"{p.usia_tahun} tahun", p.no_hp or "-", p.posko.nama if p.posko else "-", p.alamat or "-"]
        ws.append(row)

    for column in ws.columns:
        width = min(max(len(str(c.value or "")) for c in column) + 2, 38)
        ws.column_dimensions[column[0].column_letter].width = width

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="data_{status_peserta}.xlsx"'
    wb.save(response)
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
