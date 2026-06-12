"""Routes for Security Module."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from app.auth import require_api_auth, require_login, verify_password
from app.services import security_service
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
