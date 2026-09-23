from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max
from django.shortcuts import render
from django.utils import timezone

from common.access import active_posyandu_ids

from apps.accounts.models import Petugas
from apps.pemeriksaan.models import (
    Imunisasi,
    PemeriksaanBalita,
    PemeriksaanBumil,
)
from apps.peserta.models import Peserta
from apps.posyandu.models import JadwalKegiatan, PenugasanPetugas, Posyandu


NAMA_BULAN = [
    "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
    "Jul", "Agu", "Sep", "Okt", "Nov", "Des",
]


def _latest_balita_ids(queryset):
    return (
        queryset.values("peserta")
        .annotate(latest=Max("id_periksa"))
        .values_list("latest", flat=True)
    )


def _stunting_terbaru_count(queryset):
    latest_ids = _latest_balita_ids(queryset)
    return PemeriksaanBalita.objects.filter(
        id_periksa__in=latest_ids,
        status_gizi__in=("stunting", "stunting_berat"),
    ).count()


def _grafik_pemeriksaan_balita(queryset):
    tahun = timezone.localdate().year
    raw = [
        queryset.filter(
            tgl_pemeriksaan__year=tahun,
            tgl_pemeriksaan__month=bulan,
        ).count()
        for bulan in range(1, 13)
    ]
    maksimum = max(raw) or 1
    return [
        {
            "label": NAMA_BULAN[index],
            "jumlah": jumlah,
            "pct": round((jumlah / maksimum) * 100),
        }
        for index, jumlah in enumerate(raw)
    ]


def _admin_dashboard_context():
    today = timezone.localdate()
    semua_posyandu = Posyandu.objects.all().order_by("nama")
    semua_balita = Peserta.objects.filter(status_peserta="balita")
    semua_bumil = Peserta.objects.filter(status_peserta="bumil")
    pemeriksaan_balita = PemeriksaanBalita.objects.all()
    pemeriksaan_bumil = PemeriksaanBumil.objects.all()

    bidan = list(Petugas.objects.filter(level="bidan").order_by("nama"))
    covered_posyandu_ids = set()
    cakupan_bidan = []

    for item in bidan:
        ids = set(
            PenugasanPetugas.objects.filter(
                petugas=item,
            ).values_list("posyandu_id", flat=True)
        )
        if item.posyandu_id:
            ids.add(item.posyandu_id)
        covered_posyandu_ids.update(ids)
        cakupan_bidan.append({
            "bidan": item,
            "posyandu": list(Posyandu.objects.filter(pk__in=ids).order_by("nama")),
            "jumlah": len(ids),
        })

    ringkasan_posyandu = []
    for pos in semua_posyandu:
        kader_ids = set(
            Petugas.objects.filter(level="kader", posyandu=pos).values_list("pk", flat=True)
        )
        kader_ids.update(
            PenugasanPetugas.objects.filter(
                petugas__level="kader",
                posyandu=pos,
            ).values_list("petugas_id", flat=True)
        )
        ringkasan_posyandu.append({
            "posyandu": pos,
            "balita": semua_balita.filter(posko=pos).count(),
            "bumil": semua_bumil.filter(posko=pos).count(),
            "kader": len(kader_ids),
            "pemeriksaan_bulan_ini": pemeriksaan_balita.filter(
                jadwal__posyandu=pos,
                tgl_pemeriksaan__year=today.year,
                tgl_pemeriksaan__month=today.month,
            ).count(),
        })

    jadwal_mendatang = (
        JadwalKegiatan.objects.filter(tgl_kegiatan__gte=today)
        .select_related("posyandu")
        .order_by("tgl_kegiatan", "jam_mulai")[:6]
    )

    aktivitas = (
        pemeriksaan_balita.select_related("peserta", "jadwal", "jadwal__posyandu", "petugas")
        .order_by("-tgl_pemeriksaan")[:8]
    )

    return {
        "dashboard_role": "admin",
        "total_posyandu": semua_posyandu.count(),
        "total_kader": Petugas.objects.filter(level="kader").count(),
        "total_bidan": len(bidan),
        "total_balita": semua_balita.count(),
        "total_bumil": semua_bumil.count(),
        "total_peserta": semua_balita.count() + semua_bumil.count(),
        "stunting": _stunting_terbaru_count(pemeriksaan_balita),
        "total_jadwal_bulan_ini": JadwalKegiatan.objects.filter(
            tgl_kegiatan__year=today.year,
            tgl_kegiatan__month=today.month,
        ).count(),
        "total_pemeriksaan_bulan_ini": (
            pemeriksaan_balita.filter(
                tgl_pemeriksaan__year=today.year,
                tgl_pemeriksaan__month=today.month,
            ).count()
            + pemeriksaan_bumil.filter(
                tgl_pemeriksaan__year=today.year,
                tgl_pemeriksaan__month=today.month,
            ).count()
        ),
        "posyandu_tanpa_bidan": semua_posyandu.exclude(pk__in=covered_posyandu_ids).count(),
        "cakupan_bidan": cakupan_bidan,
        "ringkasan_posyandu": ringkasan_posyandu,
        "jadwal_mendatang": jadwal_mendatang,
        "aktivitas": aktivitas,
        "grafik_bulan": _grafik_pemeriksaan_balita(pemeriksaan_balita),
    }


def _kader_dashboard_context(petugas):
    today = timezone.localdate()
    scope_ids = sorted(active_posyandu_ids(petugas))
    if not scope_ids:
        return None

    cakupan_posyandu = list(
        Posyandu.objects.filter(pk__in=scope_ids).order_by("desa", "nama")
    )
    primary = (
        petugas.posyandu
        if petugas.posyandu_id in scope_ids
        else cakupan_posyandu[0]
    )

    peserta = Peserta.objects.filter(posko_id__in=scope_ids)
    balita = peserta.filter(status_peserta="balita")
    bumil = peserta.filter(status_peserta="bumil")
    periksa_balita = PemeriksaanBalita.objects.filter(jadwal__posyandu_id__in=scope_ids)
    periksa_bumil = PemeriksaanBumil.objects.filter(jadwal__posyandu_id__in=scope_ids)

    sudah_periksa_bulan_ini = periksa_balita.filter(
        tgl_pemeriksaan__year=today.year,
        tgl_pemeriksaan__month=today.month,
    ).values_list("peserta_id", flat=True).distinct()

    jadwal_hari_ini = list(
        JadwalKegiatan.objects.filter(
            posyandu_id__in=scope_ids,
            tgl_kegiatan=today,
        ).select_related("posyandu").order_by("jam_mulai")[:5]
    )
    # Tampilkan seluruh jadwal mendatang Posyandu Kader pada dashboard agar
    # jadwal yang terlihat Admin tidak "hilang" hanya karena batas 5 data.
    jadwal_mendatang = list(
        JadwalKegiatan.objects.filter(
            posyandu_id__in=scope_ids,
            tgl_kegiatan__gt=today,
        ).select_related("posyandu").order_by("tgl_kegiatan", "jam_mulai", "id_jadwal")
    )

    bidan_ids = set(
        PenugasanPetugas.objects.filter(
            petugas__level="bidan",
            posyandu_id__in=scope_ids,
        ).values_list("petugas_id", flat=True)
    )
    bidan_ids.update(
        Petugas.objects.filter(
            level="bidan",
            posyandu_id__in=scope_ids,
        ).values_list("pk", flat=True)
    )

    aktivitas = (
        periksa_balita.select_related("peserta", "jadwal", "jadwal__posyandu")
        .order_by("-tgl_pemeriksaan")[:6]
    )

    return {
        "dashboard_role": "kader",
        "petugas": petugas,
        "posyandu": primary,
        "cakupan_posyandu": cakupan_posyandu,
        "wilayah_label": (
            primary.nama
            if len(cakupan_posyandu) == 1
            else f"{len(cakupan_posyandu)} Posyandu dalam penugasan"
        ),
        "total_posyandu": len(cakupan_posyandu),
        "total_balita": balita.count(),
        "total_bumil": bumil.count(),
        "stunting": _stunting_terbaru_count(periksa_balita),
        "pemeriksaan_hari_ini": (
            periksa_balita.filter(tgl_pemeriksaan__date=today).count()
            + periksa_bumil.filter(tgl_pemeriksaan__date=today).count()
        ),
        "pemeriksaan_bulan_ini": (
            periksa_balita.filter(
                tgl_pemeriksaan__year=today.year,
                tgl_pemeriksaan__month=today.month,
            ).count()
            + periksa_bumil.filter(
                tgl_pemeriksaan__year=today.year,
                tgl_pemeriksaan__month=today.month,
            ).count()
        ),
        "imunisasi_bulan_ini": Imunisasi.objects.filter(
            jadwal__posyandu_id__in=scope_ids,
            tgl_pemberian__year=today.year,
            tgl_pemberian__month=today.month,
        ).count(),
        "balita_belum_periksa_bulan_ini": balita.exclude(pk__in=sudah_periksa_bulan_ini).count(),
        "jadwal_hari_ini": jadwal_hari_ini,
        "jadwal_mendatang": jadwal_mendatang,
        "bidan_penanggung_jawab": list(
            Petugas.objects.filter(pk__in=bidan_ids, level="bidan").order_by("nama")
        ),
        "aktivitas": aktivitas,
        "grafik_bulan": _grafik_pemeriksaan_balita(periksa_balita),
    }


@login_required
def index(request):
    petugas = getattr(request.user, "petugas", None)
    if petugas is None or not petugas.can_login:
        return render(request, "403.html", status=403)

    if petugas.level == "admin":
        return render(request, "dashboard/admin.html", _admin_dashboard_context())

    if petugas.level == "kader":
        context = _kader_dashboard_context(petugas)
        if context is None:
            return render(
                request,
                "403.html",
                {"error": "Anda belum ditugaskan ke Posyandu manapun."},
                status=403,
            )
        return render(request, "dashboard/kader.html", context)

    return render(request, "403.html", status=403)
