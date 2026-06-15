"""AI Service: Communication with OpenAI API (gpt-5.5)."""

import json
import logging
from typing import Any

import httpx

from app.services import settings_service

logger = logging.getLogger("quenza.ai")

MODEL_NAME = "gpt-5.5"


def is_ai_enabled() -> bool:
    """Return True if AI is enabled and API key is set."""
    cfg = settings_service.get_ai_config()
    return cfg.enabled and bool(cfg.api_key)


async def ask_ai(developer_prompt: str, user_prompt: str, effort: str = "low") -> str:
    """Send a prompt to OpenAI Responses API using gpt-5.5.
    
    Args:
        developer_prompt: High-level instructions for the AI (role: developer)
        user_prompt: The input data or specific request (role: user)
        effort: Reasoning effort level ("low", "medium", "high")
        
    Returns the text response from the AI.
    """
    cfg = settings_service.get_ai_config()
    if not cfg.enabled or not cfg.api_key:
        return "Fitur AI dinonaktifkan atau API Key belum diatur."

    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": MODEL_NAME,
        "reasoning": {"effort": effort},
        "instructions": developer_prompt,
        "input": user_prompt,
    }

    try:
        # High reasoning can take a while, use a long timeout
        timeout = 180.0 if effort == "high" else 60.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            
        if response.status_code != 200:
            logger.error(f"OpenAI API Error: {response.text}")
            return f"Gagal menghubungi OpenAI API (Status {response.status_code})."
            
        data = response.json()
        if "output_text" in data:
            return data["output_text"].strip()
        elif "output" in data and len(data["output"]) > 0:
            # Fallback if output_text is not aggregated
            for item in data["output"]:
                if item.get("type") == "message" and "content" in item:
                    for content_part in item["content"]:
                        if content_part.get("type") == "output_text":
                            return content_part.get("text", "").strip()
            return "Format respons tidak dikenali dari OpenAI API."
        else:
            return "Respons kosong atau tidak dikenali dari OpenAI API."
            
    except Exception as e:
        logger.exception("Kesalahan saat memanggil OpenAI API.")
        return f"Terjadi kesalahan saat memanggil AI: {str(e)}"


# --- Antivirus & Scanner AI Helpers (Phase 3) ---

async def ask_ai_quarantine_check(file_content: str, rule_matched: str) -> str:
    """Ask AI to verify if a flagged file is truly malicious or a false-positive."""
    dev_prompt = (
        "Anda adalah Analis Malware (Security Hakim Kedua). "
        "Mesin YARA/ClamAV mendeteksi file ini sebagai malware berdasarkan aturan: " + rule_matched + ". "
        "Tugas Anda: Analisis kode berikut. Jika ini skrip sah (misalnya alat sysadmin, backup script biasa, dsb), kembalikan HANYA teks 'FALSE-POSITIVE'. "
        "Jika ini benar-benar malware, backdoor, webshell, atau kode berbahaya, kembalikan HANYA teks 'MALICIOUS'."
    )
    # Truncate content if too large (e.g., first 50KB)
    safe_content = file_content[:50000]
    return await ask_ai(dev_prompt, safe_content, effort="high")


async def ask_ai_semantic_check(file_content: str) -> str:
    """Ask AI to semantically check a newly modified script for zero-days."""
    dev_prompt = (
        "Anda adalah Analis Zero-Day Malware. Periksa skrip berikut secara semantik. "
        "Jika skrip ini murni aman, kembalikan HANYA teks 'SAFE'. "
        "Jika skrip ini mengandung obfuscation mencurigakan, webshell, backdoor, atau pencuri data, "
        "kembalikan alasan singkatnya (maksimal 2 kalimat dalam Bahasa Indonesia)."
    )
    safe_content = file_content[:50000]
    return await ask_ai(dev_prompt, safe_content, effort="medium")


async def ask_ai_clean_file(file_content: str) -> str:
    """Ask AI to remove malware lines from an infected file."""
    dev_prompt = (
        "Anda adalah alat pembersih malware otomatis. Berikut adalah isi sebuah file yang terinfeksi malware "
        "(seperti kode base64_decode jahat, eval, backdoor, atau obfuscation). "
        "Tugas Anda: HAPUS HANYA bagian malware tersebut tanpa merusak logika asli file. "
        "Kembalikan HANYA KODE YANG SUDAH BERSIH tanpa markdown code blocks (```) atau penjelasan apapun. "
        "Kode yang Anda berikan akan langsung ditulis ulang ke file."
    )
    safe_content = file_content[:50000]
    res = await ask_ai(dev_prompt, safe_content, effort="high")
    
    # Clean up markdown if AI accidentally includes it
    if res.startswith("```"):
        lines = res.split("\n")
        if len(lines) > 2:
            res = "\n".join(lines[1:-1])
    return res.strip()


async def ask_ai_threat_report(findings: list) -> str:
    """Ask AI to generate a Threat Intelligence Report summary based on findings."""
    if not findings:
        return ""
        
    dev_prompt = (
        "Anda adalah Ahli Intelijen Ancaman (Threat Intelligence). "
        "Berikut adalah daftar temuan malware dari scan server. "
        "Buatlah 1 paragraf ringkasan eksekutif (dalam Bahasa Indonesia) yang menjelaskan tingkat bahaya dari temuan-temuan ini, "
        "dan apa dampak potensialnya jika tidak segera ditangani."
    )
    findings_str = json.dumps(findings)
    return await ask_ai(dev_prompt, findings_str, effort="medium")
