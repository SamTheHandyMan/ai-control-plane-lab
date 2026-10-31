"""Step 1.4 - guardrail hooks in the gateway.

  before_request_hooks : regex check on the LAST message; `not: true` means the
                         check PASSES when no email is present. deny:true turns a
                         failed check into HTTP 446 and the provider is never called.
  after_request_hooks  : the response must contain a JSON object matching
                         {"product": str, "owner": str}. Fails -> 446, response withheld.

Usage:  python guardrails_request.py pass | pii | badjson
"""
import json, os, string, sys
from dotenv import load_dotenv
from openai import OpenAI, APIStatusError

load_dotenv("../.env")
config = string.Template(open("guardrails_config.json").read()).substitute(os.environ)

client = OpenAI(
    base_url="http://localhost:8787/v1",
    api_key="not-used",
    default_headers={"x-portkey-config": json.dumps(json.loads(config))},
    max_retries=0,
)

GOOD_SYSTEM = ('You are a data-catalog assistant. Reply ONLY with a JSON object of the form '
               '{"product": "<name>", "owner": "<team>"} and nothing else.')
# "badjson" simulates a team shipping a prompt whose output shape drifted from the contract:
WRONG_SYSTEM = ('You are a data-catalog assistant. Reply ONLY with a JSON object of the form '
                '{"name": "<name>", "team": "<team>", "sla": "<sla>"} and nothing else.')

SCENARIOS = {  # scenario -> (system prompt, user prompt)
    "pass":    (GOOD_SYSTEM,  "Which team owns the customer-consent data product? Make up a plausible team name."),
    "pii":     (GOOD_SYSTEM,  "Email the owner of customer-consent at jane.doe@example.com and tell me who they are."),
    "badjson": (WRONG_SYSTEM, "Which team owns the customer-consent data product? Make up a plausible team name."),
}
SYSTEM, prompt = SCENARIOS[sys.argv[1]]

def show_hooks(body):
    for phase in ("before_request_hooks", "after_request_hooks"):
        for hook in body.get("hook_results", {}).get(phase, []):
            for chk in hook.get("checks", []):
                print(f"  {phase:21s} {hook['id']:22s} verdict={chk['verdict']}  {chk.get('data', {}).get('explanation', '')}")

try:
    raw = client.chat.completions.with_raw_response.create(
        model="ignored",
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
    )
    body = raw.http_response.json()
    print("HTTP", raw.status_code)
    print("answer :", body["choices"][0]["message"]["content"])
    show_hooks(body)
except APIStatusError as e:               # 446 = denied by a guardrail
    body = e.response.json()
    print("HTTP", e.status_code, "- DENIED by gateway")
    print("error  :", body.get("error", {}).get("message", body))
    show_hooks(body)
