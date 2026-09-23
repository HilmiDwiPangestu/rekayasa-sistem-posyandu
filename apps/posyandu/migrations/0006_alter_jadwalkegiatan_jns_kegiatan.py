from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("posyandu", "0005_sync_kader_assignments"),
    ]

    operations = [
        migrations.AlterField(
            model_name="jadwalkegiatan",
            name="jns_kegiatan",
            field=models.CharField(
                choices=[
                    ("Pemeriksaan Rutin", "Pemeriksaan Rutin"),
                    ("Imunisasi", "Imunisasi"),
                ],
                max_length=50,
                verbose_name="Jenis Kegiatan",
            ),
        ),
    ]
