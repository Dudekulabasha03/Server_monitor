# Helios AI — Multi-Agent Observability & Copilot (Experimental)

## 0. Goal & Guiding Principles
Add an **agentic AI layer** to Helios (NL fleet copilot, AI-RCA, SEL summarization,
capacity narration) powered by AMD on-prem **GPT-oss-20B**, using **LangGraph** with a
**Supervisor + specialist ReAct agents**, **3-tier memory**, and a dedicated
**Observability agent**.

**Hard principles (guardrails):**
1. AI is **advisory only** — it never decides health/status, never fires alerts, never
   writes to BMC/DB state. All agent tools are **read-only**.
2. Every numeric claim must originate from a tool result; the Observability agent flags
   any answer with unbacked numbers.
3. Deterministic rule-based engines (`rca.py`, `recommendations.py`, `analytics.py`)
   remain the **fallback** — if the LLM is slow/down/low-confidence, Helios degrades to
   rule-based output, never blocks a page.
4. **Experimental isolation**: the entire AI build runs as a *separate stack on offset
   ports*. The current production deployment is untouched and serves as the backup.

---

## 1. Experimental Deployment Isolation (CRITICAL)

The existing production stack stays exactly as-is (the backup). The AI build is a new,
parallel Compose project so nothing collides.

| Service | Prod port (keep) | Experimental port |
|---|---|---|
| frontend | 3000 | **3100** |
| backend (API) | 8000 | **8100** |
| postgres | 5432 | **5532** |
| redis | 6379 | **6479** |
| victoriametrics | 8428 | **8528** |
| grafana | 3001 | **3101** |
| nginx | 80/443 | **8080 / 8443** |

Implementation:
- New file `docker-compose.ai.yml` with `COMPOSE_PROJECT_NAME=fleetmon-ai`, distinct
  `container_name` (`fleetmon-ai-*`), distinct named volumes (`postgres_ai_data`, …),
  and the offset ports above.
- The experimental DB is a **separate volume**. Seed it once from a `pg_dump` of prod so
  the AI stack has the real 274-server fleet to reason over, but can never corrupt prod.
- Frontend env `NEXT_PUBLIC_API_URL=http://<host>:8100`.
- Bring up: `docker compose -p fleetmon-ai -f docker-compose.ai.yml up -d`.
- Tear down without touching prod: `docker compose -p fleetmon-ai -f docker-compose.ai.yml down`.

**Rollback = do nothing**: prod on 3000/8000 keeps running throughout.

---

## 2. LLM Client (AMD GPT-oss-20B)

OpenAI-compatible endpoint with a custom subscription header.
- Base URL: `https://llm-api.amd.com/OnPrem`
- Model: `GPT-oss-20B`
- Auth header: `Ocp-Apim-Subscription-Key: <key>` + `user: <login>` (NOT bearer)
- Verified working from the deploy host: returns 200, supports `tool_calls` and a
  `reasoning` field (ideal for ReAct).

Config (experimental `.env` only):
```
AI_ENABLED=true
AI_BASE_URL=https://llm-api.amd.com/OnPrem
AI_MODEL=GPT-oss-20B
AI_SUBSCRIPTION_KEY=********
AI_TIMEOUT=45
AI_MAX_TOKENS=1024
AI_TEMPERATURE=0.2          # low — we want grounded answers, not creativity
```
`backend/app/ai/client.py` — thin async wrapper (httpx) injecting the custom headers,
exposing `chat(messages, tools=None)` and `stream(messages)`. `AI_ENABLED=false` ⇒ every
AI endpoint returns `{available: false}` and the UI hides AI affordances.

---

## 3. Agent Architecture (LangGraph: Supervisor + ReAct specialists)

```
            ┌──────────────┐
 request ─► │  SUPERVISOR  │  classify intent → route to ONE specialist → aggregate
            └──────┬───────┘
   ┌─────────┬─────┼──────────┬───────────┐
   ▼         ▼     ▼          ▼           ▼
 FleetQA    RCA   SEL     Capacity   (others later)
 (ReAct)  (ReAct) Summary  /Trend
   └─────────┴─────┴──────────┘
             │ read-only tools          ┌────────────────────┐
             ▼                          │ OBSERVABILITY AGENT │ wraps EVERY run:
   existing Helios queries/APIs         │ logs each ReAct step│ thought/action/obs,
                                        │ latency, tokens,    │ tool validity,
                                        │ hallucination flags │ → ai_traces table
                                        └────────────────────┘
```

Why Supervisor + narrow specialists: a 20B model drifts when one agent owns everything.
Narrow tool sets + focused system prompts keep each ReAct loop reliable.

### ReAct loop (each specialist)
`Thought → Action(tool) → Observation → … → Final Answer`. GPT-oss-20B already returns
`reasoning` + `tool_calls`, so the loop is: call model → if tool_calls, execute tools
(read-only) → append observations → repeat (max N=5 steps) → final answer. Hard cap on
steps + per-step timeout.

### Specialists
| Agent | Purpose | Read-only tools |
|---|---|---|
| **Supervisor** | route intent, no tools | — |
| **Fleet Q&A** | "which Turin/Bangalore servers are critical?" | query_servers, get_fleet_summary, get_alerts, get_risk |
| **RCA** | root cause for an alert/server | get_server_detail, get_sel_events, get_metrics_history; **fallback: rca.py** |
| **SEL Summary** | condense SEL events | get_sel_events |
| **Capacity/Trend** | explain forecasts | get_capacity, get_metrics_history; **fallback: analytics.py** |
| **Observability** | trace + QA every run (not user-facing) | reads ai_traces |

---

## 4. Tool Layer (`backend/app/ai/tools.py`) — READ ONLY

Each tool is a thin wrapper over existing queries/endpoints, returns compact JSON, and is
declared as an OpenAI function schema. No tool can write.

- `get_fleet_summary()` → status counts, power, avg health
- `query_servers(status?, team?, family?, datacenter?, search?, limit?)`
- `get_server_detail(hostname|id)` → identity, latest snapshot, components, processors
- `get_alerts(severity?, state?, hostname?)`
- `get_sel_events(hostname?, severity?, limit?)`
- `get_risk(top?)` → risk ranking
- `get_capacity()` / `get_metrics_history(id, metric, hours)`
- `get_recommendations(hostname?)`

Validation: tool args parsed against the schema; bad calls return an error observation the
agent must recover from (not a crash).

---

## 5. Three-Tier Memory (keyword + recency now; pgvector-ready later)

pgvector is **not** installed (postgres:16-alpine). Start with Postgres JSONB + keyword +
recency; the schema leaves room for an `embedding` column to add later.

| Tier | Contents | Store | Lifetime | Recall |
|---|---|---|---|---|
| **Short-term** | current conversation turns | Redis (`ai:sess:<id>`) | session / 1h TTL | full turns for follow-ups |
| **Episodic** | past Q&A, past RCA verdicts per server/incident | PG `ai_episodes` | 90 days | keyword + recency + server_id |
| **Long-term** | confirmed root causes, remediations that worked, fleet patterns | PG `ai_knowledge` | durable | keyword + recency (vector later) |

Tables:
```
ai_episodes(id, session_id, server_id?, kind, question, answer, tools_used jsonb,
            created_at, ttl_at)
ai_knowledge(id, scope[server|family|fleet], key_terms text, fact text,
             source[rca|resolution|pattern], confidence, created_at, embedding? )
ai_traces(id, run_id, agent, step_no, thought, action jsonb, observation jsonb,
          latency_ms, tokens_in, tokens_out, flags jsonb, created_at)
```
Memory write points:
- After each answer → episodic entry.
- When an engineer **resolves an alert** (existing action) → capture context as a
  long-term "remediation" fact → suggested next time the pattern recurs.
- Confirmed RCA verdicts → long-term.

Recall: on a new request, supervisor pulls (a) short-term turns, (b) top-K episodic by
server_id+keyword+recency, (c) top-K long-term by keyword — injected as grounding context.

---

## 6. Observability Agent + AI Ops Dashboard

The Observability agent wraps every specialist run and is the answer to "keep an
observability agent":
- Logs each ReAct step to `ai_traces` (thought, tool call, observation, latency, tokens).
- **Hallucination check**: scans the final answer for numbers/hostnames not present in any
  tool observation → sets a `flags.unbacked_claims` marker.
- Tracks per-agent success rate, avg latency, token spend, fallback rate.
- Surfaces an **"AI Ops" tab** (experimental frontend): runs timeline, per-agent metrics,
  flagged answers, token/cost trend, live trace viewer.

---

## 7. API Surface (`backend/app/api/ai.py`, prefix `/api/v1/ai`)
- `POST /ai/ask` — Copilot; body `{question, session_id}`; **streams** tokens; returns
  answer + tools_used + trace_id + grounding sources.
- `GET  /ai/rca/{alert_id}` — AI RCA narrative; **falls back** to rule-based rca.py.
- `GET  /ai/sel-summary?hostname=&scope=` — SEL digest.
- `GET  /ai/capacity-narrative` — plain-English forecast explanation.
- `GET  /ai/observability` — traces, agent metrics, flagged runs (AI Ops tab).
- `POST /ai/feedback` — thumbs up/down on an answer → tunes episodic confidence.
- `GET  /ai/health` — endpoint/model reachability + AI_ENABLED.

---

## 8. Frontend (experimental, port 3100)
- **"Ask Helios"** copilot: sidebar entry + chat panel, streaming, shows which tools ran
  and the source rows behind each answer.
- **AI RCA**: narrative block on the Alerts RCA panel, *alongside* the existing rule-based
  causes (clearly labeled "AI analysis", with a confidence chip).
- **SEL page**: "AI Summary" button.
- **Capacity/Utilization**: "Explain this trend" button.
- **AI Ops** tab: observability dashboard (traces, metrics, flagged answers).
- Every AI surface shows a disclaimer + a fallback notice when the model is unavailable.

---

## 9. Proactive Ideas (suited to Helios)
- **Morning Fleet Brief** (cron): Observability + RCA agents produce "what changed
  overnight, likely causes, what to watch" — posted to the dashboard / Teams.
- **Remediation memory**: learn from resolved alerts; suggest the prior fix on recurrence.
- **"Explain this server"** one-click narrative on the detail page.
- **Anomaly explainer**: pair with `analytics.py` forecasts to say *why* a trend is odd.

---

## 10. Build Phases (each independently verifiable)
1. **Isolation + Foundation**: `docker-compose.ai.yml` (offset ports, cloned DB),
   `ai/client.py`, `ai/tools.py`, `ai_traces` table, `/ai/health` + smoke test.
2. **Fleet Q&A ReAct agent** + short-term (Redis) memory + "Ask Helios" UI (streaming).
3. **Supervisor + RCA/SEL/Capacity agents** + episodic/long-term memory + rule-based
   fallbacks wired.
4. **Observability agent + AI Ops dashboard** + proactive Fleet Brief.

---

## 11. Pros / Cons / Risk
| Area | Pro | Con | Mitigation |
|---|---|---|---|
| NL copilot | Fast answers over 274 servers | hallucinated numbers | forced tool-use; show sources; obs-agent flags |
| AI-RCA | context-aware causes | confidently wrong | rule-based fallback shown alongside |
| 20B on-prem | private, no external data egress, free | weaker than frontier models | narrow agents, low temp, structured tasks |
| Multi-agent | reliable, debuggable | more moving parts | supervisor + tracing + step caps |
| Memory | learns over time | stale/incorrect facts | confidence + recency decay + feedback |
| Latency | — | adds seconds | streaming, caching, async, step cap N=5 |

---

## 12. Dependencies (added to experimental backend image only)
`langgraph`, `langchain-core`, `langchain-openai` (OpenAI-compatible client), `redis`
(already present). No change to the production image.

---

## 13. Verification
- `/ai/health` returns model reachable + AI_ENABLED.
- Ask "How many critical servers?" → answer matches `/servers/summary` exactly (obs-agent
  shows 0 unbacked claims).
- Kill AI_ENABLED → pages still work, AI hidden, RCA falls back to rule-based.
- Prod stack on 3000/8000 unaffected throughout (curl both ports).
- AI Ops tab shows traces with per-step thought/action/observation.
```
```
