"""Factory kecil untuk test agar setup objek konsisten antar-app."""

from datetime import date, timedelta

from django.contrib.auth.models import User

from apps.accounts.models import Petugas
from apps.peserta.models import Peserta
from apps.posyandu.models import Posyandu


def make_posyandu(name="Posyandu Uji"):
    return Posyandu.objects.create(nama=name, desa="Desa Uji", alamat="Alamat Uji")


def make_petugas(*, username="petugas-uji", level="kader", posyandu=None, password="aman-12345"):
    if level in {"kader", "bidan"} and posyandu is None:
        posyandu = make_posyandu()

    # Bidan adalah data master/penanggung jawab wilayah, bukan aktor login.
    user = None
    if level in Petugas.LOGIN_LEVELS:
        user = User.objects.create_user(username=username, password=password)

    petugas = Petugas.objects.create(
        user=user,
        nama=f"{level.title()} Uji",
        no_telp="081234567890",
        level=level,
        posyandu=posyandu,
    )
    return user, petugas


def make_peserta(*, posyandu, status="balita", nama="Peserta Uji", age_days=365, no_hp="081200000001"):
    return Peserta.objects.create(
        posko=posyandu,
        nama_peserta=nama,
        tgl_lahir=date.today() - timedelta(days=age_days),
        alamat="Alamat Uji",
        no_hp=no_hp,
        status_peserta=status,
        jenis_kelamin="Laki-Laki" if status == "balita" else "Perempuan",
    )
