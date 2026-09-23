# Sistem Informasi Posyandu & Deteksi Stunting

Aplikasi berbasis **Django + PostgreSQL** untuk membantu pengelolaan pelayanan Posyandu pada tingkat kelurahan. Sistem mendukung pengelolaan data Posyandu, Kader, Bidan, peserta Balita dan Ibu Hamil, jadwal kegiatan, pemeriksaan, imunisasi, KMS, rekapitulasi, serta deteksi stunting menggunakan referensi antropometri WHO dan model Random Forest.

## Fitur Utama

### Admin Kelurahan

Admin Kelurahan berfokus pada pengelolaan data master dan monitoring seluruh Posyandu.

- Dashboard seluruh Posyandu.
- Kelola data Posyandu.
- Kelola data Kader.
- Kelola akun login Kader.
- Kelola data Bidan.
- Kelola cakupan wilayah Bidan.
- Monitoring jadwal seluruh Posyandu.
- Filter jadwal berdasarkan status dan Posyandu.
- Melihat Kader yang menerima jadwal pada setiap Posyandu.
- Rekap data Balita, Ibu Hamil, imunisasi, dan pelayanan Posyandu.
- Export data dan laporan ke PDF/Excel sesuai fitur yang tersedia.

Admin Kelurahan tidak melakukan input pemeriksaan, imunisasi, maupun transaksi pelayanan peserta.

### Kader

Kader merupakan pengguna yang melakukan pencatatan operasional Posyandu pada tempat tugasnya.

- Kelola peserta Balita dan Ibu Hamil.
- Tambah dan kelola jadwal kegiatan.
- Posyandu pada jadwal otomatis mengikuti tempat tugas Kader.
- Input pemeriksaan Balita.
- Edit/koreksi pemeriksaan Balita.
- Input pemeriksaan Ibu Hamil.
- Edit/koreksi pemeriksaan Ibu Hamil.
- Input imunisasi.
- Input Vitamin A dan obat cacing melalui pemeriksaan Balita.
- Melihat hasil antropometri WHO.
- Melihat hasil klasifikasi Random Forest.
- Melihat KMS dan riwayat pertumbuhan.
- Mengakses data hanya pada Posyandu yang menjadi tempat tugasnya.

### Bidan

Bidan tidak mempunyai akun login. Data Bidan dikelola oleh Admin Kelurahan sebagai data tenaga kesehatan dan cakupan wilayah.

Pada pemeriksaan Balita dan Ibu Hamil, Bidan pendamping ditentukan otomatis berdasarkan cakupan Posyandu tempat Kader bertugas.

### Peserta

Peserta tidak mempunyai akun login dan terdiri dari:

- Balita.
- Ibu Hamil.

---

## Alur Sistem

### Admin Kelurahan

```text
Login Admin
   ↓
Dashboard
   ↓
Master Data
├── Posyandu
├── Kader
└── Bidan + Cakupan Wilayah
   ↓
Monitoring Jadwal
   ↓
Rekap Seluruh Posyandu
```

### Kader

```text
Login Kader
   ↓
Posyandu sesuai tempat tugas
   ↓
Kelola Peserta
   ↓
Buat Jadwal
   ↓
Pelayanan
├── Pemeriksaan Balita
├── Pemeriksaan Ibu Hamil
└── Imunisasi
   ↓
KMS / Hasil Antropometri / Deteksi Stunting
   ↓
Data masuk ke rekap Admin Kelurahan
```

---

## Deteksi Stunting

Sistem menggunakan dua keluaran pada pemeriksaan Balita:

1. **Referensi antropometri WHO** untuk menentukan status panjang/tinggi badan menurut umur.
2. **Random Forest** untuk menghasilkan prediksi `Stunting` atau `Tidak Stunting`.

### Referensi WHO

Referensi WHO menggunakan tabel **Length/Height-for-Age expanded** berbasis usia harian (`Day 0–1856`) untuk laki-laki dan perempuan.

Usia WHO dihitung dari:

```text
usia_hari = tanggal_pelayanan - tanggal_lahir
```

Sistem kemudian mengambil parameter `L`, `M`, dan `S` sesuai jenis kelamin dan usia hari untuk menghitung Z-score.

Kategori antropometri yang digunakan:

```text
Z < -3         = Sangat Pendek
-3 <= Z < -2   = Pendek
-2 <= Z <= +3  = Normal
Z > +3         = Tinggi
```

Untuk perbandingan dengan hasil Random Forest:

```text
Sangat Pendek / Pendek → Stunting
Normal / Tinggi         → Tidak Stunting
```

### Random Forest

Model Random Forest menggunakan fitur:

1. `gender_encoded`
2. `age_month`
3. `weight_kg`
4. `height_cm`

Model tersedia pada:

```text
ml_models/random_forest_stunting.joblib
```

Service inferensi tersedia pada:

```text
apps/deteksi/services/random_forest.py
```

Nilai probabilitas prediksi berasal dari `predict_proba()`.

Referensi WHO runtime tersedia pada:

```text
apps/referensi/data/lfa_boys_z_exp.csv
apps/referensi/data/lfa_girls_z_exp.csv
```

File sumber WHO juga disertakan pada:

```text
apps/referensi/data/sumber/WHO_LFA_boys_z_exp.xlsx
apps/referensi/data/sumber/WHO_LFA_girls_z_exp.xlsx
```

> Hasil deteksi pada aplikasi digunakan sebagai alat bantu informasi. Penilaian dan tindak lanjut kesehatan tetap mengikuti tenaga kesehatan dan pelayanan kesehatan terkait.

---

## Jadwal Imunisasi yang Diakomodasi

| Usia | Vaksin |
|---|---|
| 0–24 jam | HB-0 |
| 1 bulan | BCG, bOPV 1 |
| 2 bulan | DPT-HB-Hib 1, bOPV 2, PCV 1, Rotavirus 1 |
| 3 bulan | DPT-HB-Hib 2, bOPV 3, PCV 2, Rotavirus 2 |
| 4 bulan | DPT-HB-Hib 3, bOPV 4, IPV 1, Rotavirus 3 |
| 9 bulan | MR 1, IPV 2 |
| 12 bulan | PCV 3 |
| 18 bulan | DPT-HB-Hib 4, MR 2 |

Japanese Encephalitis (JE) tersedia sebagai pilihan pencatatan manual karena penerapannya dapat menyesuaikan wilayah/program pelayanan.

---

## Teknologi

- Python
- Django 5.2
- PostgreSQL
- Django Tailwind
- scikit-learn
- pandas
- NumPy
- joblib
- openpyxl
- xhtml2pdf
- Pillow

Daftar dependency lengkap tersedia pada `requirements.txt`.

---

## Persyaratan Sistem

Pastikan perangkat sudah memiliki:

- Python yang kompatibel dengan dependency project.
- PostgreSQL.
- pip.
- Node.js/npm jika ingin membangun ulang asset Tailwind.

---

## Instalasi

### 1. Clone repository

```bash
git clone <URL-REPOSITORY>
cd <NAMA-FOLDER-PROJECT>
```

Atau download ZIP repository lalu extract dan masuk ke folder yang memiliki `manage.py`.

### 2. Buat virtual environment

Windows:

```powershell
python -m venv venv
venv\Scripts\activate
```

Linux/macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependency

```bash
pip install -r requirements.txt
```

### 4. Buat database PostgreSQL

Contoh:

```sql
CREATE DATABASE posyandu;
```

### 5. Konfigurasi environment

Copy `.env.example` menjadi `.env`.

Windows:

```powershell
copy .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

Contoh konfigurasi:

```env
DEBUG=True
SECRET_KEY=ganti-dengan-secret-key-yang-aman
ALLOWED_HOSTS=127.0.0.1,localhost

DB_ENGINE=django.db.backends.postgresql
DB_NAME=posyandu
DB_USER=postgres
DB_PASSWORD=password_postgresql_anda
DB_HOST=127.0.0.1
DB_PORT=5432

TIME_ZONE=Asia/Jakarta
LANGUAGE_CODE=id
SECURE_SSL_REDIRECT=False
SECURE_HSTS_SECONDS=0
```

> Jangan commit file `.env` ke repository karena dapat berisi kredensial database dan secret key.

### 6. Jalankan migration

```bash
python manage.py migrate
```

Migration project juga menyiapkan referensi WHO harian dan penyesuaian struktur database versi terbaru.

Jika database sudah berisi data penting, lakukan backup PostgreSQL sebelum menjalankan migration baru.

### 7. Seed data awal (opsional)

Untuk database baru atau environment demo:

```bash
python manage.py seed_data
```

Lihat opsi command:

```bash
python manage.py seed_data --help
```

### 8. Buat akun Admin Kelurahan

```bash
python manage.py create_admin_kelurahan --username adminkelurahan --nama "Admin Kelurahan"
```

Password akan diminta melalui terminal.

### 9. Jalankan server

```bash
python manage.py runserver
```

Buka:

```text
http://127.0.0.1:8000/
```

---

## Membuat Akun Kader

Akun Kader dibuat melalui Admin Kelurahan:

1. Login sebagai Admin Kelurahan.
2. Buka **Master Data → Data Kader**.
3. Tambahkan atau pilih data Kader.
4. Pastikan Kader memiliki Posyandu tempat tugas.
5. Pilih **Buat Akun**.
6. Isi username/password atau gunakan fitur generate yang tersedia.

Bidan tidak memerlukan akun login.

---

## Penugasan Petugas

Tabel `penugasan_Petugas` menyimpan penugasan yang berlaku saat ini dengan atribut:

```text
petugas
posyandu
tanggal_daftar
```

Ketentuan:

- `tanggal_daftar` diisi otomatis saat penugasan dibuat.
- Tidak menggunakan `tanggal_mulai` dan `tanggal_selesai`.
- Satu Kader memiliki satu Posyandu operasional.
- Bidan dapat memiliki cakupan beberapa Posyandu.
- Kombinasi `petugas + posyandu` dibuat unik.
- Saat penugasan diubah, relasi lama dihapus dan relasi baru dibuat.

---

## Struktur Folder

```text
project/
├── apps/
│   ├── accounts/       # autentikasi, Kader, Bidan, penugasan
│   ├── dashboard/      # dashboard Admin dan Kader
│   ├── deteksi/        # integrasi Random Forest
│   ├── laporan/        # rekap dan export data
│   ├── pemeriksaan/    # pemeriksaan, imunisasi, KMS
│   ├── peserta/        # peserta Balita dan Ibu Hamil
│   ├── posyandu/       # Posyandu dan jadwal kegiatan
│   └── referensi/      # referensi antropometri WHO
├── common/             # helper/decorator akses
├── config/             # konfigurasi Django
├── ml_models/          # model Random Forest
├── templates/          # template HTML
├── theme/              # Tailwind/static theme
├── .env.example
├── manage.py
├── requirements.txt
└── README.md
```

---

## Hak Akses

Hak akses diterapkan pada backend dan antarmuka.

- `admin_required` untuk fitur Admin Kelurahan.
- `kader_required` untuk transaksi operasional Kader.
- Kader dibatasi pada Posyandu tempat tugasnya.
- Bidan tidak dapat login.
- Admin Kelurahan tidak dapat mengakses URL input operasional Kader.

---

## Integritas Data

Beberapa aturan diterapkan untuk menjaga konsistensi data:

- satu peserta hanya memiliki satu pemeriksaan pada satu jadwal;
- peserta yang sudah mempunyai riwayat pelayanan tidak dapat dihapus langsung;
- jadwal yang sudah memiliki riwayat pelayanan tidak dapat dihapus;
- Posyandu yang masih digunakan oleh data lain dilindungi dari penghapusan;
- Kader/Bidan yang sudah digunakan dalam riwayat pelayanan dilindungi dari penghapusan;
- Posyandu jadwal Kader otomatis mengikuti tempat tugas;
- Bidan pemeriksaan Balita dan Ibu Hamil otomatis mengikuti cakupan Posyandu;
- NIK divalidasi 16 digit dan dicegah duplikat;
- nomor HP divalidasi;
- tanggal lahir tidak dapat berada di masa depan;
- peserta Ibu Hamil dibatasi berjenis kelamin perempuan.

---

## Pengujian

Menjalankan seluruh test dengan konfigurasi test:

```bash
python manage.py test --settings=config.settings_test
```

Dengan output lebih detail:

```bash
python manage.py test --settings=config.settings_test --verbosity 2
```

Pemeriksaan konfigurasi Django:

```bash
python manage.py check
```

---

## Django Admin

Jika diperlukan untuk kebutuhan teknis/development, buat superuser:

```bash
python manage.py createsuperuser
```

Django Admin dapat diakses melalui:

```text
/admin/
```

Superuser Django berbeda dengan akun Admin Kelurahan pada aplikasi.

---

## Troubleshooting

### PostgreSQL tidak dapat terhubung

Pastikan service PostgreSQL aktif dan nilai berikut pada `.env` benar:

```text
DB_HOST
DB_PORT
DB_NAME
DB_USER
DB_PASSWORD
```

### Database belum dibuat

```sql
CREATE DATABASE posyandu;
```

### Migration belum diterapkan

```bash
python manage.py showmigrations
python manage.py migrate
```

### Model Random Forest gagal dimuat

Pastikan file berikut tersedia:

```text
ml_models/random_forest_stunting.joblib
```

Kemudian pastikan seluruh dependency sudah terpasang:

```bash
pip install -r requirements.txt
```

### Referensi WHO tidak ditemukan

Pastikan migration sudah dijalankan:

```bash
python manage.py migrate
```

Referensi WHO yang aktif di database berjumlah **3.714 baris** (`1.857` laki-laki + `1.857` perempuan).

---

## Deployment

Untuk deployment production:

- gunakan `DEBUG=False`;
- gunakan `SECRET_KEY` yang aman;
- atur `ALLOWED_HOSTS`;
- gunakan kredensial PostgreSQL yang kuat;
- aktifkan HTTPS;
- jangan commit `.env`;
- jalankan `collectstatic` sesuai environment;
- lakukan backup database secara berkala.

---

## Ringkasan Role

| Role | Login | Akses Utama |
|---|---:|---|
| Admin Kelurahan | Ya | Master Posyandu, Kader, Bidan, monitoring dan rekap seluruh Posyandu |
| Kader | Ya | Peserta, jadwal, pemeriksaan, imunisasi, KMS, dan pelayanan Posyandu |
| Bidan | Tidak | Data tenaga kesehatan dan cakupan wilayah |
| Peserta | Tidak | Data sasaran pelayanan Balita atau Ibu Hamil |

---

## Lisensi

Tambahkan informasi lisensi repository pada bagian ini jika project akan didistribusikan secara publik.
