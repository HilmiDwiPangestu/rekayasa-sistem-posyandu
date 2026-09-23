from datetime import date

from django.db.models import Q, QuerySet

from common.access import active_posyandu_ids

from .models import Peserta


VALID_STATUS_PESERTA = {"balita", "bumil"}


def subtract_years(value: date, years: int) -> date:
    """Kurangi tahun dengan aman untuk tanggal 29 Februari."""
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, month=2, day=28)


def peserta_accessible_to(user) -> QuerySet[Peserta]:
    """Batasi peserta pada Posyandu petugas; admin dapat melihat seluruh data."""
    queryset = Peserta.objects.all()
    petugas = getattr(user, "petugas", None)

    if petugas is None:
        return queryset.none()
    if petugas.level == "admin":
        return queryset

    posyandu_ids = active_posyandu_ids(petugas)
    if not posyandu_ids:
        return queryset.none()
    return queryset.filter(posko_id__in=posyandu_ids)


def filter_peserta(queryset: QuerySet[Peserta], *, status_peserta: str, search="", gender="", age="") -> QuerySet[Peserta]:
    """Satu sumber filter peserta untuk halaman, PDF, dan Excel."""
    if status_peserta not in VALID_STATUS_PESERTA:
        return queryset.none()

    peserta = queryset.filter(status_peserta=status_peserta)
    search = (search or "").strip()
    gender = (gender or "").strip().upper()
    age = (age or "").strip()

    if search:
        peserta = peserta.filter(
            Q(nama_peserta__icontains=search)
            | Q(nama_ibu__icontains=search)
            | Q(nama_ayah__icontains=search)
            | Q(no_hp__icontains=search)
            | Q(no_nik__icontains=search)
            | Q(nik_ibu__icontains=search)
            | Q(alamat__icontains=search)
        )

    today = date.today()
    if status_peserta == "balita":
        if gender == "L":
            peserta = peserta.filter(jenis_kelamin__in=["L", "Laki-Laki", "Laki-laki"])
        elif gender == "P":
            peserta = peserta.filter(jenis_kelamin__in=["P", "Perempuan"])

        age_1 = subtract_years(today, 1)
        age_3 = subtract_years(today, 3)
        age_5 = subtract_years(today, 5)
        if age == "0-1":
            peserta = peserta.filter(tgl_lahir__gt=age_1, tgl_lahir__lte=today)
        elif age == "1-3":
            peserta = peserta.filter(tgl_lahir__gt=age_3, tgl_lahir__lte=age_1)
        elif age == "3-5":
            peserta = peserta.filter(tgl_lahir__gte=age_5, tgl_lahir__lte=age_3)
    else:
        age_20 = subtract_years(today, 20)
        age_36 = subtract_years(today, 36)
        if age == "under-20":
            peserta = peserta.filter(tgl_lahir__gt=age_20, tgl_lahir__lte=today)
        elif age == "20-35":
            peserta = peserta.filter(tgl_lahir__gt=age_36, tgl_lahir__lte=age_20)
        elif age == "over-35":
            peserta = peserta.filter(tgl_lahir__lte=age_36)

    return peserta.select_related("posko").order_by("nama_peserta")
