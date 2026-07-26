"""Quick LLM API smoke test — reads keys from .env, tests each provider."""
import os, sys, httpx, time
sys.stdout.reconfigure(encoding='utf-8')

# Load .env manually
for line in open(".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

providers = [
    {
        "name": "FreeTheAI (GLM 5.2)",
        "key": os.environ.get("EUROSCOPE_LLM_API_KEY", ""),
        "base": os.environ.get("EUROSCOPE_LLM_API_BASE", "https://api.freetheai.xyz/v1"),
        "model": os.environ.get("EUROSCOPE_LLM_MODEL", "glm/glm-5.2"),
    },
    {
        "name": "OpenRouter (DeepSeek)",
        "key": os.environ.get("EUROSCOPE_LLM_FALLBACK_API_KEY", ""),
        "base": os.environ.get("EUROSCOPE_LLM_FALLBACK_API_BASE", "https://openrouter.ai/api/v1"),
        "model": os.environ.get("EUROSCOPE_LLM_FALLBACK_MODEL", "deepseek/deepseek-chat"),
    },
]

client = httpx.Client(timeout=30)

for p in providers:
    print(f"\n{'='*50}")
    print(f"Testing: {p['name']}")
    print(f"  Base: {p['base']}")
    print(f"  Model: {p['model']}")
    print(f"  Key: {p['key'][:10]}...{p['key'][-6:]}" if len(p['key']) > 16 else f"  Key: {p['key'] or 'NOT SET'}")

    if not p["key"]:
        print("  ⏭️  SKIPPED — no API key")
        continue

    try:
        t0 = time.time()
        resp = client.post(
            f"{p['base']}/chat/completions",
            headers={
                "Authorization": f"Bearer {p['key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": p["model"],
                "messages": [{"role": "user", "content": "Say hello in exactly 3 words."}],
                "max_tokens": 30,
                "temperature": 0.1,
            },
        )
        elapsed = time.time() - t0
        print(f"  Status: {resp.status_code} ({elapsed:.1f}s)")

        if resp.status_code == 200:
            data = resp.json()
            reply = data["choices"][0]["message"]["content"]
            print(f"  ✅ Response: {reply}")
        else:
            print(f"  ❌ Error: {resp.text[:200]}")
    except Exception as e:
        print(f"  ❌ Exception: {e}")

client.close()
print(f"\n{'='*50}")
print("Done.")
