import csv
from pathlib import Path

from django.db import migrations, models


SOURCE = "WHO LFA expanded daily"


def load_daily_reference(apps, schema_editor):
    WHOStandardPBU = apps.get_model("referensi", "WHOStandardPBU")
    data_dir = Path(__file__).resolve().parents[1] / "data"
    files = [
        ("L", data_dir / "lfa_boys_z_exp.csv"),
        ("P", data_dir / "lfa_girls_z_exp.csv"),
    ]

    rows = []
    for gender, path in files:
        seen_days = []
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            for raw in reader:
                seen_days.append(int(raw["Day"]))
                m_value = float(str(raw["M"]).replace(",", "."))
                s_value = float(str(raw["S"]).replace(",", "."))
                rows.append(
                    WHOStandardPBU(
                        gender=gender,
                        day=int(raw["Day"]),
                        month=None,
                        l_value=float(str(raw["L"]).replace(",", ".")),
                        m_value=m_value,
                        s_value=s_value,
                        sd=m_value * s_value,
                        sd4neg=float(str(raw["SD4neg"]).replace(",", ".")),
                        sd3neg=float(str(raw["SD3neg"]).replace(",", ".")),
                        sd2neg=float(str(raw["SD2neg"]).replace(",", ".")),
                        sd1neg=float(str(raw["SD1neg"]).replace(",", ".")),
                        sd0=float(str(raw["SD0"]).replace(",", ".")),
                        sd1=float(str(raw["SD1"]).replace(",", ".")),
                        sd2=float(str(raw["SD2"]).replace(",", ".")),
                        sd3=float(str(raw["SD3"]).replace(",", ".")),
                        sd4=float(str(raw["SD4"]).replace(",", ".")),
                        source=SOURCE,
                    )
                )
        if seen_days != list(range(1857)):
            raise RuntimeError(
                f"Referensi WHO {path.name} harus memiliki Day 0-1856 lengkap."
            )

    # Ganti referensi bulanan lama secara atomik di migration ini.
    WHOStandardPBU.objects.all().delete()
    WHOStandardPBU.objects.bulk_create(rows, batch_size=500)


def reverse_daily_reference(apps, schema_editor):
    # Data bulanan lama tidak direkonstruksi saat rollback karena sumber aktif
    # project sudah berpindah ke WHO daily. Schema tetap dapat di-rollback.
    WHOStandardPBU = apps.get_model("referensi", "WHOStandardPBU")
    WHOStandardPBU.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("referensi", "0002_whostandardpbu_sd"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="whostandardpbu",
            name="unique_pbu_gender_month",
        ),
        migrations.AddField(
            model_name="whostandardpbu",
            name="day",
            field=models.PositiveIntegerField(
                blank=True,
                db_index=True,
                help_text="Umur dalam hari sesuai tabel WHO expanded (0-1856)",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="whostandardpbu",
            name="month",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Kolom kompatibilitas data WHO bulanan lama",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="whostandardpbu",
            name="sd4neg",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="whostandardpbu",
            name="sd4",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="whostandardpbu",
            name="source",
            field=models.CharField(
                default="WHO LFA expanded daily",
                help_text="Sumber referensi antropometri",
                max_length=64,
            ),
        ),
        migrations.RunPython(load_daily_reference, reverse_daily_reference),
        migrations.AddConstraint(
            model_name="whostandardpbu",
            constraint=models.UniqueConstraint(
                fields=("gender", "day"),
                name="unique_pbu_gender_day",
            ),
        ),
        migrations.AlterModelOptions(
            name="whostandardpbu",
            options={"ordering": ["gender", "day"]},
        ),
    ]
