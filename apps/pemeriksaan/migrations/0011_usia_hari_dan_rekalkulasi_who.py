import math

from django.db import migrations, models


def recalculate_who_daily(apps, schema_editor):
    PemeriksaanBalita = apps.get_model("pemeriksaan", "PemeriksaanBalita")
    WHOStandardPBU = apps.get_model("referensi", "WHOStandardPBU")

    references = {
        (row.gender, row.day): row
        for row in WHOStandardPBU.objects.exclude(day__isnull=True).iterator()
    }

    updates = []
    qs = PemeriksaanBalita.objects.select_related("peserta", "jadwal").all()
    for item in qs.iterator():
        peserta = item.peserta
        if not peserta or not peserta.tgl_lahir or not item.tgl_pemeriksaan:
            continue

        if getattr(item, "jadwal_id", None) and getattr(item.jadwal, "tgl_kegiatan", None):
            tanggal = item.jadwal.tgl_kegiatan
        else:
            tanggal = item.tgl_pemeriksaan.date() if hasattr(item.tgl_pemeriksaan, "date") else item.tgl_pemeriksaan
        day = (tanggal - peserta.tgl_lahir).days
        item.usia_hari = day

        gender_text = str(getattr(peserta, "jenis_kelamin", "") or "").strip().lower()
        gender = "P" if gender_text.startswith("p") else "L"
        ref = references.get((gender, day))

        if ref is not None and item.tinggi_badan is not None:
            x = float(item.tinggi_badan)
            L = float(ref.l_value)
            M = float(ref.m_value)
            S = float(ref.s_value)
            if x > 0 and M > 0 and S > 0:
                if math.isclose(L, 0.0, abs_tol=1e-12):
                    z = math.log(x / M) / S
                else:
                    z = (((x / M) ** L) - 1.0) / (L * S)
                item.z_score = round(float(z), 4)
                if z < -3:
                    item.status_gizi = "stunting_berat"
                elif z < -2:
                    item.status_gizi = "stunting"
                elif z <= 3:
                    item.status_gizi = "normal"
                else:
                    item.status_gizi = "tinggi"

        updates.append(item)

    if updates:
        PemeriksaanBalita.objects.bulk_update(
            updates,
            ["usia_hari", "z_score", "status_gizi"],
            batch_size=500,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("referensi", "0003_who_daily_expanded"),
        ("pemeriksaan", "0010_migrasi_kode_vaksin_lama"),
    ]

    operations = [
        migrations.AddField(
            model_name="pemeriksaanbalita",
            name="usia_hari",
            field=models.IntegerField(
                blank=True,
                editable=False,
                help_text="Usia eksak dalam hari untuk lookup referensi WHO daily",
                null=True,
            ),
        ),
        migrations.RunPython(recalculate_who_daily, migrations.RunPython.noop),
    ]
