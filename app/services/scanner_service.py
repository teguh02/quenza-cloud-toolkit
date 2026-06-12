import os
import glob
import logging

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
