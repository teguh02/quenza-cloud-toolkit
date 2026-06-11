# AGENTS.md

Panduan untuk agen AI yang melanjutkan pengembangan **Quenza Cloud Toolkit**.
Dokumen ini menjelaskan arsitektur, konvensi, perintah, dan aturan kerja agar
perubahan tetap konsisten dan aman.

> Manusia: baca `README.md` (fitur & instalasi) dan `CHANGELOG.md` (riwayat).
> Dokumen ini fokus pada hal teknis yang dibutuhkan agen.

---

## Ringkasan Proyek

Aplikasi web untuk **backup & restore** data server: buat project, pilih sumber
(direktori/file/MySQL/PostgreSQL), jadwalkan, kirim ke berbagai destinasi
(Local/S3/Google Drive/FTP/SCP), dan restore yang aman. Autentikasi memakai
**Master Password tunggal** (tanpa registrasi/multi-user). Mengikuti **Quenza
Design System**.

## Tumpukan Teknologi

- **Backend:** FastAPI + Uvicorn (Python 3.10+; diuji s.d. 3.14)
- **Frontend:** Jinja2 server-side + Tailwind CSS (Play CDN) + custom CSS
- **DB:** SQLite via SQLAlchemy 2.x (ORM, `Mapped`/`mapped_column`)
- **Scheduler:** APScheduler (BackgroundScheduler, in-process)
- **Cloud/Transfer:** boto3 (S3), google-api-python-client + google-auth-oauthlib
  (Drive OAuth), ftplib (FTP), paramiko (SCP/SFTP)
- **Keamanan:** bcrypt (Master Password), cryptography/Fernet (enkripsi kredensial)

## Struktur Direktori

```
app/
  main.py            # Entry FastAPI: middleware, static, lifespan, daftar router
  config.py          # Settings dari .env (pydantic-settings)
  database.py        # Engine SQLite + SessionLocal + Base
  models.py          # ORM: Project, BackupSource, Destination, Schedule,
                     #   BackupLog, AppSetting, AppMeta + enum
  auth.py            # Verifikasi bcrypt + guard (require_login, require_api_auth)
  scheduler.py       # APScheduler in-process (timezone global)
  templating.py      # Jinja2Templates + filter `localtime`
  routes/            # auth, page, project, destination, filemanager,
                     #   history, settings  (semua server-side, PRG pattern)
  services/          # Logika bisnis (lihat di bawah)
    destinations/    # Adapter: base, local, s3, gdrive, ftp, scp + registry
templates/           # base.html, login.html, dashboard.html, projects/,
                     #   destinations.html, schedules.html, history.html,
                     #   restore.html, settings.html, help.html, partials/
static/              # css/quenza.css + js/ (app, dashboard, filemanager,
                     #   modal, destinations, restore)
toolkit.py           # Management console (CLI + menu): password, layanan, update
generate_hash.py     # Util CLI: bcrypt hash untuk MASTER_PASSWORD_HASH
generate_key.py      # Util CLI: Fernet ENCRYPTION_KEY
install.sh / .ps1    # Installer otomatis (Linux/macOS & Windows)
docs/INSTALL.md      # Panduan instalasi & management console
```

### Service layer (`app/services/`)
`backup_service` (orkestrasi backup), `restore_service` (download+extract aman),
`archive_service` (zip/tar.gz), `db_dump_service` (mysqldump/pg_dump),
`destination_service` (CRUD destinasi + test), `schedule_service`,
`project_service`, `filemanager_service`, `log_service`, `dashboard_service`,
`settings_service` (timezone + notifikasi), `notification_service`
(email/telegram), `crypto` (Fernet), `gdrive_oauth` (OAuth flow).

---

## Setup Lingkungan

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

Konfigurasi `.env` (wajib untuk menjalankan):
```bash
cp .env.example .env
python generate_hash.py            # -> MASTER_PASSWORD_HASH
python -c "import secrets; print('SECRET_KEY='+secrets.token_urlsafe(48))"
python generate_key.py             # -> ENCRYPTION_KEY
```

## Menjalankan

```bash
uvicorn app.main:app --reload
# Windows: .\.venv\Scripts\uvicorn.exe app.main:app --reload
```
Buka `http://127.0.0.1:8000`. Health check: `GET /healthz`.

---

## Pengujian & Verifikasi (WAJIB sebelum menganggap tugas selesai)

Proyek ini **belum punya test suite formal**; verifikasi memakai pola berikut:

1. **Import bersih:**
   ```bash
   .\.venv\Scripts\python.exe -c "from app.main import app; print(len(app.routes))"
   ```
2. **Smoke test via Starlette `TestClient`** (httpx sudah ada). Pola: buat `.env`
   uji dengan DB terpisah (`DATABASE_URL=sqlite:///./quenza_test.db`), login,
   panggil endpoint, assert status/redirect, lalu **bersihkan** `.env` & `*.db`.
3. **Skrip shell:** `bash -n install.sh` (sintaks); PowerShell:
   `[System.Management.Automation.Language.Parser]::ParseFile(...)`.
4. **toolkit.py:** `python -m py_compile toolkit.py`; uji `toolkit.py config` /
   `check-update` secara terisolasi (jangan jalankan `update` pada working tree).
5. Selalu **hapus artefak uji** (`.env`, `quenza*.db`, `backups/`, `__pycache__/`)
   sebelum commit.

> Operasi nyata yang butuh sumber eksternal (S3/Drive/FTP/SCP/SMTP/Telegram,
> systemd/NSSM) **tidak bisa** diverifikasi penuh di sandbox — uji jalur kode
> dengan mock + graceful-failure, dan nyatakan batasan ini secara jujur.

---

## Konvensi Kode

- **Python:** type hints, docstring ringkas; error handling eksplisit
  (try/except) terutama untuk filesystem, subprocess, dan jaringan. Jangan biarkan
  kegagalan rutin melempar exception ke handler — kembalikan hasil terstruktur.
- **Routes:** server-side rendered (Jinja2). Mutasi pakai **POST + redirect**
  (PRG); umpan balik via query param `?msg=...&type=...` yang dirender partial
  `flash.html`. Guard tiap route dengan `require_login` (HTML) atau
  `require_api_auth` (JSON).
- **Service layer:** semua logika bisnis di `app/services/`; route tetap tipis.
- **Destinasi baru:** buat adapter di `app/services/destinations/` yang mewarisi
  `DestinationAdapter` (implement `upload`, `test_connection`, opsional
  `list_archives`/`download`), lalu daftarkan di `registry.py` (+ field spec UI).
  Rahasia field wajib `secret: True` agar dienkripsi.
- **Keamanan:** semua kredensial sensitif **dienkripsi** via `app.services.crypto`
  sebelum disimpan ke DB (`config_json`). Jangan pernah menampilkan/mlog nilai
  rahasia. Master Password hanya disimpan sebagai hash bcrypt.
- **Waktu:** simpan UTC; tampilkan via filter Jinja `localtime` (timezone global
  dari Settings). Scheduler memakai timezone global.
- **Frontend (Design System Quenza — patuhi):** warna brand `#22C55E→#14B8A6`,
  nav `#0EA5A4→#84CC16`, latar `#FFFFFF`/`#F5F7FA`, border `#E5E9F2`, pastel
  (biru/hijau/oranye/ungu), teks `#0F172A`/`#64748B`/`#94A3B8`, radius 12–20px,
  shadow halus, transisi 0.2–0.3s, font Inter.

---

## Aturan Git & Keamanan (PENTING)

- **JANGAN commit** rahasia/artefak: `.env`, `*.db`, `backups/`, `install.log`,
  `server.log`, `nssm/`, `.initial_master_password.txt`, `.quenza_version`,
  `.venv/`, `__pycache__/`. Semua sudah di `.gitignore` — verifikasi
  `git diff --cached --name-only` sebelum commit.
- Hanya commit/push **bila diminta** pengguna. Tulis pesan commit yang jelas
  mengikuti gaya repo (subjek ringkas + bullet body).
- Repo: `https://github.com/teguh02/quenza-cloud-toolkit` (branch `main`).
- Setelah mengubah fitur, **perbarui `CHANGELOG.md`** (format Keep a Changelog)
  dan dokumentasi terkait (`README.md`, `docs/INSTALL.md`).

---

## Alur Kerja Agen yang Disarankan

1. Pahami konteks: baca file relevan sebelum mengubah (jangan menebak).
2. Untuk perubahan multi-langkah, susun rencana/checklist tugas.
3. Implementasi bertahap; jaga route tetap tipis, logika di service.
4. Verifikasi (lihat bagian Pengujian) + bersihkan artefak uji.
5. Perbarui CHANGELOG + dokumen; laporkan batasan/asumsi secara jujur.
6. Jangan ubah perilaku yang tidak diminta; hormati arsitektur yang ada.

## Catatan & Keputusan Desain (konteks historis)

- **Mega.nz dihapus** — tidak ada pustaka Python kompatibel Python 3.12+.
- **Google Drive** memakai OAuth per-akun (bukan service account); scope
  `drive.file`; folder dibuat otomatis bila `folder_id` kosong.
- **SQLAlchemy 2.0.50** dipakai karena versi lama gagal mem-parse anotasi union
  di Python 3.14 (gunakan `Optional[...]` untuk kolom nullable).
- **Reverse-proxy friendly:** semua URL internal relatif; hanya
  `GOOGLE_REDIRECT_URI` yang absolut (dari `.env`). Service uvicorn dijalankan
  dengan `--proxy-headers`. App di-bind `0.0.0.0`, HTTP (`DEBUG=true`), TLS
  ditangani reverse proxy.
- **Restore** dilindungi dari path traversal (zip-slip/tar-slip).
