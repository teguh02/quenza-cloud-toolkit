# Changelog

Semua perubahan penting pada **Quenza Cloud Toolkit** dicatat di file ini.

Format mengikuti [Keep a Changelog](https://keepachangelog.com/id/1.1.0/),
dan proyek ini menggunakan [Semantic Versioning](https://semver.org/lang/id/).

## [Belum Dirilis]

### Ditambahkan
- **Fitur File Manager Standalone (FW#4)**: Menu mandiri untuk menjelajah, menambah, menghapus, dan mengubah *file*/*folder*. Aksi penghapusan dilindungi oleh *Math CAPTCHA* (penjumlahan angka acak) untuk mencegah *human-error*.
- **Manajemen Docker (FW#1)**: Tab khusus (Docker Mgmt) untuk mendeteksi *host* Docker secara otomatis serta melihat daftar *container* dan *volume* aktif di sistem.
- **Security Module - Tahap Akhir (FW#5)**: Tab khusus (Security) terintegrasi untuk:
  - Memantau metrik peladen secara *real-time* (*System Info*).
  - Mengelola *process* berjalan dengan fitur interaktif *Kill Task* (*Task Manager*).
  - Melakukan manajemen *rule* Firewall (*Adapter Pattern* untuk Linux `ufw` dan Windows `netsh`).
  - **Antivirus & Malware Scanner**: Integrasi mesin **ClamAV** dan **YARA** secara bersamaan. Laporan pemindaian tampil secara *real-time* dengan rincian pendeteksi di halaman History/Logs. Termasuk fitur penjadwalan otomatis.
  - Pemasangan **Otomatis**: Skrip `install.sh` dan menu *update* di `toolkit.py` sekarang secara otomatis memverifikasi dan memasang ClamAV di tingkat OS (*unattended*).
  - *Catatan Keamanan*: Fitur *Kill Task* dan modifikasi Firewall dilindungi ketat menggunakan *prompt Master Password* demi mitigasi tindakan keliru atau ancaman keamanan internal.

### Diperbaiki
- **Pemindaian Ganda**: Proses pemindaian tidak lagi langsung membatalkan seluruh operasi jika salah satu mesin pemindai (*database* YARA) belum diunduh, melainkan melanjutkan pemindaian dengan mesin yang masih tersedia (ClamAV).

---

## [1.3.0] - 2026-06-11

Management Console (`toolkit.py`) dan perbaikan installer.

### Ditambahkan
- **`toolkit.py` — Management Console** (interaktif + CLI) untuk mengelola
  instalasi tanpa instal ulang:
  - Regenerate / set **Master Password**, regenerate `SECRET_KEY` &
    `ENCRYPTION_KEY` (dengan peringatan keras).
  - Ubah **Public URL** / `GOOGLE_REDIRECT_URI`.
  - Kelola layanan: **status / start / stop / restart** + lihat log
    (deteksi otomatis systemd, dengan fallback manual; Windows best-effort).
  - Ringkasan konfigurasi `.env` (nilai rahasia disembunyikan).
  - **Backup manual** sebuah project langsung dari terminal.
- **Cek & jalankan update** (`toolkit.py check-update` / `update [--yes]`):
  - Deteksi versi via **git SHA** (`HEAD` vs `origin/main`); fallback
    **GitHub API** untuk instalasi non-git.
  - Pembaruan via `git reset --hard` (git) atau **unduh arsip + salin aman**
    (non-git) yang **mempertahankan** `.env`, `.venv`, database, dan
    `backups/`; lalu pasang ulang dependencies dan tawarkan restart layanan.

### Diperbaiki
- **Master Password & jenis layanan kosong di ringkasan installer.** Akar
  masalah: `run_step` menjalankan fungsi tahap dalam *pipeline subshell*
  sehingga variabel global (`MASTER_PASSWORD`, `SERVICE_KIND`) hilang.
  Diperbaiki memakai **process substitution** agar variabel bertahan.

### Keamanan
- Installer menulis Master Password awal ke `.initial_master_password.txt`
  (izin 600) sebagai cadangan, dengan instruksi menyalin lalu menghapusnya.

---

## [1.2.1] - 2026-06-11

Perbaikan ketangguhan installer (lingkungan Debian/Ubuntu).

### Diperbaiki
- **Virtual environment & pip kini dijamin fungsional.** Installer mendeteksi
  modul `venv`/`pip` yang belum lengkap (umum di Debian/Ubuntu, paket terpisah)
  lalu memasang `python3.X-venv` + `python3-pip` yang cocok dengan versi minor
  Python (mis. `python3.10-venv`), dengan fallback untuk `dnf`/`yum`/`pacman`/`zypper`.
- **`.venv` rusak dari percobaan gagal otomatis dibuat ulang.** Mengatasi error
  "No module named pip" saat menjalankan ulang installer.
- **Fallback pip berlapis**: `ensurepip` → unduh `get-pip.py` bila perlu, dengan
  verifikasi pip berfungsi sebelum memasang dependencies.
- **Log instalasi tidak lagi terduplikasi** (penjaga `IN_STEP` agar `log()` hanya
  menulis ke layar di dalam tahap; `tee` menangani berkas log).
- Penyelarasan pada `install.ps1` (rekreasi venv rusak + verifikasi pip).

---

## [1.2.0] - 2026-06-11

Script instalasi otomatis lintas-platform.

### Ditambahkan
- **`install.sh` (Linux/macOS)** dan **`install.ps1` (Windows)** — instalasi
  otomatis penuh: unduh project, cek prasyarat, buat virtual environment,
  pasang dependencies, generate `.env` dengan **Master Password acak terenkripsi**,
  daftarkan **layanan auto-startup** native, dan verifikasi via health check.
  - Linux: layanan **systemd** dengan fallback `nohup` + cron `@reboot`.
  - Windows: **NSSM** (Windows Service) dengan fallback **Task Scheduler**.
- **Indikator progres** per tahap: penghitung `[n/6]` + output proses real-time +
  status OK/gagal di setiap tahap.
- **Penawaran lapor isu ke GitHub** (prefilled dengan detail lingkungan) bila ada
  tahap yang gagal.
- **Ramah reverse proxy**: bind `0.0.0.0`, `--proxy-headers`, dan Public URL
  opsional yang otomatis mengisi `GOOGLE_REDIRECT_URI`.
- **`docs/INSTALL.md`** — panduan instalasi + perintah bootstrap satu baris +
  pengelolaan layanan.
- Section **Instalasi Otomatis** di README dan **galeri tampilan aplikasi**.

### Diperbaiki
- Unduh project memakai pola **clone ke direktori sementara lalu salin**, sehingga
  tidak gagal dengan "destination path already exists" pada folder tak-kosong.
- Pemasangan client database (`mysqldump`/`pg_dump`) dilaporkan **jujur** —
  verifikasi ulang per-tool dan saran `apt --fix-broken install` alih-alih klaim
  sukses palsu.
- Teks judul nyasar pada halaman login (blok duplikat di luar tag `<title>`).

---

## [1.1.0] - 2026-06-11

Integrasi cloud, notifikasi, pengaturan, dan destinasi transfer.

### Ditambahkan
- **Google Drive (OAuth)**: hubungkan akun per-destinasi lewat tombol
  *Connect Google Drive*; refresh token disimpan **terenkripsi**; folder backup
  dibuat otomatis bila Folder ID dikosongkan.
- **Halaman Settings**:
  - **Zona waktu global** — dipakai scheduler dan tampilan waktu di seluruh UI
    (penyimpanan tetap UTC).
  - **Notifikasi** — pilih satu channel: **Email** (SMTP, maks 3 penerima) atau
    **Telegram** (bot), lengkap dengan tombol **Kirim Tes**.
- **Notifikasi otomatis** pada setiap hasil backup & restore (best-effort, tidak
  menggagalkan operasi).
- **Destinasi baru**: **FTP** (`ftplib`) dan **SCP/SFTP** (`paramiko`, autentikasi
  password atau private key) — keduanya mendukung upload, list, dan restore.
- **Tombol "Backup Sekarang"** tambahan di kartu Penjadwalan (selain Run Backup).
- **Halaman dokumentasi `/help`** lengkap di dalam aplikasi.
- Utilitas **`generate_key.py`** untuk membuat `ENCRYPTION_KEY` (Fernet).
- **Organisasi sub-folder per-project** di seluruh destinasi (mis. S3 default
  `quenza-backups/<project>/`).

### Keamanan
- **Semua kredensial destinasi dienkripsi at-rest** (S3 secret key, password/
  private key FTP & SCP, refresh token Drive) via Fernet; dipertahankan saat
  diedit tanpa mengetik ulang.

### Dihapus
- **Mega.nz** dihapus — tidak ada pustaka Python yang kompatibel dengan
  Python 3.12+ (mega.py memakai `asyncio.coroutine` yang sudah dihapus).

### Diubah
- Adapter Google Drive beralih dari Service Account ke **OAuth per-akun**.

---

## [1.0.0] - 2026-06-11

Rilis awal Quenza Cloud Toolkit (Fase 1–5).

### Ditambahkan
- **Fondasi & Autentikasi** — FastAPI + Jinja2 + Tailwind (Quenza Design System),
  autentikasi **Master Password** tunggal (hash bcrypt + session cookie), SQLite.
- **Dashboard & Navigasi** — kartu statistik, grafik tren backup (Chart.js),
  Quick Actions, Recent Activity, dan sidebar responsif.
- **Manajemen Project** — CRUD project + **Integrated File Manager** untuk
  menjelajah direktori server (tree + content, checkbox, breadcrumb).
- **Sumber backup fleksibel** — direktori, file, database MySQL (`mysqldump`) &
  PostgreSQL (`pg_dump`); output `.zip` atau `.tar.gz` per project.
- **Mesin Backup & Destinasi** — pengarsipan + kompresi; destinasi Local,
  Amazon S3, Google Drive, Mega.nz (selektif per project).
- **Penjadwalan** — otomatis per project menggunakan APScheduler in-process.
- **Sistem Restore** — pasif & aman (download + extract), dengan proteksi
  path-traversal (zip-slip / tar-slip).
- **History/Logs** — pencatatan eksekusi backup/restore dengan filter & paginasi.

---

[Belum Dirilis]: https://github.com/teguh02/quenza-cloud-toolkit/compare/main...HEAD
[1.3.0]: https://github.com/teguh02/quenza-cloud-toolkit/commits/main
[1.2.1]: https://github.com/teguh02/quenza-cloud-toolkit/commits/main
[1.2.0]: https://github.com/teguh02/quenza-cloud-toolkit/commits/main
[1.1.0]: https://github.com/teguh02/quenza-cloud-toolkit/commits/main
[1.0.0]: https://github.com/teguh02/quenza-cloud-toolkit/commits/main
