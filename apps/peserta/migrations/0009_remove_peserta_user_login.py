from django.db import migrations


def disable_legacy_peserta_users(apps, schema_editor):
    Peserta = apps.get_model("peserta", "Peserta")
    User = apps.get_model("auth", "User")

    user_ids = list(
        Peserta.objects.exclude(user_id=None).values_list("user_id", flat=True)
    )

    # Peserta bukan aktor sistem. Nonaktifkan akun legacy sebelum field relasi
    # dihapus. Superuser tidak dinonaktifkan untuk mencegah lock-out admin.
    User.objects.filter(pk__in=user_ids, is_superuser=False).update(
        is_active=False,
        is_staff=False,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("peserta", "0008_alter_peserta_status_peserta"),
    ]

    operations = [
        migrations.RunPython(disable_legacy_peserta_users, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="peserta",
            name="user",
        ),
    ]
