"""Step 1.5 - read the gateway log like an operator.

The local gateway pushes one JSON entry per request over server-sent events at
/log/stream (this is what the /public/ console listens to). Each entry holds one
element in `requestOptions` PER TARGET ATTEMPTED, so a fallback shows up as two.
This script tails the stream and prints ONE LINE per request with the fields a
platform team bills and alerts on. Leave it running while you send traffic.
"""
import json, urllib.request

def usage_of(attempt):
    """Tokens in/out. The normalised response has `usage`; if the log only kept the
    provider's native body, fall back to it (Gemini calls it usageMetadata)."""
    resp = attempt.get("response") or {}
    native = (attempt.get("originalResponse") or {}).get("body") or {}
    u = resp.get("usage") or native.get("usage")
    if u:
        return u.get("prompt_tokens", "-"), u.get("completion_tokens", "-")
    g = native.get("usageMetadata")
    if g:
        return g.get("promptTokenCount", "-"), g.get("candidatesTokenCount", "-")
    return "-", "-"

def summarise(entry):
    attempts = entry["requestOptions"]
    last = attempts[-1]
    prov = last["providerOptions"]
    resp = last.get("response") or {}
    native = (last.get("originalResponse") or {}).get("body") or {}
    model = resp.get("model") or native.get("modelVersion") or prov.get("overrideParams", {}).get("model", "-")
    tin, tout = usage_of(last)
    # a guardrail denial is recorded on the attempt where it happened, not necessarily the last one
    denied = [h["id"] for a in attempts for phase in ((a.get("response") or {}).get("hook_results") or {}).values()
              for h in phase if not h["verdict"]]
    # "who": the OpenAI `user` body field is the only caller identity the local log keeps
    who = (attempts[0].get("finalUntransformedRequest") or {}).get("body", {}).get("user", "-")
    return (f"{entry['time']:<22} {entry['status']:>3} {entry['duration']:>5}ms "
            f"user={who:<8} provider={prov.get('provider','-'):<7} model={model:<24} "
            f"in/out={tin}/{tout:<5} attempts={len(attempts)} "
            f"target={last.get('lastUsedOptionIndex','-'):<18} "
            f"fallback={'YES' if len(attempts) > 1 else 'no':<3} "
            f"guardrail_denied={','.join(dict.fromkeys(denied)) or 'none'}")

print("tailing http://localhost:8787/log/stream  (Ctrl+C to stop)")
with urllib.request.urlopen("http://localhost:8787/log/stream") as stream:
    for raw in stream:
        line = raw.decode().strip()
        if line.startswith("data:") and line[5:].strip().startswith("{"):
            try:
                print(summarise(json.loads(line[5:].strip())), flush=True)
            except Exception as e:                      # never let a weird entry kill the tail
                print("could not summarise entry:", e, flush=True)
