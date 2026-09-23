from django.db import migrations


LEGACY_VACCINE_MAP = {
    "Polio 1": ("bOPV 1", "1"),
    "Polio 2": ("bOPV 2", "2"),
    "Polio 3": ("bOPV 3", "3"),
    "Polio 4": ("bOPV 4", "4"),
    "IPV": ("IPV 1", "1"),
    "Campak/MR": ("MR 1", "1"),
    "PCV": ("PCV 1", "1"),
    "PCV Booster": ("PCV 3", "3"),
}


def forward_migrate_legacy_vaccines(apps, schema_editor):
    """Konversi nomenklatur vaksin lama tanpa membuat duplikasi.

    Database versi lama dapat berisi nama vaksin yang sudah tidak digunakan
    oleh form/laporan terbaru.  Karena Imunisasi memiliki constraint unik pada
    (peserta, jadwal, jenis_vaksin), migrasi mengecek apakah target baru sudah
    ada untuk peserta dan jadwal yang sama. Bila ada, record lama dihapus
    sebagai duplikasi nomenklatur; bila tidak, record lama diperbarui dan dosis
    diselaraskan.
    """
    Imunisasi = apps.get_model("pemeriksaan", "Imunisasi")

    for legacy_name, (new_name, new_dose) in LEGACY_VACCINE_MAP.items():
        legacy_rows = list(
            Imunisasi.objects.filter(jenis_vaksin=legacy_name).order_by("pk")
        )

        for row in legacy_rows:
            duplicate = Imunisasi.objects.filter(
                peserta_id=row.peserta_id,
                jadwal_id=row.jadwal_id,
                jenis_vaksin=new_name,
            ).exclude(pk=row.pk).first()

            if duplicate is not None:
                # Kedua record merepresentasikan vaksin/dosis yang sama setelah
                # normalisasi nama. Pertahankan record dengan nomenklatur baru.
                row.delete()
                continue

            row.jenis_vaksin = new_name
            row.dosis = new_dose
            row.save(update_fields=["jenis_vaksin", "dosis"])


def reverse_noop(apps, schema_editor):
    # Tidak dikembalikan ke nama lama karena beberapa nama lama bersifat
    # ambigu dan versi baru menjadi nomenklatur kanonik project.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("pemeriksaan", "0009_kader_only_integritas_dan_bidan_pelaksana"),
    ]

    operations = [
        migrations.RunPython(
            forward_migrate_legacy_vaccines,
            reverse_code=reverse_noop,
        ),
    ]
