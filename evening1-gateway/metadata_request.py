"""Step 1.5 - tag every request with WHO and WHAT FOR.

Two places carry identity:
  * `x-portkey-metadata` header: free-form string tags ({"_user", "use_case", "team", ...}).
    Hosted Portkey indexes these for per-team dashboards and budgets. The local gateway
    parses them (we prove it with a guardrail that DENIES untagged requests) but its
    console does not store them.
  * the OpenAI `user` body field: Portkey maps it to `_user`; the local log keeps the
    request body, so this is the one identity field you can see in read_logs.py.

Usage:  python metadata_request.py tagged | untagged
"""
import json, os, string, sys
from dotenv import load_dotenv
from openai import OpenAI, APIStatusError

load_dotenv("../.env")
config = string.Template(open("metadata_config.json").read()).substitute(os.environ)

headers = {"x-portkey-config": json.dumps(json.loads(config))}
if sys.argv[1] == "tagged":
    headers["x-portkey-metadata"] = json.dumps({
        "_user": "samer",            # who (special key: powers per-user analytics)
        "use_case": "catalog-bot",   # what for -> cost-per-use-case
        "team": "platform",
        "env": "lab",
    })

client = OpenAI(base_url="http://localhost:8787/v1", api_key="not-used", default_headers=headers, max_retries=0)

try:
    resp = client.chat.completions.create(
        model="ignored",
        user="samer",                # body-level identity, visible in the local log
        messages=[{"role": "user", "content": "Reply with the single word: pong"}],
    )
    print("HTTP 200  served by", resp.model, "| answer:", resp.choices[0].message.content)
except APIStatusError as e:
    body = e.response.json()
    chk = body["hook_results"]["before_request_hooks"][0]["checks"][0]["data"]
    print(f"HTTP {e.status_code}  DENIED:", chk.get("explanation") or chk)
