from django.db import migrations, models


def samakan_status_bumil(apps, schema_editor):
    Peserta = apps.get_model("peserta", "Peserta")
    Peserta.objects.filter(status_peserta="ibu hamil").update(status_peserta="bumil")


def kembalikan_status_bumil(apps, schema_editor):
    Peserta = apps.get_model("peserta", "Peserta")
    Peserta.objects.filter(status_peserta="bumil").update(status_peserta="ibu hamil")


class Migration(migrations.Migration):
    dependencies = [
        ("peserta", "0007_peserta_lila_lahir_alter_peserta_nik_ibu_and_more"),
    ]

    operations = [
        migrations.RunPython(samakan_status_bumil, kembalikan_status_bumil),
        migrations.AlterField(
            model_name="peserta",
            name="status_peserta",
            field=models.CharField(
                choices=[("bumil", "Ibu Hamil"), ("balita", "Balita")],
                max_length=10,
            ),
        ),
    ]
