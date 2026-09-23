"""Helper akses data lintas aplikasi berdasarkan penugasan petugas.

Aturan utama sistem:
- Admin Kelurahan dapat melihat seluruh Posyandu.
- Kader hanya mempunyai satu Posyandu operasional aktif. ``Petugas.posyandu``
  menjadi sumber utama agar jadwal, peserta, pemeriksaan, imunisasi, dan dashboard
  selalu membaca wilayah yang sama.
- Bidan dapat mencakup lebih dari satu Posyandu melalui ``PenugasanPetugas``.
"""

from apps.posyandu.models import PenugasanPetugas, Posyandu


def active_posyandu_ids(petugas) -> set[int]:
    """ID Posyandu yang saat ini untuk petugas sesuai perannya.

    Untuk Kader, sistem sengaja mengembalikan tepat satu Posyandu operasional.
    Hal ini mencegah data lama pada tabel penugasan membuat Jadwal/Peserta di
    halaman Kader berbeda dengan tempat tugas yang tampil pada data master.
    """
    if petugas is None:
        return set()

    level = getattr(petugas, "level", None)

    if level == "admin":
        return set(Posyandu.objects.values_list("pk", flat=True))

    if level == "kader":
        if petugas.posyandu_id:
            return {petugas.posyandu_id}

        # Fallback untuk data legacy: bila Posyandu utama belum terisi tetapi
        # hanya ada satu penugasan saat ini, tetap izinkan Kader membaca wilayah itu.
        assignment_ids = list(
            PenugasanPetugas.objects.filter(petugas=petugas)
            .order_by("-tanggal_daftar", "-pk")
            .values_list("posyandu_id", flat=True)[:2]
        )
        if len(assignment_ids) == 1:
            return {assignment_ids[0]}
        return set()

    # Bidan/master tenaga kesehatan boleh mempunyai cakupan multi-Posyandu.
    ids = set(
        PenugasanPetugas.objects.filter(
            petugas=petugas,
        ).values_list("posyandu_id", flat=True)
    )
    if petugas.posyandu_id:
        ids.add(petugas.posyandu_id)
    return ids


def visible_posyandu_queryset(user):
    """Queryset Posyandu yang boleh dilihat user pada fitur operasional."""
    petugas = getattr(user, "petugas", None)
    if petugas and petugas.level == "admin":
        return Posyandu.objects.all()
    if petugas is None:
        return Posyandu.objects.none()
    return Posyandu.objects.filter(pk__in=active_posyandu_ids(petugas))


def report_posyandu_ids(petugas) -> list[int]:
    """ID Posyandu untuk laporan sesuai aktor aplikasi."""
    if petugas is None:
        return []
    if getattr(petugas, "level", None) == "admin":
        return list(Posyandu.objects.values_list("pk", flat=True))
    return list(active_posyandu_ids(petugas))
