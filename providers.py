"""
providers.py - Thin abstraction over different AI API providers.

Supports:
  - Claude (Anthropic) native API
  - OpenAI native API
  - Any OpenAI-compatible endpoint (Groq, Together, local Ollama, etc.)
    via a custom base_url

Uses only the Python standard library (urllib, json) - no SDK installs required.
"""

import json
import urllib.request
import urllib.error


class ProviderError(Exception):
    pass


def call_claude(api_key, model, system_prompt, user_message, max_tokens=4096):
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }
    return _post_json(url, headers, body, extractor=_extract_claude_text)


def call_openai_compatible(api_key, model, system_prompt, user_message,
                            base_url="https://api.openai.com/v1", max_tokens=4096):
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    }
    return _post_json(url, headers, body, extractor=_extract_openai_text)


def _post_json(url, headers, body, extractor, timeout=120):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw)
            return extractor(parsed)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise ProviderError(f"HTTP {e.code}: {error_body[:500]}")
    except urllib.error.URLError as e:
        raise ProviderError(f"Network error: {e.reason}")
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        raise ProviderError(f"Unexpected response format: {e}")


def _extract_claude_text(response):
    parts = response.get("content", [])
    texts = [p["text"] for p in parts if p.get("type") == "text"]
    if not texts:
        raise ProviderError(f"No text content in Claude response: {response}")
    return "\n".join(texts)


def _extract_openai_text(response):
    choices = response.get("choices", [])
    if not choices:
        raise ProviderError(f"No choices in OpenAI-compatible response: {response}")
    return choices[0]["message"]["content"]


PROVIDERS = {
    "claude": call_claude,
    "openai": call_openai_compatible,
    "compatible": call_openai_compatible,  # for Groq/Together/Ollama/etc, pass base_url
}


def call_provider(provider_name, **kwargs):
    if provider_name not in PROVIDERS:
        raise ProviderError(
            f"Unknown provider '{provider_name}'. Supported: {list(PROVIDERS.keys())}"
        )
    return PROVIDERS[provider_name](**kwargs)
