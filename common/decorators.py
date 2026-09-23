from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render

from apps.accounts.models import Petugas


def level_required(*levels):
    """Batasi view pada level Petugas tertentu."""
    allowed_levels = frozenset(levels)

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())

            try:
                petugas = request.user.petugas
            except (Petugas.DoesNotExist, AttributeError):
                return render(request, "403.html", status=403)

            if not petugas.can_login or petugas.level not in allowed_levels:
                return render(request, "403.html", status=403)

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def admin_required(view_func):
    return level_required("admin")(view_func)


def petugas_required(view_func):
    """Izinkan hanya dua aktor sistem: Admin Kelurahan dan Kader."""
    return level_required("admin", "kader")(view_func)


def kader_required(view_func):
    """Izinkan hanya Kader untuk input dan transaksi operasional Posyandu."""
    return level_required("kader")(view_func)
