from django import forms

from common.forms import IndonesianValidationMixin
from .models import (
    PemeriksaanBalita,
    PemeriksaanBumil,
)


# =========================================================
# PEMERIKSAAN IBU HAMIL
# =========================================================
class PemeriksaanBumilForm(IndonesianValidationMixin, forms.ModelForm):

    def __init__(self, *args, jadwal=None, **kwargs):
        # ``jadwal`` tetap diterima agar kompatibel dengan view, tetapi Bidan
        # tidak pernah berasal dari input form. Nilainya ditentukan otomatis
        # oleh backend berdasarkan cakupan Posyandu.
        super().__init__(*args, **kwargs)
        self.jadwal = jadwal

    class Meta:
        model = PemeriksaanBumil

        exclude = [
            'peserta',
            'petugas',
            'jadwal',
            'tgl_pemeriksaan',
            'bidan_pelaksana',
        ]

        widgets = {


            'usia_kehamilan': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Usia kehamilan'
            }),

            'berat_badan': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Berat badan',
                'step': '0.1',
                'min': '0',
            }),

            'tinggi_badan': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Tinggi badan',
                'step': '0.1',
                'min': '0',
            }),

            'lila_bumil': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'LILA',
                'step': '0.1',
                'min': '0',
            }),

            'tekanan_darah': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '120/80'
            }),

            'tinggi_fundus': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'TFU',
                'step': '0.1',
                'min': '0',
            }),

            'denyut_jantung_janin': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'DJJ',
                'min': '0',
            }),

            'hemoglobin': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'HB',
                'step': '0.1',
                'min': '0',
            }),

            'status_kehamilan': forms.Select(attrs={
                'class': 'form-select'
            }),

            'keluhan': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3
            }),

            'catatan': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3
            }),

            'perlu_rujukan': forms.CheckboxInput(attrs={
                'class': 'form-checkbox'
            }),

            'tujuan_rujukan': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Tujuan rujukan'
            }),
        }


# =========================================================
# PEMERIKSAAN BALITA
# =========================================================
class PemeriksaanBalitaForm(IndonesianValidationMixin, forms.ModelForm):

    # =====================================================
    # VITAMIN A
    # =====================================================

    vitamin_a = forms.BooleanField(
        required=False,
        label="Pemberian Vitamin A",
        widget=forms.CheckboxInput(
            attrs={
                "id": "id_vitamin_a",
                "class": "form-checkbox",
            }
        )
    )


    catatan_vitamin_a = forms.CharField(
        required=False,
        label="Catatan Vitamin A",
        widget=forms.Textarea(
            attrs={
                "class": "form-textarea",
                "rows": 2,
                "placeholder":
                    "Catatan Vitamin A (opsional)",
            }
        )
    )


    # =====================================================
    # OBAT CACING
    # =====================================================

    obat_cacing = forms.BooleanField(
        required=False,
        label="Pemberian Obat Cacing",
        widget=forms.CheckboxInput(
            attrs={
                "id": "id_obat_cacing",
                "class": "form-checkbox",
            }
        )
    )


    catatan_obat_cacing = forms.CharField(
        required=False,
        label="Catatan Obat Cacing",
        widget=forms.Textarea(
            attrs={
                "class": "form-textarea",
                "rows": 2,
                "placeholder":
                    "Catatan obat cacing (opsional)",
            }
        )
    )


    # =====================================================
    # META
    # =====================================================

    class Meta:

        model = PemeriksaanBalita

        exclude = [
            "peserta",
            "petugas",
            "jadwal",
            "bidan_pelaksana",

            "tgl_pemeriksaan",
            "usia_bulan",
            "usia_hari",

            "z_score",
            "status_gizi",

            "hsl_prediksi",
            "prob_ml",
        ]


        widgets = {


            "berat_badan":
                forms.NumberInput(
                    attrs={
                        "class": "form-input",
                        "placeholder": "Berat badan",
                        "step": "0.01",
                        "min": "0",
                    }
                ),

            "tinggi_badan":
                forms.NumberInput(
                    attrs={
                        "class": "form-input",
                        "placeholder":
                            "Tinggi/Panjang badan",
                        "step": "0.1",
                        "min": "0",
                    }
                ),

            "jenis_pengukuran":
                forms.Select(
                    attrs={
                        "class": "form-select",
                    }
                ),

            "lila_balita":
                forms.NumberInput(
                    attrs={
                        "class": "form-input",
                        "placeholder": "LILA",
                        "step": "0.1",
                        "min": "0",
                    }
                ),

            "lingkar_kepala":
                forms.NumberInput(
                    attrs={
                        "class": "form-input",
                        "placeholder":
                            "Lingkar kepala",
                        "step": "0.1",
                        "min": "0",
                    }
                ),

            "catatan":
                forms.Textarea(
                    attrs={
                        "class": "form-textarea",
                        "rows": 3,
                        "placeholder":
                            "Catatan pemeriksaan",
                    }
                ),
        }


    # =====================================================
    # INIT
    # =====================================================

    def __init__(
        self,
        *args,
        peserta=None,
        jadwal=None,
        **kwargs
    ):

        super().__init__(
            *args,
            **kwargs
        )


        self.peserta = peserta
        self.jadwal = jadwal

        # WHO membedakan panjang badan terlentang dan tinggi badan berdiri.
        # Posisi pengukuran harus disimpan karena WHO melakukan koreksi 0,7 cm
        # bila metode yang digunakan tidak sesuai kelompok usia (<731 / >=731 hari).
        if "jenis_pengukuran" in self.fields:
            self.fields["jenis_pengukuran"].label = "Posisi Pengukuran"
            self.fields["jenis_pengukuran"].help_text = (
                "Pilih sesuai posisi saat anak benar-benar diukur agar perhitungan "
                "Z-score WHO tidak berbeda karena koreksi panjang/tinggi 0,7 cm."
            )

        if peserta is not None and jadwal is not None and getattr(peserta, "tgl_lahir", None):
            umur_hari = (jadwal.tgl_kegiatan - peserta.tgl_lahir).days
            rekomendasi_jenis = "panjang" if umur_hari < 731 else "tinggi"

            # Pada input baru, pilih otomatis metode standar sesuai umur. Saat edit,
            # nilai yang sudah tersimpan tetap dipertahankan. Pada POST, pilihan
            # pengguna tidak ditimpa.
            if (
                not self.is_bound
                and not (self.instance.pk and getattr(self.instance, "jenis_pengukuran", None))
            ):
                self.fields["jenis_pengukuran"].initial = rekomendasi_jenis

            if umur_hari < 731:
                self.fields["tinggi_badan"].label = "Panjang / Tinggi Badan"
                self.fields["tinggi_badan"].widget.attrs["placeholder"] = "Panjang atau tinggi badan"
                self.fields["tinggi_badan"].help_text = (
                    "Standar WHO usia <24 bulan menggunakan panjang badan terlentang. "
                    "Jika anak diukur berdiri, sistem otomatis menambahkan 0,7 cm untuk perhitungan Z-score."
                )
            else:
                self.fields["tinggi_badan"].label = "Panjang / Tinggi Badan"
                self.fields["tinggi_badan"].widget.attrs["placeholder"] = "Tinggi atau panjang badan"
                self.fields["tinggi_badan"].help_text = (
                    "Standar WHO usia >=24 bulan menggunakan tinggi badan berdiri. "
                    "Jika anak diukur terlentang, sistem otomatis mengurangi 0,7 cm untuk perhitungan Z-score."
                )

        self.pelayanan_status = None


        if (
            peserta is None
            or jadwal is None
        ):
            return


        from .helper.pelayanan_balita import (
            get_status_pelayanan_balita
        )


        self.pelayanan_status = (
            get_status_pelayanan_balita(
                peserta=peserta,
                jadwal=jadwal,
                pemeriksaan=self.instance if self.instance.pk else None,
            )
        )


        status = self.pelayanan_status

        if self.instance.pk:
            pelayanan_map = {
                item.jenis_layanan: item
                for item in self.instance.pelayanan_balita.all()
            }
            vitamin = pelayanan_map.get("vitamin_a")
            obat = pelayanan_map.get("obat_cacing")
            if vitamin:
                self.fields["vitamin_a"].initial = True
                self.fields["catatan_vitamin_a"].initial = vitamin.catatan or ""
            if obat:
                self.fields["obat_cacing"].initial = True
                self.fields["catatan_obat_cacing"].initial = obat.catatan or ""


        # =================================================
        # VITAMIN A
        # =================================================

        if not status["vitamin_a_boleh"]:

            self.fields[
                "vitamin_a"
            ].disabled = True

            self.fields[
                "catatan_vitamin_a"
            ].disabled = True


        # =================================================
        # OBAT CACING
        # =================================================

        if not status["obat_cacing_boleh"]:

            self.fields[
                "obat_cacing"
            ].disabled = True

            self.fields[
                "catatan_obat_cacing"
            ].disabled = True


    # =====================================================
    # VALIDASI
    # =====================================================

    def clean(self):

        cleaned_data = super().clean()

        status = self.pelayanan_status


        if status is None:
            return cleaned_data


        # =================================================
        # VITAMIN A
        # =================================================

        if cleaned_data.get(
            "vitamin_a"
        ):

            if not status[
                "vitamin_a_boleh"
            ]:

                self.add_error(
                    "vitamin_a",
                    (
                        status[
                            "vitamin_a_alasan"
                        ]
                        or
                        "Vitamin A tidak dapat diberikan."
                    )
                )


        # =================================================
        # OBAT CACING
        # =================================================

        if cleaned_data.get(
            "obat_cacing"
        ):

            if not status[
                "obat_cacing_boleh"
            ]:

                self.add_error(
                    "obat_cacing",
                    (
                        status[
                            "obat_cacing_alasan"
                        ]
                        or
                        "Obat cacing tidak dapat diberikan."
                    )
                )


        return cleaned_data
