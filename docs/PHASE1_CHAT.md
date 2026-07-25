# Phase 1 — Clinical Review Chat

Phase 1 adds a **conversational interface** to the existing LangGraph case review stack. Instead of only clicking buttons in the test UI, you can chat with the same clinical agent (Neo4j tools + case context) and drive the formal workflow with slash commands.

## What you get

| Component | URL / endpoint |
|-----------|----------------|
| Chat UI | http://localhost:8000/chat |
| Create session | `POST /api/v1/chat/sessions` |
| Send message | `POST /api/v1/chat/sessions/{id}/messages` |
| Get session | `GET /api/v1/chat/sessions/{id}` |

## Architecture

```
Browser (/chat)
    │
    ▼
POST /api/v1/chat/sessions/{id}/messages
    │
    ├── Slash command? → case workflow actions
    │
    └── Free text → LangGraph chat agent
                        ├── agent node (LLM)
                        └── tools node (Neo4j)
```

**Two LangGraph graphs:**

| Graph | Purpose | HITL interrupt |
|-------|---------|----------------|
| `app/ai/agent.py` | Formal one-shot case review | Yes → `Pending_Approval` |
| `app/ai/chat_agent.py` | Multi-turn conversation | No |

Both share the same LLM (`app/ai/llm.py`) and Neo4j tools.

## Quick start

1. Start the stack:

```bash
docker compose up -d
```

2. Open http://localhost:8000/chat

3. Paste a **case ID** from the main UI (or click **Load cases**)

4. Click **New chat session**

5. Ask questions, for example:

- `What does Jane Doe's glucose result suggest?`
- `Check reference ranges for LOINC 2339-0`
- `How do diabetes and hypertension interact for this patient?`

## Slash commands (workflow bridge)

Link the chat to a case, then use:

| Command | Action |
|---------|--------|
| `/help` | List commands |
| `/status` | Show linked case status |
| `/start-review` | `Pending` → `AI_Review` |
| `/formal-review [query]` | Run full LangGraph HITL review → `Pending_Approval` |
| `/approve [reason]` | Human approve |
| `/reject [reason]` | Human reject |

### Example session

```
You: /start-review
Agent: Case moved to AI_Review...

You: Is creatinine elevated for this patient?
Agent: [conversational answer using case context + tools]

You: /formal-review Assess CKD risk based on creatinine and glucose
Agent: Formal review complete. Status: Pending_Approval ...

You: /approve Clinical criteria met
Agent: Case approved. Final status: Approved
```

## API examples

### Create session linked to a case

```bash
curl -X POST http://localhost:8000/api/v1/chat/sessions \
  -H "Content-Type: application/json" \
  -d '{"case_id": "YOUR-CASE-UUID"}'
```

### Send a message

```bash
curl -X POST http://localhost:8000/api/v1/chat/sessions/SESSION_ID/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "What is the normal glucose reference range for LOINC 2339-0?"}'
```

## Why FastAPI chat instead of Streamlit?

- Same Docker service — no extra container
- Reuses existing auth, audit, and case services
- Matches the current static UI approach
- Easy to call from curl, Swagger, or a future frontend

Streamlit can be added later as a thin client on top of these same `/api/v1/chat/*` endpoints if desired.

## Files added

```
app/ai/llm.py              # Shared LLM builder
app/ai/chat_agent.py       # Conversational LangGraph
app/services/chat_service.py
app/api/routes/chat.py
app/static/chat.html
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| 503 on send | Check `LLM_BASE_URL` / OpenAI config |
| No case context | Create session with valid `case_id` |
| `/formal-review` fails | Run `/start-review` first; case must be `AI_Review` |
| Tools return nothing | Seed Neo4j (`init.cypher`) |
