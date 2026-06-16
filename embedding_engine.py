import hashlib
import json
import math
import os
import time

import requests


EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
LLM_API_BASE = os.getenv("LLM_API_BASE", "http://localhost:11434").rstrip("/")
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "").lower()
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OLLAMA_EMBED_TIMEOUT = float(os.getenv("OLLAMA_EMBED_TIMEOUT", "4"))
OPENAI_EMBED_TIMEOUT = float(os.getenv("OPENAI_EMBED_TIMEOUT", "20"))
_OLLAMA_EMBED_AVAILABLE = None
_OLLAMA_EMBED_LAST_FAIL = 0
_OPENAI_EMBED_AVAILABLE = None
_OPENAI_EMBED_LAST_FAIL = 0


def deterministic_embedding(text, size=256):
    tokens = [t for t in str(text or "").lower().split() if t]
    vector = [0.0] * size
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "big") % size
        sign = 1 if digest[2] % 2 == 0 else -1
        vector[idx] += sign
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def generate_embedding(text, cache_get=None, cache_set=None):
    global _OLLAMA_EMBED_AVAILABLE, _OLLAMA_EMBED_LAST_FAIL, _OPENAI_EMBED_AVAILABLE, _OPENAI_EMBED_LAST_FAIL
    text = str(text or "").strip()
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if cache_get:
        cached = cache_get(text_hash, EMBEDDING_MODEL)
        if cached:
            return cached
    use_openai = OPENAI_API_KEY and (EMBEDDING_PROVIDER == "openai" or EMBEDDING_MODEL.startswith("text-embedding"))
    if use_openai:
        if _OPENAI_EMBED_AVAILABLE is False and time.time() - _OPENAI_EMBED_LAST_FAIL > 60:
            _OPENAI_EMBED_AVAILABLE = None
        if _OPENAI_EMBED_AVAILABLE is not False:
            try:
                response = requests.post(
                    f"{OPENAI_API_BASE}/embeddings",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                    json={"model": EMBEDDING_MODEL, "input": text[:8000]},
                    timeout=OPENAI_EMBED_TIMEOUT,
                )
                response.raise_for_status()
                data = response.json().get("data") or []
                embedding = (data[0] if data else {}).get("embedding") or []
                _OPENAI_EMBED_AVAILABLE = True
                if embedding and cache_set:
                    cache_set(text_hash, EMBEDDING_MODEL, embedding)
                if embedding:
                    return embedding
            except Exception:
                _OPENAI_EMBED_AVAILABLE = False
                _OPENAI_EMBED_LAST_FAIL = time.time()
    if _OLLAMA_EMBED_AVAILABLE is False and time.time() - _OLLAMA_EMBED_LAST_FAIL > 60:
        _OLLAMA_EMBED_AVAILABLE = None
    if _OLLAMA_EMBED_AVAILABLE is not False:
        try:
            response = requests.post(
                f"{LLM_API_BASE}/api/embeddings",
                json={"model": EMBEDDING_MODEL, "prompt": text[:4000]},
                timeout=OLLAMA_EMBED_TIMEOUT
            )
            response.raise_for_status()
            embedding = response.json().get("embedding") or []
            _OLLAMA_EMBED_AVAILABLE = True
            if embedding and cache_set:
                cache_set(text_hash, EMBEDDING_MODEL, embedding)
            if embedding:
                return embedding
        except Exception:
            _OLLAMA_EMBED_AVAILABLE = False
            _OLLAMA_EMBED_LAST_FAIL = time.time()
    embedding = deterministic_embedding(text)
    if cache_set:
        cache_set(text_hash, "deterministic-fallback", embedding)
    return embedding


def cosine_similarity(a, b):
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = sum(float(a[i]) * float(b[i]) for i in range(n))
    na = math.sqrt(sum(float(a[i]) ** 2 for i in range(n)))
    nb = math.sqrt(sum(float(b[i]) ** 2 for i in range(n)))
    if not na or not nb:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def serialize_embedding(vector):
    return json.dumps(vector, separators=(",", ":"))


def deserialize_embedding(value):
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []
