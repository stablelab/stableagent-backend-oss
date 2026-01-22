## StableAgent Backend – Agentic Orchestration

This backend provides an agent that answers questions over DAO data using LLM tools (schema/context, SQL generation, DB execution, web search, etc.). It uses LangGraph for a deterministic tool-calling flow with a trio-agent architecture.

### Key features
- Trio-agent with clear roles (Aggregator, Analyst, Reasoner + Think)
- Deterministic tool loop (LangGraph) with checkpointed state (memory or sqlite)
- Streaming-compatible SSE events
- Delegate voting agent with ReAct reasoning for proposal analysis.

### Project layout
- `src/llm/factory.py`: Provider-agnostic LLM factory (OpenAI, Vertex AI)
- `src/tools/*`: Tool implementations (SQL, schema context, context expansion, web search, etc.)
- `src/agent/langgraph/state.py`: Shared agent state type for LangGraph
- `src/agent/langgraph/sota_trio.py`: Trio-agent LangGraph app (Aggregator ↔ Analyst ↔ Reasoner + Think)
- `src/agent/delegate/*`: Delegate voting agent with ReAct reasoning.
- `src/agent/langgraph/checkpointer.py`: Checkpointer factory (memory/sqlite)
- `src/pipelines/rag_answer.py`: Helper utilities available to agents
- `src/routers/fastapi_router.py`: API endpoints
- `src/config/delegate_agent_settings.py`: Configuration loader for the delegate agent.
- `src/config/agent_config.yaml`: YAML configuration for delegate agent prompts and behavior.
- `src/data_models/delegate_schemas.py`: Pydantic schemas for the delegate agent.
- `src/services/delegate_database.py`: API client for fetching DAO data.

### API endpoints
- `POST /lc/v1/chat` – non-streaming agent answer
- `POST /lc/v1/chat/stream` – streaming (SSE) agent answer with tool/LLM event mapping
- `GET /analyse` – Analyzes a governance proposal and provides a voting recommendation.
- Compatibility: `POST /v1/chat/completions`, `POST /v1/responses`

### Quick start
```bash
pip install -r requirements.txt
# Optional: enable LangGraph
pip install langgraph

uvicorn src.main:app --reload --port 8080
```

Set `STABLELAB_TOKEN` and LLM provider envs, then call `/lc/v1/chat` with JSON body:
```json
{ "query": "What was the context of in the last Aave proposal?", "conversation_id": "demo" }
```

### LangGraph
- Set `USE_LANGGRAPH=1` to run the LangGraph trio agent (default code path). If not set, the router still falls back to the trio agent.

### Role-specific models (recommended)
- Aggregator (fast planner/router): `AGGREGATOR_PROVIDER` / `AGGREGATOR_MODEL`
- Analyst (tool execution): `EXECUTOR_PROVIDER` / `EXECUTOR_MODEL`
- Think (brief critique): `THINK_PROVIDER` / `THINK_MODEL`
If unset, each role falls back to request-level `provider`/`model`, then global defaults.

### Checkpointing (sessions/memory)
- `LANGGRAPH_CHECKPOINTER=memory` (default) or `sqlite`
- `LANGGRAPH_SQLITE_PATH=./data/langgraph.sqlite` (used when sqlite)
- Session continuity is keyed by `conversation_id` → `thread_id` under LangGraph.

### Iteration caps
- `LANGGRAPH_TRIO_MAX_ITERS` – trio-agent loop cap (default 18)

### Environment (.env) summary
```env
# API auth
STABLELAB_TOKEN=your_token

# DB
DATABASE_HOST=127.0.0.1
DATABASE_PORT=5432
DATABASE_NAME=stableagent
DATABASE_USER=postgres
DATABASE_PASSWORD=your_password

# LLM provider & defaults
DEFAULT_LLM_PROVIDER=vertex_ai   # or openai
VERTEX_DEFAULT_MODEL=gemini-3-flash-preview
OPENAI_DEFAULT_MODEL=gpt-5-mini
OPENAI_API_KEY=sk-...
EMBEDDING_MODEL_NAME=text-embedding-005

# Delegate Agent models
OPENAI_MODEL_NAME=gpt-4

# LangGraph
USE_LANGGRAPH=1
LANGGRAPH_CHECKPOINTER=memory   # or sqlite
LANGGRAPH_SQLITE_PATH=./data/langgraph.sqlite
LANGGRAPH_TRIO_MAX_ITERS=18

# Trio role models/providers (examples)
# Fast roles (Aggregator/Analyst): use OpenAI gpt-5-mini
AGGREGATOR_PROVIDER=openai
AGGREGATOR_MODEL=gpt-5-mini
EXECUTOR_PROVIDER=openai
EXECUTOR_MODEL=gpt-5-mini

# Thinking model
THINK_PROVIDER=openai
THINK_MODEL=gpt-5-thinking
```

### Request schema
`ChatRequest` (for `/lc/v1/chat` and `/lc/v1/chat/stream`):
```json
{
  "query": "...",                     
  "provider": "vertex_ai" | "openai", 
  "model": "model-id",                
  "conversation_id": "session-123"   
}
```

`GET /analyse` query parameters:
- `proposal_id`: The ID of the proposal.
- `dao_id`: The ID or slug of the DAO.
- `source`: The source platform ('snapshot' or 'tally').

### Streaming semantics
The router maps LangGraph events to the same SSE chunks used by the legacy agent:
- `on_tool_start` → "### Calling tool: {name}\n\n"
- `on_tool_end` → summarized message
- `on_chat_model_stream` → token/content deltas
- `on_chain_end` → final answer (if not already streamed)

### Notes
- If LangGraph isn’t installed but `USE_LANGGRAPH=1` is set, the server will raise a clear runtime error; install with `pip install langgraph`.
- The server uses the trio agent for all endpoints.
- For deeper details and a step-by-step migration, see `.idea/langgraph_migration.md`.