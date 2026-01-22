# Research Agent

A specialized agent for querying DAO governance data from multiple sources using semantic search.

## Overview

The Research Agent is part of the Growth Chat super-graph and handles queries about:

- **Governance Proposals**: Snapshot (off-chain) and Tally (on-chain) proposals
- **Voting Data**: Individual vote records, delegate activity, voting patterns
- **Forum Discussions**: Discourse posts and governance debates
- **Community Conversations**: Telegram and Discord messages
- **Development Activity**: GitHub repository and commit data
- **Token Prices**: DAO governance token market data

## Architecture

```
Growth Chat Super Graph
├── Router (classifies intent)
├── Knowledge Hub Agent (RAG on org docs)
├── App Automation Agent (team/form management)
├── Forse Analyzer Agent (insights.forse.io)
└── Research Agent (DAO governance data) ← This agent
```

The Research Agent uses a simple ReAct pattern:

1. User asks a question about DAO governance
2. Router classifies intent as "research"
3. Research Agent receives the query
4. Agent selects appropriate tool(s) based on query
5. Tools execute semantic search on unified_* tables
6. Results are formatted and returned

## Tools

### Core Data Source Tools

| Tool | Table | Description |
|------|-------|-------------|
| `discourse_search` | `unified_discourse_embeddings` | Forum post search |
| `snapshot_proposals` | `unified_proposals` (source=snapshot) | Off-chain proposals |
| `tally_proposals` | `unified_proposals` (source=tally) | On-chain proposals |
| `github_repos` | `github_metadata` | Repository data |
| `github_commits` | `github_commits_daos` | Commit history |
| `github_stats` | `github_commits_daos` | Dev statistics |
| `github_board` | `github_board` | Project roadmap |
| `telegram_search` | `unified_telegram` | Telegram messages |
| `discord_search` | `unified_discord` | Discord messages |
| `votes_lookup` | `snapshot.votelist` | Vote records |
| `voter_stats` | `snapshot.votelist` | Voter activity stats |
| `proposal_vote_stats` | `snapshot.votelist` | Proposal vote breakdown |
| `voting_power_trends` | `snapshot.votelist` | VP over time |
| `top_voters` | `snapshot.votelist` | Voter leaderboards |
| `dao_catalog` | `internal.daos` | DAO metadata |

### Supporting Tools

| Tool | Source | Description |
|------|--------|-------------|
| `token_prices` | CoinGecko API | Token market data |
| `ens_resolver` | ENS | Name ↔ address resolution |
| `web_search` | Web | Recent events fallback |
| `code_execute` | E2B Sandbox + Claude Sonnet | Python code execution |

## Semantic Search

All data source tools use semantic search with:

- **Model**: `gemini-embedding-001`
- **Dimensions**: 3072
- **Distance**: Cosine similarity (`<=>` operator)

Query embeddings are generated on-the-fly and compared against pre-computed embeddings in the `unified_*` tables.

## Configuration

Environment variables:

```bash
# Research Agent LLM
RESEARCH_AGENT_MODEL=gemini-3-flash-preview
RESEARCH_AGENT_TEMPERATURE=0.3
RESEARCH_AGENT_MAX_ITERATIONS=10

# Embeddings (used by tools)
EMBEDDING_MODEL_NAME=gemini-embedding-001
EMBEDDING_DIMENSIONALITY=3072

# Code Execution (E2B sandbox + Claude Sonnet)
E2B_API_KEY=your_e2b_api_key
CODE_EXECUTION_MODEL=claude-3-5-sonnet-latest
```

## Usage Examples

### Search Proposals

```
User: "What are Compound's recent proposals?"
Agent: Uses tally_proposals with dao_id="compound"
```

### Check Voting Data

```
User: "How did vitalik.eth vote on Uniswap proposals?"
Agent: Uses ens_resolver to get address, then votes_lookup with voter filter
```

### Forum Discussions

```
User: "What's the community saying about Aave's treasury?"
Agent: Uses discourse_search with query="treasury" and dao_id="aave"
```

### Cross-DAO Research

```
User: "Compare incentive programs across DAOs"
Agent: Uses snapshot_proposals with query="incentive" across multiple DAOs
```

## File Structure

```
research_agent/
├── __init__.py              # Module exports
├── graph.py                 # ReAct agent graph
├── prompts.py               # System prompts
├── README.md                # This file
├── tools/
│   ├── __init__.py          # Tool exports
│   ├── base.py              # Base tool classes
│   ├── database_client.py   # Shared DB client
│   ├── discourse_tool.py    # Forum search
│   ├── snapshot_tool.py     # Snapshot proposals
│   ├── tally_tool.py        # Tally proposals
│   ├── github_tool.py       # GitHub repos, commits, stats, board
│   ├── telegram_tool.py     # Telegram search
│   ├── discord_tool.py      # Discord search
│   ├── votes_tool.py        # Vote lookup
│   ├── dao_catalog_tool.py  # DAO metadata
│   ├── token_price_tool.py  # Token prices
│   ├── web_search_tool.py   # Web fallback
│   ├── ens_tool.py          # ENS resolution
│   ├── tools.py             # Tool factory
│   └── schemas/             # Pydantic schemas
└── tests/
    ├── test_tools.py        # Tool unit tests
    └── test_graph.py        # Integration tests
```

## Development

### Adding a New Tool

1. Create schema in `tools/schemas/<name>_schemas.py`
2. Create tool in `tools/<name>_tool.py`
3. Extend `SemanticSearchTool` or `ResearchBaseTool`
4. Add to `tools/tools.py` factory
5. Update prompts to mention the new tool
6. Add tests

### Running Tests

```bash
pytest src/growth_chat/research_agent/tests/ -v
```

## Migration from sota_trio.py

This agent replaces the complex `sota_trio.py` (1100+ lines) with a simpler architecture:

| Aspect | sota_trio.py | Research Agent |
|--------|--------------|----------------|
| Architecture | Planner → Executor → Synthesizer | Single ReAct agent |
| SQL | One monolithic SQL tool | Separate tools per source |
| Prompts | 400+ lines | ~100 lines |
| Routing | External | Integrated in super-graph |
| Code | 1100+ lines | ~200 lines graph + tools |

