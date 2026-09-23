"""Service integrasi model Random Forest untuk deteksi stunting.

Model final dibangun di project machine learning terpisah dan disimpan sebagai
``ml_models/random_forest_stunting.joblib``. Service ini hanya menangani
inferensi pada data pemeriksaan baru; preprocessing dataset dan training model
tidak dijalankan dari aplikasi Django.

Fitur model final, dalam urutan yang sama dengan saat training:
    1. gender_encoded  (Perempuan=0, Laki-laki=1)
    2. age_month       (usia bulan)
    3. weight_kg       (berat badan kg)
    4. height_cm       (panjang/tinggi badan cm)

Klasifikasi utama SELALU berasal dari ``model.predict()``. ``predict_proba()``
hanya dipakai untuk menampilkan probabilitas keluaran model terhadap kelas
stunting dan tidak digunakan sebagai threshold manual.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd
from django.conf import settings


MODEL_PATH = Path(settings.BASE_DIR) / "ml_models" / "random_forest_stunting.joblib"

EXPECTED_FEATURE_COLUMNS = [
    "gender_encoded",
    "age_month",
    "weight_kg",
    "height_cm",
]

# Encoding harus identik dengan preprocessing/training final.
GENDER_MAPPING = {
    "F": 0,
    "P": 0,
    "FEMALE": 0,
    "PEREMPUAN": 0,
    "M": 1,
    "L": 1,
    "MALE": 1,
    "LAKI-LAKI": 1,
    "LAKI LAKI": 1,
    "LAKILAKI": 1,
}


@lru_cache(maxsize=1)
def load_model_package() -> dict:
    """Memuat dan memvalidasi package model final satu kali per worker Django."""
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            "Model Random Forest tidak ditemukan. "
            f"Lokasi yang dicari: {MODEL_PATH}"
        )

    try:
        package = joblib.load(MODEL_PATH)
    except Exception as error:  # pragma: no cover - detail tergantung runtime
        raise RuntimeError(
            "Model Random Forest gagal dimuat. "
            f"Detail error: {error}"
        ) from error

    if not isinstance(package, dict):
        raise ValueError(
            "File model tidak memiliki format package yang sesuai dengan "
            "hasil training final."
        )

    # Package final September 2026 tidak menggunakan threshold manual.
    required_keys = {"model", "feature_columns", "label_mapping"}
    missing_keys = required_keys - set(package)
    if missing_keys:
        raise ValueError(
            "Package model tidak lengkap. Key yang tidak ditemukan: "
            f"{sorted(missing_keys)}"
        )

    model = package["model"]
    if not hasattr(model, "predict"):
        raise ValueError("Object model tidak mempunyai fungsi predict().")
    if not hasattr(model, "predict_proba"):
        raise ValueError("Object model tidak mempunyai fungsi predict_proba().")
    if not hasattr(model, "classes_"):
        raise ValueError("Object model tidak mempunyai atribut classes_.")

    feature_columns = package["feature_columns"]
    if not isinstance(feature_columns, (list, tuple)):
        raise ValueError("feature_columns pada package model harus berupa list atau tuple.")

    feature_columns = list(feature_columns)
    if feature_columns != EXPECTED_FEATURE_COLUMNS:
        raise ValueError(
            "Urutan/struktur fitur model tidak sesuai dengan integrasi Django. "
            f"Diharapkan {EXPECTED_FEATURE_COLUMNS}, diterima {feature_columns}."
        )

    try:
        classes = {int(value) for value in model.classes_}
    except (TypeError, ValueError) as error:
        raise ValueError("Kelas model tidak dapat dibaca sebagai label 0/1.") from error

    if classes != {0, 1}:
        raise ValueError(
            "Model harus memiliki kelas 0 (Tidak Stunting) dan 1 (Stunting). "
            f"Kelas yang ditemukan: {sorted(classes)}"
        )

    label_mapping = package["label_mapping"]
    if not isinstance(label_mapping, dict):
        raise ValueError("label_mapping pada package model harus berupa dictionary.")

    return package


def normalize_gender(gender) -> str:
    """Menyeragamkan jenis kelamin menjadi F (Perempuan) atau M (Laki-laki)."""
    if gender is None:
        raise ValueError("Jenis kelamin tidak boleh kosong.")

    value = str(gender).strip().upper().replace("_", " ")

    if value in {"F", "P", "FEMALE", "PEREMPUAN"}:
        return "F"
    if value in {"M", "L", "MALE", "LAKI-LAKI", "LAKI LAKI", "LAKILAKI"}:
        return "M"

    raise ValueError(f"Jenis kelamin tidak valid. Nilai yang diterima: {value}")


def encode_gender(gender) -> int:
    """Mengubah jenis kelamin menjadi encoding model final."""
    return GENDER_MAPPING[normalize_gender(gender)]


def convert_to_float(value, field_name: str) -> float:
    """Mengubah nilai input menjadi float dengan pesan validasi yang jelas."""
    if value is None:
        raise ValueError(f"{field_name} tidak boleh kosong.")

    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{field_name} harus berupa angka. Nilai diterima: {value}"
        ) from error


def validate_input(*, age_month, weight_kg, height_cm) -> tuple[float, float, float]:
    """Validasi dasar input pemeriksaan sebelum diteruskan ke model."""
    age_month = convert_to_float(age_month, "Usia")
    weight_kg = convert_to_float(weight_kg, "Berat badan")
    height_cm = convert_to_float(height_cm, "Panjang/tinggi badan")

    if not 0 <= age_month <= 59:
        raise ValueError("Usia balita harus berada pada rentang 0 sampai 59 bulan.")
    if not 1 <= weight_kg <= 35:
        raise ValueError("Berat badan berada di luar rentang pemeriksaan 1 sampai 35 kg.")
    if not 40 <= height_cm <= 130:
        raise ValueError(
            "Panjang/tinggi badan berada di luar rentang pemeriksaan 40 sampai 130 cm."
        )

    return age_month, weight_kg, height_cm


def create_input_dataframe(
    *,
    gender,
    age_month,
    weight_kg,
    height_cm,
    feature_columns,
):
    """Membentuk satu baris DataFrame dengan urutan fitur identik saat training."""
    gender_encoded = encode_gender(gender)

    input_data = pd.DataFrame(
        [
            {
                "gender_encoded": gender_encoded,
                "age_month": age_month,
                "weight_kg": weight_kg,
                "height_cm": height_cm,
            }
        ]
    )

    feature_columns = list(feature_columns)
    missing_columns = set(feature_columns) - set(input_data.columns)
    if missing_columns:
        raise ValueError(
            "Input tidak mempunyai semua fitur yang dibutuhkan model. "
            f"Kolom yang hilang: {sorted(missing_columns)}"
        )

    return input_data[feature_columns], gender_encoded


def _label_text(label_mapping: dict, label: int) -> str:
    """Mengambil teks label package dengan fallback Bahasa Indonesia."""
    value = label_mapping.get(label)
    if value is None:
        value = label_mapping.get(str(label))
    if value is None:
        value = "Stunting" if label == 1 else "Tidak Stunting"
    return str(value)


def prediksi_stunting_rf(*, gender, age_month, weight_kg, height_cm) -> dict:
    """Melakukan inferensi Random Forest untuk satu pemeriksaan balita.

    Label klasifikasi berasal dari ``model.predict()``. Probabilitas kelas
    diperoleh secara terpisah dari ``model.predict_proba()`` hanya sebagai
    informasi keluaran model.
    """
    age_month, weight_kg, height_cm = validate_input(
        age_month=age_month,
        weight_kg=weight_kg,
        height_cm=height_cm,
    )
    normalized_gender = normalize_gender(gender)

    package = load_model_package()
    model = package["model"]
    feature_columns = list(package["feature_columns"])
    label_mapping = package["label_mapping"]
    metadata = package.get("metadata", {})

    input_data, gender_encoded = create_input_dataframe(
        gender=normalized_gender,
        age_month=age_month,
        weight_kg=weight_kg,
        height_cm=height_cm,
        feature_columns=feature_columns,
    )

    # Klasifikasi final: sama seperti 04_training.py, yaitu model.predict().
    try:
        prediction_label = int(model.predict(input_data)[0])
    except Exception as error:
        raise RuntimeError(
            "Model gagal melakukan klasifikasi. "
            f"Detail error: {error}"
        ) from error

    if prediction_label not in (0, 1):
        raise ValueError(
            "Model Random Forest menghasilkan label di luar kelas 0/1: "
            f"{prediction_label}"
        )

    # Probabilitas hanya untuk informasi UI, bukan penentu label manual.
    try:
        probabilities = model.predict_proba(input_data)[0]
    except Exception as error:
        raise RuntimeError(
            "Model gagal menghasilkan probabilitas kelas. "
            f"Detail error: {error}"
        ) from error

    classes = [int(value) for value in model.classes_]
    try:
        index_not_stunted = classes.index(0)
        index_stunted = classes.index(1)
    except ValueError as error:
        raise ValueError(
            "Model tidak memiliki kelas 0 dan 1 sesuai konfigurasi training."
        ) from error

    probability_not_stunted = float(probabilities[index_not_stunted])
    probability_stunted = float(probabilities[index_stunted])

    if not 0 <= probability_not_stunted <= 1 or not 0 <= probability_stunted <= 1:
        raise ValueError("Probabilitas model berada di luar rentang 0-1.")

    prediction_status = _label_text(label_mapping, prediction_label)

    return {
        "label": prediction_label,
        "status": prediction_status,
        "probability_stunted": probability_stunted,
        "probability_not_stunted": probability_not_stunted,
        "probability_stunted_percent": round(probability_stunted * 100, 2),
        "probability_not_stunted_percent": round(probability_not_stunted * 100, 2),
        "prediction_method": "model.predict",
        "input": {
            "gender": normalized_gender,
            "gender_encoded": gender_encoded,
            "age_month": age_month,
            "weight_kg": weight_kg,
            "height_cm": height_cm,
        },
        "metadata": metadata,
    }


def get_model_info() -> dict:
    """Mengambil metadata model final tanpa melakukan prediksi."""
    package = load_model_package()
    model = package["model"]

    return {
        "model_path": str(MODEL_PATH),
        "model_name": type(model).__name__,
        "feature_columns": list(package["feature_columns"]),
        "label_mapping": package["label_mapping"],
        "classes": model.classes_.tolist() if hasattr(model, "classes_") else [],
        "n_estimators": getattr(model, "n_estimators", None),
        "prediction_method": "model.predict",
        "uses_manual_threshold": False,
        "metadata": package.get("metadata", {}),
    }


def check_model_ready() -> dict:
    """Health check sederhana untuk memastikan model siap digunakan aplikasi."""
    try:
        info = get_model_info()
        return {
            "ready": True,
            "message": "Model Random Forest siap digunakan.",
            "model_path": info["model_path"],
            "model_name": info["model_name"],
            "features": info["feature_columns"],
            "prediction_method": info["prediction_method"],
            "uses_manual_threshold": False,
            "metadata": info["metadata"],
        }
    except Exception as error:
        return {
            "ready": False,
            "message": str(error),
            "model_path": str(MODEL_PATH),
        }
