# posyandu/forms.py
from django import forms
import re
from common.forms import IndonesianValidationMixin
from .models import JadwalKegiatan, Posyandu
from django.contrib.auth.models import User
from apps.accounts.models import Petugas


class JadwalKegiatanForm(IndonesianValidationMixin, forms.ModelForm):
    """Form jadwal untuk Kader.

    Posyandu sengaja tidak diekspos sebagai input. Lokasi kegiatan selalu
    ditetapkan oleh backend dari tempat tugas Kader yang sedang login.
    Dengan demikian nilai Posyandu tidak dapat dimanipulasi melalui POST.
    """

    def clean(self):
        cleaned_data = super().clean()
        mulai = cleaned_data.get("jam_mulai")
        selesai = cleaned_data.get("jam_selesai")
        if mulai and selesai and selesai <= mulai:
            self.add_error("jam_selesai", "Jam selesai harus setelah jam mulai.")
        return cleaned_data

    class Meta:
        model = JadwalKegiatan
        fields = [
            "tgl_kegiatan",
            "jam_mulai",
            "jam_selesai",
            "jns_kegiatan",
        ]

        widgets = {
            "tgl_kegiatan": forms.DateInput(
                format='%Y-%m-%d',
                attrs={
                    "type": "date",
                    "class": "form-input"
                }
            ),

            "jam_mulai": forms.TimeInput(
                format='%H:%M',
                attrs={
                    "type": "time",
                    "class": "form-input"
                }
            ),

            "jam_selesai": forms.TimeInput(
                format='%H:%M',
                attrs={
                    "type": "time",
                    "class": "form-input"
                }
            ),

            "jns_kegiatan": forms.Select(
                attrs={
                    "class": "form-select"
                }
            ),

        }
        
        
class PosyanduForm(IndonesianValidationMixin, forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The UI marks all master Posyandu fields as mandatory; keep server-side
        # validation aligned with that visual contract.
        for field_name in ("nama", "desa", "alamat"):
            self.fields[field_name].required = True
        self.fields["nama"].error_messages["required"] = "Nama Posyandu wajib diisi."
        self.fields["desa"].error_messages["required"] = "Desa / Kelurahan wajib diisi."
        self.fields["alamat"].error_messages["required"] = "Alamat Posyandu wajib diisi."

    class Meta:
        model = Posyandu
        fields = [
            "nama",
            "alamat",
            "desa",
        ]

        widgets = {
            "nama": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Masukkan nama posyandu"
                }
            ),

            "alamat": forms.Textarea(
                attrs={
                    "class": "form-textarea",
                    "rows": 3,
                    "placeholder": "Masukkan alamat posyandu"
                }
            ),

            "desa": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Masukkan nama desa"
                }
            ),
        }

        labels = {
            "nama": "Nama Posyandu",
            "alamat": "Alamat",
            "desa": "Desa / Kelurahan",
        }

class PosyanduEditForm(IndonesianValidationMixin, forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("nama", "desa", "alamat"):
            self.fields[field_name].required = True
        self.fields["nama"].error_messages["required"] = "Nama Posyandu wajib diisi."
        self.fields["desa"].error_messages["required"] = "Desa / Kelurahan wajib diisi."
        self.fields["alamat"].error_messages["required"] = "Alamat Posyandu wajib diisi."

    class Meta:
        model = Posyandu
        fields = [
            "nama",
            "alamat",
            "desa",
        ]

        widgets = {
            "nama": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Masukkan nama posyandu"
                }
            ),

            "alamat": forms.Textarea(
                attrs={
                    "class": "form-textarea",
                    "rows": 3,
                    "placeholder": "Masukkan alamat posyandu"
                }
            ),

            "desa": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Masukkan nama desa"
                }
            ),
        }
        


class UserEditForm(IndonesianValidationMixin, forms.ModelForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-300 focus:outline-none focus:border-emerald-500',
            'placeholder': 'Masukkan username'
        })
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-300 focus:outline-none focus:border-emerald-500',
            'placeholder': 'contoh@email.com'
        })
    )

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise forms.ValidationError("Username wajib diisi.")
        qs = User.objects.filter(username__iexact=username)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Username sudah digunakan oleh akun lain.")
        return username

    class Meta:
        model = User
        fields = ['username', 'email']

class PetugasEditForm(IndonesianValidationMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nama"].widget.attrs.setdefault("placeholder", "Masukkan nama lengkap")
        self.fields["no_telp"].widget.attrs.setdefault("placeholder", "08xxxxxxxxxx")
        self.fields["alamat"].widget.attrs.setdefault("placeholder", "Masukkan alamat lengkap")
        if self.instance and self.instance.pk and self.instance.level == "kader":
            self.fields["posyandu"].required = True
            self.fields["posyandu"].empty_label = "Pilih Posyandu penempatan"
            self.fields["posyandu"].error_messages["required"] = "Penempatan Posyandu wajib dipilih untuk Kader."
        if self.instance and self.instance.pk and self.instance.level == "bidan":
            # Posyandu utama bidan ditentukan otomatis dari halaman Cakupan Wilayah.
            # Field dibuat read-only agar admin tidak mengubah satu Posyandu saja
            # dan membuat penugasan multi-wilayah menjadi tidak sinkron.
            self.fields["posyandu"].disabled = True
            self.fields["posyandu"].help_text = (
                "Posyandu utama mengikuti cakupan wilayah kerja bidan. "
                "Gunakan tombol Atur Cakupan Wilayah untuk mengubah penugasan."
            )

        # Override generic fallback placeholders with examples that are easier
        # to understand during data entry.
        self.fields["nama"].widget.attrs["placeholder"] = "Masukkan nama lengkap"
        self.fields["no_telp"].widget.attrs["placeholder"] = "08xxxxxxxxxx"
        self.fields["alamat"].widget.attrs["placeholder"] = "Masukkan alamat lengkap"

    def clean_no_telp(self):
        value = (self.cleaned_data.get("no_telp") or "").strip().replace(" ", "").replace("-", "")
        if not value:
            return None
        if not re.fullmatch(r"\+?\d{8,15}", value):
            raise forms.ValidationError("Nomor telepon harus berupa 8–15 digit dan boleh diawali tanda +.")
        return value

    class Meta:
        model = Petugas
        fields = ['nama', 'alamat', 'no_telp', 'posyandu']
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'w-full px-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-300 focus:outline-none focus:border-emerald-500', 'autocomplete': 'name'}),
            'alamat': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-300 focus:outline-none focus:border-emerald-500', 'autocomplete': 'street-address'}),
            'no_telp': forms.TextInput(attrs={'class': 'w-full px-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-300 focus:outline-none focus:border-emerald-500', 'inputmode': 'tel', 'autocomplete': 'tel'}),
            'posyandu': forms.Select(attrs={'class': 'w-full px-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-300 focus:outline-none focus:border-emerald-500'}),
        }
