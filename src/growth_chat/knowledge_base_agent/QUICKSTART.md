# Knowledge Base Agent - Quick Start Guide

Get up and running with RAG-based knowledge retrieval in 5 minutes.

## Prerequisites

- PostgreSQL database with pgvector extension enabled
- Knowledge items synced from external sources (via TypeScript backend)
- Google Cloud credentials configured (`.gcloud.json` file)
- Python environment with dependencies installed

## Step 1: Environment Setup (2 minutes)

Create a `.env` file or set environment variables:

```bash
# Database Connection (required)
export GROWTH_DATABASE_HOST=localhost
export GROWTH_DATABASE_NAME=grants_db
export GROWTH_DATABASE_USER=grants_user
export GROWTH_DATABASE_PASSWORD=your_secure_password

# Google Cloud (required for embeddings)
export GOOGLE_CLOUD_PROJECT=your_gcp_project

# Optional: Database Pool Settings
export GROWTH_DATABASE_MIN_CONN=1
export GROWTH_DATABASE_MAX_CONN=10
```

## Step 2: Verify Installation (30 seconds)

```bash
# Check if agent is available
curl http://localhost:8000/knowledge/health
```

Expected response:

```json
{
  "status": "healthy",
  "service": "knowledge_base_agent",
  "embeddings_config": {
    "model": "gemini-embedding-001",
    "dimensionality": 768,
    "status": "available (Google Cloud JSON)"
  }
}
```

## Step 3: Test Query (1 minute)

```bash
# Query the knowledge base
curl -X POST http://localhost:8000/knowledge/query \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How do I apply for a grant?",
    "limit": 3,
    "org": "polygon"
  }'
```

Expected response:

```json
{
  "query": "How do I apply for a grant?",
  "items": [
    {
      "id": 123,
      "title": "Grant Application Process",
      "content": "To apply for a grant...",
      "distance": 0.234,
      "source_type": "notion",
      ...
    }
  ],
  "total_results": 1,
  "org_schema": "polygon"
}
```

## Step 4: Integrate with Chat (2 minutes)

### Basic Integration

```python
from src.knowledge_base_agent import KnowledgeDatabase
from src.utils.db_utils import get_database_connection, return_database_connection
from src.services.gemini_embeddings import EmbeddingsService
from src.utils.model_factory import create_chat_model
from langchain_core.messages import HumanMessage

async def chat_with_knowledge(user_query: str, org: str):
    """Simple chat with RAG enhancement."""

    # 1. Get relevant knowledge
    conn = get_database_connection()
    try:
        db = KnowledgeDatabase(conn)
        org_schema = await db.resolve_org_schema(org)

        # Generate query embedding
        embeddings = EmbeddingsService(model="text-embedding-005", dimensionality=768)
        query_embedding = embeddings.embed_query(user_query)

        # Search knowledge base
        items = await db.search_knowledge_items(
            org_schema=org_schema,
            query_embedding=query_embedding,
            limit=3
        )
    finally:
        return_database_connection(conn)

    # 2. Build context
    if items:
        context = "\n\n".join([
            f"**{item['title']}**\n{item['content'][:500]}"
            for item in items
        ])
    else:
        context = "No relevant knowledge found."

    # 3. Generate chat response
    prompt = f"""
Context from knowledge base:
{context}

User: {user_query}

Provide a helpful answer based on the context.
"""

    chat_model = create_chat_model("gpt-4", temperature=0.7)
    response = await chat_model.ainvoke([HumanMessage(content=prompt)])

    return response.content

# Usage
answer = await chat_with_knowledge(
    "How do I submit a proposal?",
    org="polygon"
)
print(answer)
```

## Common Use Cases

### 1. FAQ Bot

```python
# User asks question
question = "What are the eligibility requirements?"

# Get knowledge
knowledge_items = await query_knowledge_base(question, org="polygon")

# Generate answer from knowledge
answer = generate_answer_from_knowledge(question, knowledge_items)
```

### 2. Form Field Help

```python
# User stuck on form field
field_question = "What should I include in the project description?"

# Get relevant examples/guidance
examples = await query_knowledge_base(field_question, org="polygon")

# Show examples to user
```

### 3. Grant Writing Assistant

```python
# User drafting grant proposal
draft_section = "Our project aims to..."

# Get relevant successful examples
similar_proposals = await query_knowledge_base(
    f"grant proposals similar to: {draft_section[:200]}",
    org="polygon"
)

# Provide suggestions based on examples
```

## Troubleshooting

### "No knowledge items found"

**Cause**: Knowledge base is empty or not synced.

**Solution**:

1. Check TypeScript backend knowledge sync status
2. Verify knowledge items exist in database:
   ```sql
   SELECT COUNT(*) FROM polygon.knowledge_items WHERE is_deprecated = false;
   ```
3. Ensure embeddings are present:
   ```sql
   SELECT COUNT(*) FROM polygon.knowledge_items WHERE embedding IS NOT NULL;
   ```

### "Organisation not found"

**Cause**: Invalid org identifier.

**Solution**:

1. Check available organizations:
   ```sql
   SELECT id, name, url, slug FROM public.organisations;
   ```
2. Use exact name, url, slug, or ID from the table

### "Embeddings service error"

**Cause**: Google Cloud credentials not configured.

**Solution**:

1. Set `GOOGLE_CLOUD_PROJECT` environment variable
2. Ensure `.gcloud.json` file is present
3. Verify credentials have access to Vertex AI

### "Connection pool not initialized"

**Cause**: Database not initialized at startup.

**Solution**:

1. Ensure `initialize_criteria_agent()` is called in startup event
2. Check database environment variables are set
3. Verify PostgreSQL is running and accessible

## Next Steps

1. **Test with real data**: Query your actual knowledge base
2. **Integrate with chat**: Add RAG to your chat system
3. **Monitor performance**: Track query latency and relevance
4. **Tune parameters**: Adjust limit and similarity thresholds
5. **Add filtering**: Implement source_type or tag filtering if needed

## API Quick Reference

### Query Knowledge Base

```
POST /knowledge/query
Authorization: Bearer {token}
Body: {"query": "...", "limit": 5, "org": "..."}
```

### Health Check

```
GET /knowledge/health
```

### Configuration

```
GET /knowledge/config
Authorization: Bearer {token}
```

## Support

For detailed documentation, see [README.md](README.md).

For architecture details, see [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md).

---

**Ready to use!** Start querying your knowledge base for RAG-enhanced chat responses.

