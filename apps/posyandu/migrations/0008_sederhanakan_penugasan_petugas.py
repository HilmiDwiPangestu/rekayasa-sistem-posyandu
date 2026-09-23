from django.db import migrations, models
from django.utils import timezone


def migrasi_penugasan_saat_ini(apps, schema_editor):
    """Ubah riwayat mulai/selesai menjadi satu daftar penugasan yang berlaku saat ini.

    - Penugasan yang sudah memiliki tanggal_selesai dianggap riwayat dan dihapus.
    - Untuk duplikasi petugas + Posyandu yang masih aktif, baris terbaru dipertahankan.
    - tanggal_daftar mengambil tanggal_mulai lama agar tanggal penugasan aktif tetap
      bermakna pada database existing.
    - Kader dinormalisasi menjadi satu penugasan yang sama dengan Petugas.posyandu.
    """
    Petugas = apps.get_model("accounts", "Petugas")
    PenugasanPetugas = apps.get_model("posyandu", "PenugasanPetugas")
    today = timezone.localdate()

    # Setelah struktur baru berlaku, hanya penugasan saat ini yang disimpan.
    PenugasanPetugas.objects.filter(tanggal_selesai__isnull=False).delete()

    # Hilangkan duplikasi aktif dan salin tanggal_mulai menjadi tanggal_daftar.
    pasangan = list(
        PenugasanPetugas.objects.values_list("petugas_id", "posyandu_id").distinct()
    )
    for petugas_id, posyandu_id in pasangan:
        rows = list(
            PenugasanPetugas.objects.filter(
                petugas_id=petugas_id,
                posyandu_id=posyandu_id,
            ).order_by("-tanggal_mulai", "-pk")
        )
        if not rows:
            continue
        keep = rows[0]
        keep.tanggal_daftar = keep.tanggal_mulai or today
        keep.save(update_fields=["tanggal_daftar"])
        if len(rows) > 1:
            PenugasanPetugas.objects.filter(pk__in=[row.pk for row in rows[1:]]).delete()

    # Kader memakai satu Posyandu operasional yang sama dengan Petugas.posyandu.
    for kader in Petugas.objects.filter(level="kader").iterator():
        qs = PenugasanPetugas.objects.filter(petugas_id=kader.pk)
        primary_id = kader.posyandu_id
        if primary_id is None:
            latest = qs.order_by("-tanggal_daftar", "-pk").first()
            if latest is not None:
                primary_id = latest.posyandu_id
                Petugas.objects.filter(pk=kader.pk).update(posyandu_id=primary_id)

        if primary_id is None:
            qs.delete()
            continue

        qs.exclude(posyandu_id=primary_id).delete()
        if not qs.filter(posyandu_id=primary_id).exists():
            PenugasanPetugas.objects.create(
                petugas_id=kader.pk,
                posyandu_id=primary_id,
                tanggal_daftar=today,
            )

    # Bidan boleh multi-Posyandu. Pastikan Posyandu utama tetap punya baris penugasan.
    for bidan in Petugas.objects.filter(level="bidan", posyandu_id__isnull=False).iterator():
        PenugasanPetugas.objects.get_or_create(
            petugas_id=bidan.pk,
            posyandu_id=bidan.posyandu_id,
            defaults={"tanggal_daftar": today},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("posyandu", "0007_repair_kader_operational_scope"),
    ]

    operations = [
        migrations.AddField(
            model_name="penugasanpetugas",
            name="tanggal_daftar",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(migrasi_penugasan_saat_ini, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="penugasanpetugas",
            name="tanggal_mulai",
        ),
        migrations.RemoveField(
            model_name="penugasanpetugas",
            name="tanggal_selesai",
        ),
        migrations.AlterField(
            model_name="penugasanpetugas",
            name="tanggal_daftar",
            field=models.DateField("Tanggal Daftar", default=timezone.localdate, editable=False),
        ),
        migrations.AlterModelOptions(
            name="penugasanpetugas",
            options={
                "ordering": ["-tanggal_daftar", "-pk"],
                "verbose_name": "Penugasan Petugas",
                "verbose_name_plural": "Penugasan Petugas",
            },
        ),
        migrations.AddConstraint(
            model_name="penugasanpetugas",
            constraint=models.UniqueConstraint(
                fields=("petugas", "posyandu"),
                name="unique_penugasan_petugas_posyandu",
            ),
        ),
    ]
