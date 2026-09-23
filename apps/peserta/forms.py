import re
from datetime import date

from dateutil.relativedelta import relativedelta
from django import forms

from .models import Peserta


INPUT_CLASS = """
w-full
h-11
px-4
bg-white
dark:bg-[#253240]
border
border-[#dce0e5]
dark:border-[#3e4c59]
rounded-lg
text-sm
text-[#111418]
dark:text-white
placeholder:text-gray-400
dark:placeholder:text-gray-500
outline-none
transition-all
duration-200
focus:border-blue-500
focus:ring-2
focus:ring-blue-500/20
"""

SELECT_CLASS = """
w-full
h-11
px-4
bg-white
dark:bg-[#253240]
border
border-[#dce0e5]
dark:border-[#3e4c59]
rounded-lg
text-sm
text-[#111418]
dark:text-white
outline-none
transition-all
duration-200
focus:border-blue-500
focus:ring-2
focus:ring-blue-500/20
"""

TEXTAREA_CLASS = """
w-full
px-4
py-3
bg-white
dark:bg-[#253240]
border
border-[#dce0e5]
dark:border-[#3e4c59]
rounded-lg
text-sm
text-[#111418]
dark:text-white
placeholder:text-gray-400
dark:placeholder:text-gray-500
outline-none
transition-all
duration-200
resize-y
focus:border-blue-500
focus:ring-2
focus:ring-blue-500/20
"""

CHECKBOX_CLASS = """
w-5
h-5
rounded
border
border-gray-300
dark:border-[#3e4c59]
text-blue-600
focus:ring-2
focus:ring-blue-500/30
cursor-pointer
"""


class PesertaForm(forms.ModelForm):
    """Form peserta operasional yang hanya dipakai Kader.

    ``status_peserta`` diberikan oleh view agar aturan Balita dan Ibu Hamil
    dapat divalidasi tanpa mempercayai input status dari browser.
    """

    def __init__(self, *args, posyandu_queryset=None, status_peserta=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.status_peserta = status_peserta or getattr(self.instance, "status_peserta", None)

        if posyandu_queryset is not None:
            self.fields["posko"].queryset = posyandu_queryset

        self.fields["tgl_lahir"].input_formats = ["%Y-%m-%d"]

        if self.status_peserta == "bumil":
            # Ibu hamil pada modul ini selalu peserta perempuan.
            self.fields["jenis_kelamin"].choices = [("Perempuan", "Perempuan")]
            self.fields["jenis_kelamin"].initial = "Perempuan"
            self.fields["jenis_kelamin"].required = True

    class Meta:
        model = Peserta
        fields = [
            "nama_peserta",
            "jenis_kelamin",
            "tgl_lahir",
            "alamat",
            "no_hp",
            "no_nik",
            "nama_ibu",
            "nama_ayah",
            "nik_ibu",
            "anak_ke",
            "bb_lahir",
            "tb_lahir",
            "lila_lahir",
            "posko",
            "is_tamu",
            "asal_posyandu",
        ]
        widgets = {
            "nama_peserta": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Nama Peserta"}),
            "jenis_kelamin": forms.Select(attrs={"class": SELECT_CLASS}),
            "no_nik": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "NIK Peserta (16 digit)", "inputmode": "numeric", "maxlength": "16"}),
            "tgl_lahir": forms.DateInput(attrs={"type": "date", "class": INPUT_CLASS}, format="%Y-%m-%d"),
            "alamat": forms.Textarea(attrs={"class": TEXTAREA_CLASS, "rows": 3, "placeholder": "Alamat lengkap"}),
            "no_hp": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Nomor HP, contoh 081234567890", "inputmode": "tel"}),
            "nama_ibu": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Nama Ibu"}),
            "nama_ayah": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Nama Suami atau Ayah"}),
            "nik_ibu": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "NIK Ibu (16 digit)", "inputmode": "numeric", "maxlength": "16"}),
            "anak_ke": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1, "placeholder": "Anak Ke"}),
            "bb_lahir": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "placeholder": "Contoh: 3.20"}),
            "tb_lahir": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "placeholder": "Contoh: 49.50"}),
            "lila_lahir": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "placeholder": "Contoh: 11.50"}),
            "asal_posyandu": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Contoh: Posyandu Mawar"}),
            "is_tamu": forms.CheckboxInput(attrs={"class": CHECKBOX_CLASS}),
            "posko": forms.Select(attrs={"class": SELECT_CLASS}),
        }

    def clean_no_hp(self):
        value = (self.cleaned_data.get("no_hp") or "").strip().replace(" ", "").replace("-", "")
        if not re.fullmatch(r"\+?\d{8,15}", value):
            raise forms.ValidationError("Nomor HP harus berupa 8–15 digit dan boleh diawali tanda +.")
        return value

    def _clean_nik(self, field_name, *, unique=False):
        value = (self.cleaned_data.get(field_name) or "").strip()
        if not value:
            return None
        if not value.isdigit() or len(value) != 16:
            raise forms.ValidationError("NIK harus terdiri dari tepat 16 digit angka.")
        if unique:
            qs = Peserta.objects.filter(no_nik=value)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("NIK tersebut sudah terdaftar sebagai peserta.")
        return value

    def clean_no_nik(self):
        return self._clean_nik("no_nik", unique=True)

    def clean_nik_ibu(self):
        return self._clean_nik("nik_ibu")

    def clean_tgl_lahir(self):
        value = self.cleaned_data.get("tgl_lahir")
        if value and value > date.today():
            raise forms.ValidationError("Tanggal lahir tidak boleh melebihi tanggal hari ini.")

        if value and self.status_peserta == "balita":
            umur = relativedelta(date.today(), value)
            total_bulan = umur.years * 12 + umur.months
            if total_bulan >= 60:
                raise forms.ValidationError("Peserta Balita harus berusia kurang dari 60 bulan.")
        return value

    def clean_bb_lahir(self):
        bb = self.cleaned_data.get("bb_lahir")
        if bb is not None and (bb < 0.5 or bb > 8):
            raise forms.ValidationError("Berat badan lahir tidak valid.")
        return bb

    def clean_tb_lahir(self):
        tb = self.cleaned_data.get("tb_lahir")
        if tb is not None and (tb < 20 or tb > 70):
            raise forms.ValidationError("Panjang badan lahir tidak valid.")
        return tb

    def clean_lila_lahir(self):
        lila = self.cleaned_data.get("lila_lahir")
        if lila is not None and (lila < 5 or lila > 30):
            raise forms.ValidationError("Lingkar lengan lahir harus antara 5–30 cm.")
        return lila

    def clean(self):
        cleaned_data = super().clean()
        is_tamu = cleaned_data.get("is_tamu")
        posko = cleaned_data.get("posko")
        asal = (cleaned_data.get("asal_posyandu") or "").strip()

        # Posko selalu berarti lokasi pelayanan/pencatatan peserta. Peserta tamu
        # tetap harus menempel pada Posyandu tempat ia dilayani agar dapat muncul
        # pada daftar Kader dan dapat dibuatkan pemeriksaan.
        if not posko:
            self.add_error("posko", "Posyandu tempat pelayanan wajib dipilih.")

        if is_tamu and not asal:
            self.add_error("asal_posyandu", "Peserta tamu wajib mengisi asal Posyandu.")
        if not is_tamu:
            cleaned_data["asal_posyandu"] = None

        if self.status_peserta == "bumil":
            cleaned_data["jenis_kelamin"] = "Perempuan"

        return cleaned_data
