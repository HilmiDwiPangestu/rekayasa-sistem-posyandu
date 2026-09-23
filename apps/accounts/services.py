from dataclasses import dataclass

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.crypto import get_random_string

from .models import Petugas


class PetugasAccountError(ValueError):
    """Kesalahan validasi saat membuat akun login petugas."""


@dataclass(frozen=True)
class PetugasAccountResult:
    user: User
    temporary_password: str
    username: str
    username_generated: bool
    password_generated: bool


def normalize_phone_username(value: str | None) -> str:
    """Normalisasi nomor telepon menjadi username yang konsisten."""
    if not value:
        return ""
    return "".join(char for char in str(value).strip() if char.isdigit())


@transaction.atomic
def create_petugas_account(
    petugas: Petugas,
    *,
    username: str | None = None,
    password: str | None = None,
) -> PetugasAccountResult:
    """
    Buat akun Django dan hubungkan ke profil Kader secara atomik.

    ``username`` dan ``password`` bersifat opsional. Jika username kosong,
    sistem menggunakan nomor telepon Kader yang sudah dinormalisasi. Jika
    password kosong, sistem membuat password sementara secara otomatis.
    """
    if petugas.level != "kader":
        raise PetugasAccountError(
            "Akun login melalui data petugas hanya tersedia untuk Kader. "
            "Bidan tidak memiliki akses login ke sistem."
        )

    if petugas.user_id:
        raise PetugasAccountError("Petugas sudah memiliki akun login.")

    requested_username = (username or "").strip()
    username_generated = not bool(requested_username)

    if username_generated:
        final_username = normalize_phone_username(petugas.no_telp)
        if not final_username:
            raise PetugasAccountError(
                "Username otomatis tidak dapat dibuat karena Kader tidak memiliki nomor telepon aktif. "
                "Silakan isi username secara manual."
            )
    else:
        final_username = requested_username

    # Gunakan validator username bawaan Django agar format username manual
    # konsisten dengan autentikasi User.
    try:
        User._meta.get_field("username").clean(final_username, None)
    except ValidationError as error:
        raise PetugasAccountError("Username tidak valid: " + "; ".join(error.messages)) from error

    if User.objects.filter(username=final_username).exists():
        raise PetugasAccountError(
            f"Username ({final_username}) sudah digunakan oleh akun lain."
        )

    requested_password = password or ""
    password_generated = not bool(requested_password)
    final_password = get_random_string(10) if password_generated else requested_password

    if not password_generated:
        candidate_user = User(username=final_username, first_name=petugas.nama)
        try:
            validate_password(final_password, user=candidate_user)
        except ValidationError as error:
            raise PetugasAccountError("Password tidak valid: " + "; ".join(error.messages)) from error

    user = User.objects.create_user(
        username=final_username,
        password=final_password,
        first_name=petugas.nama,
    )
    petugas.user = user
    petugas.save(update_fields=["user"])

    # Sinkronkan penugasan Kader saat akun dibuat agar Data Peserta,
    # pemeriksaan, jadwal, dan laporan langsung memakai Posyandu yang benar.
    from apps.posyandu.services import sync_kader_assignment
    sync_kader_assignment(petugas)

    return PetugasAccountResult(
        user=user,
        temporary_password=final_password,
        username=final_username,
        username_generated=username_generated,
        password_generated=password_generated,
    )
