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
