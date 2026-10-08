# Sistem Informasi Posyandu & Deteksi Stunting

Aplikasi berbasis **Django + PostgreSQL** untuk pengelolaan pelayanan Posyandu tingkat kelurahan. Sistem mendukung pengelolaan Posyandu, Kader, Bidan, peserta Balita dan Ibu Hamil, jadwal kegiatan, pemeriksaan, imunisasi, KMS, laporan, serta deteksi stunting dengan **referensi antropometri WHO** dan **Random Forest**.

README ini merupakan **dokumentasi utama dan satu-satunya** untuk instalasi, penggunaan, akun demo usability, tampilan responsif, pengujian, export, dan deployment.

---

## 1. Fitur Utama

### Admin Kelurahan

Admin Kelurahan berfokus pada data master, monitoring, dan rekap seluruh Posyandu.

- Dashboard seluruh Posyandu.
- Kelola data Posyandu.
- Kelola data Kader dan akun login Kader.
- Kelola data Bidan dan cakupan wilayah Bidan.
- Monitoring jadwal seluruh Posyandu.
- Filter jadwal berdasarkan status dan Posyandu.
- Melihat Kader yang menerima jadwal pada setiap Posyandu.
- Rekap Balita, Ibu Hamil, imunisasi, dan pelayanan Posyandu.
- Export laporan/data ke PDF dan Excel pada fitur yang tersedia.

Admin Kelurahan **tidak melakukan input pemeriksaan atau imunisasi**.

### Kader

Kader melakukan pencatatan operasional pada Posyandu tempat tugasnya.

- Kelola peserta Balita dan Ibu Hamil.
- Tambah dan kelola jadwal kegiatan.
- Posyandu jadwal otomatis mengikuti tempat tugas Kader.
- Input dan edit pemeriksaan Balita.
- Input dan edit pemeriksaan Ibu Hamil.
- Input imunisasi.
- Input Vitamin A dan obat cacing melalui pemeriksaan Balita.
- Melihat hasil antropometri WHO.
- Melihat prediksi Random Forest.
- Melihat KMS dan riwayat pertumbuhan.
- Mengakses data hanya pada Posyandu yang menjadi tempat tugasnya.

### Bidan

Bidan tidak mempunyai akun login. Data Bidan dikelola Admin Kelurahan sebagai tenaga kesehatan dan cakupan wilayah.

Pada pemeriksaan Balita dan Ibu Hamil, Bidan pendamping ditentukan berdasarkan cakupan Posyandu tempat Kader bertugas.

### Peserta

Peserta tidak mempunyai akun login dan terdiri dari:

- Balita.
- Ibu Hamil.

---

## 2. Alur Sistem

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
KMS / Antropometri WHO / Deteksi Stunting
   ↓
Data masuk ke rekap Admin Kelurahan
```

---

## 3. Antropometri WHO dan Deteksi Stunting

Sistem menghasilkan dua keluaran pada pemeriksaan Balita:

1. **Status antropometri WHO** berdasarkan PB/TB menurut umur.
2. **Prediksi Random Forest** berupa `Stunting` atau `Tidak Stunting`.

### 3.1 Referensi WHO

Referensi WHO menggunakan tabel **Length/Height-for-Age expanded** berbasis usia harian untuk **Day 0–1856**, terpisah antara laki-laki dan perempuan.

Usia dihitung dari tanggal pelayanan, bukan tanggal input data:

```text
usia_hari = tanggal_pelayanan - tanggal_lahir
```

Sistem mengambil parameter `L`, `M`, dan `S` berdasarkan jenis kelamin dan usia hari, lalu menghitung Z-score.

Kategori yang digunakan:

```text
Z < -3         = Sangat Pendek
-3 <= Z < -2   = Pendek
-2 <= Z <= +3  = Normal
Z > +3         = Tinggi
```

Untuk pembandingan dengan Random Forest:

```text
Sangat Pendek / Pendek → Stunting
Normal / Tinggi         → Tidak Stunting
```

### 3.2 Posisi Pengukuran dan Koreksi 0,7 cm

Pemeriksaan Balita menyimpan cara pengukuran:

- `panjang` = panjang badan **terlentang**;
- `tinggi` = tinggi badan **berdiri**.

Standar runtime berpindah dari length ke height pada **Day 731**. Bila metode pengukuran tidak sesuai kelompok usia, sistem melakukan koreksi:

```text
Usia < 731 hari, diukur berdiri   → nilai + 0,7 cm
Usia >= 731 hari, diukur terlentang → nilai - 0,7 cm
```

Nilai yang diketik pengguna **tetap disimpan sebagai nilai pengukuran asli**. Koreksi digunakan pada perhitungan WHO. Payload grafik KMS PB/TB-U dan IMT/U juga menggunakan nilai WHO yang sama agar grafik dan Z-score konsisten.

Migration terkait:

```text
apps/pemeriksaan/migrations/0013_jenis_pengukuran_antropometri.py
```

Data lama yang belum memiliki informasi posisi ukur diisi dengan metode standar berdasarkan usia agar hasil historis tidak berubah secara tiba-tiba. Posisi ukur dapat dikoreksi melalui menu **Edit Pemeriksaan**.

### 3.3 Random Forest

Model Random Forest menggunakan fitur:

1. `gender_encoded`
2. `age_month`
3. `weight_kg`
4. `height_cm`

Model berada di:

```text
ml_models/random_forest_stunting.joblib
```

Service inferensi:

```text
apps/deteksi/services/random_forest.py
```

Probabilitas prediksi berasal dari `predict_proba()`.

> Antropometri WHO dan Random Forest merupakan proses yang berbeda. Hasil sistem digunakan sebagai alat bantu informasi; penilaian dan tindak lanjut kesehatan tetap mengikuti tenaga kesehatan/pelayanan kesehatan terkait.

### 3.4 File Referensi WHO

Runtime CSV:

```text
apps/referensi/data/lfa_boys_z_exp.csv
apps/referensi/data/lfa_girls_z_exp.csv
```

File sumber:

```text
apps/referensi/data/sumber/WHO_LFA_boys_z_exp.xlsx
apps/referensi/data/sumber/WHO_LFA_girls_z_exp.xlsx
```

Setelah migration referensi lengkap, database berisi **3.714 baris**: 1.857 laki-laki + 1.857 perempuan.

---

## 4. Jadwal Imunisasi yang Diakomodasi

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

## 5. Teknologi

- Python
- Django 5.2
- PostgreSQL
- Django Tailwind
- Tailwind CSS melalui Node.js/npm
- scikit-learn
- pandas
- NumPy
- joblib
- openpyxl
- xhtml2pdf
- Pillow

Dependency Python lengkap tersedia pada `requirements.txt`.

Asset Tailwind dikelola dari:

```text
theme/static_src/
```

---

## 6. Persyaratan Sistem

Pastikan perangkat memiliki:

- Python yang kompatibel dengan dependency project.
- PostgreSQL.
- pip.
- Node.js dan npm.

Cek instalasi:

```bash
python --version
pip --version
node --version
npm --version
```

Jika muncul pesan `node.js and/or npm is not installed or cannot be found`, install Node.js terlebih dahulu dan pastikan `node` serta `npm` dapat dipanggil dari terminal.

---

## 7. Instalasi Lokal

### 7.1 Clone atau extract project

```bash
git clone <URL-REPOSITORY>
cd <NAMA-FOLDER-PROJECT>
```

Atau extract ZIP lalu masuk ke folder yang memiliki `manage.py`.

### 7.2 Buat virtual environment

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

### 7.3 Install dependency Python

```bash
pip install -r requirements.txt
```

### 7.4 Install dependency Tailwind/npm

```bash
cd theme/static_src
npm install
cd ../..
```

### 7.5 Buat database PostgreSQL

Contoh:

```sql
CREATE DATABASE posyandu;
```

### 7.6 Konfigurasi `.env`

Copy `.env.example` menjadi `.env`.

Windows:

```powershell
copy .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

Contoh:

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

Jangan commit `.env` karena dapat berisi kredensial dan secret key.

### 7.7 Jalankan migration

```bash
python manage.py migrate
```

Jika database sudah berisi data penting, lakukan backup PostgreSQL sebelum migration baru.

### 7.8 Seed data awal (opsional)

```bash
python manage.py seed_data
```

Cek opsi:

```bash
python manage.py seed_data --help
```

### 7.9 Buat Admin Kelurahan

```bash
python manage.py create_admin_kelurahan --username adminkelurahan --nama "Admin Kelurahan"
```

Password diminta melalui terminal.

### 7.10 Jalankan Tailwind saat development

Buka terminal pertama:

```bash
python manage.py tailwind start
```

Biarkan terminal tersebut tetap berjalan agar perubahan template/class Tailwind dibangun otomatis.

Buka terminal kedua, aktifkan virtual environment, lalu:

```bash
python manage.py runserver
```

Buka:

```text
http://127.0.0.1:8000/
```

> Setelah menarik/update source yang mengubah template Tailwind, jalankan kembali proses Tailwind. CSS `responsive-overrides.css` sengaja berada di luar file generated agar perbaikan responsif dan style form dasar tidak hilang ketika Tailwind dibangun ulang.

---

## 8. Membuat Akun Kader

Akun Kader dibuat melalui Admin Kelurahan:

1. Login sebagai Admin Kelurahan.
2. Buka **Master Data → Data Kader**.
3. Tambahkan atau pilih data Kader.
4. Pastikan Kader memiliki Posyandu tempat tugas.
5. Pilih **Buat Akun**.
6. Isi username/password atau gunakan fitur generate yang tersedia.

Bidan tidak memerlukan akun login.

---

## 9. Akun Demo Usability — 36 Responden

Project menyediakan command untuk membuat **dua akun bersama** yang dapat digunakan dari beberapa browser/perangkat pada saat pengujian usability.

Pembagian responden:

- **R01–R34** menggunakan satu akun Kader.
- **R35–R36** menggunakan satu akun Admin Kelurahan.

### 9.1 Membuat atau mereset data demo

```bash
python manage.py setup_usability_demo --reset
```

Akun default:

| Peran | Username | Password | Responden |
|---|---|---|---|
| Kader | `kader` | `kader123` | R01–R34 |
| Admin Kelurahan | `kelurahan` | `kelurahan123` | R35–R36 |

Django membuat session per browser/perangkat sehingga akun bersama dapat login secara bersamaan. PostgreSQL tetap direkomendasikan untuk skenario akses/tulis serentak.

### 9.2 Mengganti password saat setup

```bash
python manage.py setup_usability_demo --reset --kader-password "PasswordKaderBaru!" --admin-password "PasswordAdminBaru!"
```

Opsi kompatibilitas satu password untuk kedua akun:

```bash
python manage.py setup_usability_demo --reset --password "PasswordBaru!"
```

### 9.3 Data yang otomatis dibuat

Command menyiapkan:

- `Posyandu Demo Usability Bersama`.
- `Kader Demo Bersama`.
- `Bidan Demo Usability`.
- `Balita Demo R01` sampai `Balita Demo R34`.
- Jadwal **Pemeriksaan Rutin** pada tanggal command dijalankan, pukul **06:30–07:30**.

### 9.4 Aturan Kader R01–R34

Setiap responden wajib menyertakan kode responden pada data yang dibuat.

Contoh R07:

```text
Nama Balita : Balita Uji R07
Nama Ibu    : Ibu Uji R07
```

Jika membuat jadwal sendiri, gunakan jam yang berbeda berdasarkan kode responden, misalnya:

```text
R01 → 08:01–09:01
R02 → 08:02–09:02
...
R34 → 08:34–09:34
```

Untuk tugas pemeriksaan, responden dapat mencari `Balita Demo Rxx` sesuai kodenya. Data acuan ini mencegah tugas pemeriksaan otomatis gagal hanya karena peserta/jadwal pada tugas sebelumnya belum berhasil dibuat.

### 9.5 Aturan Admin R35–R36

Gunakan kode responden pada nama data:

```text
R35 → Kader Uji R35 / Bidan Uji R35 / Posyandu Uji R35
R36 → Kader Uji R36 / Bidan Uji R36 / Posyandu Uji R36
```

Jangan menghapus data demo bersama selama sesi pengujian berlangsung.

### 9.6 Reset atau hapus data demo

Reset:

```bash
python manage.py setup_usability_demo --reset
```

Hapus seluruh data dan akun demo:

```bash
python manage.py setup_usability_demo --remove
```

> Akun demo menggunakan password sederhana khusus pengujian terkontrol. Jangan mempertahankannya pada sistem production setelah pengujian selesai.

---

## 10. Penugasan Petugas

Tabel `penugasan_Petugas` menyimpan penugasan aktif dengan atribut:

```text
petugas
posyandu
tanggal_daftar
```

Ketentuan:

- `tanggal_daftar` otomatis saat penugasan dibuat.
- Tidak menggunakan `tanggal_mulai` dan `tanggal_selesai`.
- Satu Kader memiliki satu Posyandu operasional.
- Bidan dapat mencakup beberapa Posyandu.
- Kombinasi `petugas + posyandu` unik.
- Saat penugasan diubah, relasi lama diganti dengan relasi baru.

---

## 11. Tampilan Desktop dan Mobile

Project memiliki layout responsif global melalui:

```text
templates/base.html
theme/static/css/responsive-overrides.css
theme/static/js/kms_charts.js
```

Perbaikan responsif yang sudah terintegrasi:

- Sidebar menjadi drawer pada mobile dengan overlay dan tombol tutup.
- Header, breadcrumb, dan ruang konten dibuat lebih ringkas pada layar kecil.
- Tabel sederhana otomatis berubah menjadi card responsif; tabel kompleks tetap dapat digeser horizontal.
- Modal dibatasi terhadap tinggi viewport mobile.
- Tombol export PDF/Excel dapat wrap dan memiliki area sentuh yang lebih nyaman.
- Form `form-input`, `form-select`, `form-textarea`, dan `form-checkbox` memiliki style konsisten desktop/mobile, termasuk dark mode.
- Input mobile memakai ukuran teks 16 px untuk mengurangi auto-zoom browser.
- KMS BB/U, PB/TB/U, dan IMT/U menggunakan frame canvas responsif dan legend HTML.
- Tick umur pada KMS mobile diringkas agar grafik tidak bertumpuk.
- Riwayat KMS menggunakan card pada mobile dan tabel pada layar yang lebih besar.
- Card Data Peserta dan Pemeriksaan menampilkan informasi utama lebih dahulu dan aksi yang sesuai layar sentuh.
- Aksi **Edit Pemeriksaan Balita** pada mobile membawa URL edit yang sama dengan desktop.
- Ringkasan laporan imunisasi menggunakan 2 kolom pada HP dan 4 kolom mulai breakpoint `md` agar tidak terlalu sempit.
- Navigasi utama menggunakan atribut aksesibilitas `aria` dan bahasa halaman disetel ke `id`.

### Setelah perubahan tampilan

Development:

```bash
python manage.py tailwind start
```

Production:

```bash
python manage.py tailwind build
python manage.py collectstatic --noinput
```

Setelah deploy, lakukan hard refresh atau buka Incognito/Private Window agar browser tidak memakai CSS/JavaScript lama.

---

## 12. Export PDF dan Excel

Fitur export yang sudah tersedia/dirapikan:

- Data Peserta Balita/Ibu Hamil ke Excel dan PDF.
- Filter halaman peserta ikut diterapkan pada export.
- Jadwal Pemeriksaan ke PDF dan Excel.
- Filter `mendatang/riwayat` serta pencarian ikut pada export jadwal.
- Laporan Admin Balita/Ibu Hamil menggunakan file attachment agar lebih konsisten di browser mobile.
- Toolbar export responsif pada mobile.

PDF/Excel yang diunduh mengikuti data yang dapat diakses oleh role/Posyandu pengguna.

---

## 13. Hak Akses dan Integritas Data

Hak akses diterapkan pada backend dan antarmuka:

- `admin_required` untuk fitur Admin Kelurahan.
- `kader_required` untuk transaksi operasional Kader.
- Kader dibatasi pada Posyandu tempat tugasnya.
- Bidan tidak dapat login.
- Admin Kelurahan tidak dapat mengakses URL input operasional Kader.

Aturan integritas utama:

- satu peserta hanya memiliki satu pemeriksaan pada satu jadwal;
- peserta dengan riwayat pelayanan tidak dapat langsung dihapus;
- jadwal dengan riwayat pelayanan tidak dapat langsung dihapus;
- Posyandu yang masih direferensikan dilindungi dari penghapusan;
- Kader/Bidan yang sudah digunakan dalam riwayat pelayanan dilindungi dari penghapusan;
- Posyandu jadwal Kader mengikuti tempat tugas;
- Bidan pemeriksaan mengikuti cakupan Posyandu;
- NIK divalidasi 16 digit dan dicegah duplikat;
- nomor HP divalidasi;
- tanggal lahir tidak dapat berada di masa depan;
- peserta Ibu Hamil dibatasi berjenis kelamin perempuan.

---

## 14. Struktur Folder

```text
project/
├── apps/
│   ├── accounts/       # autentikasi, Kader, Bidan, penugasan, akun demo
│   ├── dashboard/      # dashboard Admin dan Kader
│   ├── deteksi/        # WHO dan integrasi Random Forest
│   ├── laporan/        # rekap, KMS, export
│   ├── pemeriksaan/    # pemeriksaan, imunisasi, KMS
│   ├── peserta/        # Balita dan Ibu Hamil
│   ├── posyandu/       # Posyandu dan jadwal
│   └── referensi/      # referensi antropometri WHO
├── common/             # helper/decorator akses
├── config/             # settings/ASGI/WSGI
├── ml_models/          # model Random Forest
├── templates/          # template HTML
├── theme/
│   ├── static/         # CSS/JS yang digunakan aplikasi
│   └── static_src/     # source/build Tailwind npm
├── .env.example
├── manage.py
├── requirements.txt
└── README.md
```

---

## 15. Pengujian dan Pemeriksaan Sebelum Deploy

Pemeriksaan konfigurasi:

```bash
python manage.py check
```

Seluruh test:

```bash
python manage.py test --settings=config.settings_test --verbosity 2
```

Test modul utama:

```bash
python manage.py test apps.peserta apps.pemeriksaan apps.posyandu apps.laporan --settings=config.settings_test --verbosity 2
```

Khusus referensi WHO dan pemeriksaan:

```bash
python manage.py test apps.referensi apps.pemeriksaan --settings=config.settings_test --verbosity 2
```

Lihat migration:

```bash
python manage.py showmigrations
```

Pastikan tidak ada migration yang belum diterapkan sebelum sistem digunakan untuk pengujian lapangan.

---

## 16. Deployment VPS

Contoh alur pada server Linux yang menjalankan Gunicorn + Nginx:

```bash
cd /var/www/posyandu
source venv/bin/activate
pip install -r requirements.txt
npm --prefix theme/static_src install
python manage.py migrate
python manage.py check
python manage.py tailwind build
python manage.py collectstatic --noinput
python manage.py test apps.referensi apps.pemeriksaan --settings=config.settings_test
sudo systemctl restart posyandu
sudo systemctl reload nginx
```

Hal penting production:

- `DEBUG=False`.
- Gunakan `SECRET_KEY` yang aman.
- Atur `ALLOWED_HOSTS` sesuai domain.
- Gunakan PostgreSQL dengan kredensial kuat.
- Aktifkan HTTPS.
- Jangan menimpa `.env` production dengan `.env` lokal.
- Jangan commit `.env`.
- Backup database sebelum migration penting.
- Jalankan `tailwind build` dan `collectstatic` setelah update tampilan.
- Hapus/nonaktifkan akun demo setelah pengujian usability jika tidak lagi dibutuhkan.

Jika deployment memakai service bernama `posyandu`, restart dengan:

```bash
sudo systemctl restart posyandu
```

---

## 17. Troubleshooting

### Node/npm tidak ditemukan

Cek:

```bash
node --version
npm --version
```

Jika belum tersedia, install Node.js lalu buka terminal baru. Bila npm berada di lokasi non-standar, sesuaikan `NPM_BIN_PATH` pada settings.

### CSS/Tampilan tidak berubah

Development:

```bash
python manage.py tailwind start
```

Production:

```bash
python manage.py tailwind build
python manage.py collectstatic --noinput
sudo systemctl restart posyandu
sudo systemctl reload nginx
```

Lalu hard refresh/Incognito.

### PostgreSQL tidak dapat terhubung

Pastikan service PostgreSQL aktif dan cek:

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

### Z-score berbeda dari hitung manual

Periksa empat hal berikut:

1. jenis kelamin peserta;
2. tanggal lahir dan tanggal pelayanan sehingga `usia_hari` sama;
3. posisi pengukuran: terlentang atau berdiri;
4. apakah perhitungan manual memakai tabel harian WHO yang sama, bukan usia bulan yang dibulatkan.

Untuk anak yang posisi ukurnya tidak sesuai kelompok umur, ingat koreksi ±0,7 cm sebagaimana dijelaskan pada bagian antropometri.

### Model Random Forest gagal dimuat

Pastikan tersedia:

```text
ml_models/random_forest_stunting.joblib
```

Kemudian:

```bash
pip install -r requirements.txt
```

### Referensi WHO tidak ditemukan

```bash
python manage.py migrate
```

---

## 18. Django Admin

Untuk kebutuhan teknis/development:

```bash
python manage.py createsuperuser
```

Akses:

```text
/admin/
```

Superuser Django berbeda dengan akun **Admin Kelurahan** aplikasi.

---

## 19. Ringkasan Role

| Role | Login | Akses Utama |
|---|---:|---|
| Admin Kelurahan | Ya | Master Posyandu, Kader, Bidan, monitoring, dan rekap seluruh Posyandu |
| Kader | Ya | Peserta, jadwal, pemeriksaan, imunisasi, KMS, dan pelayanan Posyandu |
| Bidan | Tidak | Data tenaga kesehatan dan cakupan wilayah |
| Peserta | Tidak | Data sasaran pelayanan Balita atau Ibu Hamil |

---

## 20. Catatan Keamanan

- Jangan menyimpan password production di README atau source code.
- Password akun demo hanya untuk pengujian terkontrol.
- Jangan membagikan `.env`, backup database, atau secret key ke repository publik.
- Validasi dan hak akses backend tetap harus dipertahankan walaupun tombol tertentu disembunyikan dari UI.

---

## 21. Lisensi

Tambahkan informasi lisensi repository pada bagian ini apabila project akan didistribusikan secara publik.
