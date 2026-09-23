from datetime import date

from django.db import migrations


def sync_kader_assignments(apps, schema_editor):
    Petugas = apps.get_model("accounts", "Petugas")
    PenugasanPetugas = apps.get_model("posyandu", "PenugasanPetugas")

    for kader in Petugas.objects.filter(level="kader", posyandu_id__isnull=False):
        active = PenugasanPetugas.objects.filter(
            petugas_id=kader.pk,
            tanggal_selesai__isnull=True,
        )
        active.exclude(posyandu_id=kader.posyandu_id).update(tanggal_selesai=date.today())
        if not active.filter(posyandu_id=kader.posyandu_id).exists():
            PenugasanPetugas.objects.create(
                petugas_id=kader.pk,
                posyandu_id=kader.posyandu_id,
                tanggal_mulai=date.today(),
            )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_disable_bidan_login"),
        ("posyandu", "0004_posyandu_desa"),
    ]

    operations = [
        migrations.RunPython(sync_kader_assignments, migrations.RunPython.noop),
    ]
