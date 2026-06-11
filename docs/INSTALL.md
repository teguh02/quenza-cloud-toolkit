# Panduan Instalasi Otomatis — Quenza Cloud Toolkit

Script instalasi otomatis menangani **seluruh proses** dari awal hingga
aplikasi berjalan sebagai layanan (service) di sistem operasi Anda:

1. Mendeteksi sistem operasi, arsitektur, dan hak akses (root/Administrator).
2. Memeriksa prasyarat (Python 3.10+, git, dll).
3. Mengunduh project (via `git` atau arsip ZIP/tar.gz).
4. Membuat virtual environment & memasang dependencies.
5. Membuat `.env` lengkap dengan **Master Password acak terenkripsi**,
   `SECRET_KEY`, dan `ENCRYPTION_KEY`.
6. Mendaftarkan aplikasi sebagai **layanan auto-startup** yang native.
7. Menjalankan & memverifikasi layanan.

Bila ada tahap yang gagal, script menawarkan untuk **melaporkan isu** ke
GitHub secara otomatis (dengan detail lingkungan terisi).

> Anda cukup menunggu. Satu-satunya hal yang perlu dicatat adalah **Master
> Password** yang ditampilkan **sekali** di akhir instalasi.

---

## Prasyarat

- **Python 3.10+** (di Linux, script dapat memasangnya otomatis).
- Koneksi internet.
- Untuk mendaftarkan layanan: **root/sudo** (Linux) atau **Administrator**
  (Windows). Tanpa itu, Windows otomatis memakai Task Scheduler.

---

## Linux / macOS

### Cara 1 — Unduh lalu jalankan
```bash
git clone https://github.com/teguh02/quenza-cloud-toolkit.git
cd quenza-cloud-toolkit
bash install.sh
```

### Cara 2 — One-liner (bootstrap)
```bash
curl -fsSL https://raw.githubusercontent.com/teguh02/quenza-cloud-toolkit/main/install.sh | bash
```

> Jalankan dengan `sudo` bila ingin layanan terpasang untuk seluruh sistem:
> `curl -fsSL .../install.sh | sudo bash`

**Layanan:** menggunakan **systemd** (`quenza.service`). Pada sistem tanpa
systemd, fallback ke `nohup` + cron `@reboot`.

Kelola layanan (systemd):
```bash
sudo systemctl status quenza
sudo systemctl restart quenza
sudo journalctl -u quenza -f
```

---

## Windows (PowerShell)

Buka **PowerShell sebagai Administrator** (disarankan, agar terpasang sebagai
Windows Service).

### Cara 1 — Unduh lalu jalankan
```powershell
git clone https://github.com/teguh02/quenza-cloud-toolkit.git
cd quenza-cloud-toolkit
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

### Cara 2 — One-liner (bootstrap)
```powershell
irm https://raw.githubusercontent.com/teguh02/quenza-cloud-toolkit/main/install.ps1 | iex
```

> Jika muncul error kebijakan eksekusi, jalankan dulu:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

**Layanan:** menggunakan **NSSM** (diunduh otomatis) → Windows Service sejati.
Bila tidak dijalankan sebagai Administrator atau NSSM gagal, fallback ke
**Task Scheduler** (auto-start saat boot).

Kelola layanan (NSSM):
```powershell
sc query Quenza
.\nssm\nssm.exe restart Quenza   # dari folder instalasi
```

---

## Yang Ditanyakan Saat Instalasi

Script menanyakan beberapa hal di awal (semua punya nilai default):

| Pertanyaan        | Default                          | Keterangan |
| ----------------- | -------------------------------- | ---------- |
| Lokasi instalasi  | `~/quenza-cloud-toolkit` (Linux) / `%LOCALAPPDATA%\QuenzaCloudToolkit` (Windows) | Folder tujuan |
| Port aplikasi     | `8000`                           | Bila dipakai, ditawarkan port lain |
| Public URL        | _(kosong)_                       | Untuk reverse proxy + OAuth Drive |

Aplikasi selalu di-_bind_ ke `0.0.0.0` agar dapat diakses dari jaringan
(mis. di belakang reverse proxy).

---

## Reverse Proxy (HTTPS)

Aplikasi berjalan via **HTTP** dan dirancang untuk berada di belakang reverse
proxy (Nginx/Caddy/Traefik) yang menangani TLS. Service dijalankan dengan
`--proxy-headers --forwarded-allow-ips=*` sehingga menghormati header
`X-Forwarded-*` dari proxy.

Jika Anda mengisi **Public URL** (mis. `https://quenza.domain.com`) saat
instalasi, script otomatis menyetel `GOOGLE_REDIRECT_URI` ke
`https://quenza.domain.com/destinations/gdrive/callback`. Pastikan URI ini
juga didaftarkan di Google Cloud Console (lihat README → Integrasi Google
Drive).

---

## Setelah Instalasi

- Buka URL akses yang ditampilkan (mis. `http://<ip-server>:8000`).
- Login dengan **Master Password** yang ditampilkan di akhir instalasi.
- Atur zona waktu, notifikasi, destinasi, dan project Anda.

> **Lupa Master Password?** Buat hash baru:
> `./.venv/bin/python generate_hash.py` (Linux) atau
> `.\.venv\Scripts\python.exe generate_hash.py` (Windows), lalu tempel
> nilainya ke `MASTER_PASSWORD_HASH` di `.env`, dan restart layanan.

---

## Menjalankan Ulang Script

Script bersifat **idempotent** — aman dijalankan ulang. `.env` yang sudah ada
tidak ditimpa total; hanya kunci yang relevan diperbarui. Menjalankan ulang
juga dapat dipakai untuk memperbarui project (git pull) dan dependencies.

---

## Bila Terjadi Kegagalan

Script akan menampilkan tahap yang gagal beserta detail error, lalu menawarkan
untuk membuka halaman **GitHub Issues** dengan informasi lingkungan terisi
otomatis. Log lengkap tersimpan di `install.log` pada folder instalasi.

Laporkan manual di:
<https://github.com/teguh02/quenza-cloud-toolkit/issues>
