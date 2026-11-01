# Learning log

Format for each step: heading, the command(s), what happened, and 1–2 sentences on how I'd explain it in an interview.

## Setup

### Prerequisites check (2026-10-31)

- Node 22.0.0, Python 3.11.1, git 2.31 already installed.
- GitHub CLI, Docker and uv not installed. Only `gh` is needed (to create the repo from the terminal).

---

## Evening 1 — gateway, routing, guardrails, logs

### Step 1.1 — Run the open-source Portkey gateway locally

Docs used: Portkey gateway README (github.com/Portkey-AI/gateway), docs/installation-deployments.md in that repo, and the route table in `src/index.ts`.

**Commands**

```bash
npx @portkey-ai/gateway          # terminal 1, stays in the foreground
curl.exe http://localhost:8787/  # terminal 2
```

**What happened**

- Gateway started on port 8787 and printed `Ready for connections!` plus a UI link at `http://localhost:8787/public/`.
- `GET /` returned the plain text `AI Gateway says hey!`. There is no dedicated `/health` route in the OSS gateway; the root path is what you poll.
- The gateway is a single Node process. It holds no state and no keys yet; it only becomes useful once a request tells it which provider to talk to.

**How I'd explain it in an interview**

An AI gateway is a reverse proxy between every app and every model provider: apps speak one API, the gateway translates and is the one place to enforce keys, routing, guardrails and logging. Consumers never hold provider keys because a key in fifty repos cannot be rotated or attributed; a key in one gateway can.


**Concept: "stateless"**

The gateway remembers nothing between requests. Each request carries everything it needs (provider header, key, config); the gateway forwards it, streams the reply, writes a log line and forgets. Consequences: any replica can serve any request (no sticky sessions), a crashed replica loses nothing permanent, Kubernetes can scale pods freely, and the same code runs as a Cloudflare Worker, a container or a plain Node process. Stateless does not mean "no data": logs and metrics are written *out* to another system, and policy is read *in* from config at request time; nothing lives only inside the process. Contrast with the LangGraph agent in evening 2, which is stateful by design (a checkpointer remembers where a run paused). Clean split for interviews: the gateway is a stateless policy enforcement point; the agent runtime is where state lives.

### Step 1.2 — First request through the gateway

Docs used: Portkey headers reference (portkey.ai/docs/api-reference/inference-api/headers), provider slugs in gateway `src/globals.ts`, Groq model list (console.groq.com/docs/models).

**Command**

```bash
cd evening1-gateway
.\.venv\Scripts\python.exe first_request.py
```

Script: stock `openai` SDK with `base_url="http://localhost:8787/v1"`, `api_key=GROQ_API_KEY` (sent as `Authorization: Bearer`, forwarded to the provider) and one header `x-portkey-provider: groq`.

**What happened**

- First attempt failed with `404 - groq error: The model llama-3.1-8b-instant does not exist or you do not have access to it`. Groq now labels the Llama models "Enterprise", so the free key cannot use them. Switched to `openai/gpt-oss-20b`.
- That 404 was itself informative: the error text was Groq's, relayed verbatim, so app → gateway → Groq was already authenticated and working. The gateway passes upstream errors through transparently.
- Second attempt: `provider model: openai/gpt-oss-20b`, 81 tokens in / 104 out, a one-sentence answer. (The model described an IoT edge gateway rather than an LLM gateway. A small model misreading an ambiguous prompt is exactly the kind of thing the evening-2 evals are for.)

**Why the client is called `OpenAI` when we talk to Groq**

"OpenAI" names the wire format, not the company. The chat-completions request/response shape is the de facto standard; Groq's API is natively compatible, and the gateway accepts it on the way in and translates it for providers with their own formats (Anthropic `/v1/messages`, Gemini `generateContent`). Standardising every app on one SDK and one shape is what makes the gateway drop-in: an existing OpenAI-SDK app needs a one-line `base_url` change.

**How I'd explain it in an interview**

Unified API: the app speaks one request shape and changes nothing when the provider changes; the gateway owns the translation. I proved it by sending an OpenAI-SDK request to a Groq model through a local gateway with a single header to pick the provider.

### Step 1.3 — Routing config: fallback, retries, timeout

Docs used: config object schema (portkey.ai/docs/api-reference/inference-api/config-object), fallbacks, automatic-retries and request-timeouts pages under portkey.ai/docs/product/ai-gateway, Gemini model list (ai.google.dev/gemini-api/docs/models).

**Files:** `evening1-gateway/fallback_config.json` (two targets: groq → google, `strategy.mode: fallback`, `retry.attempts: 2` on 429/5xx, `request_timeout: 10000`), `evening1-gateway/fallback_request.py`. The JSON holds `${GROQ_API_KEY}` placeholders filled from `.env` at runtime; the config is sent inline in the `x-portkey-config` header. The client sends a dummy API key and no provider header: provider, model and key all live in the config now.

**Commands**

```powershell
.\.venv\Scripts\python.exe fallback_request.py              # run 1: served by openai/gpt-oss-20b (groq)
$env:GROQ_API_KEY = "gsk_this_is_deliberately_wrong"        # poison groq key for this shell only
.\.venv\Scripts\python.exe fallback_request.py              # run 2: served by gemini-3.5-flash-lite (google)
Remove-Item Env:GROQ_API_KEY                                # restore
```

**What happened**

- Run 1: Groq served it, 78 / 26 tokens.
- Run 2: Groq rejected the bad key (401, not a retry code, so no backoff wasted), the gateway moved to target 2, Gemini answered. Client saw a normal 200 and never knew.
- Fingerprints of the fallback in the console entry: request logged with `model: openai/gpt-oss-20b` (target 1's override) but response `model: gemini-3.5-flash-lite`, `provider: google`; duration 1313 ms vs ~400 ms (includes the failed first attempt); response id `portkey-...` instead of Groq's `chatcmpl-...` because the gateway synthesised an OpenAI-shaped response from Gemini's native format.
- Token counts are not comparable across providers: same prompt was 78 tokens on Groq (chat-template overhead counted) and 8 on Gemini. Cost dashboards must price per provider, never compare raw token totals.
- Limitation of the OSS console: one log entry per request showing the final provider. Hosted Portkey shows the full attempt chain; here you infer it from the mismatch above.

**Routing strategies, where each is used**

- **Fallback** (what we ran): ordered list, next target only when the current one fails. Resilience against provider outages, rate limits, key rotation mistakes.
- **Load balance**: weighted split across targets on every request. Spread spend across accounts/regions, stay under per-key rate limits, or mix a cheap and a strong model.
- **Conditional**: route by request metadata (team, data classification, user tier). The enterprise workhorse: "regulated data → in-region Azure OpenAI; everything else → cheapest provider".
- **Canary**: load balance with a small weight (e.g. 5%) to a new model/provider while watching evals and latency, then ramp. How model upgrades are promoted without a big-bang switch.

**How I'd explain it in an interview**

I put Groq and Gemini behind one fallback config with retries and a timeout, then poisoned the Groq key; the client got a 200 served by Gemini and never changed a line. The value is that resilience, provider choice and keys became a config the platform team owns, not code every app team maintains.

### Step 1.4 — Guardrail hooks

Docs used: gateway `plugins/default/manifest.json` (check ids and parameters), portkey.ai/docs/product/guardrails (200 / 246 / 446 semantics), creating-raw-guardrails-in-json (hook shape), and the plugin sources `regexMatch.ts`, `jsonSchema.ts`, `plugins/utils.ts` (regex runs on the LAST message only; verdict = "matched", inverted with `not`; JSON is extracted from a code fence or the first `{...}` and validated with draft 2020-12).

**Files:** `evening1-gateway/guardrails_config.json`, `evening1-gateway/guardrails_request.py pass|pii|badjson`.

- `before_request_hooks`: `default.regexMatch` with an email regex and `not: true`, `deny: true`. Passes when no email present.
- `after_request_hooks`: `default.jsonSchema` requiring exactly `{"product": str, "owner": str}` (`additionalProperties: false`), `deny: true`.

**What happened**

| scenario | status | duration | provider called? | evidence |
|---|---|---|---|---|
| pass | 200 | 520 ms | yes | both hooks `verdict: true`; `hook_results` attached to a normal response |
| pii | 446 | **1 ms** | **no** | `after_request_hooks: []`, `matchedText: jane.doe@example.com`; PII never left the network |
| badjson | 446 | 468 ms | yes, response withheld | `validationErrors`: missing `product`/`owner`, extra `name`/`team`/`sla` |

- Pre-request denial is free (1 ms, zero tokens). Post-response denial still costs the provider call; it protects consumers, not the budget.
- The denied email still appears in the gateway log (`textExcerpt`). Blocking at the gateway protects the provider boundary, not the log store; a real PII guardrail also redacts before logging.
- In the "pass" run, 145 of 168 completion tokens were hidden reasoning about the output format. Strict-format prompts are not free on reasoning models.
- The client sees 446 with a structured `hook_results` body, so an app can tell "blocked by policy" from "provider error" and show the right message.

**Why a fixed set of JSON keys**

The model's output is an API contract for the code that consumes it: a parser, a database insert, a UI card. If a prompt edit or a model swap changes `owner` to `team`, nothing errors at the model; the consumer breaks later, possibly silently (nulls in a table). A schema check at the gateway turns that into a loud 446 at the moment of the change, and because it lives in the gateway it holds across every provider and every model version. Providers offer native structured outputs (`response_format: json_schema`) which are better when available; the gateway check is the provider-agnostic backstop, and the only option when the provider has no such feature.

**Why guardrails live in the gateway, and how they tier**

- Every team inherits them without writing code; a new rule (block a new PII pattern, ban a model) ships once, centrally, instantly.
- They are enforced, not optional: an app cannot forget to call the guardrail library because it never sees the provider.
- Tiering by data classification is done with conditional routing + metadata: public data → cheap model, light checks; internal → PII block + logging; confidential/regulated → in-region provider, PII redaction, output schema, no prompt logging, human approval for side effects. The gateway reads the classification from request metadata (step 1.5) and applies the matching config.

**How I'd explain it in an interview**

I ran a pre-request regex guardrail that denied a prompt containing an email in 1 ms without calling the provider, and a post-response JSON-schema guardrail that withheld a response whose keys had drifted from the contract. Guardrails belong in the gateway because that is the one place every team's traffic already passes through, so policy is inherited, not opted into.

### Step 1.5 — Metadata and reading the logs like an operator

Docs used: portkey.ai/docs/product/observability/metadata (`x-portkey-metadata` JSON header, string values ≤128 chars, special `_user` key; OpenAI body `user` is mapped to `_user`), plugin source `requiredMetadataKeys.ts` (`metadataKeys`, `operator: all|any|none`, before-request only), and the installed gateway build: the console is fed by server-sent events at `GET /log/stream`, one entry per request `{time, method, endpoint, status, duration, requestOptions[]}` with one element in `requestOptions` per target attempted.

**Files:** `evening1-gateway/metadata_config.json` (fallback + a `default.requiredMetadataKeys` guardrail that denies requests missing `_user` or `use_case`), `evening1-gateway/metadata_request.py tagged|untagged`, `evening1-gateway/read_logs.py` (tails `/log/stream`, prints one operator line per request).

**Commands**

```powershell
.\.venv\Scripts\python.exe read_logs.py                 # terminal 3, leave running
.\.venv\Scripts\python.exe metadata_request.py tagged   # 200
.\.venv\Scripts\python.exe metadata_request.py untagged # 446 require-attribution-tags
.\.venv\Scripts\python.exe guardrails_request.py pii    # 446 block-email-pii
$env:GROQ_API_KEY = "gsk_wrong"; .\.venv\Scripts\python.exe fallback_request.py; Remove-Item Env:GROQ_API_KEY   # fallback
```

**What happened**

```
200   431ms user=samer provider=groq   model=openai/gpt-oss-20b    in/out=78/76 attempts=1 target=targets[0] fallback=no  guardrail_denied=none
446     1ms user=samer provider=groq   model=openai/gpt-oss-20b    in/out=-/-   attempts=1 target=targets[0] fallback=no  guardrail_denied=require-attribution-tags
446     1ms user=-     provider=groq   model=openai/gpt-oss-20b    in/out=-/-   attempts=1 target=config     fallback=no  guardrail_denied=block-email-pii
200   886ms user=samer provider=google model=gemini-3.5-flash-lite in/out=8/1   attempts=2 target=targets[1] fallback=YES guardrail_denied=none
```

- **Finding: guardrail denials triggered the fallback.** First version of the config had `strategy: {mode: fallback}` with no `on_status_codes`, so the default "any non-2xx" applied and a 446 from the metadata guardrail made the gateway try target 2 (Gemini), which was denied again (`attempts=2`, 2 ms). A policy failure is not a provider failure; retrying it on another provider is wasted work and, with a weaker guardrail on target 2, a bypass. Fix: `strategy.on_status_codes: [408, 429, 500, 502, 503, 504]`.
- The local console does **not** store `x-portkey-metadata` (the guardrail proves the gateway parses it). The OpenAI body `user` field is the one identity that survives into the local log. Hosted Portkey indexes metadata for dashboards and filters.
- Gemini's attempt is stored only as its native body (`usageMetadata.promptTokenCount`), so the operator script normalises token fields per provider. This is exactly the job of the gateway's log pipeline in production.
- **Uncomfortable detail:** each log entry includes `providerOptions.apiKey` in plaintext and the full `Authorization` header in `transformedRequest`. The local log stream is a secret-bearing system; in production the log pipeline must redact before persisting, and access to raw gateway logs is a privileged role.

**From log line to dashboard and budget**

Each line is already a fact table row: `(timestamp, user, use_case, team, provider, model, tokens_in, tokens_out, latency, status, fallback, guardrail)`. Join with a per-model price list → cost per request; `GROUP BY use_case, day` → cost-per-use-case dashboard; `GROUP BY team` → chargeback. Add a running sum per `use_case` and compare to a limit → budget alert; reject with 429 when exceeded → budget enforcement. Count `fallback=YES` per provider per minute → provider health alert. Count `guardrail_denied` per team → policy-violation report. None of this is possible unless the `use_case`/`_user` tags are mandatory, which is why the metadata guardrail exists.

**How I'd explain it in an interview**

Every request through the gateway produces one structured log line with who, what for, provider, model, tokens, latency, fallback and guardrail outcome, and I made the attribution tags mandatory with a guardrail so no spend is unowned. That line is the raw material for cost-per-use-case dashboards, chargeback, budget alerts and provider health, all without touching application code. I also found that guardrail denials default to triggering fallback, which has to be switched off explicitly.

### Step 1.6 — Five sentences on what I saw (evening 1)

1. I ran the open-source Portkey gateway locally with `npx`, pointed the stock OpenAI Python SDK at it, and sent requests to Groq and Gemini by changing only a header or a config, never the application code.
2. I put Groq and Gemini behind one fallback config with retries and a timeout, poisoned the Groq key, and watched the client get a normal 200 served by Gemini; the only evidence was in the gateway log, where the request model and the response model no longer matched.
3. I attached a pre-request regex guardrail that denied a prompt containing an email address in 1 ms without the provider ever being called, and a post-response JSON-schema guardrail that withheld a reply whose keys had drifted from the contract.
4. I made `_user` and `use_case` tags mandatory with a metadata guardrail and tailed the gateway's log stream to print one line per request with who, provider, model, tokens, latency, which target served it, whether fallback fired, and which guardrail denied it.
5. Along the way I found that guardrail denials trigger fallback unless `on_status_codes` is set explicitly, and that the local log entries contain provider API keys in plaintext, so the gateway's logs are a secret-bearing system that needs redaction and access control before production.

---

## Evening 2 — one agent, one MCP tool, one trace, one eval

### Step 2.1 — A tiny MCP server

Docs used: modelcontextprotocol.io/quickstart/server (Python tab) and the installed `mcp` 2.3.0 package. **Plan correction:** in mcp ≥ 2 `FastMCP` was renamed `MCPServer` (`from mcp.server import MCPServer`); result fields are snake_case (`input_schema`, `structured_content`).

**Files:** `evening2-agent/catalog.json` (5 fake data products: owner, SLA, classification), `evening2-agent/catalog_server.py` (one tool `lookup_product(name)`, `mcp.run(transport="stdio")`), `evening2-agent/call_tool.py` (bare client, no LLM).

**Command**

```bash
.\.venv\Scripts\python.exe call_tool.py
```

**What happened**

- The client launched the server as a subprocess, did the MCP handshake (server name `data-catalog`), called `tools/list` and got one tool with a JSON schema generated from the Python signature and docstring, then called `tools/call` with `{"name": "consent"}` and got the `customer-consent` record back.
- The server never printed anything itself: stdin/stdout carry the protocol, so a stray `print()` in a stdio server corrupts the stream.
- The result only contains `customer-consent` because the client hard-coded the argument. From 2.2 onward the model chooses the argument.

**Concepts**

- **Tools / resources / prompts:** tools are functions the model may call; resources are read-only data the application can load into context; prompts are reusable templates a user picks. Tools are model-initiated, resources and prompts are application- or user-initiated.
- **Client vs server:** the server is model-agnostic and only answers list/call; the client lives inside the AI application, owns the connection and relays the model's tool calls. The docstring and type hints *are* the interface the model sees.
- **What an enterprise MCP gateway adds:** a *registry* (which servers exist, who published them, versioned schemas), *per-agent identity* (the agent authenticates to the gateway, not to each server; the gateway holds the downstream credentials, same pattern as the LLM gateway and provider keys), *scopes* (this agent may call `lookup_product` but not `delete_product`), *audit* (every tool call logged with who/which agent/arguments/result), plus rate limits and the ability to kill a bad server centrally. Without it every agent connects to every server with its own credentials, and nobody can answer "which agents can touch the orders ledger?".

**How I'd explain it in an interview**

I wrote a 30-line MCP server with one tool and a bare client that discovered and called it over stdio with no LLM involved, so I understand the protocol as plain JSON-RPC before any agent framework hides it. An MCP gateway is to tool servers what the LLM gateway is to model providers: one place for identity, scopes, audit and credentials.
