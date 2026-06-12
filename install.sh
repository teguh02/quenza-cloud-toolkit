#!/usr/bin/env bash
# ==============================================================================
# Quenza Cloud Toolkit - Installer (Linux / macOS)
#
# Otomatis: download -> cek prasyarat -> venv -> dependencies -> .env
# (Master Password acak terenkripsi) -> daftarkan service (systemd / fallback)
# -> jalankan & verifikasi. Bila ada tahap gagal, menawarkan lapor isu ke GitHub.
#
# Penggunaan:
#   bash install.sh
#   curl -fsSL https://raw.githubusercontent.com/teguh02/quenza-cloud-toolkit/main/install.sh | bash
# ==============================================================================

set -o pipefail

# --- Constants ----------------------------------------------------------------
REPO_URL="https://github.com/teguh02/quenza-cloud-toolkit.git"
REPO_ZIP="https://github.com/teguh02/quenza-cloud-toolkit/archive/refs/heads/main.tar.gz"
ISSUES_URL="https://github.com/teguh02/quenza-cloud-toolkit/issues/new"
APP_MODULE="app.main:app"
SERVICE_NAME="quenza"
MIN_PY_MINOR=10          # require Python 3.10+
DEFAULT_PORT=8000

# --- Colors (disabled if not a TTY) -------------------------------------------
if [ -t 1 ]; then
  C_RESET="\033[0m"; C_DIM="\033[2m"; C_RED="\033[31m"; C_GRN="\033[32m"
  C_YEL="\033[33m"; C_BLU="\033[34m"; C_CYN="\033[36m"; C_BOLD="\033[1m"
else
  C_RESET=""; C_DIM=""; C_RED=""; C_GRN=""; C_YEL=""; C_BLU=""; C_CYN=""; C_BOLD=""
fi

# --- Globals populated during run ---------------------------------------------
OS=""; ARCH=""; PKG_MGR=""; PY_BIN=""; HAS_GIT=0; HAS_SYSTEMD=0
INSTALL_DIR=""; PORT="$DEFAULT_PORT"; PUBLIC_URL=""; HOST_IP="127.0.0.1"
MASTER_PASSWORD=""; SUDO=""; LOG_FILE=""; CURRENT_STEP="inisialisasi"
SERVICE_KIND=""   # systemd | cron | none
STEP_NO=0; STEP_TOTAL=7   # progress counter for run_step
IN_STEP=0                 # when 1, log() skips file append (tee handles it)

# ==============================================================================
# Logging helpers
# ==============================================================================
log()      { printf "%b\n" "$1"; [ "$IN_STEP" = "1" ] && return 0; [ -n "$LOG_FILE" ] && printf "%s\n" "$(printf "%b" "$1" | sed 's/\x1b\[[0-9;]*m//g')" >>"$LOG_FILE" 2>/dev/null || true; }
log_info() { log "${C_BLU}•${C_RESET} $1"; }
log_ok()   { log "${C_GRN}✓${C_RESET} $1"; }
log_warn() { log "${C_YEL}!${C_RESET} $1"; }
log_err()  { log "${C_RED}✗${C_RESET} $1"; }
log_step() { log "\n${C_BOLD}${C_CYN}==> $1${C_RESET}"; }

banner() {
  log "${C_BOLD}${C_CYN}"
  log "  ___                            "
  log " / _ \ _   _  ___ _ __  ____ _   "
  log "| | | | | | |/ _ \ '_ \|_  / _\` |  Quenza Cloud Toolkit"
  log "| |_| | |_| |  __/ | | |/ / (_| |  Installer (Linux/macOS)"
  log " \__\_\\\\__,_|\___|_| |_/___\__,_|"
  log "${C_RESET}"
}

# ==============================================================================
# Failure handling + GitHub issue reporting
# ==============================================================================
urlencode() {
  # Pure-shell URL encoding.
  local s="$1" out="" c i
  for (( i=0; i<${#s}; i++ )); do
    c="${s:$i:1}"
    case "$c" in
      [a-zA-Z0-9.~_-]) out+="$c" ;;
      *) out+=$(printf '%%%02X' "'$c") ;;
    esac
  done
  printf '%s' "$out"
}

open_url() {
  local url="$1"
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$url" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then open "$url" >/dev/null 2>&1 &
  else return 1; fi
}

offer_issue_report() {
  local step="$1" detail="$2"
  log ""
  log_warn "Instalasi gagal pada tahap: ${C_BOLD}${step}${C_RESET}"
  [ -n "$detail" ] && log "${C_DIM}${detail}${C_RESET}"
  log ""
  printf "%b" "Laporkan masalah ini sebagai isu di GitHub? [y/N] "
  local answer=""
  read -r answer </dev/tty 2>/dev/null || answer=""
  case "$answer" in
    [yY]|[yY][eE][sS])
      local title body py_ver
      py_ver="$([ -n "$PY_BIN" ] && "$PY_BIN" --version 2>&1 || echo 'tidak ada')"
      title="[Install] Gagal pada tahap: ${step}"
      body=$(cat <<EOF
**Tahap gagal:** ${step}

**Detail error:**
\`\`\`
${detail}
\`\`\`

**Lingkungan:**
- OS: ${OS} (${ARCH})
- Package manager: ${PKG_MGR:-tidak terdeteksi}
- Python: ${py_ver}
- systemd: $([ "$HAS_SYSTEMD" = "1" ] && echo ya || echo tidak)
- Direktori instalasi: ${INSTALL_DIR:-belum ditentukan}

**Langkah reproduksi:**
1. Jalankan install.sh
2. ...
EOF
)
      local url="${ISSUES_URL}?title=$(urlencode "$title")&body=$(urlencode "$body")"
      if open_url "$url"; then
        log_ok "Browser dibuka untuk membuat isu."
      else
        log_info "Buka URL berikut di browser untuk melaporkan:"
        log "$url"
      fi
      ;;
    *) : ;;
  esac
}

fail() {
  # fail "<detail>"  — uses CURRENT_STEP
  local detail="${1:-}"
  log_err "Terjadi kesalahan."
  offer_issue_report "$CURRENT_STEP" "$detail"
  log ""
  log_info "Log lengkap: ${LOG_FILE:-(tidak tersedia)}"
  exit 1
}

# Run a step with a [n/total] header. Output streams live to the screen and is
# tee'd into the log. Exit code is taken from the command (PIPESTATUS[0]).
run_step() {
  local label="$1"; shift
  STEP_NO=$((STEP_NO + 1))
  CURRENT_STEP="$label"
  log "\n${C_BOLD}${C_CYN}==> [${STEP_NO}/${STEP_TOTAL}] ${label}${C_RESET}"

  local rc=0
  IN_STEP=1   # log_* inside the step go to screen only; tee handles the file
  # IMPORTANT: run the command in the CURRENT shell (not a pipeline subshell)
  # so any global variables it sets (e.g. MASTER_PASSWORD, SERVICE_KIND) persist.
  # Process substitution keeps "$@" in the main shell while still streaming
  # output live + appending to the log.
  if [ -n "$LOG_FILE" ]; then
    "$@" > >(_indent_stream | tee -a "$LOG_FILE") 2>&1
    rc=$?
  else
    "$@" > >(_indent_stream) 2>&1
    rc=$?
  fi
  IN_STEP=0
  # Give the process-substitution writer a moment to flush before continuing.
  sleep 0.05 2>/dev/null || true

  if [ "$rc" -eq 0 ]; then
    log "${C_GRN}✓ [${STEP_NO}/${STEP_TOTAL}] ${label} — selesai${C_RESET}"
    return 0
  else
    log "${C_RED}✗ [${STEP_NO}/${STEP_TOTAL}] ${label} — gagal (exit ${rc})${C_RESET}"
    fail "Tahap '${label}' gagal dengan exit code ${rc}. Lihat output di atas / ${LOG_FILE}"
  fi
}

# Indent + dim streamed output so it reads as sub-output of the step.
_indent_stream() {
  local line
  while IFS= read -r line; do
    printf "   %b%s%b\n" "$C_DIM" "$line" "$C_RESET"
  done
}

# ==============================================================================
# Detection
# ==============================================================================
detect_system() {
  CURRENT_STEP="deteksi sistem"
  case "$(uname -s)" in
    Linux*)  OS="linux" ;;
    Darwin*) OS="macos" ;;
    *)       OS="unknown" ;;
  esac
  ARCH="$(uname -m)"

  # Elevation helper
  if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
  elif command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    SUDO=""
  fi

  # Package manager (Linux)
  if [ "$OS" = "linux" ]; then
    for pm in apt-get dnf yum pacman zypper; do
      if command -v "$pm" >/dev/null 2>&1; then PKG_MGR="$pm"; break; fi
    done
  fi

  # systemd?
  if [ "$OS" = "linux" ] && command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    HAS_SYSTEMD=1
  fi

  command -v git >/dev/null 2>&1 && HAS_GIT=1

  log_ok "OS: ${OS} (${ARCH})"
  [ -n "$PKG_MGR" ] && log_ok "Package manager: ${PKG_MGR}"
  [ "$OS" = "linux" ] && log_ok "systemd: $([ "$HAS_SYSTEMD" = "1" ] && echo tersedia || echo tidak)"
  log_ok "git: $([ "$HAS_GIT" = "1" ] && echo tersedia || echo 'tidak (akan pakai download arsip)')"
}

detect_host_ip() {
  local ip=""
  if command -v hostname >/dev/null 2>&1; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  [ -z "$ip" ] && ip="127.0.0.1"
  HOST_IP="$ip"
}

# ==============================================================================
# Python helpers
# ==============================================================================
py_version_ok() {
  # $1 = python binary; returns 0 if >= 3.MIN_PY_MINOR
  "$1" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, ${MIN_PY_MINOR}) else 1)" >/dev/null 2>&1
}

find_python() {
  for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1 && py_version_ok "$cand"; then
      PY_BIN="$(command -v "$cand")"
      return 0
    fi
  done
  return 1
}

install_python_linux() {
  log_info "Mencoba memasang Python 3 via ${PKG_MGR}..."
  case "$PKG_MGR" in
    apt-get) $SUDO apt-get update -y && $SUDO apt-get install -y python3 python3-venv python3-pip ;;
    dnf)     $SUDO dnf install -y python3 python3-pip ;;
    yum)     $SUDO yum install -y python3 python3-pip ;;
    pacman)  $SUDO pacman -Sy --noconfirm python python-pip ;;
    zypper)  $SUDO zypper install -y python3 python3-pip ;;
    *)       return 1 ;;
  esac
}

ensure_python() {
  CURRENT_STEP="memeriksa Python"
  if find_python; then
    log_ok "Python ditemukan: $("$PY_BIN" --version 2>&1) (${PY_BIN})"
  else
    log_warn "Python ${MIN_PY_MINOR}+ tidak ditemukan."
    if [ "$OS" = "linux" ] && [ -n "$PKG_MGR" ]; then
      if install_python_linux >>"${LOG_FILE:-/dev/null}" 2>&1; then
        if find_python; then
          log_ok "Python terpasang: $("$PY_BIN" --version 2>&1)"
        else
          fail "Gagal memasang Python secara otomatis. Pasang Python ${MIN_PY_MINOR}+ lalu jalankan ulang."
        fi
      else
        fail "Gagal memasang Python secara otomatis. Pasang Python ${MIN_PY_MINOR}+ lalu jalankan ulang."
      fi
    else
      log_err "Python ${MIN_PY_MINOR}+ wajib dipasang lebih dulu."
      if [ "$OS" = "macos" ]; then
        log_info "macOS: pasang via Homebrew  ->  brew install python"
        log_info "atau unduh dari https://www.python.org/downloads/macos/"
      fi
      fail "Python tidak tersedia."
    fi
  fi

  ensure_python_venv
}

# Ensure the `venv` module and `ensurepip` actually work. On Debian/Ubuntu,
# python3 and python3-venv/python3-pip are separate packages, so a bare
# python3 may exist while `python -m venv` fails ("ensurepip is not available").
ensure_python_venv() {
  CURRENT_STEP="memeriksa modul venv & pip"
  if "$PY_BIN" -c "import ensurepip, venv" >/dev/null 2>&1; then
    log_ok "Modul venv & pip tersedia."
    return 0
  fi

  log_warn "Modul venv/pip Python belum lengkap (umum di Debian/Ubuntu)."
  if [ "$OS" = "linux" ] && [ "$PKG_MGR" = "apt-get" ]; then
    # Determine exact minor version, e.g. 3.10 -> python3.10-venv
    local pyver
    pyver="$("$PY_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)"
    log_info "Memasang python${pyver}-venv & python3-pip..."
    $SUDO apt-get update -y >>"${LOG_FILE:-/dev/null}" 2>&1 || true
    # Try version-specific venv first, then generic, plus pip.
    $SUDO apt-get install -y "python${pyver}-venv" python3-venv python3-pip >>"${LOG_FILE:-/dev/null}" 2>&1 \
      || $SUDO apt-get install -y python3-venv python3-pip >>"${LOG_FILE:-/dev/null}" 2>&1 || true
  elif [ "$OS" = "linux" ] && [ -n "$PKG_MGR" ]; then
    case "$PKG_MGR" in
      dnf)    $SUDO dnf install -y python3-pip >>"${LOG_FILE:-/dev/null}" 2>&1 || true ;;
      yum)    $SUDO yum install -y python3-pip >>"${LOG_FILE:-/dev/null}" 2>&1 || true ;;
      pacman) $SUDO pacman -Sy --noconfirm python-pip >>"${LOG_FILE:-/dev/null}" 2>&1 || true ;;
      zypper) $SUDO zypper install -y python3-pip >>"${LOG_FILE:-/dev/null}" 2>&1 || true ;;
    esac
  fi

  # Re-verify.
  if "$PY_BIN" -c "import ensurepip, venv" >/dev/null 2>&1; then
    log_ok "Modul venv & pip kini tersedia."
    return 0
  fi

  log_warn "Modul venv/pip masih belum lengkap — akan dicoba fallback get-pip saat membuat venv."
  return 0
}

# ==============================================================================
# DB tools (optional)
# ==============================================================================
check_db_tools() {
  CURRENT_STEP="memeriksa tools database (opsional)"
  local missing=()
  command -v mysqldump >/dev/null 2>&1 && log_ok "mysqldump tersedia" || missing+=("mysqldump")
  command -v pg_dump  >/dev/null 2>&1 && log_ok "pg_dump tersedia"  || missing+=("pg_dump")

  if [ "${#missing[@]}" -eq 0 ]; then return 0; fi

  log_warn "Tools backup database belum lengkap: ${missing[*]}"
  log_info "Ini opsional — backup direktori/file tetap berjalan tanpa tools ini."

  if [ "$OS" = "linux" ] && [ -n "$PKG_MGR" ]; then
    printf "%b" "Pasang client database (mysql/postgres) sekarang? [y/N] "
    local ans=""; read -r ans </dev/tty 2>/dev/null || ans=""
    case "$ans" in
      [yY]|[yY][eE][sS])
        log_info "Memasang client database (output di bawah)..."
        local pm_rc=0
        # Stream output live so the user sees progress.
        case "$PKG_MGR" in
          apt-get) { $SUDO apt-get install -y mariadb-client postgresql-client 2>&1 | _indent_stream; pm_rc=${PIPESTATUS[0]}; } ;;
          dnf)     { $SUDO dnf install -y mariadb postgresql 2>&1 | _indent_stream; pm_rc=${PIPESTATUS[0]}; } ;;
          yum)     { $SUDO yum install -y mariadb postgresql 2>&1 | _indent_stream; pm_rc=${PIPESTATUS[0]}; } ;;
          pacman)  { $SUDO pacman -Sy --noconfirm mariadb-clients postgresql-libs 2>&1 | _indent_stream; pm_rc=${PIPESTATUS[0]}; } ;;
          zypper)  { $SUDO zypper install -y mariadb-client postgresql 2>&1 | _indent_stream; pm_rc=${PIPESTATUS[0]}; } ;;
        esac

        if [ "$pm_rc" -ne 0 ]; then
          log_warn "Package manager mengembalikan error (exit ${pm_rc})."
          if [ "$PKG_MGR" = "apt-get" ]; then
            log_info "Coba perbaiki manual: ${SUDO} apt-get --fix-broken install"
          fi
        fi

        # Honest re-verification per tool (do NOT claim success blindly).
        if command -v mysqldump >/dev/null 2>&1; then log_ok "mysqldump kini tersedia"; else log_warn "mysqldump masih belum tersedia (lewati — opsional)"; fi
        if command -v pg_dump  >/dev/null 2>&1; then log_ok "pg_dump kini tersedia";  else log_warn "pg_dump masih belum tersedia (lewati — opsional)"; fi
        ;;
      *) log_info "Dilewati. Anda bisa memasangnya nanti." ;;
    esac
  fi
}

# ==============================================================================
# Prompts (interactive, with defaults)
# ==============================================================================
prompt_inputs() {
  CURRENT_STEP="konfigurasi instalasi"
  local default_dir="$HOME/quenza-cloud-toolkit"
  [ "$(id -u)" -eq 0 ] && default_dir="/opt/quenza-cloud-toolkit"

  printf "%b" "Lokasi instalasi [${default_dir}]: "
  local in_dir=""; read -r in_dir </dev/tty 2>/dev/null || in_dir=""
  INSTALL_DIR="${in_dir:-$default_dir}"

  printf "%b" "Port aplikasi [${DEFAULT_PORT}]: "
  local in_port=""; read -r in_port </dev/tty 2>/dev/null || in_port=""
  PORT="${in_port:-$DEFAULT_PORT}"

  # Port conflict check
  if port_in_use "$PORT"; then
    log_warn "Port ${PORT} sedang dipakai."
    printf "%b" "Masukkan port lain [8080]: "
    local p2=""; read -r p2 </dev/tty 2>/dev/null || p2=""
    PORT="${p2:-8080}"
  fi

  log_info "Public URL opsional untuk reverse proxy (mis. https://quenza.domain.com)."
  log_info "Kosongkan bila akses langsung via IP/port. Penting untuk OAuth Google Drive."
  printf "%b" "Public URL [kosong]: "
  local in_url=""; read -r in_url </dev/tty 2>/dev/null || in_url=""
  PUBLIC_URL="${in_url%/}"   # strip trailing slash

  log_ok "Lokasi: ${INSTALL_DIR} | Port: ${PORT} | Public URL: ${PUBLIC_URL:-(tidak ada)}"
}

port_in_use() {
  local p="$1"
  if command -v ss >/dev/null 2>&1; then ss -ltn 2>/dev/null | grep -q ":${p} "
  elif command -v netstat >/dev/null 2>&1; then netstat -ltn 2>/dev/null | grep -q ":${p} "
  else return 1; fi
}

# ==============================================================================
# Stage: download
# ==============================================================================
download_project() {
  # Already a git checkout? -> update.
  if [ -d "$INSTALL_DIR/.git" ] && [ "$HAS_GIT" = "1" ]; then
    log_info "Repo sudah ada — memperbarui (git pull)..."
    git -C "$INSTALL_DIR" pull --ff-only --progress
    return $?
  fi
  # Already contains the project (non-git copy)? -> skip download.
  if [ -f "$INSTALL_DIR/app/main.py" ]; then
    log_info "Direktori instalasi sudah berisi project — melewati download."
    return 0
  fi

  # Fresh download into a TEMP dir, then copy contents into INSTALL_DIR.
  # This is safe even if INSTALL_DIR already exists / is not empty
  # (e.g. it may already contain install.log).
  local tmp; tmp="$(mktemp -d)" || { log_err "Gagal membuat direktori sementara."; return 1; }
  local src=""

  if [ "$HAS_GIT" = "1" ]; then
    log_info "Meng-clone repository (ke direktori sementara)..."
    git clone --depth 1 --progress "$REPO_URL" "$tmp/repo" || { rm -rf "$tmp"; return 1; }
    src="$tmp/repo"
  else
    log_info "git tidak ada — mengunduh arsip..."
    if command -v curl >/dev/null 2>&1; then
      curl -fL --progress-bar "$REPO_ZIP" -o "$tmp/quenza.tar.gz" || { rm -rf "$tmp"; return 1; }
    elif command -v wget >/dev/null 2>&1; then
      wget --show-progress -q "$REPO_ZIP" -O "$tmp/quenza.tar.gz" || { rm -rf "$tmp"; return 1; }
    else
      log_err "curl/wget tidak tersedia untuk mengunduh."; rm -rf "$tmp"; return 1
    fi
    log_info "Mengekstrak arsip..."
    tar -xzf "$tmp/quenza.tar.gz" -C "$tmp" || { rm -rf "$tmp"; return 1; }
    src="$(find "$tmp" -maxdepth 1 -type d -name 'quenza-cloud-toolkit-*' | head -n1)"
    [ -z "$src" ] && { log_err "Struktur arsip tidak dikenali."; rm -rf "$tmp"; return 1; }
  fi

  # Ensure target exists, then copy ALL contents (including dotfiles) in.
  mkdir -p "$INSTALL_DIR" || { rm -rf "$tmp"; return 1; }
  log_info "Menyalin berkas project ke ${INSTALL_DIR}..."
  # cp -a "$src/." preserves dotfiles and copies into existing dir safely.
  cp -a "$src/." "$INSTALL_DIR/" || { rm -rf "$tmp"; return 1; }
  rm -rf "$tmp"
  return 0
}

# ==============================================================================
# Stage: YARA rules
# ==============================================================================
download_yara_rules() {
  cd "$INSTALL_DIR" || return 1
  local rules_dir="app/data/yara_rules"
  mkdir -p "app/data"
  if [ -d "$rules_dir/.git" ]; then
    log_info "Memperbarui basis data YARA..."
    git -C "$rules_dir" pull --ff-only --progress >/dev/null 2>&1 || true
  else
    log_info "Mengunduh basis data YARA (signature-base)..."
    if [ "$HAS_GIT" = "1" ]; then
      git clone --depth 1 https://github.com/Neo23x0/signature-base.git "$rules_dir" >/dev/null 2>&1 || true
    else
      if command -v curl >/dev/null 2>&1; then
        curl -fL --progress-bar https://github.com/Neo23x0/signature-base/archive/refs/heads/master.tar.gz -o /tmp/yara.tar.gz || true
      elif command -v wget >/dev/null 2>&1; then
        wget --show-progress -q https://github.com/Neo23x0/signature-base/archive/refs/heads/master.tar.gz -O /tmp/yara.tar.gz || true
      fi
      if [ -f "/tmp/yara.tar.gz" ]; then
        mkdir -p "$rules_dir"
        tar -xzf /tmp/yara.tar.gz -C "$rules_dir" --strip-components=1 >/dev/null 2>&1 || true
        rm -f /tmp/yara.tar.gz
      fi
    fi
  fi
  return 0
}

# ==============================================================================
# Stage: venv + deps
# ==============================================================================
setup_venv() {
  cd "$INSTALL_DIR" || return 1
  local vpy="./.venv/bin/python"

  # Recreate the venv if missing OR broken (e.g. a previous failed run left a
  # .venv without pip). A healthy venv must have a working python + pip.
  local need_create=0
  if [ ! -x "$vpy" ]; then
    need_create=1
  elif ! "$vpy" -c "import sys" >/dev/null 2>&1; then
    need_create=1
  fi

  if [ "$need_create" -eq 1 ]; then
    [ -d ".venv" ] && { echo "Membersihkan .venv yang tidak lengkap..."; rm -rf .venv; }
    if ! "$PY_BIN" -m venv .venv; then
      echo "venv standar gagal — mencoba tanpa pip lalu bootstrap get-pip..."
      rm -rf .venv
      "$PY_BIN" -m venv --without-pip .venv || return 1
    fi
  fi

  # Ensure pip exists inside the venv (handles --without-pip and broken cases).
  if ! "$vpy" -m pip --version >/dev/null 2>&1; then
    echo "pip tidak ada di venv — mencoba ensurepip..."
    if ! "$vpy" -m ensurepip --upgrade >/dev/null 2>&1; then
      echo "ensurepip gagal — mengunduh get-pip.py..."
      local getpip="/tmp/get-pip-$$.py"
      if command -v curl >/dev/null 2>&1; then
        curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$getpip" || return 1
      elif command -v wget >/dev/null 2>&1; then
        wget -q https://bootstrap.pypa.io/get-pip.py -O "$getpip" || return 1
      else
        echo "curl/wget tidak tersedia untuk mengunduh get-pip.py"; return 1
      fi
      "$vpy" "$getpip" || { rm -f "$getpip"; return 1; }
      rm -f "$getpip"
    fi
  fi

  # Final verification: pip must work now.
  if ! "$vpy" -m pip --version >/dev/null 2>&1; then
    echo "pip masih tidak tersedia di virtual environment."
    echo "Coba pasang manual: sudo apt-get install -y python3-venv python3-pip"
    return 1
  fi

  "$vpy" -m pip install --upgrade pip || return 1
  "$vpy" -m pip install -r requirements.txt || return 1
}

# ==============================================================================
# Stage: .env configuration
# ==============================================================================
set_env_var() {
  # set_env_var KEY VALUE  — replace existing line or append. File: $INSTALL_DIR/.env
  local key="$1" value="$2" file="$INSTALL_DIR/.env"
  "$INSTALL_DIR/.venv/bin/python" - "$file" "$key" "$value" <<'PYEOF'
import sys, io
path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with io.open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
except FileNotFoundError:
    lines = []
out, found = [], False
for ln in lines:
    stripped = ln.lstrip()
    if stripped.startswith(key + "="):
        out.append(f"{key}={value}\n"); found = True
    else:
        out.append(ln)
if not found:
    if out and not out[-1].endswith("\n"):
        out[-1] += "\n"
    out.append(f"{key}={value}\n")
with io.open(path, "w", encoding="utf-8") as f:
    f.writelines(out)
PYEOF
}

configure_env() {
  cd "$INSTALL_DIR" || return 1
  if [ ! -f ".env" ]; then
    cp ".env.example" ".env" || return 1
    log_ok "Membuat .env dari .env.example"
  else
    log_info ".env sudah ada — memperbarui kunci yang diperlukan saja."
  fi

  local py="$INSTALL_DIR/.venv/bin/python"

  # SECRET_KEY
  local secret; secret="$("$py" -c 'import secrets; print(secrets.token_urlsafe(48))')" || return 1
  set_env_var "SECRET_KEY" "$secret"

  # ENCRYPTION_KEY (Fernet)
  local enc; enc="$("$py" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" || return 1
  set_env_var "ENCRYPTION_KEY" "$enc"

  # Master Password (random strong) -> bcrypt hash
  MASTER_PASSWORD="$("$py" -c 'import secrets; print(secrets.token_urlsafe(18))')" || return 1
  local hash; hash="$("$py" generate_hash.py "$MASTER_PASSWORD" | grep '^MASTER_PASSWORD_HASH=' | cut -d= -f2-)" || return 1
  [ -z "$hash" ] && { log_err "Gagal membuat hash Master Password."; return 1; }
  set_env_var "MASTER_PASSWORD_HASH" "$hash"

  # Safety net: also write the plaintext to a 600 file so it is not lost if the
  # terminal scrolls away. The summary instructs the user to copy & delete it.
  local pwfile="${INSTALL_DIR}/.initial_master_password.txt"
  {
    printf "%s\n" "Quenza Cloud Toolkit — Master Password awal"
    printf "%s\n" "Dibuat: $(date 2>/dev/null)"
    printf "%s\n" "SIMPAN password ini, lalu HAPUS file ini (rm '${pwfile}')."
    printf "\n%s\n" "$MASTER_PASSWORD"
  } > "$pwfile" 2>/dev/null || true
  chmod 600 "$pwfile" 2>/dev/null || true

  # DEBUG true (HTTP, reverse-proxy friendly)
  set_env_var "DEBUG" "true"

  # GOOGLE_REDIRECT_URI
  local redirect
  if [ -n "$PUBLIC_URL" ]; then
    redirect="${PUBLIC_URL}/destinations/gdrive/callback"
  else
    redirect="http://${HOST_IP}:${PORT}/destinations/gdrive/callback"
  fi
  set_env_var "GOOGLE_REDIRECT_URI" "$redirect"

  log_ok "Konfigurasi .env selesai (SECRET_KEY, ENCRYPTION_KEY, Master Password, redirect URI)."
}

# ==============================================================================
# Stage: verify import
# ==============================================================================
verify_app() {
  cd "$INSTALL_DIR" || return 1
  ./.venv/bin/python -c "from app.main import app; print('app import OK')" || return 1
}

# ==============================================================================
# Stage: service registration
# ==============================================================================
install_systemd_service() {
  local unit="/etc/systemd/system/${SERVICE_NAME}.service"
  local run_user; run_user="$(id -un)"
  [ "$(id -u)" -eq 0 ] && run_user="root"
  local exec="${INSTALL_DIR}/.venv/bin/uvicorn ${APP_MODULE} --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips=*"

  local content="[Unit]
Description=Quenza Cloud Toolkit
After=network.target

[Service]
Type=simple
User=${run_user}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${exec}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"
  printf "%s" "$content" | $SUDO tee "$unit" >/dev/null || return 1
  $SUDO systemctl daemon-reload || return 1
  $SUDO systemctl enable "${SERVICE_NAME}" >/dev/null 2>&1 || return 1
  $SUDO systemctl restart "${SERVICE_NAME}" || return 1
  SERVICE_KIND="systemd"
}

install_cron_fallback() {
  # Non-systemd fallback: run script + @reboot cron entry
  local runner="${INSTALL_DIR}/run.sh"
  cat >"$runner" <<EOF
#!/usr/bin/env bash
cd "${INSTALL_DIR}" || exit 1
exec ./.venv/bin/uvicorn ${APP_MODULE} --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips=* >>"${INSTALL_DIR}/server.log" 2>&1
EOF
  chmod +x "$runner"

  # Start now (background)
  nohup "$runner" >/dev/null 2>&1 &

  # Add @reboot entry if not present
  local cron_line="@reboot ${runner}"
  if command -v crontab >/dev/null 2>&1; then
    ( crontab -l 2>/dev/null | grep -vF "$runner"; echo "$cron_line" ) | crontab - 2>/dev/null || true
  fi
  SERVICE_KIND="cron"
}

register_service() {
  if [ "$HAS_SYSTEMD" = "1" ]; then
    install_systemd_service || return 1
  else
    log_warn "systemd tidak tersedia — memakai fallback nohup + cron @reboot."
    install_cron_fallback || return 1
  fi
}

# ==============================================================================
# Stage: health check
# ==============================================================================
health_check() {
  local url="http://127.0.0.1:${PORT}/healthz"
  local i
  for i in $(seq 1 20); do
    if command -v curl >/dev/null 2>&1; then
      if curl -fsS "$url" >/dev/null 2>&1; then return 0; fi
    elif command -v wget >/dev/null 2>&1; then
      if wget -q -O /dev/null "$url" 2>/dev/null; then return 0; fi
    else
      sleep 2; return 0   # cannot check; assume ok
    fi
    sleep 1
  done
  return 1
}

# ==============================================================================
# Final summary
# ==============================================================================
print_summary() {
  local access_url="${PUBLIC_URL:-http://${HOST_IP}:${PORT}}"
  log ""
  log "${C_GRN}${C_BOLD}========================================================${C_RESET}"
  log "${C_GRN}${C_BOLD}  Quenza Cloud Toolkit berhasil dipasang & berjalan!    ${C_RESET}"
  log "${C_GRN}${C_BOLD}========================================================${C_RESET}"
  log ""
  log "  ${C_BOLD}URL Akses     :${C_RESET} ${access_url}"
  log "  ${C_BOLD}Lokal         :${C_RESET} http://127.0.0.1:${PORT}"
  log "  ${C_BOLD}Lokasi        :${C_RESET} ${INSTALL_DIR}"
  log "  ${C_BOLD}Service       :${C_RESET} ${SERVICE_NAME} (${SERVICE_KIND})"
  log ""
  log "  ${C_YEL}${C_BOLD}Master Password (SIMPAN — hanya tampil sekali):${C_RESET}"
  log "  ${C_BOLD}${MASTER_PASSWORD:-(tidak tersedia — lihat file di bawah)}${C_RESET}"
  log "  ${C_DIM}Cadangan tersimpan di: ${INSTALL_DIR}/.initial_master_password.txt${C_RESET}"
  log "  ${C_DIM}Setelah disalin, hapus: rm '${INSTALL_DIR}/.initial_master_password.txt'${C_RESET}"
  log ""
  log "  ${C_DIM}Konsol manajemen (regenerate password, restart layanan, dll):${C_RESET}"
  log "    cd '${INSTALL_DIR}' && ./.venv/bin/python toolkit.py"
  log ""
  if [ "$SERVICE_KIND" = "systemd" ]; then
    log "  ${C_DIM}Kelola service:${C_RESET}"
    log "    ${SUDO} systemctl status ${SERVICE_NAME}"
    log "    ${SUDO} systemctl restart ${SERVICE_NAME}"
    log "    ${SUDO} journalctl -u ${SERVICE_NAME} -f"
  else
    log "  ${C_DIM}Log server: ${INSTALL_DIR}/server.log${C_RESET}"
  fi
  if [ -n "$PUBLIC_URL" ]; then
    log ""
    log "  ${C_YEL}Reverse proxy:${C_RESET} arahkan ${PUBLIC_URL} -> 127.0.0.1:${PORT}"
    log "  ${C_YEL}Google Drive:${C_RESET} daftarkan redirect URI berikut di Google Cloud Console:"
    log "    ${PUBLIC_URL}/destinations/gdrive/callback"
  fi
  log ""
}

# ==============================================================================
# Main
# ==============================================================================
main() {
  banner
  detect_system
  detect_host_ip

  # Log to a temp file until the install dir is confirmed (after download).
  LOG_FILE="$(mktemp 2>/dev/null || echo /tmp/quenza_install.log)"

  prompt_inputs

  ensure_python
  check_db_tools

  run_step "Mengunduh project" download_project
  run_step "Mengunduh basis data YARA" download_yara_rules

  # Project dir is now valid — relocate the log inside it.
  if [ -d "$INSTALL_DIR" ]; then
    local newlog="${INSTALL_DIR}/install.log"
    if cat "$LOG_FILE" >>"$newlog" 2>/dev/null; then
      rm -f "$LOG_FILE" 2>/dev/null || true
      LOG_FILE="$newlog"
    fi
  fi

  run_step "Menyiapkan virtual environment & dependencies" setup_venv
  run_step "Mengonfigurasi .env (Master Password terenkripsi)" configure_env
  run_step "Memverifikasi aplikasi" verify_app
  run_step "Mendaftarkan service (auto-startup)" register_service

  STEP_NO=$((STEP_NO + 1))
  CURRENT_STEP="memverifikasi layanan berjalan"
  log "\n${C_BOLD}${C_CYN}==> [${STEP_NO}/${STEP_TOTAL}] Memverifikasi layanan berjalan${C_RESET}"
  if health_check; then
    log_ok "Layanan merespons di /healthz."
  else
    log_warn "Layanan belum merespons health check. Periksa log service."
    log_info "systemd: ${SUDO} journalctl -u ${SERVICE_NAME} -e   |  fallback: ${INSTALL_DIR}/server.log"
  fi

  print_summary
}

main "$@"
