"""Routes for Security Module."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
import json

from app.auth import require_api_auth, require_login, verify_password
from app.services import security_service, scanner_service, ai_service
from app.database import get_db
from sqlalchemy.orm import Session
from app.models import AppSetting, QuarantineLog
from app.templating import templates

router = APIRouter()

@router.get("/security", response_class=HTMLResponse, name="security", response_model=None)
async def security_page(
    request: Request,
) -> HTMLResponse | RedirectResponse:
    """Render the main Security dashboard."""
    guard = require_login(request)
    if guard is not None:
        return guard

    return templates.TemplateResponse(
        request,
        "security.html",
        {
            "active_page": "security",
            "page_title": "Security & Monitoring",
            "page_subtitle": "Pantau penggunaan sistem, kelola proses berjalan, dan atur firewall.",
        },
    )

@router.get("/api/security/system")
async def api_get_system(_auth: None = Depends(require_api_auth)):
    try:
        data = security_service.get_system_info()
        return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.get("/api/security/processes")
async def api_get_processes(_auth: None = Depends(require_api_auth)):
    try:
        data = security_service.get_processes()
        return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.get("/api/security/firewall")
async def api_get_firewall(_auth: None = Depends(require_api_auth)):
    try:
        adapter = security_service.get_firewall_adapter()
        data = adapter.get_rules()
        return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.get("/api/security/antivirus")
async def api_get_antivirus(db: Session = Depends(get_db), _auth: None = Depends(require_api_auth)):
    try:
        settings = db.query(AppSetting).filter(AppSetting.key.in_([
            "av_enabled", "av_auto_quarantine", "av_targets"
        ])).all()
        config = {
            "av_enabled": False,
            "av_auto_quarantine": False,
            "av_targets": []
        }
        for s in settings:
            if s.key == "av_enabled": config["av_enabled"] = (s.value == "1")
            elif s.key == "av_auto_quarantine": config["av_auto_quarantine"] = (s.value == "1")
            elif s.key == "av_targets": config["av_targets"] = json.loads(s.value) if s.value else []
            
        logs_db = db.query(QuarantineLog).order_by(QuarantineLog.created_at.desc()).limit(50).all()
        logs = []
        for lg in logs_db:
            logs.append({
                "id": lg.id,
                "original_path": lg.original_path,
                "rule_matched": lg.rule_matched,
                "status": lg.status,
                "created_at": lg.created_at.isoformat() if lg.created_at else ""
            })

        # Antivirus health check
        from app.services import av_health_service
        health = av_health_service.get_health_status(db)
        health_data = {
            "is_healthy": health.is_healthy,
            "av_enabled": health.av_enabled,
            "any_engine_available": health.any_engine_available,
            "engines": [
                {"name": e.name, "available": e.available, "detail": e.detail}
                for e in health.engines
            ],
            "targets_configured": health.targets_configured,
            "targets_accessible": health.targets_accessible,
            "inaccessible_targets": health.inaccessible_targets,
            "yara_rules_count": health.yara_rules_count,
            "quarantine_count": health.quarantine_count,
            "last_scan": None,
            "alerts": health.alerts,
            "warnings": health.warnings,
        }
        if health.last_scan:
            health_data["last_scan"] = {
                "ran_at": health.last_scan.ran_at.isoformat() if health.last_scan.ran_at else None,
                "status": health.last_scan.status,
                "files_scanned": health.last_scan.files_scanned,
                "threats_found": health.last_scan.threats_found,
                "duration_ms": health.last_scan.duration_ms,
                "hours_ago": health.last_scan.hours_ago,
            }

        return {"ok": True, "data": {"config": config, "logs": logs, "health": health_data}}
    except Exception as e:
        return {"ok": False, "error": str(e)}

class AntivirusConfigRequest(BaseModel):
    av_enabled: bool
    av_auto_quarantine: bool
    av_targets: list[str]

@router.post("/api/security/antivirus/config")
async def api_set_antivirus_config(
    req: AntivirusConfigRequest,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_api_auth)
):
    try:
        for k, v in [
            ("av_enabled", "1" if req.av_enabled else "0"),
            ("av_auto_quarantine", "1" if req.av_auto_quarantine else "0"),
            ("av_targets", json.dumps(req.av_targets))
        ]:
            setting = db.query(AppSetting).filter_by(key=k).first()
            if not setting:
                setting = AppSetting(key=k, value=v)
                db.add(setting)
            else:
                setting.value = v
        db.commit()
        
        # Sync scheduler immediately
        try:
            from app import scheduler
            scheduler.sync_av_scan()
        except Exception as se:
            pass # Ignored if scheduler is not running
            
        return {"ok": True, "message": "Konfigurasi Antivirus berhasil disimpan."}
    except Exception as e:
        db.rollback()
        return {"ok": False, "error": str(e)}

class QuarantineActionRequest(BaseModel):
    action: str  # 'restore', 'delete', or 'clean'

@router.post("/api/security/antivirus/quarantine/{log_id}")
async def api_quarantine_action(
    log_id: int,
    req: QuarantineActionRequest,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_api_auth)
):
    try:
        if req.action == "restore":
            res = scanner_service.restore_quarantined_file(log_id, db=db)
            msg = "File berhasil dipulihkan."
        elif req.action == "delete":
            res = scanner_service.delete_quarantined_file(log_id, db=db)
            msg = "File berhasil dihapus permanen."
        elif req.action == "clean":
            res, msg = scanner_service.clean_quarantined_file(log_id, db=db)
        else:
            return {"ok": False, "error": "Aksi tidak dikenali."}
            
        if res:
            return {"ok": True, "message": msg}
        else:
            if req.action == "clean":
                return {"ok": False, "error": f"Gagal membersihkan: {msg}"}
            return {"ok": False, "error": "Gagal memproses file. Mungkin sudah terhapus atau dipulihkan."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.post("/api/security/antivirus/scan")
async def api_manual_scan(_auth: None = Depends(require_api_auth)):
    try:
        from app.services import job_service
        job_service.enqueue_scan(trigger="manual")
        return {"ok": True, "message": "Pemindaian manual telah dijalankan di latar belakang."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

class SecureActionRequest(BaseModel):
    master_password: str
    action: str = ""
    port: int = 0
    protocol: str = "tcp"

@router.post("/api/security/process/{pid}/kill")
async def api_kill_process(
    pid: int,
    req: SecureActionRequest,
    _auth: None = Depends(require_api_auth)
):
    if not verify_password(req.master_password):
        return {"ok": False, "error": "Master Password salah."}
        
    try:
        success = security_service.kill_process(pid)
        if success:
            return {"ok": True, "message": f"Proses {pid} berhasil dihentikan."}
        else:
            return {"ok": False, "error": f"Proses {pid} tidak ditemukan."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.post("/api/security/firewall/rule")
async def api_firewall_rule(
    req: SecureActionRequest,
    _auth: None = Depends(require_api_auth)
):
    if not verify_password(req.master_password):
        return {"ok": False, "error": "Master Password salah."}
        
    try:
        adapter = security_service.get_firewall_adapter()
        if req.action in ["allow", "block", "deny"]:
            success = adapter.add_rule(req.port, req.protocol, req.action)
            msg = f"Aturan '{req.action}' untuk {req.port}/{req.protocol} ditambahkan."
        elif req.action == "delete":
            success = adapter.delete_rule(req.port, req.protocol)
            msg = f"Aturan {req.port}/{req.protocol} dihapus."
        else:
            return {"ok": False, "error": "Aksi firewall tidak valid."}
            
        if success:
            return {"ok": True, "message": msg}
        else:
            return {"ok": False, "error": "Gagal menerapkan aturan (pastikan hak akses memadai/sudo)."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.get("/api/security/osscheduler")
@router.get("/api/security/os-scheduler")
async def api_get_os_scheduler(_auth: None = Depends(require_api_auth)):
    try:
        adapter = security_service.get_os_scheduler_adapter()
        data = adapter.get_tasks()
        return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}

class OsSchedulerActionRequest(BaseModel):
    master_password: str
    action: str = ""
    name: str = ""
    schedule: str = ""
    command: str = ""

@router.post("/api/security/os-scheduler/action")
async def api_os_scheduler_action(
    req: OsSchedulerActionRequest,
    _auth: None = Depends(require_api_auth)
):
    if not verify_password(req.master_password):
        return {"ok": False, "error": "Master Password salah."}
        
    try:
        adapter = security_service.get_os_scheduler_adapter()
        if req.action == "add":
            if not req.name or not req.command or not req.schedule:
                return {"ok": False, "error": "Nama, Jadwal, dan Perintah harus diisi."}
            success = adapter.add_task(req.name, req.schedule, req.command)
            msg = f"Tugas OS Scheduler '{req.name}' ditambahkan."
        elif req.action == "delete":
            if not req.name:
                return {"ok": False, "error": "Nama tugas tidak valid."}
            success = adapter.delete_task(req.name)
            msg = f"Tugas '{req.name}' dihapus."
        else:
            return {"ok": False, "error": "Aksi tidak valid."}
            
        if success:
            return {"ok": True, "message": msg}
        else:
            return {"ok": False, "error": "Gagal menerapkan aksi (pastikan akses memadai/Administrator/sudo)."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# --- AI Endpoints ---

from datetime import datetime, timezone, timedelta

_AI_CACHE = {}
CACHE_TTL_MINUTES = 60

def _get_cached(key: str):
    if key in _AI_CACHE:
        if (datetime.now(timezone.utc) - _AI_CACHE[key]["time"]).total_seconds() < CACHE_TTL_MINUTES * 60:
            return _AI_CACHE[key]["data"]
    return None

def _set_cached(key: str, data: str):
    _AI_CACHE[key] = {
        "time": datetime.now(timezone.utc),
        "data": data
    }

@router.get("/api/security/ai/system")
async def api_ai_system(_auth: None = Depends(require_api_auth)):
    if not ai_service.is_ai_enabled():
        return {"ok": False, "error": "AI dinonaktifkan."}
        
    cache_key = "system_info"
    cached = _get_cached(cache_key)
    if cached:
        return {"ok": True, "data": cached, "cached": True}
    
    data = security_service.get_system_info()
    dev_prompt = "Anda adalah pakar keamanan IT (Security Expert). Berikan analisis performa dan rekomendasi optimalisasi ringkas (RAM, CPU, Disk) dalam Bahasa Indonesia berdasarkan data JSON berikut."
    resp = await ai_service.ask_ai(dev_prompt, json.dumps(data), effort="low")
    _set_cached(cache_key, resp)
    return {"ok": True, "data": resp, "cached": False}


@router.get("/api/security/ai/processes")
async def api_ai_processes(_auth: None = Depends(require_api_auth)):
    if not ai_service.is_ai_enabled():
        return {"ok": False, "error": "AI dinonaktifkan."}
        
    cache_key = "processes"
    cached = _get_cached(cache_key)
    if cached:
        return {"ok": True, "data": cached, "cached": True}
    
    data = security_service.get_top_processes()
    dev_prompt = (
        "Anda adalah pakar keamanan IT. Analisis daftar proses ini. "
        "Kembalikan respon DALAM FORMAT JSON SAJA, berupa list/array of object dengan field: "
        "'pid' (number), 'flag' (string: 'Safe', 'Suspicious', atau 'Resource Heavy'), dan 'reason' (alasan ringkas max 2 kalimat dalam bahasa Indonesia). "
        "Hanya sertakan proses yang 'Suspicious' atau 'Resource Heavy'."
    )
    short_data = [{"pid": d["pid"], "name": d["name"], "cpu": d["cpu_percent"], "ram": d["memory_mb"], "cmd": d.get("cmdline")} for d in data[:50]]
    resp = await ai_service.ask_ai(dev_prompt, json.dumps(short_data), effort="medium")
    _set_cached(cache_key, resp)
    return {"ok": True, "data": resp, "cached": False}


@router.get("/api/security/ai/firewall")
async def api_ai_firewall(_auth: None = Depends(require_api_auth)):
    if not ai_service.is_ai_enabled():
        return {"ok": False, "error": "AI dinonaktifkan."}
        
    cache_key = "firewall"
    cached = _get_cached(cache_key)
    if cached:
        return {"ok": True, "data": cached, "cached": True}
    
    adapter = security_service.get_firewall_adapter()
    data = adapter.get_rules()
    dev_prompt = "Anda adalah pakar keamanan IT. Audit aturan firewall ini. Rekomendasikan port apa yang berbahaya dan perlu diblock, atau aturan dasar apa yang kurang dalam bentuk poin-poin singkat (Bahasa Indonesia)."
    resp = await ai_service.ask_ai(dev_prompt, json.dumps(data), effort="low")
    _set_cached(cache_key, resp)
    return {"ok": True, "data": resp, "cached": False}


@router.get("/api/security/ai/osscheduler")
async def api_ai_osscheduler(_auth: None = Depends(require_api_auth)):
    if not ai_service.is_ai_enabled():
        return {"ok": False, "error": "AI dinonaktifkan."}
        
    cache_key = "osscheduler"
    cached = _get_cached(cache_key)
    if cached:
        return {"ok": True, "data": cached, "cached": True}
    
    adapter = security_service.get_os_scheduler_adapter()
    data = adapter.get_tasks()
    dev_prompt = "Anda adalah pakar keamanan IT. Audit sebagian daftar OS Task/Cron ini. Identifikasi apakah ada tugas yang berpotensi malware (persistence mechanism) atau memberi tips keamanan ringkas (Bahasa Indonesia)."
    short_data = data[:100]
    resp = await ai_service.ask_ai(dev_prompt, json.dumps(short_data), effort="medium")
    _set_cached(cache_key, resp)
    return {"ok": True, "data": resp, "cached": False}
