import os
import glob
import logging
import shutil
import uuid
import json
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import QuarantineLog, AppSetting

try:
    import yara
except ImportError:
    yara = None

logger = logging.getLogger(__name__)

# Compile YARA rules lazily and globally to avoid recompiling on every scan
_COMPILED_RULES = None
_YARA_DISABLED = False


def get_yara_rules():
    global _COMPILED_RULES, _YARA_DISABLED
    if _YARA_DISABLED:
        return None
    if _COMPILED_RULES is not None:
        return _COMPILED_RULES

    if yara is None:
        logger.warning("yara-python is not installed. Malware scanning will be disabled.")
        _YARA_DISABLED = True
        return None

    rules_dir = os.path.join("app", "data", "yara_rules")
    if not os.path.isdir(rules_dir):
        logger.info(f"YARA rules directory not found: {rules_dir}. Skipping scan.")
        _YARA_DISABLED = True
        return None

    # Gather webshell and malware rules from signature-base
    filepaths = {}
    
    # We mainly care about webshells and common malware in signature-base
    for category in ["web_shells", "malware"]:
        cat_dir = os.path.join(rules_dir, category)
        if os.path.isdir(cat_dir):
            for file in glob.glob(os.path.join(cat_dir, "**", "*.yar"), recursive=True):
                # Provide a unique namespace for each file
                rel_path = os.path.relpath(file, rules_dir)
                namespace = rel_path.replace(os.sep, "_").replace(".", "_")
                filepaths[namespace] = file

    if not filepaths:
        logger.warning("No YARA rules (*.yar) found in expected categories.")
        _YARA_DISABLED = True
        return None

    logger.info(f"Compiling {len(filepaths)} YARA rules files...")
    try:
        _COMPILED_RULES = yara.compile(filepaths=filepaths)
    except Exception as exc:
        logger.warning(f"Bulk compile failed: {exc}. Trying individual compilation...")
        valid_filepaths = {}
        for ns, fp in filepaths.items():
            try:
                yara.compile(filepath=fp)
                valid_filepaths[ns] = fp
            except Exception:
                pass
        
        if valid_filepaths:
            _COMPILED_RULES = yara.compile(filepaths=valid_filepaths)
        else:
            logger.error("All YARA rules failed to compile.")
            _YARA_DISABLED = True
            return None

    return _COMPILED_RULES


def scan_file(filepath: str) -> list[str]:
    """Scan a single file and return a list of triggered rule names."""
    rules = get_yara_rules()
    if not rules:
        return []
    
    # Skip very large files (> 50MB) to prevent memory exhaustion
    try:
        if os.path.getsize(filepath) > 50 * 1024 * 1024:
            return []
    except OSError:
        return []
    
    try:
        matches = rules.match(filepath, timeout=60)
        return [match.rule for match in matches]
    except Exception as exc:
        logger.debug(f"Failed to scan file {filepath}: {exc}")
        return []


def scan_directory(dirpath: str) -> list[dict]:
    """Scan a directory recursively and return a list of findings."""
    rules = get_yara_rules()
    if not rules:
        return []

    findings = []
    for root, _, files in os.walk(dirpath):
        for name in files:
            filepath = os.path.join(root, name)
            triggered = scan_file(filepath)
            if triggered:
                findings.append({
                    "file": filepath,
                    "rules": triggered
                })
    return findings


def quarantine_file(filepath: str, rule_matched: str, db=None) -> QuarantineLog:
    """Move a malicious file to quarantine and log it."""
    quarantine_dir = os.path.join("app", "data", "quarantine")
    os.makedirs(quarantine_dir, exist_ok=True)
    
    filename = os.path.basename(filepath)
    safe_name = f"{uuid.uuid4().hex}_{filename}.quarantined"
    safe_path = os.path.join(quarantine_dir, safe_name)
    
    try:
        shutil.move(filepath, safe_path)
    except Exception as e:
        logger.error(f"Failed to move file {filepath} to quarantine: {e}")
        raise
    
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
        
    try:
        log = QuarantineLog(
            original_path=filepath,
            quarantined_path=safe_path,
            rule_matched=rule_matched,
            status="quarantined"
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log
    finally:
        if close_db:
            db.close()


def restore_quarantined_file(log_id: int, db=None) -> bool:
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
        
    try:
        log = db.get(QuarantineLog, log_id)
        if not log or log.status != "quarantined":
            return False
            
        # Ensure original directory exists
        orig_dir = os.path.dirname(log.original_path)
        if orig_dir:
            os.makedirs(orig_dir, exist_ok=True)
            
        shutil.move(log.quarantined_path, log.original_path)
        log.status = "restored"
        log.resolved_at = datetime.now(timezone.utc)
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to restore file: {e}")
        db.rollback()
        return False
    finally:
        if close_db:
            db.close()


def delete_quarantined_file(log_id: int, db=None) -> bool:
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
        
    try:
        log = db.get(QuarantineLog, log_id)
        if not log or log.status != "quarantined":
            return False
            
        if os.path.exists(log.quarantined_path):
            os.remove(log.quarantined_path)
            
        log.status = "deleted"
        log.resolved_at = datetime.now(timezone.utc)
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to delete quarantined file: {e}")
        db.rollback()
        return False
    finally:
        if close_db:
            db.close()


def run_standalone_scan(progress_cb=None, trigger="manual"):
    """Run a standalone scan based on global Security settings."""
    start_time = datetime.now(timezone.utc)
    db = SessionLocal()
    
    def emit(idx, label, pct, total=100):
        if progress_cb:
            progress_cb(idx, label, pct, total)

    try:
        emit(0, "Membaca konfigurasi antivirus...", 5)
        # Load settings
        targets_setting = db.query(AppSetting).filter_by(key="av_targets").first()
        auto_quarantine_setting = db.query(AppSetting).filter_by(key="av_auto_quarantine").first()
        
        targets = json.loads(targets_setting.value) if targets_setting and targets_setting.value else []
        auto_quarantine = (auto_quarantine_setting and auto_quarantine_setting.value == "1")
        
        status = "success"
        msg = "Pencarian dibatalkan."
        detail = {}
        total_files = 0
        findings = []
        quarantined = []
        
        if not targets:
            logger.info("No targets configured for standalone scan. Skipping.")
            msg = "Tidak ada target direktori untuk dipindai."
        else:
            emit(1, "Menghimpun daftar file...", 10)
            files_to_scan = []
            for target in targets:
                if not os.path.exists(target):
                    continue
                if os.path.isdir(target):
                    for root, _, files in os.walk(target):
                        for name in files:
                            files_to_scan.append(os.path.join(root, name))
                else:
                    files_to_scan.append(target)
                    
            total_files = len(files_to_scan)
            if total_files == 0:
                logger.info("No files found in targets.")
                msg = "Tidak ditemukan file pada target direktori."
            else:
                rules = get_yara_rules()
                if not rules:
                    status = "failed"
                    msg = "Mesin YARA (aturan deteksi) gagal dimuat."
                else:
                    emit(2, f"Memindai {total_files} file...", 20)
                    for i, filepath in enumerate(files_to_scan):
                        if i % max(1, total_files // 20) == 0:
                            pct = 20 + int((i / total_files) * 70)
                            emit(2, f"Memindai file ke-{i} dari {total_files}...", pct)

                        triggered = scan_file(filepath)
                        if triggered:
                            findings.append({"file": filepath, "rules": triggered})
                    
                    emit(3, "Menganalisa dan karantina...", 95)
                    if auto_quarantine and findings:
                        logger.info(f"Auto-quarantining {len(findings)} detected files.")
                        for f in findings:
                            filepath = f["file"]
                            rule_matched = ", ".join(f["rules"])
                            try:
                                if os.path.exists(filepath):
                                    quarantine_file(filepath, rule_matched, db=db)
                                    quarantined.append({"file": filepath, "status": "quarantined"})
                            except Exception as e:
                                logger.error(f"Failed to auto-quarantine {filepath}: {e}")
                                quarantined.append({"file": filepath, "status": "error", "error": str(e)})
                    elif findings:
                        logger.warning(f"Standalone scan found {len(findings)} malware, but auto-quarantine is OFF.")
                    
                    if findings:
                        status = "failed"
                        msg = f"Peringatan! Ditemukan {len(findings)} file terinfeksi."
                        if auto_quarantine:
                            msg += f" {len(quarantined)} file berhasil dikarantina."
                    else:
                        status = "success"
                        msg = f"Sistem aman. {total_files} file bersih tanpa masalah."

        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        
        detail = {
            "total_files_scanned": total_files,
            "findings": findings,
            "quarantined": quarantined
        }

        from app.models import BackupLog
        blog = BackupLog(
            project_id=None,
            project_name="Security Scanner",
            action="scan",
            status=status,
            trigger=trigger,
            message=msg,
            detail_json=json.dumps(detail, ensure_ascii=False),
            duration_ms=duration_ms
        )
        db.add(blog)
        db.commit()
        db.refresh(blog)
        
        return {
            "status": status,
            "message": msg,
            "detail": detail,
            "log_id": blog.id
        }
            
    except Exception as e:
        logger.error(f"Scan failed: {e}")
        
        # Write error log to BackupLog
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        from app.models import BackupLog
        blog = BackupLog(
            project_id=None,
            project_name="Security Scanner",
            action="scan",
            status="failed",
            trigger=trigger,
            message=f"Terjadi kesalahan saat memindai: {e}",
            detail_json="{}",
            duration_ms=duration_ms
        )
        db.add(blog)
        db.commit()
        db.refresh(blog)
        
        return {
            "status": "failed",
            "message": f"Terjadi kesalahan saat memindai: {e}",
            "log_id": blog.id
        }
    finally:
        db.close()
