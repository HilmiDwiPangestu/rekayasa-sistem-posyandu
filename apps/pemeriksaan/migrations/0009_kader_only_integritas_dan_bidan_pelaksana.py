import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Count


def deduplicate_pemeriksaan(apps, schema_editor):
    """Normalisasi duplikasi lama sebelum constraint peserta+jadwal dibuat.

    Versi lama belum memiliki constraint pemeriksaan per peserta/jadwal. Jika
    pernah terjadi double-submit, pertahankan record terbaru sebagai koreksi
    final dan hapus duplikasi yang lebih lama agar migration PostgreSQL tidak
    gagal.
    """
    for model_name in ("PemeriksaanBalita", "PemeriksaanBumil"):
        Model = apps.get_model("pemeriksaan", model_name)
        groups = (
            Model.objects.values("peserta_id", "jadwal_id")
            .annotate(total=Count("pk"))
            .filter(total__gt=1)
        )
        for group in groups:
            rows = Model.objects.filter(
                peserta_id=group["peserta_id"],
                jadwal_id=group["jadwal_id"],
            ).order_by("-tgl_pemeriksaan", "-pk")
            keep = rows.first()
            if keep is not None:
                rows.exclude(pk=keep.pk).delete()


def reverse_deduplicate_noop(apps, schema_editor):
    # Record duplikat yang merupakan akibat double-submit tidak dibuat kembali.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_disable_bidan_login"),
        ("peserta", "0009_remove_peserta_user_login"),
        ("posyandu", "0005_sync_kader_assignments"),
        ("pemeriksaan", "0008_pelayananbalita_alter_pemeriksaanbalita_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="pemeriksaanbalita",
            name="bidan_pelaksana",
            field=models.ForeignKey(
                blank=True,
                help_text="Bidan/tenaga kesehatan pendamping pelayanan",
                limit_choices_to={"level": "bidan"},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pemeriksaan_balita_sebagai_bidan",
                to="accounts.petugas",
            ),
        ),
        migrations.AddField(
            model_name="pemeriksaanbumil",
            name="bidan_pelaksana",
            field=models.ForeignKey(
                blank=True,
                help_text="Bidan/tenaga kesehatan pendamping pemeriksaan",
                limit_choices_to={"level": "bidan"},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pemeriksaan_bumil_sebagai_bidan",
                to="accounts.petugas",
            ),
        ),
        migrations.AddField(
            model_name="imunisasi",
            name="bidan_pelaksana",
            field=models.ForeignKey(
                blank=True,
                help_text="Bidan/tenaga kesehatan pelaksana imunisasi",
                limit_choices_to={"level": "bidan"},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="imunisasi_sebagai_bidan",
                to="accounts.petugas",
            ),
        ),
        migrations.AlterField(
            model_name="pemeriksaanbalita",
            name="peserta",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pemeriksaan_balita",
                to="peserta.peserta",
            ),
        ),
        migrations.AlterField(
            model_name="pemeriksaanbalita",
            name="jadwal",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pemeriksaan_balita",
                to="posyandu.jadwalkegiatan",
            ),
        ),
        migrations.AlterField(
            model_name="pemeriksaanbalita",
            name="status_gizi",
            field=models.CharField(
                choices=[
                    ("stunting_berat", "Sangat Pendek"),
                    ("stunting", "Pendek"),
                    ("normal", "Normal"),
                    ("tinggi", "Tinggi"),
                ],
                default="normal",
                editable=False,
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="pemeriksaanbumil",
            name="peserta",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pemeriksaan_bumil",
                to="peserta.peserta",
            ),
        ),
        migrations.AlterField(
            model_name="pemeriksaanbumil",
            name="jadwal",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pemeriksaan_bumil",
                to="posyandu.jadwalkegiatan",
            ),
        ),
        migrations.AlterField(
            model_name="pemeriksaanbumil",
            name="status_kehamilan",
            field=models.CharField(
                choices=[
                    ("normal", "Normal"),
                    ("resiko", "Risiko Tinggi"),
                    ("anemia", "Anemia"),
                    ("kek", "KEK"),
                ],
                default="normal",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="imunisasi",
            name="peserta",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="imunisasi",
                to="peserta.peserta",
            ),
        ),
        migrations.AlterField(
            model_name="imunisasi",
            name="jadwal",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="imunisasi",
                to="posyandu.jadwalkegiatan",
            ),
        ),
        migrations.AlterField(
            model_name="imunisasi",
            name="jenis_vaksin",
            field=models.CharField(
                choices=[
                    ("HB-0", "Hepatitis B (HB-0)"),
                    ("BCG", "BCG"),
                    ("bOPV 1", "Polio Tetes (bOPV) 1"),
                    ("bOPV 2", "Polio Tetes (bOPV) 2"),
                    ("bOPV 3", "Polio Tetes (bOPV) 3"),
                    ("bOPV 4", "Polio Tetes (bOPV) 4"),
                    ("DPT-HB-Hib 1", "DPT-HB-Hib 1"),
                    ("DPT-HB-Hib 2", "DPT-HB-Hib 2"),
                    ("DPT-HB-Hib 3", "DPT-HB-Hib 3"),
                    ("DPT-HB-Hib 4", "DPT-HB-Hib 4"),
                    ("PCV 1", "PCV 1"),
                    ("PCV 2", "PCV 2"),
                    ("PCV 3", "PCV 3"),
                    ("Rotavirus 1", "Rotavirus 1"),
                    ("Rotavirus 2", "Rotavirus 2"),
                    ("Rotavirus 3", "Rotavirus 3"),
                    ("IPV 1", "Polio Suntik (IPV) 1"),
                    ("IPV 2", "Polio Suntik (IPV) 2"),
                    ("MR 1", "Campak Rubela (MR) 1"),
                    ("MR 2", "Campak Rubela (MR) 2"),
                    ("JE", "Japanese Encephalitis (wilayah endemis)"),
                    ("TT-1", "TT-1 (Tetanus Toksoid)"),
                    ("TT-2", "TT-2 (Tetanus Toksoid)"),
                    ("TT-3", "TT-3 (Tetanus Toksoid)"),
                    ("TT-4", "TT-4 (Tetanus Toksoid)"),
                    ("TT-5", "TT-5 (Tetanus Toksoid)"),
                ],
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="kehadiran",
            name="peserta",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="kehadiran",
                to="peserta.peserta",
            ),
        ),
        migrations.AlterField(
            model_name="kehadiran",
            name="jadwal",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="kehadiran",
                to="posyandu.jadwalkegiatan",
            ),
        ),
        migrations.RunPython(
            deduplicate_pemeriksaan,
            reverse_code=reverse_deduplicate_noop,
        ),
        migrations.AddConstraint(
            model_name="pemeriksaanbalita",
            constraint=models.UniqueConstraint(
                fields=("peserta", "jadwal"),
                name="unique_pemeriksaan_balita_peserta_jadwal",
            ),
        ),
        migrations.AddConstraint(
            model_name="pemeriksaanbumil",
            constraint=models.UniqueConstraint(
                fields=("peserta", "jadwal"),
                name="unique_pemeriksaan_bumil_peserta_jadwal",
            ),
        ),
    ]
