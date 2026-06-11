# Quenza Cloud Toolkit

Aplikasi web internal untuk manajemen **backup & restore** data server yang
sederhana, aman, dan terpusat. Mengikuti **Quenza Design System**.

> **Status:** Fase 1 — Inisialisasi & Autentikasi.

---

## Teknologi

| Komponen   | Pilihan                                   |
| ---------- | ----------------------------------------- |
| Backend    | FastAPI                                   |
| Frontend   | Jinja2 + Tailwind CSS (Play CDN) + custom CSS |
| Database   | SQLite (via SQLAlchemy)                   |
| Session    | Signed cookie (Starlette SessionMiddleware) |
| Auth       | Master Password (bcrypt hash di `.env`)   |

---

## Struktur Project

```
quenza-cloud-toolkit/
├── app/
│   ├── main.py              # Entry FastAPI (middleware, static, routing)
│   ├── config.py            # Konfigurasi dari .env (pydantic-settings)
│   ├── auth.py              # Verifikasi bcrypt + guard login
│   ├── database.py          # Engine SQLite + session
│   ├── models.py            # Model ORM (placeholder Fase 1)
│   ├── templating.py        # Jinja2Templates terpusat
│   └── routes/
│       └── auth_routes.py   # /login, /logout, / (dashboard)
├── templates/
│   ├── base.html            # App shell (sidebar + header + main)
│   ├── login.html           # Halaman login
│   ├── dashboard.html       # Dashboard (placeholder Fase 1)
│   └── partials/            # head, sidebar, header, icons/
├── static/
│   ├── css/quenza.css       # Custom CSS (transitions, scrollbar, responsif)
│   └── js/app.js            # Drawer sidebar + toggle password
├── generate_hash.py         # Util: generate bcrypt hash Master Password
├── requirements.txt
└── .env.example
```

---

## Setup & Menjalankan

### 1. Buat virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Siapkan `.env`

Salin `.env.example` menjadi `.env`:

```powershell
Copy-Item .env.example .env
```

Generate hash untuk Master Password Anda:

```powershell
python generate_hash.py
```

Salin baris `MASTER_PASSWORD_HASH=...` yang dihasilkan ke dalam `.env`.

Generate juga `SECRET_KEY`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Tempelkan hasilnya sebagai `SECRET_KEY=...` di `.env`.

### 4. Jalankan aplikasi

```powershell
uvicorn app.main:app --reload
```

Buka <http://127.0.0.1:8000> — Anda akan diarahkan ke halaman login.

---

## Catatan Keamanan

- Master Password **tidak pernah** disimpan dalam bentuk plaintext; hanya hash bcrypt.
- Set `DEBUG=false` di produksi agar cookie session hanya dikirim via HTTPS.
- File `.env` dan `*.db` sudah di-ignore oleh git.

---

## Roadmap Fase

- [x] **Fase 1** — Inisialisasi & Autentikasi
- [x] **Fase 2** — Dashboard & Navigasi Inti (stat cards, line chart, quick actions)
- [x] **Fase 3** — Manajemen Project & Integrated File Manager
- [x] **Fase 4** — Mesin Backup & Destinations (S3, Drive, Mega, scheduling)
- [x] **Fase 5** — Restore, Logging & Penyempurnaan
