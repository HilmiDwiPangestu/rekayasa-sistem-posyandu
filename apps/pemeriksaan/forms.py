from django import forms

from .models import (
    PemeriksaanBalita,
    PemeriksaanBumil,
)


# =========================================================
# PEMERIKSAAN IBU HAMIL
# =========================================================
class PemeriksaanBumilForm(forms.ModelForm):

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
class PemeriksaanBalitaForm(forms.ModelForm):

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

        # Label pengukuran mengikuti referensi WHO daily: sebelum Day 731
        # menggunakan panjang badan terlentang, mulai Day 731 menggunakan
        # tinggi badan berdiri. Nilai ini hanya memandu Kader; lookup WHO
        # tetap ditentukan backend dari tanggal lahir dan tanggal pelayanan.
        if peserta is not None and jadwal is not None and getattr(peserta, "tgl_lahir", None):
            umur_hari = (jadwal.tgl_kegiatan - peserta.tgl_lahir).days
            if umur_hari < 731:
                self.fields["tinggi_badan"].label = "Panjang Badan (terlentang)"
                self.fields["tinggi_badan"].widget.attrs["placeholder"] = "Panjang badan terlentang"
                self.fields["tinggi_badan"].help_text = "Ukur panjang badan dalam posisi terlentang."
            else:
                self.fields["tinggi_badan"].label = "Tinggi Badan (berdiri)"
                self.fields["tinggi_badan"].widget.attrs["placeholder"] = "Tinggi badan berdiri"
                self.fields["tinggi_badan"].help_text = "Ukur tinggi badan dalam posisi berdiri."

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
