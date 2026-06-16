import os
import glob
import logging
import shutil
import uuid
import json
import subprocess
import asyncio
from typing import Any
from datetime import datetime, timezone, timedelta

from app.database import SessionLocal
from app.models import QuarantineLog, AppSetting
from app.services import notification_service, ai_service, av_whitelist_service
from app.services.heuristic_filter import HeuristicPreFilter
from app.services.quarantine_filter import QuarantineHeuristicFilter

try:
    import yara
except ImportError:
    yara = None

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scan aggressiveness profiles (heuristic layer only; ClamAV/YARA unaffected)
# ---------------------------------------------------------------------------
SCAN_LEVEL_PROFILES: dict[str, dict] = {
    "low": {
        "min_triggers": 5,
        "recent_hours": 24,
        "quarantine_threshold": 8,
        "max_ai_calls": 5,
    },
    "default": {
        "min_triggers": 3,
        "recent_hours": 48,
        "quarantine_threshold": 5,
        "max_ai_calls": 15,
    },
    "high": {
        "min_triggers": 1,
        "recent_hours": 168,
        "quarantine_threshold": 3,
        "max_ai_calls": 40,
    },
}

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


def scan_with_clamav(filepath: str) -> list[str]:
    """Scan a file using clamscan/clamdscan if available."""
    scanner_bin = shutil.which("clamdscan") or shutil.which("clamscan")
    if not scanner_bin:
        return []
        
    try:
        # --fdpass is useful for clamdscan to bypass permission issues
        cmd = [scanner_bin, "--no-summary", "--fdpass", filepath] if "clamdscan" in scanner_bin else [scanner_bin, "--no-summary", filepath]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        findings = []
        if result.returncode == 1:
            for line in result.stdout.strip().split("\n"):
                if " FOUND" in line:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        virus_name = parts[1].strip().replace(" FOUND", "")
                        findings.append(f"ClamAV: {virus_name}")
        return findings
    except Exception as exc:
        logger.debug(f"ClamAV scan failed for {filepath}: {exc}")
        return []

def scan_file(filepath: str) -> list[str]:
    """Scan a single file and return a list of triggered rule names."""
    all_triggered = []
    
    rules = get_yara_rules()
    
    # Skip very large files (> 50MB) to prevent memory exhaustion
    try:
        if os.path.getsize(filepath) > 50 * 1024 * 1024:
            return []
    except OSError:
        return []
    
    if rules:
        try:
            matches = rules.match(filepath, timeout=60)
            all_triggered.extend([match.rule for match in matches])
        except Exception as exc:
            logger.debug(f"Failed to scan file {filepath} with YARA: {exc}")
            
    # Add ClamAV scanning
    clamav_findings = scan_with_clamav(filepath)
    all_triggered.extend(clamav_findings)
    
    return all_triggered


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


def restore_all_quarantined_files(db=None) -> dict[str, Any]:
    """Restore all files currently in quarantine."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    restored = 0
    failed = 0

    try:
        logs = db.query(QuarantineLog).filter(QuarantineLog.status == "quarantined").all()
        total = len(logs)
        if total == 0:
            return {"total": 0, "restored": 0, "failed": 0}

        for log in logs:
            try:
                # Ensure original directory exists
                orig_dir = os.path.dirname(log.original_path)
                if orig_dir:
                    os.makedirs(orig_dir, exist_ok=True)

                shutil.move(log.quarantined_path, log.original_path)
                log.status = "restored"
                log.resolved_at = datetime.now(timezone.utc)
                restored += 1
            except Exception as exc:
                failed += 1
                logger.error(f"Failed to restore quarantined file {log.id}: {exc}")

        db.commit()
        return {"total": total, "restored": restored, "failed": failed}
    except Exception:
        db.rollback()
        raise
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


def clean_quarantined_file(log_id: int, db=None) -> tuple[bool, str]:
    """Use AI to remove malware lines and restore the clean file."""
    if not ai_service.is_ai_enabled():
        return False, "AI dinonaktifkan."
        
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
        
    try:
        log = db.get(QuarantineLog, log_id)
        if not log or log.status != "quarantined":
            return False, "File tidak ditemukan di karantina."
            
        if not os.path.exists(log.quarantined_path):
            return False, "File fisik tidak ditemukan."
            
        with open(log.quarantined_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        import asyncio
        cleaned_content = asyncio.run(ai_service.ask_ai_clean_file(content))
        
        if "Fitur AI dinonaktifkan" in cleaned_content or "Terjadi kesalahan" in cleaned_content:
            return False, "Gagal membersihkan menggunakan AI."
            
        # Ensure original directory exists
        orig_dir = os.path.dirname(log.original_path)
        if orig_dir:
            os.makedirs(orig_dir, exist_ok=True)
            
        # Write clean content to original path
        with open(log.original_path, "w", encoding="utf-8") as f:
            f.write(cleaned_content)
            
        # Delete quarantined file
        os.remove(log.quarantined_path)
            
        log.status = "restored" # Mark as restored since it's back in place
        log.resolved_at = datetime.now(timezone.utc)
        db.commit()
        return True, "File berhasil dibersihkan dan dipulihkan."
    except Exception as e:
        logger.error(f"Failed to clean quarantined file: {e}")
        db.rollback()
        return False, str(e)
    finally:
        if close_db:
            db.close()


def _is_script_file(filepath: str) -> bool:
    exts = [".php", ".py", ".js", ".sh", ".bash", ".pl", ".rb", ".ps1", ".html", ".htm"]
    return any(filepath.lower().endswith(ext) for ext in exts)

def _is_recently_modified(filepath: str, hours=48) -> bool:
    try:
        mtime = os.path.getmtime(filepath)
        dt = datetime.fromtimestamp(mtime, timezone.utc)
        return (datetime.now(timezone.utc) - dt) < timedelta(hours=hours)
    except OSError:
        return False

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
        scan_level_setting = db.query(AppSetting).filter_by(key="av_scan_level").first()
        whitelist_names = av_whitelist_service.get_filename_set(db)
        
        targets = json.loads(targets_setting.value) if targets_setting and targets_setting.value else []
        auto_quarantine = (auto_quarantine_setting and auto_quarantine_setting.value == "1")
        
        scan_level = (scan_level_setting.value if scan_level_setting and scan_level_setting.value else "default")
        profile = SCAN_LEVEL_PROFILES.get(scan_level, SCAN_LEVEL_PROFILES["default"])
        logger.info(f"Scan aggressiveness level: {scan_level} (profile: {profile})")
        
        status = "success"
        msg = "Pencarian dibatalkan."
        detail = {}
        total_files = 0
        findings = []
        quarantined = []
        skipped_whitelist = []
        
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
                            filepath = os.path.join(root, name)
                            if av_whitelist_service.is_whitelisted_path(filepath, whitelist_names):
                                skipped_whitelist.append(filepath)
                                continue
                            files_to_scan.append(filepath)
                else:
                    if av_whitelist_service.is_whitelisted_path(target, whitelist_names):
                        skipped_whitelist.append(target)
                    else:
                        files_to_scan.append(target)
                    
            total_files = len(files_to_scan)
            if total_files == 0:
                if skipped_whitelist:
                    logger.info("All target files are skipped by Antivirus whitelist.")
                    msg = "Semua file target cocok dengan daftar putih, tidak ada yang dipindai."
                else:
                    logger.info("No files found in targets.")
                    msg = "Tidak ditemukan file pada target direktori."
            else:
                rules = get_yara_rules()
                has_clamav = shutil.which("clamdscan") or shutil.which("clamscan")
                
                if not rules and not has_clamav:
                    status = "failed"
                    msg = "Semua mesin antivirus (YARA & ClamAV) tidak tersedia/gagal dimuat."
                else:
                    active_engines = []
                    if rules: active_engines.append("YARA")
                    if has_clamav: active_engines.append("ClamAV")
                    
                    emit(2, f"Memindai {total_files} file dengan {' + '.join(active_engines)}...", 20)
                    ai_call_count = 0
                    MAX_AI_CALLS = profile["max_ai_calls"]
                    heuristic_filter = HeuristicPreFilter()
                    quarantine_filter = QuarantineHeuristicFilter(
                        heuristic_filter,
                        malicious_threshold=profile["quarantine_threshold"],
                    )
                    
                    for i, filepath in enumerate(files_to_scan):
                        if i % max(1, total_files // 20) == 0:
                            pct = 20 + int((i / total_files) * 70)
                            emit(2, f"Memindai file ke-{i} dari {total_files}...", pct)

                        triggered = scan_file(filepath)
                        
                        # Semantic Zero-Day Check
                        if not triggered and _is_script_file(filepath) and _is_recently_modified(filepath, hours=profile["recent_hours"]):
                            if ai_service.is_ai_enabled():
                                try:
                                    with open(filepath, "r", encoding="utf-8") as f_obj:
                                        content = f_obj.read()
                                        
                                    _, ext = os.path.splitext(filepath)
                                    scan_result = heuristic_filter.scan_content(content, ext, min_triggers=profile["min_triggers"])
                                    if scan_result["suspicious"]:
                                        if ai_call_count < MAX_AI_CALLS:
                                            ai_call_count += 1
                                            ai_result = asyncio.run(ai_service.ask_ai_semantic_check(content))
                                            
                                            # Robust parsing to avoid quarantining clean config files
                                            # sometimes AI writes things like "Aman, tapi mengekspos kredensial"
                                            ai_lower = ai_result.lower().strip()
                                            is_safe = False
                                            
                                            if ai_lower == "safe" or ai_lower.startswith("safe") or "safe." in ai_lower:
                                                is_safe = True
                                            elif any(safe_kw in ai_lower for safe_kw in [
                                                "tidak ditemukan webshell", "bersih dari malware",
                                                "hanya mengekspos kredensial", "aman", "skrip ini aman",
                                                "tidak ada indikasi"
                                            ]):
                                                is_safe = True
                                                
                                            if not is_safe and not any(err in ai_result for err in ["Fitur AI", "Terjadi kesalahan", "Gagal menghubungi"]):
                                                triggered.append(f"AI-Semantic: {ai_result[:100]}")
                                                
                                                # Dynamic YARA Rule Generator
                                                import hashlib
                                                fhash = hashlib.sha256(content.encode('utf-8')).hexdigest()
                                                rule_name = f"ai_zero_day_{fhash[:8]}"
                                                rule_content = f'rule {rule_name} {{\n    meta:\n        description = "AI Detected Semantic Zero-Day"\n        hash = "{fhash}"\n    condition:\n        hash.sha256(0, filesize) == "{fhash}"\n}}'
                                                rule_path = os.path.join("app", "data", "yara_rules", "malware", f"{rule_name}.yar")
                                                os.makedirs(os.path.dirname(rule_path), exist_ok=True)
                                                with open(rule_path, "w", encoding="utf-8") as rf:
                                                    rf.write(rule_content)
                                        else:
                                            logger.debug(f"AI quota limit reached ({MAX_AI_CALLS}). Skipping semantic check for {filepath}")
                                except Exception as e:
                                    logger.debug(f"AI Semantic check failed for {filepath}: {e}")

                        if triggered:
                            findings.append({"file": filepath, "rules": triggered})
                    
                    emit(3, "Menganalisa dan karantina...", 95)
                    quarantine_ai_calls = 0
                    MAX_QUARANTINE_AI_CALLS = 10
                    
                    if auto_quarantine and findings:
                        logger.info(f"Auto-quarantining {len(findings)} detected files.")
                        for f in findings:
                            filepath = f["file"]
                            rule_matched = ", ".join(f["rules"])
                            
                            is_malicious = True
                            if ai_service.is_ai_enabled() and _is_script_file(filepath):
                                try:
                                    with open(filepath, "r", encoding="utf-8") as file_obj:
                                        content = file_obj.read()
                                    _, ext = os.path.splitext(filepath)
                                    q_action = quarantine_filter.evaluate(content, ext)
                                    
                                    if q_action == "QUARANTINE_DIRECT":
                                        logger.info(f"Heuristic score is extremely high for {filepath}. Bypassing AI verification.")
                                    elif q_action == "ASK_AI":
                                        if quarantine_ai_calls < MAX_QUARANTINE_AI_CALLS:
                                            quarantine_ai_calls += 1
                                            ai_verdict = asyncio.run(ai_service.ask_ai_quarantine_check(content, rule_matched))
                                            if "FALSE-POSITIVE" in ai_verdict:
                                                is_malicious = False
                                                logger.info(f"AI Hakim Kedua marked {filepath} as False-Positive. Aborting quarantine.")
                                        else:
                                            logger.debug(f"Smart Quarantine AI limit reached ({MAX_QUARANTINE_AI_CALLS}). Proceeding with standard quarantine for {filepath}")
                                except Exception as e:
                                    logger.debug(f"AI Quarantine check failed: {e}")

                            if is_malicious:
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
            "quarantined": quarantined,
            "whitelist_names": sorted(whitelist_names),
            "skipped_whitelist_count": len(skipped_whitelist),
            "skipped_whitelist_samples": skipped_whitelist[:100],
        }

        if findings and ai_service.is_ai_enabled():
            try:
                report = asyncio.run(ai_service.ask_ai_threat_report(findings))
                if report and "Fitur AI" not in report:
                    detail["ai_threat_report"] = report
            except Exception as e:
                logger.debug(f"AI Threat report failed: {e}")

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
        
        notification_service.notify_scan_completed(
            project_name="Security Scanner",
            file_count=total_files,
            infected_count=len(findings),
            duration_ms=duration_ms
        )
        
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
