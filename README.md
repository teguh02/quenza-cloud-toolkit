# Quenza Cloud Toolkit

Aplikasi web internal untuk manajemen **backup & restore** data server yang
sederhana, aman, dan terpusat. Mengikuti **Quenza Design System**.

> **Status:** v1 lengkap (Fase 1–5). Autentikasi Master Password tunggal,
> backup multi-sumber, penjadwalan, multi-destinasi (Local/S3/Google Drive),
> serta restore yang aman.

---

## Tampilan Aplikasi

Antarmuka modern, bersih, dan responsif yang mengikuti **Quenza Design
System** — gradasi hijau-teal, kartu rounded, shadow halus, dan animasi
lembut di setiap interaksi. Dirancang agar manajemen backup terasa ringan,
intuitif, dan menyenangkan: dari dashboard yang informatif, manajemen project
yang fleksibel, file manager terintegrasi, multi-destinasi penyimpanan,
penjadwalan otomatis, hingga restore yang aman.

![Quenza Cloud Toolkit - 1](static/img/screenshot-1.png)

![Quenza Cloud Toolkit - 2](static/img/screenshot-2.png)

![Quenza Cloud Toolkit - 3](static/img/screenshot-3.png)

![Quenza Cloud Toolkit - 4](static/img/screenshot-4.png)

![Quenza Cloud Toolkit - 5](static/img/screenshot-5.png)

![Quenza Cloud Toolkit - 6](static/img/screenshot-6.png)

![Quenza Cloud Toolkit - 7](static/img/screenshot-7.png)

---

## Fitur Utama

- **Autentikasi** Master Password tunggal (hash bcrypt, session cookie).
- **Dashboard** kartu statistik, grafik tren backup, Quick Actions, activity feed.
- **Projects** CRUD + Integrated File Manager (jelajah direktori server).
- **Sumber backup** fleksibel: direktori, file, database MySQL & PostgreSQL.
- **Output** arsip `.zip` atau `.tar.gz` per project.
- **Destinasi**: Local, Amazon S3, Google Drive (OAuth), FTP, SCP/SSH — selektif per project, arsip dirapikan ke sub-folder per project.
- **Penjadwalan** otomatis per project (APScheduler in-process), mengikuti zona waktu global.
- **Backup manual** kapan saja (tombol Run Backup), independen dari jadwal.
- **Restore** pasif & aman (download + extract, proteksi path traversal).
- **History/Logs** dengan filter, paginasi, dan detail.
- **Settings**: zona waktu global + notifikasi (Email atau Telegram) dengan tombol uji kirim.
- **Notifikasi** hasil backup & restore via Email (maks 3 penerima) atau Telegram bot.

---

## Teknologi

| Komponen   | Pilihan                                       |
| ---------- | --------------------------------------------- |
| Backend    | FastAPI + Uvicorn                             |
| Frontend   | Jinja2 + Tailwind CSS (Play CDN) + custom CSS |
| Database   | SQLite (via SQLAlchemy)                       |
| Session    | Signed cookie (Starlette SessionMiddleware)   |
| Auth       | Master Password (bcrypt hash di `.env`)       |
| Scheduler  | APScheduler (BackgroundScheduler)             |
| Cloud      | boto3 (S3), google-api-python-client (Drive)  |
| Transfer   | ftplib (FTP), paramiko (SCP/SFTP)             |
| Notifikasi | smtplib (Email), Telegram Bot API (httpx)     |
| Enkripsi   | cryptography / Fernet (semua kredensial)      |

---

## Prasyarat

- **Python 3.10+** (diuji pada 3.14)
- **pip** dan kemampuan membuat virtual environment (`venv`)
- *(Opsional)* `mysqldump` / `pg_dump` di PATH bila ingin backup database
- *(Opsional)* Akun Google Cloud bila ingin memakai destinasi Google Drive

Cek versi Python:

```bash
python --version    # Linux/macOS
```
```powershell
python --version    # Windows
```

> Di sebagian distro Linux, gunakan `python3` dan `pip3`.

---

## Struktur Project

```
quenza-cloud-toolkit/
├── app/
│   ├── main.py                 # Entry FastAPI (middleware, static, routing, lifespan)
│   ├── config.py               # Konfigurasi dari .env (pydantic-settings)
│   ├── auth.py                 # Verifikasi bcrypt + guard login/API
│   ├── database.py             # Engine SQLite + session
│   ├── models.py               # Model ORM (Project, Source, Destination, Schedule, Log)
│   ├── scheduler.py            # APScheduler in-process
│   ├── templating.py           # Jinja2Templates terpusat
│   ├── routes/                 # auth, page, project, destination, filemanager, history
│   └── services/               # backup, archive, db_dump, restore, log, dashboard,
│       └── destinations/       #   crypto, gdrive_oauth + adapter Local/S3/Drive
├── templates/                  # base, login, dashboard, projects/, destinations,
│                               #   schedules, history, restore, partials/
├── static/                     # css/quenza.css + js/ (app, dashboard, filemanager, ...)
├── generate_hash.py            # Util: generate bcrypt hash Master Password
├── generate_key.py             # Util: generate Fernet ENCRYPTION_KEY
├── requirements.txt
└── .env.example
```

---

## Instalasi Otomatis (Direkomendasikan)

Cara tercepat: jalankan script instalasi yang menangani semuanya
(download → venv → dependencies → `.env` + Master Password → daftarkan
layanan auto-startup → jalankan). Anda cukup menunggu.

**Linux / macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/teguh02/quenza-cloud-toolkit/main/install.sh | bash
```

**Windows (PowerShell sebagai Administrator):**
```powershell
irm https://raw.githubusercontent.com/teguh02/quenza-cloud-toolkit/main/install.ps1 | iex
```

Detail lengkap, opsi, reverse proxy, dan pengelolaan layanan ada di
[`docs/INSTALL.md`](docs/INSTALL.md).

---

## Setup & Menjalankan (manual, dari awal)

Bila ingin memasang secara manual, langkah berikut tersedia untuk
**Windows (PowerShell)** dan **Linux/macOS (bash)**.

### 1. Clone repository

```bash
git clone https://github.com/teguh02/quenza-cloud-toolkit.git
cd quenza-cloud-toolkit
```

### 2. Buat & aktifkan virtual environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> Jika muncul error eksekusi script di PowerShell, jalankan sekali:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

**Linux/macOS (bash):**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Siapkan file `.env`

**Windows:**
```powershell
Copy-Item .env.example .env
```

**Linux/macOS:**
```bash
cp .env.example .env
```

### 5. Generate Master Password hash

```bash
python generate_hash.py
```
Ikuti prompt, lalu salin baris `MASTER_PASSWORD_HASH=...` ke dalam `.env`.

### 6. Generate SECRET_KEY

**Windows:**
```powershell
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
```
**Linux/macOS:**
```bash
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
```
Tempel hasilnya sebagai `SECRET_KEY=...` di `.env`.

### 7. Generate ENCRYPTION_KEY (untuk Google Drive; aman untuk selalu diisi)

```bash
python generate_key.py
```
Salin baris `ENCRYPTION_KEY=...` ke dalam `.env`.

### 8. Jalankan aplikasi

**Windows:**
```powershell
.\.venv\Scripts\uvicorn.exe app.main:app --reload
```
**Linux/macOS:**
```bash
uvicorn app.main:app --reload
```

Buka <http://127.0.0.1:8000> → Anda diarahkan ke halaman login. Masuk dengan
Master Password yang Anda buat di langkah 5.

> **Stop server:** `Ctrl + C`. **Ganti port:** tambahkan `--port 8080`.
> Database `quenza.db` dibuat otomatis saat pertama dijalankan.

---

## Menjalankan untuk Produksi (ringkas)

Gunakan beberapa worker tanpa `--reload`, dan set `DEBUG=false` di `.env`
(agar cookie session hanya via HTTPS):

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

> **Catatan scheduler:** APScheduler berjalan in-process. Bila memakai banyak
> worker, jadwal dapat ter-trigger lebih dari sekali. Untuk produksi dengan
> banyak worker, jalankan scheduler pada satu instance khusus atau gunakan
> 1 worker untuk proses yang menangani penjadwalan.

---

## Backup Database (opsional)

Backup sumber MySQL/PostgreSQL memanggil `mysqldump` / `pg_dump` lewat subprocess.

**Linux (contoh Debian/Ubuntu):**
```bash
sudo apt-get install mysql-client postgresql-client
```

**Windows:** pasang MySQL/PostgreSQL client tools, lalu (bila tidak di PATH)
set path eksplisit di `.env`:
```
MYSQLDUMP_PATH=C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe
PG_DUMP_PATH=C:\Program Files\PostgreSQL\16\bin\pg_dump.exe
```

Jika tool tidak ditemukan, hanya sumber database itu yang ditandai gagal —
backup sumber lain tetap berjalan.

---

## Integrasi Google Drive (OAuth)

Pengguna dapat menghubungkan akun Google Drive masing-masing lewat tombol
**Connect Google Drive** di halaman Destinations. Tiap akun menjadi satu
destinasi yang dapat dipilih per-project. Backup masuk ke Drive akun tersebut.

### Setup di Google Cloud Console
1. Buat project, lalu **Enable** Google Drive API.
2. **OAuth consent screen**: tipe *External*, scope `.../auth/drive.file`,
   tambahkan email Anda sebagai *Test user* (selama app belum diverifikasi
   Google, hanya test user yang dapat connect).
3. **Credentials → Create OAuth client ID → Web application**. Tambahkan
   *Authorized redirect URI* (harus sama persis dengan `GOOGLE_REDIRECT_URI`):
   `http://127.0.0.1:8000/destinations/gdrive/callback`
4. Salin **Client ID** & **Client Secret** ke `.env`.

### Setup di `.env`
```
GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxxx
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/destinations/gdrive/callback
```
Pastikan `ENCRYPTION_KEY` juga sudah diisi (langkah 7). Bila kredensial Google
atau `ENCRYPTION_KEY` belum diisi, tombol *Connect* nonaktif dengan peringatan
(aplikasi tetap berjalan normal untuk destinasi lain).

> **Scope `drive.file`**: aplikasi hanya dapat melihat/mengelola file yang
> dibuatnya sendiri — paling aman & tidak butuh verifikasi Google yang ketat.
> Restore hanya menemukan arsip yang dibuat Quenza.

---

## FTP & SCP/SSH (transfer antar-server)

Selain cloud, hasil backup dapat dikirim ke server lain:

- **FTP** — isi host, port (default 21), user, password, dan direktori tujuan.
  Menggunakan `ftplib` bawaan Python (tanpa dependency tambahan).
- **SCP / SSH** — transfer via SFTP menggunakan `paramiko`. Mendukung
  autentikasi **password** atau **private key** (tempel isi PEM atau path
  file + passphrase opsional).

Kredensial (password, private key, passphrase) disimpan **terenkripsi**
(butuh `ENCRYPTION_KEY`). Keduanya mendukung backup + restore penuh, dan
arsip otomatis dirapikan ke sub-folder per project.

---

## Settings: Zona Waktu & Notifikasi

Buka menu **Settings**:

- **Zona Waktu** — menentukan interpretasi jam penjadwalan dan tampilan waktu
  di seluruh aplikasi. Data tetap disimpan dalam UTC. Mengubah zona waktu
  otomatis menyinkronkan ulang jadwal.
- **Notifikasi** — pilih satu channel:
  - **Email** — konfigurasi SMTP (host/port/user/password/from) + hingga
    **3 email penerima**. Untuk Gmail, gunakan App Password.
  - **Telegram** — token bot dari `@BotFather` + Chat ID tujuan.

Gunakan tombol **Kirim Tes** untuk memverifikasi konfigurasi. Notifikasi
dikirim untuk setiap hasil backup & restore (atau hanya saat gagal, sesuai
pilihan). Kredensial SMTP/Telegram disimpan **terenkripsi** di database
(butuh `ENCRYPTION_KEY`).

---

## Management Console (`toolkit.py`)

Konsol bawaan untuk mengelola instalasi tanpa instal ulang. Jalankan dari
folder instalasi (gunakan Python venv):

```bash
./.venv/bin/python toolkit.py            # menu interaktif (Linux/macOS)
.\.venv\Scripts\python.exe toolkit.py    # Windows
```

Fitur: regenerate/set Master Password, regenerate `SECRET_KEY`/`ENCRYPTION_KEY`,
ubah Public URL, **start/stop/restart/status** layanan + lihat log, ringkasan
konfigurasi, **backup manual** per project, dan **cek & jalankan update** dari
GitHub. Tersedia juga mode CLI, mis.:

```bash
./.venv/bin/python toolkit.py regen-password   # lupa password? buat baru
./.venv/bin/python toolkit.py restart
./.venv/bin/python toolkit.py backup 1
./.venv/bin/python toolkit.py check-update     # cek versi terbaru
./.venv/bin/python toolkit.py update --yes     # update + reinstall deps + restart
```

Lihat detail di [`docs/INSTALL.md`](docs/INSTALL.md).

---

## Troubleshooting

| Gejala | Solusi |
| ------ | ------ |
| PowerShell menolak `Activate.ps1` | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| `uvicorn` tidak dikenali | Pastikan venv aktif, atau panggil `.\.venv\Scripts\uvicorn.exe` (Windows) |
| Port 8000 sudah dipakai | Tambah `--port 8080` (dan sesuaikan `GOOGLE_REDIRECT_URI` bila pakai Drive) |
| `redirect_uri_mismatch` (Google) | URI di Google Console harus sama persis dengan `GOOGLE_REDIRECT_URI` (tanpa trailing slash) |
| `access_blocked` / app not verified | Tambahkan email Anda sebagai **Test user** di OAuth consent screen |
| Tombol Connect Drive nonaktif | Isi `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, dan `ENCRYPTION_KEY` di `.env` |

---

## Catatan Keamanan

- Master Password **tidak pernah** disimpan plaintext; hanya hash bcrypt.
- Set `DEBUG=false` di produksi agar cookie session hanya dikirim via HTTPS.
- File `.env`, `*.db`, dan `backups/` sudah di-ignore oleh git.
- Refresh token Google Drive **dienkripsi** (Fernet) sebelum disimpan ke database.
- Restore memproteksi terhadap path traversal (zip-slip / tar-slip).

---

## Roadmap Fase

- [x] **Fase 1** — Inisialisasi & Autentikasi
- [x] **Fase 2** — Dashboard & Navigasi Inti (stat cards, line chart, quick actions)
- [x] **Fase 3** — Manajemen Pro## Future Work (Rencana Pengembangan)

Bagian ini mendokumentasikan rencana fitur berikutnya secara detail agar
kontributor lain (manusia maupun AI) dapat melanjutkan dengan konteks penuh.

**Status Saat Ini:**
- FW#1 (Docker Management) **Telah Selesai**.
- FW#3 (Background Jobs & Monitoring) **Telah Selesai**.
- FW#4 (Standalone File Manager) **Telah Selesai**.
- FW#5 (Security Module) **Telah Selesai**.

### Analisis Skala Prioritas Implementasi

Tersisa satu rancangan pengembangan utama:

**1. Skala Prioritas: FW#2 — Docker Backup**
   - **Tingkat Kesulitan:** Menengah.
   - **Dampak Kemanfaatan:** Menengah.
   - **Analisa:** Eksekusinya bergantung pada koneksi host Docker yang telah diselesaikan di FW#1. Alurnya akan berjalan mulus bersandar pada *background job* dari FW#3.

---

### Detail: FW#2 — Docker Backup (container & volume)

**Tujuan:** Backup container & volume Docker, memakai mekanisme job background
& monitoring dari FW#3.

**Keputusan desain:** Tipe **sumber backup baru** (selain
directory/file/mysql/postgres):
- **`docker_volume`** — backup isi named volume. Teknik standar: jalankan
  container helper sementara
  (`docker run --rm -v <volume>:/data -v <staging>:/backup alpine tar czf
  /backup/vol.tar.gz -C /data .`), atau via SDK `get_archive` pada container
  yang me-mount volume tersebut.
- **`docker_container`** — `docker export` (tar filesystem) dan/atau
  `docker commit` + `docker image save` (tar image). Pilihan di form
  (export filesystem vs save image).

**Integrasi:**
- Buat `docker_dump_service.py` (sejajar `db_dump_service.py`) untuk menghasilkan
  arsip volume/container ke staging dir.
- Tambah cabang tipe sumber Docker di `backup_service.run_backup` — hasil
  dibungkus ke arsip project dan diunggah ke destinasi seperti biasa
  (konsisten dengan alur yang ada).

**Risiko & catatan:**
- Backup volume "live" tanpa menghentikan container bisa **tidak konsisten**
  (mis. database aktif). Sediakan opsi stop → backup → start, atau peringatan
  konsistensi.
- Ukuran image/volume bisa besar → makin penting eksekusi background (FW#3) +
  progres realtime.
- **Restore** volume: ikuti filosofi restore pasif saat ini (download +
  extract); restore langsung ke volume tujuan dipertimbangkan terpisah.

**Estimasi kompleksitas:** Sedang (bergantung FW#1 untuk SDK/host & FW#3 untuk
job/progres).
