"""Layanan domain Posyandu, termasuk pengaturan cakupan wilayah kerja bidan."""

from collections import defaultdict
from django.db import models, transaction

from apps.accounts.models import Petugas
from common.access import active_posyandu_ids

from .models import PenugasanPetugas, Posyandu


class BidanCoverageError(ValueError):
    """Kesalahan aturan bisnis saat mengatur wilayah kerja bidan."""


def active_bidan_assignments(bidan: Petugas):
    """Queryset penugasan saat ini seorang bidan."""
    return (
        PenugasanPetugas.objects
        .filter(petugas=bidan)
        .select_related("posyandu")
        .order_by("posyandu__desa", "posyandu__nama")
    )


def bidan_coverage_ids(bidan: Petugas) -> set[int]:
    """ID Posyandu yang menjadi cakupan bidan, termasuk fallback Posyandu utama."""
    if bidan is None or bidan.level != "bidan":
        return set()
    return active_posyandu_ids(bidan)


def bidan_coverage_queryset(bidan: Petugas):
    ids = bidan_coverage_ids(bidan)
    if not ids:
        return Posyandu.objects.none()
    return Posyandu.objects.filter(pk__in=ids).order_by("desa", "nama")


def active_bidan_owner_map(*, exclude_bidan: Petugas | None = None) -> dict[int, str]:
    """Peta Posyandu -> nama bidan lain yang sedang menangani wilayah tersebut.

    Selain PenugasanPetugas, ``Petugas.posyandu`` turut diperiksa sebagai fallback
    agar data lama yang belum mempunyai baris penugasan tetap terlindungi.
    """
    owner_map: dict[int, str] = {}

    assignments = (
        PenugasanPetugas.objects
        .filter(petugas__level="bidan")
        .select_related("petugas", "posyandu")
    )
    if exclude_bidan is not None:
        assignments = assignments.exclude(petugas=exclude_bidan)

    for assignment in assignments:
        owner_map.setdefault(assignment.posyandu_id, assignment.petugas.nama)

    legacy = Petugas.objects.filter(level="bidan", posyandu__isnull=False).select_related("posyandu")
    if exclude_bidan is not None:
        legacy = legacy.exclude(pk=exclude_bidan.pk)

    for bidan in legacy:
        owner_map.setdefault(bidan.posyandu_id, bidan.nama)

    return owner_map


def validate_bidan_coverage(bidan: Petugas | None, posyandu_ids) -> list[int]:
    """Validasi cakupan: minimal satu Posyandu dan tidak tumpang tindih antar-bidan."""
    normalized = []
    seen = set()
    for value in posyandu_ids or []:
        try:
            pk = int(value)
        except (TypeError, ValueError):
            continue
        if pk > 0 and pk not in seen:
            seen.add(pk)
            normalized.append(pk)

    if not normalized:
        raise BidanCoverageError("Bidan harus memiliki minimal satu Posyandu dalam cakupan wilayah kerja.")

    existing_ids = set(Posyandu.objects.filter(pk__in=normalized).values_list("pk", flat=True))
    if existing_ids != set(normalized):
        raise BidanCoverageError("Terdapat Posyandu yang tidak ditemukan atau sudah dihapus.")

    owner_map = active_bidan_owner_map(exclude_bidan=bidan)
    conflicts = [pk for pk in normalized if pk in owner_map]
    if conflicts:
        conflict_names = []
        for pos in Posyandu.objects.filter(pk__in=conflicts).order_by("nama"):
            conflict_names.append(f"{pos.nama} ({owner_map.get(pos.pk)})")
        raise BidanCoverageError(
            "Posyandu berikut sudah menjadi cakupan bidan lain: " + ", ".join(conflict_names) + "."
        )

    return normalized


@transaction.atomic
def set_bidan_coverage(bidan: Petugas, posyandu_ids):
    """Ganti cakupan wilayah Bidan dengan struktur penugasan saat ini.

    Setiap baris ``PenugasanPetugas`` merupakan penugasan yang sedang berlaku.
    Posyandu yang dilepas dihapus dari tabel penugasan, sedangkan penugasan baru
    otomatis mencatat ``tanggal_daftar`` saat dibuat.
    """
    if bidan.level != "bidan":
        raise BidanCoverageError("Pengaturan cakupan wilayah hanya tersedia untuk petugas dengan level Bidan.")

    selected_ids = validate_bidan_coverage(bidan, posyandu_ids)
    selected_set = set(selected_ids)

    assignment_qs = PenugasanPetugas.objects.filter(petugas=bidan)
    current_ids = set(assignment_qs.values_list("posyandu_id", flat=True))

    removed_ids = current_ids - selected_set
    if removed_ids:
        assignment_qs.filter(posyandu_id__in=removed_ids).delete()

    for posyandu_id in selected_set - current_ids:
        PenugasanPetugas.objects.get_or_create(
            petugas=bidan,
            posyandu_id=posyandu_id,
        )

    if bidan.posyandu_id in selected_set:
        primary_id = bidan.posyandu_id
    else:
        primary_id = (
            Posyandu.objects
            .filter(pk__in=selected_set)
            .order_by("desa", "nama", "pk")
            .values_list("pk", flat=True)
            .first()
        )

    if bidan.posyandu_id != primary_id:
        Petugas.objects.filter(pk=bidan.pk).update(posyandu_id=primary_id)
        bidan.posyandu_id = primary_id

    return bidan_coverage_queryset(bidan)


@transaction.atomic
def ensure_single_assignment(petugas: Petugas, posyandu: Posyandu | None):
    """Sinkronkan satu penugasan Kader/legacy dengan Posyandu utama petugas."""
    assignment_qs = PenugasanPetugas.objects.filter(petugas=petugas)
    if posyandu is None:
        assignment_qs.delete()
        return

    assignment_qs.exclude(posyandu=posyandu).delete()
    PenugasanPetugas.objects.get_or_create(
        petugas=petugas,
        posyandu=posyandu,
    )



@transaction.atomic
def sync_kader_assignment(petugas: Petugas):
    """Pastikan Kader memiliki tepat satu penugasan saat ini yang sama dengan Posyandu utamanya.

    Fungsi ini dipakai untuk memperbaiki data legacy setelah beberapa perubahan
    struktur akun/penugasan. Jika ``petugas.posyandu`` belum terisi tetapi hanya
    ada satu penugasan saat ini, Posyandu utama akan dipulihkan dari penugasan itu.
    """
    if petugas is None or petugas.level != "kader":
        return None

    assignment_qs = PenugasanPetugas.objects.filter(
        petugas=petugas,
    ).select_related("posyandu")

    if petugas.posyandu_id:
        ensure_single_assignment(petugas, petugas.posyandu)
        return petugas.posyandu

    assignments = list(assignment_qs[:2])
    if len(assignments) == 1:
        primary = assignments[0].posyandu
        Petugas.objects.filter(pk=petugas.pk).update(posyandu=primary)
        petugas.posyandu = primary
        return primary

    return None

def decorate_bidan_coverage(bidans):
    """Tambahkan atribut presentasi cakupan pada daftar bidan tanpa query N+1."""
    bidan_list = list(bidans)
    if not bidan_list:
        return bidan_list

    by_bidan = defaultdict(list)
    rows = (
        PenugasanPetugas.objects
        .filter(petugas_id__in=[b.pk for b in bidan_list])
        .select_related("posyandu")
        .order_by("posyandu__desa", "posyandu__nama")
    )
    for row in rows:
        by_bidan[row.petugas_id].append(row.posyandu)

    for bidan in bidan_list:
        coverage = by_bidan.get(bidan.pk, [])
        if bidan.posyandu_id and all(pos.pk != bidan.posyandu_id for pos in coverage):
            coverage = [bidan.posyandu] + coverage

        unique = []
        seen = set()
        for pos in coverage:
            if pos and pos.pk not in seen:
                seen.add(pos.pk)
                unique.append(pos)

        bidan.cakupan_posyandu = unique
        bidan.cakupan_count = len(unique)
        bidan.cakupan_nama = ", ".join(pos.nama for pos in unique)
        bidan.cakupan_search = " ".join(
            f"{pos.nama} {pos.desa or ''}" for pos in unique
        ).lower()

    return bidan_list


def bidan_for_posyandu_queryset(posyandu):
    """Bidan aktif yang mencakup suatu Posyandu.

    Mendukung penugasan multi-Posyandu dan fallback ``Petugas.posyandu`` untuk
    data lama. Dipakai pada form yang diinput Kader untuk mencatat tenaga
    kesehatan pendamping tanpa memberi Bidan akun login.
    """
    if posyandu is None:
        return Petugas.objects.none()

    assignment_ids = PenugasanPetugas.objects.filter(
        petugas__level="bidan",
        posyandu=posyandu,
    ).values_list("petugas_id", flat=True)

    return (
        Petugas.objects
        .filter(level="bidan")
        .filter(models.Q(pk__in=assignment_ids) | models.Q(posyandu=posyandu))
        .distinct()
        .order_by("nama")
    )
