# posyandu/forms.py
from django import forms
from .models import JadwalKegiatan, Posyandu
from django.contrib.auth.models import User
from apps.accounts.models import Petugas


class JadwalKegiatanForm(forms.ModelForm):
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
                    "class": "form-control"
                }
            ),

            "jam_mulai": forms.TimeInput(
                format='%H:%M',
                attrs={
                    "type": "time",
                    "class": "form-control"
                }
            ),

            "jam_selesai": forms.TimeInput(
                format='%H:%M',
                attrs={
                    "type": "time",
                    "class": "form-control"
                }
            ),

            "jns_kegiatan": forms.Select(
                attrs={
                    "class": "form-select"
                }
            ),

        }
        
        
class PosyanduForm(forms.ModelForm):

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
                    "class": "form-control",
                    "placeholder": "Masukkan nama posyandu"
                }
            ),

            "alamat": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Masukkan alamat posyandu"
                }
            ),

            "desa": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Masukkan nama desa"
                }
            ),
        }

        labels = {
            "nama": "Nama Posyandu",
            "alamat": "Alamat",
            "desa": "Desa / Kelurahan",
        }

class PosyanduEditForm(forms.ModelForm):

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
                    "class": "form-control",
                    "placeholder": "Masukkan nama posyandu"
                }
            ),

            "alamat": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Masukkan alamat posyandu"
                }
            ),

            "desa": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Masukkan nama desa"
                }
            ),
        }
        


class UserEditForm(forms.ModelForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-300 focus:outline-none focus:border-emerald-500'
        })
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-300 focus:outline-none focus:border-emerald-500'
        })
    )

    class Meta:
        model = User
        fields = ['username', 'email']

class PetugasEditForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.level == "bidan":
            # Posyandu utama bidan ditentukan otomatis dari halaman Cakupan Wilayah.
            # Field dibuat read-only agar admin tidak mengubah satu Posyandu saja
            # dan membuat penugasan multi-wilayah menjadi tidak sinkron.
            self.fields["posyandu"].disabled = True
            self.fields["posyandu"].help_text = (
                "Posyandu utama mengikuti cakupan wilayah kerja bidan. "
                "Gunakan tombol Atur Cakupan Wilayah untuk mengubah penugasan."
            )

    class Meta:
        model = Petugas
        fields = ['nama', 'alamat', 'no_telp', 'posyandu']
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'w-full px-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-300 focus:outline-none focus:border-emerald-500'}),
            'alamat': forms.Textarea(attrs={'rows': 3, 'class': 'w-full px-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-300 focus:outline-none focus:border-emerald-500'}),
            'no_telp': forms.TextInput(attrs={'class': 'w-full px-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-300 focus:outline-none focus:border-emerald-500'}),
            'posyandu': forms.Select(attrs={'class': 'w-full px-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-300 focus:outline-none focus:border-emerald-500'}),
        }
