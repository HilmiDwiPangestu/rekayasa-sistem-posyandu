from django.db import migrations, models


def disable_bidan_login(apps, schema_editor):
    Petugas = apps.get_model("accounts", "Petugas")
    User = apps.get_model("auth", "User")

    user_ids = list(
        Petugas.objects.filter(level="bidan", user_id__isnull=False)
        .values_list("user_id", flat=True)
    )

    # Putuskan relasi lebih dahulu agar data Bidan tetap tersimpan sebagai
    # data master/penanggung jawab wilayah.
    Petugas.objects.filter(level="bidan", user_id__isnull=False).update(user_id=None)

    # Akun legacy Bidan biasa dinonaktifkan. Superuser tidak disentuh karena
    # diperlakukan sebagai Admin Kelurahan/super-admin dan tidak lagi terkait Bidan.
    User.objects.filter(pk__in=user_ids, is_superuser=False).update(
        is_active=False,
        is_staff=False,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_alter_petugas_options_alter_petugas_posyandu"),
    ]

    operations = [
        migrations.RunPython(disable_bidan_login, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="petugas",
            constraint=models.CheckConstraint(
                condition=(~models.Q(level="bidan") | models.Q(user__isnull=True)),
                name="petugas_bidan_tanpa_akun",
            ),
        ),
    ]
