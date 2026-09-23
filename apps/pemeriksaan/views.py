from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.urls import reverse
from django.core.paginator import Paginator
from datetime import date
from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
import json
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from common.decorators import kader_required
from common.access import active_posyandu_ids

from .helper.pelayanan_balita import simpan_pelayanan_balita



from apps.deteksi.services.who_services import (
    hitung_status_antropometri,
)

from apps.deteksi.services.random_forest import (
    prediksi_stunting_rf,
)

# MODELS
from apps.posyandu.models import JadwalKegiatan
from apps.pemeriksaan.models import PemeriksaanBalita, PemeriksaanBumil, Imunisasi
from apps.peserta.models import Peserta
from apps.peserta.services import filter_peserta
from apps.posyandu.services import bidan_for_posyandu_queryset

# FORMS
from apps.pemeriksaan.forms import PemeriksaanBalitaForm, PemeriksaanBumilForm
from apps.pemeriksaan.services import (
    build_kms_payload,
    format_probabilitas_stunting,
    hitung_kesesuaian,
    z_score_valid as is_z_score_valid,
)

# helper
from apps.pemeriksaan.helper.imunisasi import (
    get_dosis_otomatis,
    get_vaksin_rekomendasi_balita,
    get_vaksin_rekomendasi_bumil,
)

# MACHINE LEARNING




def _bertugas_di(petugas, posyandu_id):
    return posyandu_id in active_posyandu_ids(petugas)



@login_required
@kader_required
def list_jadwal_pemeriksaan(request, status_peserta):

    if status_peserta not in {"balita", "bumil"}:
        return render(request, "403.html", status=403)

    petugas = getattr(request.user, "petugas", None)
    if not petugas:
        return render(request, "403.html")

    # ✅ FIX 1 — Baca status_filter dari query param
    status_filter = request.GET.get('status', 'mendatang')
    today = timezone.localdate()

    posyandu_ids = active_posyandu_ids(petugas)

    # Subquery annotate — hindari N+1 di loop
    has_balita = PemeriksaanBalita.objects.filter(jadwal_id=OuterRef('pk'))
    has_bumil = PemeriksaanBumil.objects.filter(jadwal_id=OuterRef('pk'))

    base_qs = JadwalKegiatan.objects.filter(
        posyandu_id__in=posyandu_ids,
        jns_kegiatan="Pemeriksaan Rutin"
    ).select_related("posyandu").annotate(
        ada_balita=Exists(has_balita),
        ada_bumil=Exists(has_bumil),
    )

    search = request.GET.get("search", "").strip()
    if search:
        base_qs = base_qs.filter(
            Q(posyandu__nama__icontains=search)
            | Q(jns_kegiatan__icontains=search)
        )

    # Terapkan filter tanggal sesuai status_filter
    if status_filter == 'riwayat':
        jadwal = base_qs.filter(tgl_kegiatan__lt=today).order_by('-tgl_kegiatan')
    else:
        jadwal = base_qs.filter(tgl_kegiatan__gte=today).order_by('tgl_kegiatan')

    paginator = Paginator(jadwal, 5)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Loop ringan — tidak ada query DB
    for j in page_obj:
        has_data = j.ada_balita or j.ada_bumil
        if has_data:
            j.status_pelaksanaan = "selesai"
        elif j.tgl_kegiatan < today:
            j.status_pelaksanaan = "kosong"
        else:
            j.status_pelaksanaan = "belum"

    return render(request, "pemeriksaan/list.html", {
        "page_obj": page_obj,
        "status_peserta": status_peserta,
        "status_filter": status_filter,  # ✅ FIX 3 — Kirim ke template
    })

@login_required
@kader_required
def list_peserta(request, status_peserta, id_jadwal):

    petugas = getattr(request.user, "petugas", None)
    
    if not petugas:
        return render(request, "403.html")

    if status_peserta not in ["balita", "bumil"]:
        return render(request, "403.html")

    if petugas.level != "kader":
        return render(request, "403.html", status=403)

    jadwal = get_object_or_404(JadwalKegiatan, id_jadwal=id_jadwal)

    if not _bertugas_di(petugas, jadwal.posyandu_id):
        return render(request, "403.html", status=403)

    peserta_queryset = filter_peserta(
        Peserta.objects.filter(posko=jadwal.posyandu),
        status_peserta=status_peserta,
        search=request.GET.get("search", ""),
        gender=request.GET.get("gender", ""),
        age=request.GET.get("age", ""),
    )
    search = request.GET.get("search", "").strip()

    jenis_kegiatan = jadwal.jns_kegiatan
    pemeriksaan_ids = set()
    imunisasi_map = {}
    pemeriksaan_map = {}   # ← selalu init di sini
    vaksin_choices = []

    if jenis_kegiatan == "Imunisasi":
        imunisasi_qs = Imunisasi.objects.filter(
            jadwal=jadwal,
            peserta__status_peserta=status_peserta
        ).select_related("peserta")

        for imun in imunisasi_qs:
            if imun.peserta_id not in imunisasi_map:
                imunisasi_map[imun.peserta_id] = []
            imunisasi_map[imun.peserta_id].append(imun.jenis_vaksin)

        pemeriksaan_ids = set(imunisasi_map.keys())
        vaksin_choices = (
            Imunisasi.VAKSIN_BALITA if status_peserta == "balita"
            else Imunisasi.VAKSIN_BUMIL
        )

    else:
        PemeriksaanModel = {
            "balita": PemeriksaanBalita,
            "bumil": PemeriksaanBumil,
        }.get(status_peserta)

        pemeriksaan_qs = PemeriksaanModel.objects.filter(jadwal=jadwal)
        pemeriksaan_map = {p.peserta_id: p for p in pemeriksaan_qs}
        pemeriksaan_ids = set(pemeriksaan_map.keys())

    paginator = Paginator(peserta_queryset, 5)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    
    # Attach data pemeriksaan ke peserta pada halaman aktif.
    periksa_list = {}
    for p in page_obj:
        p.sudah = p.id in pemeriksaan_ids
        p.vaksin_sudah = set(imunisasi_map.get(p.id, []))
        p.data_periksa = pemeriksaan_map.get(p.id, None)

        if p.data_periksa:
            dp = p.data_periksa
            base = {
                "nama": p.nama_peserta,
                "gender": str(p.jenis_kelamin),
                "usia": str(p.usia),
                "tgl": dp.tgl_pemeriksaan.strftime("%d %b %Y"),
                "petugas": dp.petugas_nama,
                "bidan_pelaksana": dp.bidan_pelaksana.nama if dp.bidan_pelaksana else "-",
                "catatan": dp.catatan or "",
            }
            
            if status_peserta == "balita":
                

                base.update({
                    "berat":          float(dp.berat_badan)    if dp.berat_badan    is not None else None,
                    "tinggi":         float(dp.tinggi_badan)   if dp.tinggi_badan   is not None else None,
                    "lila":           float(dp.lila_balita)    if dp.lila_balita    is not None else None,
                    "lingkar_kepala": float(dp.lingkar_kepala) if dp.lingkar_kepala is not None else None,
                    "z_score":        float(dp.z_score)        if dp.z_score        is not None else None,
                    "status_gizi":    dp.status_gizi           or "normal",
                    "hsl_prediksi":   dp.hsl_prediksi          or "",
                    "prob_ml":        float(dp.prob_ml)        if dp.prob_ml        is not None else None,
                    # KMS lengkap: BB/U, PB/TB/U, dan IMT/U
                    "kms_chart_data": build_kms_payload(p),
                    "kms_url": reverse("laporan:laporan_kms", args=[p.id]),
                })
            else:
                base.update({
                    "usia_kehamilan": dp.usia_kehamilan,
                    "berat": float(dp.berat_badan) if dp.berat_badan is not None else None,
                    "tinggi": float(dp.tinggi_badan) if dp.tinggi_badan is not None else None,
                    "lila": float(dp.lila_bumil) if dp.lila_bumil is not None else None,
                    "tekanan_darah": dp.tekanan_darah or "",
                    "tinggi_fundus": float(dp.tinggi_fundus) if dp.tinggi_fundus is not None else None,
                    "djj": dp.denyut_jantung_janin,
                    "hemoglobin": float(dp.hemoglobin) if dp.hemoglobin is not None else None,
                    "status_kehamilan": dp.status_kehamilan or "normal",
                    "perlu_rujukan": dp.perlu_rujukan,
                    "tujuan_rujukan": dp.tujuan_rujukan or "",
                    "keluhan": dp.keluhan or "",
                })
            periksa_list[str(dp.id_periksa)] = base
            
    imunisasi_list = {}
    if jenis_kegiatan == "Imunisasi":
        imunisasi_qs = Imunisasi.objects.filter(jadwal=jadwal, peserta__status_peserta=status_peserta).select_related("peserta","petugas")

        for imun in imunisasi_qs:

            id_imun = str(imun.peserta_id)

            if id_imun not in imunisasi_list:

                imunisasi_list[id_imun] = {
                    "nama": imun.peserta.nama_peserta,
                    "tgl": imun.tgl_pemberian.strftime("%d %b %Y"),
                    "petugas": str(imun.petugas),
                    "vaksin": []
                }

            imunisasi_list[id_imun]["vaksin"].append({
                "nama": imun.jenis_vaksin,
                "dosis": imun.dosis,
                "keterangan": imun.catatan or ""
            })

    return render(request, 'pemeriksaan/list_peserta.html', {
        'page_obj': page_obj,
        'jadwal': jadwal,
        'status_peserta': status_peserta,
        'search': search,
        'pemeriksaan_ids': pemeriksaan_ids,
        'jenis_kegiatan': jenis_kegiatan,
        'vaksin_choices': vaksin_choices,
        'periksa_json': json.dumps(periksa_list, ensure_ascii=False),  # ← tambah ini
        'imunisasi_json': json.dumps(imunisasi_list, ensure_ascii=False),  # <-- TAMBAH
    })


# ============================================================
# FORM PEMERIKSAAN PESERTA
# ============================================================

@login_required
@kader_required
def periksa_peserta(
    request,
    status_peserta,
    id_jadwal,
    id_peserta,
    id_periksa=None,
):

    # ========================================================
    # PETUGAS
    # ========================================================

    petugas = getattr(
        request.user,
        "petugas",
        None
    )

    if not petugas:
        return render(
            request,
            "403.html"
        )


    # ========================================================
    # KONFIGURASI
    # ========================================================

    CONFIG = {

        "balita": {
            "roles": {"kader"},
            "model": PemeriksaanBalita,
            "form": PemeriksaanBalitaForm,
            "template": "pemeriksaan/form_balita.html",
        },

        "bumil": {
            "roles": {"kader"},
            "model": PemeriksaanBumil,
            "form": PemeriksaanBumilForm,
            "template": "pemeriksaan/form_bumil.html",
        },

    }


    # ========================================================
    # VALIDASI STATUS PESERTA
    # ========================================================

    if status_peserta not in CONFIG:
        return render(
            request,
            "403.html"
        )


    config = CONFIG[
        status_peserta
    ]


    # ========================================================
    # VALIDASI ROLE
    # ========================================================

    if petugas.level not in config["roles"]:
        return render(
            request,
            "403.html"
        )


    # ========================================================
    # JADWAL
    # ========================================================

    jadwal = get_object_or_404(
        JadwalKegiatan,
        id_jadwal=id_jadwal
    )


    # ========================================================
    # PESERTA
    # ========================================================

    peserta = get_object_or_404(
        Peserta,
        id=id_peserta,
        status_peserta=status_peserta,
        posko=jadwal.posyandu,
    )


    # ========================================================
    # VALIDASI PENUGASAN PETUGAS
    # ========================================================

    if not _bertugas_di(petugas, jadwal.posyandu_id):
        return render(
            request,
            "403.html"
        )


    # ========================================================
    # BIDAN OTOMATIS PEMERIKSAAN BALITA & BUMIL
    # ========================================================
    # Kader tidak memilih Bidan dari form. Bidan ditentukan dari master
    # cakupan wilayah Posyandu yang dikelola Admin Kelurahan. Cakupan Bidan
    # pada sistem dibuat tidak tumpang tindih, sehingga satu Posyandu memiliki
    # satu Bidan aktif yang menjadi pendamping pelayanan.
    bidan_otomatis = None
    if jadwal.jns_kegiatan != "Imunisasi":
        bidan_otomatis = bidan_for_posyandu_queryset(jadwal.posyandu).first()


    # ========================================================
    # ROUTING IMUNISASI
    # ========================================================

    if jadwal.jns_kegiatan == "Imunisasi":

        return _handle_imunisasi(
            request,
            petugas,
            jadwal,
            peserta,
            status_peserta
        )


    # ========================================================
    # MODEL & FORM
    # ========================================================

    PemeriksaanModel = config[
        "model"
    ]

    FormClass = config[
        "form"
    ]

    if id_periksa is not None:
        # Mode edit: ambil record pemeriksaan yang dipilih secara eksplisit.
        # Filter peserta + jadwal mencegah kader mengedit pemeriksaan di luar
        # peserta/jadwal yang sedang dibuka.
        pemeriksaan_tersimpan = get_object_or_404(
            PemeriksaanModel,
            id_periksa=id_periksa,
            peserta=peserta,
            jadwal=jadwal,
        )
    else:
        pemeriksaan_tersimpan = PemeriksaanModel.objects.filter(
            peserta=peserta,
            jadwal=jadwal,
        ).order_by("-tgl_pemeriksaan").first()

    is_edit = id_periksa is not None


    # ========================================================
    # PAYLOAD KMS LENGKAP
    # ========================================================
    kms_chart_data = (
        build_kms_payload(peserta)
        if status_peserta == "balita"
        else {}
    )

    # ========================================================
    # CONTEXT FORM
    # ========================================================

    def get_context(form):

        return {

            "form": form,

            "jadwal": jadwal,

            "peserta": peserta,

            "status_peserta":
                status_peserta,

            "is_edit": is_edit,
            "pemeriksaan": pemeriksaan_tersimpan,

            # Bidan pemeriksaan Balita dan Bumil ditentukan otomatis dari
            # cakupan Posyandu; hanya ditampilkan sebagai informasi di form.
            "bidan_otomatis": bidan_otomatis,

            "kms_chart_data": kms_chart_data,

            # ================================================
            # STATUS VITAMIN A + OBAT CACING
            # ================================================
            "pelayanan_status": getattr(
                form,
                "pelayanan_status",
                None
            ),

        }


    # ========================================================
    # POST
    # ========================================================

    if request.method == "POST":

        # ====================================================
        # FORM BALITA MEMBUTUHKAN PESERTA + JADWAL
        # untuk menentukan:
        #
        # Vitamin A
        # - 6-11 bulan   = Biru 100.000 SI
        # - 12-59 bulan  = Merah 200.000 SI
        #
        # Obat Cacing
        # - 12-23 bulan  = Albendazole 200 mg
        # - 24-59 bulan  = Albendazole 400 mg
        #
        # serta cek periode Februari / Agustus.
        # ====================================================

        if status_peserta == "balita":

            form = FormClass(
                request.POST,
                peserta=peserta,
                jadwal=jadwal,
                instance=pemeriksaan_tersimpan,
            )

        else:

            form = FormClass(
                request.POST,
                instance=pemeriksaan_tersimpan,
                jadwal=jadwal,
            )


        # ====================================================
        # FORM VALID
        # ====================================================

        if form.is_valid():

            pemeriksaan = form.save(
                commit=False
            )


            # =================================================
            # RELASI
            # =================================================

            pemeriksaan.peserta = peserta
            pemeriksaan.petugas = petugas
            pemeriksaan.jadwal = jadwal

            # Pemeriksaan Balita maupun Bumil wajib memakai Bidan yang
            # ditentukan otomatis dari cakupan Posyandu. Nilai dari browser
            # tidak pernah dipercaya/digunakan.
            if bidan_otomatis is None:
                messages.error(
                    request,
                    (
                        f"Belum ada Bidan aktif yang mencakup {jadwal.posyandu.nama}. "
                        "Minta Admin Kelurahan mengatur cakupan wilayah Bidan terlebih dahulu."
                    ),
                )
                return render(
                    request,
                    config["template"],
                    get_context(form),
                )

            pemeriksaan.bidan_pelaksana = bidan_otomatis


            # =================================================
            # TANGGAL PELAYANAN
            # =================================================
            # Seluruh perhitungan usia, WHO dan Random Forest harus
            # memakai tanggal pelayanan pada jadwal, bukan waktu Kader
            # memasukkan data ke sistem.
            tanggal_periksa = jadwal.tgl_kegiatan


            # =================================================
            # VALIDASI TANGGAL LAHIR
            # =================================================

            if not peserta.tgl_lahir:

                messages.error(
                    request,
                    (
                        "Tanggal lahir peserta belum tersedia. "
                        "Usia peserta tidak dapat dihitung."
                    )
                )

                return render(
                    request,
                    config["template"],
                    get_context(form)
                )


            if peserta.tgl_lahir > tanggal_periksa:

                messages.error(
                    request,
                    (
                        "Tanggal lahir peserta tidak valid "
                        "karena lebih besar dari tanggal "
                        "pemeriksaan."
                    )
                )

                return render(
                    request,
                    config["template"],
                    get_context(form)
                )


            # =================================================
            # HITUNG USIA
            # =================================================

            selisih = relativedelta(
                tanggal_periksa,
                peserta.tgl_lahir
            )


            usia_bulan = (
                selisih.years * 12
                + selisih.months
            )

            # Referensi WHO expanded yang digunakan project memakai usia
            # eksak dalam hari, sedangkan Random Forest tetap usia bulan.
            usia_hari = (
                tanggal_periksa - peserta.tgl_lahir
            ).days


            # =================================================
            # KHUSUS BALITA
            # =================================================

            if status_peserta == "balita":

                pemeriksaan.usia_bulan = usia_bulan
                pemeriksaan.usia_hari = usia_hari


                try:

                    # =========================================
                    # VALIDASI USIA BALITA
                    # =========================================

                    if not (
                        0 <= usia_bulan <= 59
                    ):

                        raise ValueError(
                            (
                                "Usia peserta berada di luar "
                                "rentang balita 0-59 bulan."
                            )
                        )

                    if not (0 <= usia_hari <= 1856):
                        raise ValueError(
                            "Usia peserta berada di luar rentang referensi WHO 0-1856 hari."
                        )


                    # =========================================
                    # ANTROPOMETRI
                    # =========================================

                    if pemeriksaan.berat_badan is None:

                        raise ValueError(
                            "Berat badan wajib diisi."
                        )


                    if pemeriksaan.tinggi_badan is None:

                        raise ValueError(
                            (
                                "Panjang/tinggi badan "
                                "wajib diisi."
                            )
                        )


                    berat_badan = float(
                        pemeriksaan.berat_badan
                    )


                    tinggi_badan = float(
                        pemeriksaan.tinggi_badan
                    )


                    # =========================================
                    # VALIDASI INPUT
                    # =========================================

                    if berat_badan <= 0:

                        raise ValueError(
                            (
                                "Berat badan harus "
                                "lebih besar dari 0 kg."
                            )
                        )


                    if tinggi_badan <= 0:

                        raise ValueError(
                            (
                                "Panjang/tinggi badan harus "
                                "lebih besar dari 0 cm."
                            )
                        )


                    # =========================================
                    # A. WHO / GROUND TRUTH
                    # =========================================

                    hasil_who = (
                        hitung_status_antropometri(

                            umur_hari=usia_hari,

                            jk=(
                                peserta.jenis_kelamin
                            ),

                            tinggi_badan=(
                                tinggi_badan
                            ),
                        )
                    )


                    # =========================================
                    # Z-SCORE
                    # =========================================

                    z_score = hasil_who.get(
                        "z_score"
                    )


                    if z_score is None:

                        raise ValueError(
                            (
                                "Z-score PB/U atau TB/U "
                                "tidak dapat dihitung. "
                                "Pastikan referensi WHO "
                                "untuk usia dan jenis kelamin "
                                "peserta tersedia."
                            )
                        )


                    z_score = float(
                        z_score
                    )


                    # =========================================
                    # BIOLOGICAL PLAUSIBILITY
                    # =========================================

                    if not is_z_score_valid(
                        z_score
                    ):

                        raise ValueError(
                            (
                                "Data panjang/tinggi badan "
                                "tidak wajar untuk usia dan "
                                "jenis kelamin balita. "
                                f"Nilai Z-score = {z_score:.2f}. "
                                "Silakan periksa kembali usia, "
                                "panjang/tinggi badan, dan "
                                "hasil pengukuran sebelum "
                                "menyimpan pemeriksaan."
                            )
                        )


                    # =========================================
                    # SIMPAN Z-SCORE
                    # =========================================

                    pemeriksaan.z_score = round(
                        z_score,
                        4
                    )


                    # =========================================
                    # STATUS ANTROPOMETRI
                    # =========================================
                    # Gunakan hasil kategori dari service WHO agar aturan
                    # Sangat Pendek/Pendek/Normal/Tinggi tidak diduplikasi
                    # dan nilai Z-score positif > +3 tersimpan sebagai Tinggi.
                    pemeriksaan.status_gizi = hasil_who.get("kode")
                    if pemeriksaan.status_gizi not in {
                        "stunting_berat", "stunting", "normal", "tinggi"
                    }:
                        raise ValueError("Kategori antropometri WHO tidak dikenali.")


                    # =========================================
                    # B. RANDOM FOREST
                    # =========================================

                    hasil_rf = (
                        prediksi_stunting_rf(

                            gender=(
                                peserta.jenis_kelamin
                            ),

                            age_month=(
                                usia_bulan
                            ),

                            weight_kg=(
                                berat_badan
                            ),

                            height_cm=(
                                tinggi_badan
                            ),
                        )
                    )


                    # =========================================
                    # LABEL RANDOM FOREST
                    # =========================================

                    rf_label = hasil_rf.get(
                        "label"
                    )


                    if rf_label == 1:

                        pemeriksaan.hsl_prediksi = (
                            "Stunting"
                        )


                    elif rf_label == 0:

                        pemeriksaan.hsl_prediksi = (
                            "Tidak Stunting"
                        )


                    else:

                        raise ValueError(
                            (
                                "Model Random Forest "
                                "menghasilkan label yang "
                                "tidak dikenali."
                            )
                        )


                    # =========================================
                    # PROBABILITAS STUNTING
                    # =========================================

                    probability_stunted = (
                        hasil_rf.get(
                            "probability_stunted"
                        )
                    )


                    if probability_stunted is None:

                        raise ValueError(
                            (
                                "Model tidak menghasilkan "
                                "probabilitas kelas stunting."
                            )
                        )


                    probability_stunted = float(
                        probability_stunted
                    )


                    if not (
                        0
                        <= probability_stunted
                        <= 1
                    ):

                        raise ValueError(
                            (
                                "Probabilitas Random Forest "
                                "berada di luar rentang 0-1."
                            )
                        )


                    pemeriksaan.prob_ml = round(
                        probability_stunted * 100,
                        2
                    )


                # =============================================
                # VALIDASI INPUT / DATA
                # =============================================

                except ValueError as error:

                    messages.error(
                        request,
                        str(error)
                    )

                    return render(
                        request,
                        config["template"],
                        get_context(form)
                    )


                # =============================================
                # ERROR MODEL / SISTEM
                # =============================================

                except Exception as error:

                    messages.error(
                        request,
                        (
                            "Proses deteksi stunting gagal. "
                            f"Detail: {error}"
                        )
                    )

                    return render(
                        request,
                        config["template"],
                        get_context(form)
                    )


            # =================================================
            # SIMPAN PEMERIKSAAN + PELAYANAN
            # =================================================

            pelayanan_disimpan = []


            try:

                with transaction.atomic():

                    # =========================================
                    # SIMPAN PEMERIKSAAN
                    # =========================================

                    pemeriksaan.save()


                    # =========================================
                    # MANY TO MANY
                    # =========================================

                    if hasattr(
                        form,
                        "save_m2m"
                    ):
                        form.save_m2m()


                    # =========================================
                    # VITAMIN A + OBAT CACING
                    # =========================================

                    if status_peserta == "balita":

                        pelayanan_disimpan = (
                            simpan_pelayanan_balita(

                                pemeriksaan=pemeriksaan,

                                cleaned_data=(
                                    form.cleaned_data
                                ),
                            )
                        )


            # =================================================
            # VALIDATION ERROR PELAYANAN
            # =================================================

            except ValidationError as error:

                messages.error(
                    request,
                    " ".join(
                        error.messages
                    )
                )

                return render(
                    request,
                    config["template"],
                    get_context(form)
                )


            # =================================================
            # ERROR PENYIMPANAN
            # =================================================

            except Exception as error:

                messages.error(
                    request,
                    (
                        "Data pemeriksaan gagal disimpan. "
                        f"Detail: {error}"
                    )
                )

                return render(
                    request,
                    config["template"],
                    get_context(form)
                )


            # =================================================
            # SUCCESS
            # =================================================

            if status_peserta == "balita":

                pesan = (
                    ("Pemeriksaan berhasil diperbarui " if is_edit else "Pemeriksaan berhasil disimpan ")
                    + "dan deteksi stunting menggunakan "
                    + "Random Forest berhasil dilakukan."
                )


                # Tambahkan informasi pelayanan
                if pelayanan_disimpan:

                    pesan += (
                        " Pelayanan yang diberikan: "
                        + ", ".join(
                            pelayanan_disimpan
                        )
                        + "."
                    )


                messages.success(
                    request,
                    pesan
                )


            else:

                messages.success(
                    request,
                    "Pemeriksaan berhasil diperbarui." if is_edit else "Pemeriksaan berhasil disimpan."
                )


            # =================================================
            # REDIRECT
            # =================================================

            return redirect(
                "pemeriksaan:list_peserta",
                status_peserta,
                jadwal.id_jadwal
            )


    # ========================================================
    # GET
    # ========================================================

    else:

        # ====================================================
        # BALITA
        # ====================================================

        if status_peserta == "balita":

            form = FormClass(
                peserta=peserta,
                jadwal=jadwal,
                instance=pemeriksaan_tersimpan,
            )


        # ====================================================
        # BUMIL
        # ====================================================

        else:

            form = FormClass(
                instance=pemeriksaan_tersimpan,
                jadwal=jadwal,
            )


    # ========================================================
    # RENDER
    # ========================================================

    return render(
        request,
        config["template"],
        get_context(form)
    )
    



# ============================================================
# DETAIL HASIL DETEKSI STUNTING
# ============================================================

@login_required
@kader_required
def detail_deteksi_stunting(
    request,
    id_periksa
):

    # ========================================================
    # PEMERIKSAAN
    # ========================================================

    petugas = getattr(request.user, "petugas", None)
    pemeriksaan_qs = PemeriksaanBalita.objects.select_related(
        "peserta", "petugas", "jadwal",
    )
    if petugas and petugas.level != "admin":
        pemeriksaan_qs = pemeriksaan_qs.filter(
            jadwal__posyandu_id__in=active_posyandu_ids(petugas)
        )

    pemeriksaan = get_object_or_404(

        pemeriksaan_qs,

        id_periksa=id_periksa,

    )


    peserta = (
        pemeriksaan.peserta
    )


    # prob_ml disimpan langsung pada skala persen (0-100).
    probabilitas = (
        format_probabilitas_stunting(
            pemeriksaan.prob_ml
        )
    )


    # ========================================================
    # KESESUAIAN PEMERIKSAAN SAAT INI
    # ========================================================

    kesesuaian = (
        hitung_kesesuaian(

            z_score=(
                pemeriksaan.z_score
            ),

            status_gizi=(
                pemeriksaan.status_gizi
            ),

            hasil_prediksi=(
                pemeriksaan.hsl_prediksi
            ),

        )
    )


    # ========================================================
    # RIWAYAT PEMERIKSAAN
    # ========================================================

    riwayat_qs = (

        PemeriksaanBalita.objects
        .filter(
            peserta=peserta
        )
        .select_related(
            "petugas",
            "jadwal"
        )
        .order_by(
            "tgl_pemeriksaan"
        )

    )


    riwayat_pemeriksaan = []


    # ========================================================
    # LOOP RIWAYAT
    # ========================================================

    for item in riwayat_qs:

        # ====================================================
        # PROBABILITAS
        # ====================================================

        prob_item = (
            format_probabilitas_stunting(
                item.prob_ml
            )
        )


        # ====================================================
        # KESESUAIAN
        # ====================================================

        item_kesesuaian = (
            hitung_kesesuaian(

                z_score=(
                    item.z_score
                ),

                status_gizi=(
                    item.status_gizi
                ),

                hasil_prediksi=(
                    item.hsl_prediksi
                ),

            )
        )


        # ====================================================
        # VALIDITAS Z-SCORE
        # ====================================================

        item_z_valid = False


        if item.z_score is not None:

            try:

                item_z_valid = (
                    is_z_score_valid(
                        float(
                            item.z_score
                        )
                    )
                )

            except (
                TypeError,
                ValueError
            ):

                item_z_valid = False


        # ====================================================
        # RIWAYAT DATA
        # ====================================================

        riwayat_pemeriksaan.append({

            "id_periksa": (
                item.id_periksa
            ),


            "tanggal": (

                timezone.localtime(
                    item.tgl_pemeriksaan
                )
                .strftime(
                    "%d-%m-%Y"
                )

                if item.tgl_pemeriksaan

                else "-"

            ),


            "usia": (

                f"{item.usia_bulan} bulan"

                if (
                    item.usia_bulan
                    is not None
                )

                else "-"

            ),


            "berat": (
                item.berat_badan
            ),


            "tinggi": (
                item.tinggi_badan
            ),


            # ================================================
            # WHO
            # ================================================

            "z_score": (
                item.z_score
            ),


            "z_score_valid": (
                item_z_valid
            ),


            "status_gizi": (
                item.status_gizi
            ),


            "status_gizi_display": (

                item.get_status_gizi_display()

                if item.status_gizi

                else "-"

            ),


            # ================================================
            # RANDOM FOREST
            # ================================================

            "hasil_prediksi": (
                item.hsl_prediksi
            ),


            "probabilitas": (
                prob_item
            ),


            # ================================================
            # KESESUAIAN
            # ================================================

            "kesesuaian": (
                item_kesesuaian
            ),

        })


    # ========================================================
    # VALIDITAS DATA PEMERIKSAAN SEKARANG
    # ========================================================

    current_z_score_valid = False


    if pemeriksaan.z_score is not None:

        try:

            current_z_score_valid = (
                is_z_score_valid(
                    float(
                        pemeriksaan.z_score
                    )
                )
            )

        except (
            TypeError,
            ValueError
        ):

            current_z_score_valid = False


    # ========================================================
    # DETAIL DATA
    # ========================================================

    detail_data = {

        # ====================================================
        # ID
        # ====================================================

        "id_periksa": (
            pemeriksaan.id_periksa
        ),

        "kms_url": reverse(
            "laporan:laporan_kms",
            args=[peserta.id],
        ),


        # ====================================================
        # IDENTITAS PESERTA
        # ====================================================

        "nama": (
            peserta.nama_peserta
        ),


        "nik": getattr(
            peserta,
            "nik",
            None
        ),


        "gender": (
            peserta.jenis_kelamin
        ),


        "tanggal_lahir": (

            peserta.tgl_lahir.strftime(
                "%d-%m-%Y"
            )

            if getattr(
                peserta,
                "tgl_lahir",
                None
            )

            else None

        ),


        "nama_ibu": getattr(
            peserta,
            "nama_ibu",
            None
        ),


        "nama_ayah": getattr(
            peserta,
            "nama_ayah",
            None
        ),


        "anak_ke": getattr(
            peserta,
            "anak_ke",
            None
        ),


        # ====================================================
        # PEMERIKSAAN
        # ====================================================

        "tanggal_pemeriksaan": (

            timezone.localtime(
                pemeriksaan.tgl_pemeriksaan
            )
            .strftime(
                "%d-%m-%Y %H:%M"
            )

            if pemeriksaan.tgl_pemeriksaan

            else "-"

        ),


        "petugas": (
            pemeriksaan.petugas_nama
        ),

        "bidan_pelaksana": (
            pemeriksaan.bidan_pelaksana.nama
            if pemeriksaan.bidan_pelaksana
            else "-"
        ),


        "jadwal": str(
            pemeriksaan.jadwal
        ),


        "usia_bulan": (
            pemeriksaan.usia_bulan
        ),

        "usia_hari": (
            pemeriksaan.usia_hari
        ),


        "usia": (

            f"{pemeriksaan.usia_bulan} bulan"

            if (
                pemeriksaan.usia_bulan
                is not None
            )

            else "-"

        ),


        "berat": (
            pemeriksaan.berat_badan
        ),


        "tinggi": (
            pemeriksaan.tinggi_badan
        ),


        "lila": (
            pemeriksaan.lila_balita
        ),


        "lingkar_kepala": (
            pemeriksaan.lingkar_kepala
        ),


        # ====================================================
        # WHO
        # ====================================================

        "z_score": (
            pemeriksaan.z_score
        ),


        "z_score_valid": (
            current_z_score_valid
        ),


        "status_gizi": (
            pemeriksaan.status_gizi
        ),


        "status_gizi_display": (

            pemeriksaan
            .get_status_gizi_display()

            if pemeriksaan.status_gizi

            else "-"

        ),


        # ====================================================
        # RANDOM FOREST
        # ====================================================

        "hasil_prediksi": (
            pemeriksaan.hsl_prediksi
        ),


        "probabilitas": (
            probabilitas
        ),


        "nama_model": (
            "Random Forest"
        ),


        # ====================================================
        # KESESUAIAN
        # ====================================================

        "kesesuaian": (
            kesesuaian
        ),


        # ====================================================
        # CATATAN
        # ====================================================

        "catatan": (
            pemeriksaan.catatan
        ),


        # ====================================================
        # RIWAYAT
        # ====================================================

        "riwayat_pemeriksaan": (
            riwayat_pemeriksaan
        ),

    }


    # ========================================================
    # RENDER
    # ========================================================

    return render(

        request,

        "pemeriksaan/detail_stunting.html",

        {

            "pemeriksaan": (
                pemeriksaan
            ),

            "detail_data": (
                detail_data
            ),

        }

    )




# =====================
# BAGIAN IMUNISASI
# =====================
@login_required
@kader_required
def imunisasi_jadwal (request, status_peserta):
    if status_peserta not in {"balita", "bumil"}:
        return render(request, "403.html", status=403)
    
    petugas = getattr(request.user, "petugas", None)

    if not petugas:
        return render(request, "403.html")

    # ✅ FIX 1 — Baca status_filter dari query param
    status_filter = request.GET.get('status', 'mendatang')
    today = timezone.localdate()    

    # ambil semua penugasan petugas
    posyandu_ids = active_posyandu_ids(petugas)

    # Subquery annotate — hindari N+1 di loop
    has_imunisasi = Imunisasi.objects.filter(jadwal_id=OuterRef('pk'))

    base_qs = JadwalKegiatan.objects.filter(
        posyandu_id__in=posyandu_ids,
        jns_kegiatan="Imunisasi"
    ).select_related("posyandu").annotate(
        ada_imunisasi=Exists(has_imunisasi),
    )

    search = request.GET.get("search", "").strip()
    if search:
        base_qs = base_qs.filter(
            Q(posyandu__nama__icontains=search)
            | Q(jns_kegiatan__icontains=search)
        )

    # Terapkan filter tanggal sesuai status_filter
    if status_filter == 'riwayat':
        jadwal = base_qs.filter(tgl_kegiatan__lt=today).order_by('-tgl_kegiatan')
    else:
        jadwal = base_qs.filter(tgl_kegiatan__gte=today).order_by('tgl_kegiatan')

    # pagination
    paginator = Paginator(jadwal, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    # Taruh logika ini di dalam loop 'for j in page_obj:' pada fungsi views Anda
    today = timezone.localdate()
    for j in page_obj:
        # 1. Cek isi data pemeriksaan
        has_data = j.ada_imunisasi
        
        # 2. Tentukan status berdasarkan kombinasi data & tanggal
        if has_data:
            j.status_pelaksanaan = "selesai"
        elif not has_data and j.tgl_kegiatan < today:
            j.status_pelaksanaan = "kosong"  # Tanggal lewat tapi tidak ada pemeriksaan
        else:
            j.status_pelaksanaan = "belum"

    return render (request, 'pemeriksaan/imunisasi_list.html',{
        'page_obj':page_obj,
        'status_peserta':status_peserta,
        'status_filter':status_filter
    })




# =====================
# HELPER IMUNISASI
# =====================
def _handle_imunisasi(request, petugas, jadwal, peserta, status_peserta):

    bidan_choices = bidan_for_posyandu_queryset(jadwal.posyandu)

    vaksin_pada_jadwal = set(
        Imunisasi.objects.filter(
            jadwal=jadwal,
            peserta=peserta
        ).values_list(
            "jenis_vaksin",
            flat=True
        )
    )

    riwayat = Imunisasi.objects.filter(
        peserta=peserta
    ).order_by("-tgl_pemberian")

    if request.method == "POST":
        bidan_id = (request.POST.get("bidan_pelaksana") or "").strip()
        bidan_pelaksana = None
        if bidan_id:
            bidan_pelaksana = bidan_choices.filter(pk=bidan_id).first()
            if bidan_pelaksana is None:
                messages.error(request, "Bidan pelaksana tidak sesuai cakupan Posyandu.")
                return redirect(
                    "pemeriksaan:periksa_peserta",
                    status_peserta,
                    jadwal.id_jadwal,
                    peserta.id,
                )
        elif bidan_choices.exists():
            messages.error(request, "Pilih Bidan/tenaga kesehatan pelaksana imunisasi.")
            return redirect(
                "pemeriksaan:periksa_peserta",
                status_peserta,
                jadwal.id_jadwal,
                peserta.id,
            )

        vaksin_list = request.POST.getlist("jenis_vaksin")
        pilihan = dict(
            Imunisasi.VAKSIN_BALITA
            if status_peserta == "balita" else Imunisasi.VAKSIN_BUMIL
        )
        vaksin_list = list(dict.fromkeys(vaksin_list))
        vaksin_tidak_valid = [v for v in vaksin_list if v not in pilihan]
        if not vaksin_list or vaksin_tidak_valid:
            messages.error(request, "Pilih minimal satu jenis vaksin yang valid.")
            return redirect(
                "pemeriksaan:periksa_peserta",
                status_peserta,
                jadwal.id_jadwal,
                peserta.id,
            )

        usia_kehamilan = None
        if status_peserta == "bumil":
            try:
                usia_kehamilan = int(request.POST.get("usia_kehamilan", ""))
            except (TypeError, ValueError):
                usia_kehamilan = 0
            if not 1 <= usia_kehamilan <= 45:
                messages.error(request, "Usia kehamilan harus antara 1–45 minggu.")
                return redirect(
                    "pemeriksaan:periksa_peserta",
                    status_peserta,
                    jadwal.id_jadwal,
                    peserta.id,
                )

        berhasil = 0
        duplikat = 0

        for vaksin in vaksin_list:

            defaults = {
                "petugas": petugas,
                "bidan_pelaksana": bidan_pelaksana,
                "tgl_pemberian": jadwal.tgl_kegiatan,
                "dosis": get_dosis_otomatis(vaksin),
                "catatan": request.POST.get("catatan", ""),
            }

            if status_peserta == "balita":
                selisih = relativedelta(jadwal.tgl_kegiatan, peserta.tgl_lahir)
                defaults["usia_saat_vaksin"] = max(
                    0, selisih.years * 12 + selisih.months
                )
            else:
                defaults["usia_kehamilan"] = usia_kehamilan

            obj, created = Imunisasi.objects.get_or_create(
                peserta=peserta,
                # jadwal=jadwal,
                jenis_vaksin=vaksin,
                defaults={
                    **defaults,
                    "jadwal":jadwal,
                }
            )

            if created:
                berhasil += 1
            else:
                duplikat += 1

        if berhasil:
            messages.success(request, f"{berhasil} vaksin berhasil disimpan.")
        if duplikat:
            messages.warning(request, f"{duplikat} vaksin sudah pernah diberikan, dilewati.")

        return redirect("pemeriksaan:list_peserta", status_peserta, jadwal.id_jadwal)

    # Rekomendasi disesuaikan dengan jenis peserta dan riwayat imunisasi.
    if status_peserta == "balita":
        vaksin_choices = Imunisasi.VAKSIN_BALITA
        vaksin_rekomendasi = get_vaksin_rekomendasi_balita(
            peserta, jadwal.tgl_kegiatan
        )

    else:
        vaksin_choices = Imunisasi.VAKSIN_BUMIL
        vaksin_rekomendasi = get_vaksin_rekomendasi_bumil(
            peserta, jadwal.tgl_kegiatan
        )
    
    return render(request, "pemeriksaan/form_imunisasi.html", {
        "jadwal": jadwal,
        "peserta": peserta,
        "status_peserta": status_peserta,
        "vaksin_choices": vaksin_choices,
        "vaksin_sudah": vaksin_pada_jadwal,
        "vaksin_pada_jadwal": vaksin_pada_jadwal,
        "riwayat": riwayat,
        "vaksin_rekomendasi": vaksin_rekomendasi,
        "bidan_choices": bidan_choices,
    })
