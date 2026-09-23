from getpass import getpass

from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Petugas


class Command(BaseCommand):
    help = (
        "Membuat akun operasional Admin Kelurahan sebagai User biasa, "
        "terpisah dari superuser/staff Django."
    )

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--nama", required=True)
        parser.add_argument("--no-telp", default="")
        parser.add_argument("--password", default=None)
        parser.add_argument(
            "--petugas-id",
            type=int,
            default=None,
            help=(
                "Opsional: gunakan profil Petugas Admin yang sudah ada. "
                "Jika profil masih terhubung ke akun superuser/staff lama, "
                "relasi tersebut akan dilepas tanpa menghapus akun teknisnya."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        username = options["username"].strip()
        nama = options["nama"].strip()
        no_telp = options["no_telp"].strip()
        password = options["password"]
        petugas_id = options["petugas_id"]

        if not username or not nama:
            raise CommandError("Username dan nama wajib diisi.")
        if User.objects.filter(username=username).exists():
            raise CommandError(f"Username '{username}' sudah digunakan.")

        if not password:
            password = getpass("Password Admin Kelurahan: ")
            confirmation = getpass("Ulangi password: ")
            if password != confirmation:
                raise CommandError("Konfirmasi password tidak sama.")

        try:
            password_validation.validate_password(password)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error

        if petugas_id is not None:
            try:
                petugas = Petugas.objects.select_related("user").get(
                    pk=petugas_id,
                    level="admin",
                )
            except Petugas.DoesNotExist as error:
                raise CommandError("Profil Petugas Admin tidak ditemukan.") from error

            if petugas.user_id:
                old_user = petugas.user
                if not (old_user.is_staff or old_user.is_superuser):
                    raise CommandError(
                        "Profil Admin tersebut sudah terhubung ke akun aplikasi biasa."
                    )
                petugas.user = None
                petugas.save(update_fields=["user"])
                self.stdout.write(
                    self.style.WARNING(
                        f"Relasi akun teknis '{old_user.username}' dilepas dari profil Admin. "
                        "Akun teknis tetap ada untuk /admin/."
                    )
                )
        else:
            petugas = Petugas(
                nama=nama,
                no_telp=no_telp or None,
                level="admin",
                posyandu=None,
            )

        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=nama,
            is_staff=False,
            is_superuser=False,
        )

        petugas.user = user
        petugas.nama = nama
        if no_telp:
            petugas.no_telp = no_telp
        petugas.save()

        self.stdout.write(self.style.SUCCESS("Admin Kelurahan berhasil dibuat."))
        self.stdout.write(f"Username : {username}")
        self.stdout.write(f"Petugas ID: {petugas.pk}")
        self.stdout.write("Akses     : aplikasi Posyandu (bukan Django Admin)")
