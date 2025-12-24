"""
Ollama LLM Client

HTTP client for calling local Ollama server.
"""
import json
import httpx
from typing import Optional
import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


async def generate(
    prompt: str,
    system: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """
    Generate text using Ollama.
    
    Args:
        prompt: The user prompt
        system: Optional system prompt
        model: Model name (default: llama3.2)
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate
        
    Returns:
        Generated text response
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        }
    }
    
    if system:
        payload["system"] = system
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
        )
        response.raise_for_status()
        result = response.json()
        return result.get("response", "")


async def generate_json(
    prompt: str,
    system: Optional[str] = None,
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    Generate JSON using Ollama.
    
    Attempts to parse the response as JSON.
    If parsing fails, extracts JSON from markdown code blocks.
    
    Args:
        prompt: The user prompt
        system: Optional system prompt
        model: Model name
        
    Returns:
        Parsed JSON dictionary
        
    Raises:
        ValueError: If response cannot be parsed as JSON
    """
    response = await generate(prompt, system, model, temperature=0.3)
    
    # Try direct parsing
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    
    # Try extracting from markdown code block
    if "```json" in response:
        start = response.find("```json") + 7
        end = response.find("```", start)
        if end > start:
            try:
                return json.loads(response[start:end].strip())
            except json.JSONDecodeError:
                pass
    
    # Try extracting from generic code block
    if "```" in response:
        start = response.find("```") + 3
        # Skip language identifier if present
        newline = response.find("\n", start)
        if newline > start:
            start = newline + 1
        end = response.find("```", start)
        if end > start:
            try:
                return json.loads(response[start:end].strip())
            except json.JSONDecodeError:
                pass
    
    # Try finding JSON object boundaries
    start = response.find("{")
    end = response.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(response[start:end])
        except json.JSONDecodeError:
            pass
    
    raise ValueError(f"Could not parse JSON from response: {response[:500]}...")


async def check_health() -> bool:
    """Check if Ollama server is running."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            return response.status_code == 200
    except Exception:
        return False


async def list_models() -> list[str]:
    """List available models."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []
