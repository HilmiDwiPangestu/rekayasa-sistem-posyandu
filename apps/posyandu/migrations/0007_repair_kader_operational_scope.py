from datetime import date

from django.db import migrations


def repair_kader_operational_scope(apps, schema_editor):
    """Normalisasi data Kader legacy menjadi satu Posyandu operasional aktif.

    Sumber utama adalah Petugas.posyandu. Bila kosong tetapi terdapat penugasan
    aktif lama, penugasan terbaru dipakai sebagai Posyandu utama. Penugasan aktif
    lain ditutup agar seluruh fitur Kader membaca wilayah yang sama.
    """
    Petugas = apps.get_model("accounts", "Petugas")
    PenugasanPetugas = apps.get_model("posyandu", "PenugasanPetugas")
    today = date.today()

    for kader in Petugas.objects.filter(level="kader").iterator():
        active = PenugasanPetugas.objects.filter(
            petugas_id=kader.pk,
            tanggal_selesai__isnull=True,
        ).order_by("-tanggal_mulai", "-pk")

        primary_id = kader.posyandu_id
        if primary_id is None:
            latest = active.first()
            if latest is not None:
                primary_id = latest.posyandu_id
                Petugas.objects.filter(pk=kader.pk).update(posyandu_id=primary_id)

        if primary_id is None:
            continue

        active.exclude(posyandu_id=primary_id).update(tanggal_selesai=today)
        if not active.filter(posyandu_id=primary_id).exists():
            PenugasanPetugas.objects.create(
                petugas_id=kader.pk,
                posyandu_id=primary_id,
                tanggal_mulai=today,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("posyandu", "0006_alter_jadwalkegiatan_jns_kegiatan"),
    ]

    operations = [
        migrations.RunPython(repair_kader_operational_scope, migrations.RunPython.noop),
    ]
