from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_POST
from common.decorators import admin_required

from .models import Petugas
from apps.posyandu.models import (Posyandu, PenugasanPetugas)
from apps.posyandu.services import (
    BidanCoverageError,
    ensure_single_assignment,
    set_bidan_coverage,
    validate_bidan_coverage,
    sync_kader_assignment,
)
from .forms import PetugasForm

def login_view(request):
    if request.user.is_authenticated:
        petugas = getattr(request.user, "petugas", None)
        if petugas and petugas.can_login:
            if petugas.level == "kader":
                sync_kader_assignment(petugas)
            return redirect("dashboard:index")
        if request.user.is_staff or request.user.is_superuser:
            return redirect("/admin/")
        logout(request)

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_staff or user.is_superuser:
                messages.error(
                    request,
                    "Akun teknis Django tidak digunakan untuk aplikasi Posyandu. "
                    "Gunakan /admin/ untuk administrasi teknis.",
                )
            else:
                petugas = getattr(user, "petugas", None)
                if petugas and petugas.can_login:
                    if petugas.level == "kader":
                        sync_kader_assignment(petugas)
                    login(request, user)
                    messages.success(request, "Login berhasil")
                    return redirect("dashboard:index")
                messages.error(
                    request,
                    "Akun ini tidak memiliki akses login. Sistem hanya dapat diakses oleh Admin Kelurahan dan Kader.",
                )
        else:
            messages.error(request, "Username atau password salah")

    return render(request, "accounts/login.html")

@login_required
@admin_required
@transaction.atomic
def register_view(request):
    posyandu_list = Posyandu.objects.all().order_by("nama")

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        password2 = request.POST.get("password2") or ""
        nama = (request.POST.get("nama") or "").strip()
        alamat = (request.POST.get("alamat") or "").strip()
        no_telp = (request.POST.get("no_telp") or "").strip()
        level = (request.POST.get("level") or "").strip()
        posyandu_id = (request.POST.get("posyandu") or "").strip()

        if not username or not nama:
            messages.error(request, "Username dan nama petugas wajib diisi.")
            return redirect("accounts:register")
        # Admin Kelurahan tidak dikelola dari UI aplikasi. Endpoint legacy ini
        # dipertahankan hanya untuk membuat akun Kader; Admin awal dibuat lewat
        # command create_admin_kelurahan.
        if level != "kader":
            messages.error(request, "Halaman ini hanya dapat digunakan untuk membuat akun Kader.")
            return redirect("accounts:register")
        if password != password2:
            messages.error(request, "Password dan konfirmasi password tidak sama.")
            return redirect("accounts:register")
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username sudah digunakan.")
            return redirect("accounts:register")

        try:
            password_validation.validate_password(password)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
            return redirect("accounts:register")

        posyandu = None
        if level == "kader":
            if not posyandu_id.isdigit():
                messages.error(request, "Posyandu wajib dipilih untuk Kader.")
                return redirect("accounts:register")
            posyandu = Posyandu.objects.filter(pk=int(posyandu_id)).first()
            if posyandu is None:
                messages.error(request, "Posyandu tidak ditemukan.")
                return redirect("accounts:register")

        user = User.objects.create_user(username=username, password=password)
        petugas = Petugas.objects.create(
            user=user,
            nama=nama,
            alamat=alamat,
            no_telp=no_telp,
            level=level,
            posyandu=posyandu,
        )
        if posyandu:
            ensure_single_assignment(petugas, posyandu)

        messages.success(request, "Akun pengguna berhasil dibuat.")
        return redirect("dashboard:index")

    return render(request, "accounts/register.html", {"posyandu_list": posyandu_list})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("accounts:login")

@login_required
def settings_page(request):
    petugas = getattr(request.user, "petugas", None)
    if petugas is None or not petugas.can_login:
        return render(request, "403.html", status=403)

    penempatan_saat_ini = (
        PenugasanPetugas.objects
        .filter(petugas=petugas)
        .select_related("posyandu")
        .first()
    )
    return render(request, "accounts/setting.html", {
        "petugas": petugas,
        "penempatan_saat_ini": penempatan_saat_ini,
    })


@login_required
@require_POST
@transaction.atomic
def update_settings(request):
    petugas = getattr(request.user, "petugas", None)
    if petugas is None or not petugas.can_login:
        return render(request, "403.html", status=403)

    user = request.user
    nama = (request.POST.get("nama") or "").strip()
    username = (request.POST.get("username") or user.username).strip()
    no_telp = (request.POST.get("no_telp") or "").strip()
    alamat = (request.POST.get("alamat") or "").strip()
    password_baru = request.POST.get("password_baru") or ""
    konfirmasi_password = request.POST.get("konfirmasi_password") or ""

    if not nama:
        messages.error(request, "Nama lengkap wajib diisi.")
        return redirect("accounts:setting")
    if not username:
        messages.error(request, "Username wajib diisi.")
        return redirect("accounts:setting")
    if User.objects.exclude(pk=user.pk).filter(username=username).exists():
        messages.error(request, "Username sudah digunakan oleh akun lain.")
        return redirect("accounts:setting")

    if password_baru:
        if password_baru != konfirmasi_password:
            messages.error(request, "Password baru dan konfirmasi password tidak cocok.")
            return redirect("accounts:setting")
        try:
            password_validation.validate_password(password_baru, user=user)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
            return redirect("accounts:setting")

    petugas.nama = nama
    petugas.alamat = alamat
    petugas.no_telp = no_telp
    petugas.save(update_fields=["nama", "alamat", "no_telp"])

    username_changed = user.username != username
    if username_changed:
        user.username = username

    if password_baru:
        user.set_password(password_baru)

    if username_changed or password_baru:
        user.save()
    if password_baru:
        update_session_auth_hash(request, user)

    messages.success(request, "Pengaturan akun berhasil diperbarui.")
    return redirect("accounts:setting")


@login_required
@admin_required
@transaction.atomic
def tambah_petugas(request, level_petugas):
    if level_petugas not in {"kader", "bidan"}:
        return render(request, "403.html", status=403)

    if request.method == "POST":
        form = PetugasForm(request.POST, level_petugas=level_petugas)

        if form.is_valid():
            petugas = form.save(commit=False)
            petugas.level = level_petugas
            coverage = []

            if level_petugas == "bidan":
                coverage = list(form.cleaned_data["cakupan_posyandu"])
                try:
                    validate_bidan_coverage(None, [pos.pk for pos in coverage])
                except BidanCoverageError as error:
                    form.add_error("cakupan_posyandu", str(error))
                else:
                    # Tetapkan Posyandu utama sebelum save agar data lama yang
                    # masih membaca petugas.posyandu tetap kompatibel.
                    petugas.posyandu = coverage[0]

            if not form.errors:
                try:
                    with transaction.atomic():
                        petugas.save()

                        if level_petugas == "bidan":
                            set_bidan_coverage(petugas, [pos.pk for pos in coverage])
                        else:
                            ensure_single_assignment(petugas, petugas.posyandu)
                except BidanCoverageError as error:
                    form.add_error("cakupan_posyandu", str(error))
                else:
                    messages.success(
                        request,
                        f"Data {level_petugas} berhasil ditambahkan."
                    )
                    return redirect(
                        "posyandu:daftar_petugas_kader"
                        if level_petugas == "kader"
                        else "posyandu:daftar_bidan"
                    )
    else:
        form = PetugasForm(level_petugas=level_petugas)

    form.fields["nama"].label = f"Nama {level_petugas.title()}"

    return render(
        request,
        "accounts/tambah_petugas.html",
        {
            "form": form,
            "level_petugas": level_petugas,
        },
    )
