from django.db import migrations, models


def isi_jenis_pengukuran_existing(apps, schema_editor):
    PemeriksaanBalita = apps.get_model("pemeriksaan", "PemeriksaanBalita")

    for item in PemeriksaanBalita.objects.all().iterator():
        # Data historis tidak menyimpan posisi ukur. Gunakan metode standar WHO
        # berdasarkan usia sehingga hasil lama tidak berubah: <731 hari panjang
        # terlentang, >=731 hari tinggi berdiri. Pengguna dapat mengoreksi saat edit.
        umur_hari = getattr(item, "usia_hari", None)
        item.jenis_pengukuran = (
            "panjang" if umur_hari is not None and umur_hari < 731 else "tinggi"
        )
        item.save(update_fields=["jenis_pengukuran"])


class Migration(migrations.Migration):
    dependencies = [
        ("pemeriksaan", "0012_alter_pemeriksaanbalita_usia_bulan"),
    ]

    operations = [
        migrations.AddField(
            model_name="pemeriksaanbalita",
            name="jenis_pengukuran",
            field=models.CharField(
                choices=[
                    ("panjang", "Panjang badan (terlentang)"),
                    ("tinggi", "Tinggi badan (berdiri)"),
                ],
                default="panjang",
                help_text=(
                    "Pilih posisi saat panjang/tinggi badan benar-benar diukur. "
                    "Digunakan untuk koreksi WHO 0,7 cm bila posisi ukur tidak sesuai kelompok usia."
                ),
                max_length=10,
            ),
            preserve_default=False,
        ),
        migrations.RunPython(
            isi_jenis_pengukuran_existing,
            migrations.RunPython.noop,
        ),
    ]
