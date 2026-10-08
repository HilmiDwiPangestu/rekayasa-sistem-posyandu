from django import forms
import re

from common.forms import IndonesianValidationMixin
from apps.posyandu.models import Posyandu

from .models import Petugas


COMMON_CLASS = """
    w-full rounded-xl border border-slate-200 dark:border-slate-700
    bg-white dark:bg-slate-950
    px-4 py-2.5 text-sm
    text-slate-700 dark:text-slate-200
    focus:outline-none focus:ring-2
    focus:ring-emerald-500/20
    focus:border-emerald-500
"""


class PetugasForm(IndonesianValidationMixin, forms.ModelForm):
    cakupan_posyandu = forms.ModelMultipleChoiceField(
        queryset=Posyandu.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Cakupan Wilayah Kerja Bidan",
        help_text="Pilih satu atau lebih Posyandu yang menjadi wilayah tugas bidan.",
    )

    def __init__(self, *args, level_petugas=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.level_petugas = level_petugas

        if level_petugas == "bidan":
            self.fields.pop("posyandu", None)
            self.fields["cakupan_posyandu"].queryset = Posyandu.objects.all().order_by("desa", "nama")
            self.fields["cakupan_posyandu"].required = True
            self.fields["cakupan_posyandu"].error_messages["required"] = (
                "Pilih minimal satu Posyandu untuk cakupan wilayah kerja Bidan."
            )
        else:
            self.fields.pop("cakupan_posyandu", None)
            if "posyandu" in self.fields:
                self.fields["posyandu"].required = True
                self.fields["posyandu"].empty_label = "Pilih Posyandu penempatan"
                self.fields["posyandu"].error_messages["required"] = (
                    "Penempatan Posyandu wajib dipilih untuk Kader."
                )

    def clean_no_telp(self):
        value = (self.cleaned_data.get("no_telp") or "").strip().replace(" ", "").replace("-", "")
        if not value:
            return None
        if not re.fullmatch(r"\+?\d{8,15}", value):
            raise forms.ValidationError("Nomor telepon harus berupa 8–15 digit dan boleh diawali tanda +.")
        return value

    def clean(self):
        cleaned = super().clean()
        if self.level_petugas == "bidan":
            coverage = cleaned.get("cakupan_posyandu")
            if coverage:
                # Model Petugas tetap membutuhkan satu Posyandu utama.
                # Pilihan pertama menjadi primary, sedangkan seluruh pilihan
                # disimpan sebagai PenugasanPetugas setelah form valid.
                self.instance.posyandu = coverage[0]
        return cleaned

    class Meta:
        model = Petugas
        fields = [
            "nama",
            "alamat",
            "no_telp",
            "posyandu",
        ]

        widgets = {
            "nama": forms.TextInput(attrs={
                "class": COMMON_CLASS,
                "placeholder": "Masukkan nama lengkap",
                "autocomplete": "name",
            }),
            "posyandu": forms.Select(attrs={
                "class": COMMON_CLASS,
            }),
            "no_telp": forms.TextInput(attrs={
                "class": COMMON_CLASS,
                "placeholder": "08xxxxxxxxxx",
                "inputmode": "tel",
                "autocomplete": "tel",
            }),
            "alamat": forms.Textarea(attrs={
                "class": COMMON_CLASS,
                "rows": 4,
                "placeholder": "Masukkan alamat lengkap",
                "autocomplete": "street-address",
            }),
        }

        labels = {
            "nama": "Nama Petugas",
            "alamat": "Alamat",
            "no_telp": "Nomor Telepon",
            "posyandu": "Posyandu",
        }
