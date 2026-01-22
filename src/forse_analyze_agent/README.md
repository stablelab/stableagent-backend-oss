# FORSE Analyzer Agent - API Documentation

> **Version:** 1.0.0  
> **Last Updated:** January 2026  
> **Source of Truth** for frontend/backend integration of the FORSE Analyzer agent.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Authentication](#authentication)
- [Endpoints](#endpoints)
  - [Streaming Chat](#1-streaming-chat)
  - [Non-Streaming Invoke](#2-non-streaming-invoke)
  - [Dashboard Analysis](#3-dashboard-analysis)
  - [Graph Analysis](#4-graph-analysis)
- [Request Formats](#request-formats)
- [Response Formats](#response-formats)
- [Streaming Protocol (SSE)](#streaming-protocol-sse)
- [Data Context](#data-context)
- [Error Handling](#error-handling)
- [Constraints & Limits](#constraints--limits)
- [Integration Examples](#integration-examples)
- [Sub-Agent Usage](#sub-agent-usage)

---

## Overview

The FORSE Analyzer Agent provides intelligent analysis of dashboards and graphs from the `insights.forse.io` platform. It supports two primary integration patterns:

1. **Frontend Integration** — HTTP endpoints with Vercel AI SDK compatible streaming
2. **Sub-Agent Integration** — Direct Python API for embedding in multi-agent systems

### Capabilities

| Feature | Description |
|---------|-------------|
| **Dashboard Discovery** | Browse and select dashboards from available DAO spaces |
| **Graph Exploration** | View metadata and select specific charts within dashboards |
| **Data Analysis** | Fetch graph data and generate AI-powered insights |
| **Custom Analysis** | User-defined analysis prompts (trends, anomalies, comparisons) |
| **Dashboard Overview** | Holistic analysis across all graphs in a dashboard |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend Apps                             │
│     (Terminal Chat)              (Graph Chat)                    │
└──────────┬───────────────────────────┬──────────────────────────┘
           │                           │
           ▼                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Router                               │
│  /stream  │  /invoke  │  /analyze/dashboard  │  /analyze/graph  │
└──────────┬───────────────────────────┬──────────────────────────┘
           │                           │
           ▼                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LangGraph Agent (ReAct)                       │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────────┐ │
│  │ step_1  │  │ step_2  │  │ step_3  │  │ step_4              │ │
│  │ spaces  │→ │ graphs  │→ │ render  │→ │ data + analysis     │ │
│  └─────────┘  └─────────┘  └─────────┘  └─────────────────────┘ │
│                    │                              │              │
│  ┌─────────────────┴──────────────────────────────┴───────────┐ │
│  │  fetch_dashboard_overview  │  analyze_graph_custom         │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FORSE Backend API                             │
│            (insights.forse.io data services)                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Authentication

### Required Headers

| Header | Value | Required |
|--------|-------|----------|
| `Content-Type` | `application/json` | ✅ Yes |

### Backend Authentication

The agent authenticates with the FORSE backend using environment variables:

| Variable | Description |
|----------|-------------|
| `FORSE_BACKEND_URL` | Base URL for FORSE API |
| `FORSE_BACKEND_JWT` | JWT token for FORSE API authentication |

> **Note:** Frontend clients do not need to provide FORSE credentials. The agent handles backend authentication internally.

---

## Endpoints

Base path: `/forse` (configured in FastAPI router)

### 1. Streaming Chat

**Conversational analysis with SSE streaming (Vercel AI SDK compatible)**

```
POST /forse/stream
```

#### Use Case
- General conversational exploration of dashboards
- Multi-turn conversations
- Natural language queries

#### Request

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Show me the Uniswap dashboard",
      "parts": [
        {
          "type": "text",
          "text": "Show me the Uniswap dashboard"
        }
      ]
    }
  ]
}
```

#### Response
Server-Sent Events (SSE) stream. See [Streaming Protocol](#streaming-protocol-sse).

---

### 2. Non-Streaming Invoke

**Complete response after full agent execution**

```
POST /forse/invoke
```

#### Use Case
- Simple request/response pattern
- Backend-to-backend calls
- Testing and debugging

#### Request

```json
{
  "messages": [
    {
      "role": "user",
      "content": "What dashboards are available?",
      "parts": [
        {
          "type": "text",
          "text": "What dashboards are available?"
        }
      ]
    }
  ]
}
```

#### Response

```json
{
  "response": "Here are the available dashboards:\n\n1. **Uniswap** - DEX analytics...",
  "metadata": {
    "message_id": "msg-abc123"
  }
}
```

---

### 3. Dashboard Analysis

**Holistic analysis of an entire dashboard**

```
POST /forse/analyze/dashboard
```

#### Use Case
- Frontend knows the `dashboard_id` upfront
- User wants overview of all metrics
- Comparing trends across multiple graphs

#### Request

```json
{
  "dashboard_id": "uniswap-v3",
  "analysis_prompt": "Compare TVL trends across all pools",
  "stream": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `dashboard_id` | string | ✅ | The dashboard ID to analyze |
| `analysis_prompt` | string | ❌ | Custom analysis instructions |
| `stream` | boolean | ❌ | Enable SSE streaming (default: `true`) |

#### Response (Non-Streaming)

```json
{
  "analysis": "## Dashboard Overview\n\nThe Uniswap V3 dashboard contains 12 graphs...",
  "dashboard_id": "uniswap-v3",
  "graph_id": null,
  "category_id": null,
  "mode": "dashboard_overview"
}
```

#### Response (Streaming)
Server-Sent Events (SSE) stream. See [Streaming Protocol](#streaming-protocol-sse).

---

### 4. Graph Analysis

**Analyze a specific graph with optional custom prompts**

```
POST /forse/analyze/graph
```

#### Use Case
- Frontend displaying a specific graph
- User asks about the displayed chart
- Custom analysis (anomalies, trends, comparisons)

#### Request

```json
{
  "dashboard_id": "uniswap-v3",
  "graph_id": "tvl-over-time",
  "category_id": "tvl",
  "analysis_prompt": "Find the top 3 growth periods and explain why",
  "stream": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `dashboard_id` | string | ✅ | The parent dashboard ID |
| `graph_id` | string | ✅ | The graph ID to analyze |
| `category_id` | string | ❌ | Specific category (uses first if omitted) |
| `analysis_prompt` | string | ❌ | Custom analysis instructions |
| `stream` | boolean | ❌ | Enable SSE streaming (default: `true`) |

#### Response (Non-Streaming)

```json
{
  "analysis": "## TVL Analysis\n\nThe top 3 growth periods were:\n1. **March 2024**...",
  "dashboard_id": "uniswap-v3",
  "graph_id": "tvl-over-time",
  "category_id": "tvl",
  "mode": "graph_analysis"
}
```

---

## Request Formats

### Chat Message Structure

```typescript
interface ClientMessage {
  role: "user" | "assistant";
  content?: string;           // Plain text content
  parts?: ClientMessagePart[]; // Structured content parts
  toolInvocations?: ToolInvocation[]; // Tool call history
}

interface ClientMessagePart {
  type: "text" | "tool-call" | "tool-result";
  text?: string;              // For type="text"
  toolCallId?: string;        // For tool interactions
  toolName?: string;
  input?: any;                // Tool input
  output?: any;               // Tool output
}
```

### Terminal Context vs Graph Context

| Context Type | Endpoint | Data Passing |
|--------------|----------|--------------|
| **Terminal** | `/stream`, `/invoke` | Conversational - user describes what they want |
| **Graph** | `/analyze/graph` | Direct - `dashboard_id`, `graph_id`, `category_id` provided |
| **Dashboard** | `/analyze/dashboard` | Direct - `dashboard_id` provided |

---

## Response Formats

### Non-Streaming Response

```typescript
interface ChatResponse {
  response: string;           // AI-generated analysis text
  metadata?: {
    message_id: string;       // Unique message identifier
  };
}

interface AnalysisResponse {
  analysis: string;           // AI-generated analysis text
  dashboard_id: string;
  graph_id?: string;          // Only for graph analysis
  category_id?: string;       // Only if specific category analyzed
  mode: "dashboard_overview" | "graph_analysis";
}
```

### Data Types from FORSE API

```typescript
// Graph data point
interface GraphData {
  position: string;   // X-axis value (time, category)
  value: string;      // Y-axis value (metric)
  label: string;      // Data series identifier
  category: string;   // Metric category (TVL, Users, etc.)
}

// Category metadata
interface GraphCategory {
  graph_id: string;
  category_id: string;
  category_name: string;
  value_label: string;      // Y-axis label
  position_label: string;   // X-axis label
  value_type: string;       // "currency", "count", etc.
  position_type: string;    // "datetime", "categorical"
  formatter_type: string;   // "number", "percentage", etc.
  type: string;             // Chart type
}

// Dashboard graph
interface DashboardGraph {
  graph_id: string;
  title: string;
  info?: string;
  dashboard_id: string;
  type: string;
  categories: GraphCategory[];
}
```

---

## Streaming Protocol (SSE)

The agent uses **Server-Sent Events (SSE)** compatible with the **Vercel AI SDK**.

### Event Types

| Event Type | Description | Payload |
|------------|-------------|---------|
| `start` | Stream started | `{ messageId: string }` |
| `text-start` | Text generation started | `{ id: string }` |
| `text-delta` | Text chunk | `{ id: string, delta: string }` |
| `text-end` | Text generation finished | `{ id: string }` |
| `tool-input-start` | Tool call initiated | `{ toolCallId, toolName }` |
| `tool-input-delta` | Tool arguments streaming | `{ toolCallId, inputTextDelta }` |
| `tool-input-available` | Tool arguments complete | `{ toolCallId, toolName, input }` |
| `tool-output-available` | Tool result available | `{ toolCallId, output }` |
| `finish` | Stream complete | `{ messageMetadata: { finishReason } }` |

### SSE Format

```
data: {"type":"start","messageId":"msg-abc123"}

data: {"type":"text-start","id":"text-1"}

data: {"type":"text-delta","id":"text-1","delta":"The "}

data: {"type":"text-delta","id":"text-1","delta":"TVL "}

data: {"type":"text-delta","id":"text-1","delta":"is..."}

data: {"type":"text-end","id":"text-1"}

data: {"type":"finish","messageMetadata":{"finishReason":"stop"}}

data: [DONE]
```

### Finish Reasons

| Reason | Description |
|--------|-------------|
| `stop` | Natural completion |
| `tool-calls` | Waiting for tool execution |

---

## Data Context

### How Data is Passed

| Method | When to Use | Example |
|--------|-------------|---------|
| **Reference IDs** | Frontend knows IDs | `dashboard_id`, `graph_id`, `category_id` |
| **Conversational** | User explores naturally | "Show me the Uniswap TVL chart" |
| **Inline via State** | Sub-agent integration | Pass full state object |

### Agent State Fields

| Field | Type | Description |
|-------|------|-------------|
| `dashboard_id` | string | Current dashboard being analyzed |
| `graph_id` | string | Current graph being analyzed |
| `category_ids` | string[] | Categories to include in analysis |
| `analysis_mode` | string | `"dashboard"` or `"graph"` |
| `user_analysis_prompt` | string | Custom analysis request |
| `dashboard_context` | object | Cached dashboard overview data |

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | When |
|------|---------|------|
| `200` | Success | Request processed successfully |
| `400` | Bad Request | Invalid payload structure |
| `500` | Internal Error | Agent execution failed |

### Error Response Format

```json
{
  "detail": "Error message describing what went wrong"
}
```

### Common Errors

| Error | Cause | Resolution |
|-------|-------|------------|
| `Dashboard not found` | Invalid `dashboard_id` | Verify ID exists via `step_1_fetch_dao_spaces` |
| `Graph not found` | Invalid `graph_id` | Verify ID via `step_2_graphs_by_dashboard_id` |
| `Could not complete in steps` | Recursion limit hit | Simplify query or increase limit |
| `FORSE_BACKEND_URL not set` | Missing env var | Configure backend environment |

### SSE Error Events

```
data: {"type":"tool-input-error","toolCallId":"call_123","toolName":"step_2","errorText":"HTTP 404"}

data: {"type":"tool-output-error","toolCallId":"call_123","errorText":"Failed to parse response"}
```

---

## Constraints & Limits

### Request Limits

| Constraint | Value | Configurable |
|------------|-------|--------------|
| Max recursion steps | 25 | `recursion_limit` parameter |
| Tool call timeout | 30-60s | Per-tool `timeout` parameter |
| Max graphs in overview | 10 | `max_graphs` parameter |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FORSE_AGENT_MODEL` | `gemini-3-flash-preview` | LLM model to use |
| `FORSE_AGENT_TEMPERATURE` | `0.7` | Model temperature |
| `FORSE_BACKEND_URL` | — | FORSE API base URL (required) |
| `FORSE_BACKEND_JWT` | — | FORSE API JWT token (required) |

### Rate Limits

- No explicit rate limiting at agent level
- Subject to underlying FORSE API rate limits
- Subject to LLM provider rate limits

---

## Integration Examples

### Frontend (TypeScript + Vercel AI SDK)

```typescript
import { useChat } from 'ai/react';

// Conversational chat
const { messages, input, handleSubmit } = useChat({
  api: '/api/forse/stream',
});

// Direct graph analysis
async function analyzeGraph(graphId: string, dashboardId: string) {
  const response = await fetch('/api/forse/analyze/graph', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dashboard_id: dashboardId,
      graph_id: graphId,
      analysis_prompt: 'Identify key trends and anomalies',
      stream: false,
    }),
  });
  return response.json();
}
```

### Frontend (SSE Stream Handling)

```typescript
async function streamAnalysis(dashboardId: string) {
  const response = await fetch('/api/forse/analyze/dashboard', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dashboard_id: dashboardId,
      stream: true,
    }),
  });

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');
    
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6);
        if (data === '[DONE]') return;
        
        const event = JSON.parse(data);
        if (event.type === 'text-delta') {
          // Append to UI
          appendText(event.delta);
        }
      }
    }
  }
}
```

### Backend (Python)

```python
from fastapi import FastAPI
from src.forse_analyze_agent.router.main import router

app = FastAPI()
app.include_router(router, prefix="/forse", tags=["FORSE Analyzer"])
```

---

## Sub-Agent Usage

For embedding in multi-agent systems (e.g., growth_chat supervisor):

### Direct API Functions

```python
from src.forse_analyze_agent.main import analyze_dashboard, analyze_graph

# Dashboard analysis
result = await analyze_dashboard(
    dashboard_id="uniswap-v3",
    analysis_prompt="Compare all liquidity pools",
    model_name="gpt-4o",  # Optional model override
)

# Graph analysis
result = await analyze_graph(
    dashboard_id="uniswap-v3",
    graph_id="tvl-chart",
    category_id="tvl",
    analysis_prompt="Find growth patterns",
)
```

### Using the Graph Directly

```python
from src.forse_analyze_agent import forse_agent_graph, create_forse_agent_graph
from langchain_core.messages import HumanMessage

# Default graph
result = await forse_agent_graph.ainvoke({
    "messages": [HumanMessage(content="Analyze Uniswap TVL")],
})

# Custom configuration
custom_graph = create_forse_agent_graph(
    model_name="gpt-4o",
    temperature=0.3,
    recursion_limit=30,
)

result = await custom_graph.ainvoke({
    "messages": [HumanMessage(content="...")],
    "dashboard_id": "uniswap-v3",
    "analysis_mode": "dashboard",
})
```

### Exports

```python
from src.forse_analyze_agent import (
    forse_agent_graph,        # Default compiled graph
    create_forse_agent_graph, # Factory for custom instances
)

from src.forse_analyze_agent.main import (
    router,                   # FastAPI router
    analyze_dashboard,        # Direct dashboard analysis
    analyze_graph,            # Direct graph analysis
)
```

---

## Tools Reference

| Tool | Purpose | Input |
|------|---------|-------|
| `step_1_fetch_dao_spaces` | List available dashboards | None |
| `step_2_graphs_by_dashboard_id` | Get graphs for a dashboard | `dashboard_id` |
| `step_3_graph_by_graph_id_only` | Render a specific graph | `graph_id` |
| `step_4_graph_data_by_id_and_category_id` | Fetch graph data | `graph_id`, `category_id` |
| `fetch_dashboard_overview` | Get all dashboard data | `dashboard_id`, `max_graphs` |
| `analyze_graph_custom` | Custom user analysis | `graph_id`, `category_id`, `analysis_prompt` |

---

## Changelog

### v1.0.0 (January 2026)
- Initial documented API contract
- Added `/analyze/dashboard` and `/analyze/graph` endpoints
- Streaming with initial state support
- Sub-agent integration API
- Environment variable configuration
