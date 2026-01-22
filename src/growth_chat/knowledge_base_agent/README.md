# Knowledge Base Agent

RAG-based knowledge retrieval for general chat using vector similarity search.

## Overview

The Knowledge Base Agent provides semantic search over an organization's knowledge base, enabling Retrieval-Augmented Generation (RAG) for context-aware chat responses. It uses pgvector for efficient vector similarity search over embedded knowledge items from various sources (Notion, ClickUp, Confluence, etc.).

## Features

- **Vector Similarity Search**: Uses pgvector with cosine similarity for semantic search
- **Multi-Source Support**: Works with knowledge from Notion, ClickUp, Confluence, Google Docs
- **Google Gemini Embeddings**: Uses gemini-embedding-001 (768 dimensions) for query embeddings
- **Organization Isolation**: Per-organization knowledge bases with schema-based isolation
- **Efficient Retrieval**: Connection pooling and optimized vector queries

## Architecture

```
knowledge_base_agent/
├── __init__.py          # Module initialization
├── types.py             # Pydantic models for requests/responses
├── database.py          # Vector similarity search operations
├── router.py            # FastAPI endpoints
├── main.py              # Public API exports
└── README.md            # This file
```

## Database Schema

The agent queries the following tables:

### `{org_schema}.knowledge_items`

Organization-specific knowledge items with embeddings:

- `id`: Knowledge item ID
- `title`: Item title
- `content`: Full content (markdown format)
- `source_type`: Source system (notion, clickup, etc.)
- `source_item_id`: Original item ID from source
- `embedding`: Vector embedding (768 dimensions, pgvector)
- `visibility`: 'public' or 'org_only'
- `is_deprecated`: Boolean flag for deprecated items
- `metadata`: JSONB with additional metadata
- `created_at`, `last_synced_at`: Timestamps

### `public.knowledge_source_connections`

OAuth connections to external knowledge sources:

- `id`: Connection ID
- `org_id`: Organisation ID
- `source_type`: Source system type
- `source_workspace_id`: Workspace/team ID from source
- `access_token`: Encrypted access token

## Installation

The module is designed to work within the existing StableAgent backend project:

```bash
# Required dependencies (should already be installed)
pip install psycopg2-binary google-generativeai
```

## Configuration

Configure using environment variables:

```bash
# Database Connection (required)
GROWTH_DATABASE_HOST=localhost
GROWTH_DATABASE_NAME=your_database_name
GROWTH_DATABASE_USER=your_database_user
GROWTH_DATABASE_PASSWORD=your_secure_password
GROWTH_DATABASE_PORT=5432

# Google Cloud for Embeddings (required)
GOOGLE_CLOUD_PROJECT=your_gcp_project
# Ensure .gcloud.json file is present for authentication
```

## API Endpoints

### Query Knowledge Base

Search the knowledge base using natural language:

```bash
POST /knowledge/query
Authorization: Bearer your_token
Content-Type: application/json

{
  "query": "How do I apply for a grant?",
  "limit": 5,
  "org": "polygon"
}
```

**Response:**

```json
{
  "query": "How do I apply for a grant?",
  "items": [
    {
      "id": 123,
      "title": "Grant Application Process",
      "content": "To apply for a grant, follow these steps...",
      "source_type": "notion",
      "source_item_id": "abc123",
      "distance": 0.15,
      "metadata": { "page_url": "https://..." },
      "created_at": "2025-10-01T12:00:00Z",
      "last_synced_at": "2025-10-14T08:30:00Z",
      "visibility": "public"
    }
  ],
  "total_results": 1,
  "org_schema": "polygon"
}
```

### Health Check

```bash
GET /knowledge/health
```

### Configuration

```bash
GET /knowledge/config
Authorization: Bearer your_token
```

## Usage Examples

### Python Integration

```python
from knowledge_base_agent import KnowledgeDatabase
from src.utils.db_utils import get_database_connection, return_database_connection
from src.services.gemini_embeddings import EmbeddingsService

# Get database connection
conn = get_database_connection()

try:
    database = KnowledgeDatabase(conn)

    # Generate query embedding
    embeddings_service = EmbeddingsService(model="text-embedding-005", dimensionality=768)
    query_embedding = embeddings_service.embed_query("How do I submit a proposal?")

    # Search knowledge base
    results = await database.search_knowledge_items(
        org_schema="polygon",
        query_embedding=query_embedding,
        limit=5
    )

    for item in results:
        print(f"- {item['title']} (distance: {item['distance']:.4f})")
        print(f"  {item['content'][:100]}...")

finally:
    return_database_connection(conn)
```

### cURL Examples

**Basic Query:**

```bash
curl -X POST "http://localhost:8000/knowledge/query" \
  -H "Authorization: Bearer your_token" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the grant application requirements?",
    "limit": 5,
    "org": "polygon"
  }'
```

**Health Check:**

```bash
curl http://localhost:8000/knowledge/health
```

## Integration with Chat System

The Knowledge Base Agent is designed to integrate with a general chat system:

1. **Chat receives user query**: User asks a question in chat
2. **Query knowledge base**: System calls `/knowledge/query` to find relevant context
3. **Augment chat prompt**: Retrieved knowledge items are added to the LLM prompt
4. **Generate response**: LLM generates a context-aware response using the retrieved knowledge

Example integration flow:

```python
# 1. User asks question
user_query = "How do I apply for a grant?"

# 2. Retrieve relevant knowledge
knowledge_response = await query_knowledge_base(
    KnowledgeQueryRequest(query=user_query, limit=3, org=org_id)
)

# 3. Build context from retrieved items
context = "\n\n".join([
    f"**{item.title}**\n{item.content}"
    for item in knowledge_response.items
])

# 4. Augment prompt with context
chat_prompt = f"""
Context from knowledge base:
{context}

User question: {user_query}

Provide a helpful answer based on the context above.
"""

# 5. Generate chat response
response = await chat_model.generate(chat_prompt)
```

## Vector Similarity

The agent uses pgvector's cosine similarity operator (`<=>`) for semantic search:

- **Lower scores = more similar**: Similarity score of 0.0 means identical vectors
- **Typical range**: 0.0 (very similar) to 2.0 (very different)
- **Good matches**: Usually have scores < 0.5
- **Default limit**: Returns top 5 most similar items

## Performance

- **Embedding Generation**: ~100-300ms per query (Google Gemini API)
- **Vector Search**: ~10-50ms (with proper pgvector indexes)
- **Total Query Time**: ~150-400ms typical
- **Concurrent Queries**: Supported via connection pooling

## Error Handling

The agent handles errors gracefully:

1. **Organization Not Found**: Returns 400 with error message
2. **No Knowledge Items**: Returns empty results list
3. **Embeddings Error**: Returns 500 with error details
4. **Database Error**: Returns 500 with appropriate message

## Security

- **Authentication**: Uses existing project authentication via bearer tokens
- **Organization Isolation**: Schema-based multi-tenancy
- **SQL Injection Prevention**: Parameterized queries
- **Access Control**: Respects visibility settings (public/org_only)

## Future Enhancements

- [ ] Extract org from JWT token automatically
- [ ] Add filtering by source_type, tags, date ranges
- [ ] Implement result caching for common queries
- [ ] Add re-ranking with cross-encoder models
- [ ] Support hybrid search (vector + keyword)
- [ ] Add usage analytics and monitoring
- [ ] Implement query expansion and reformulation

## Troubleshooting

### "Organisation not found"

Ensure the org identifier matches an organisation in the `public.organisations` table.

### "No embeddings service available"

Check that `GOOGLE_CLOUD_PROJECT` is set and `.gcloud.json` authentication file is present.

### "Connection pool not initialized"

Ensure `initialize_database()` is called during application startup.

### "No knowledge items found"

Verify that knowledge items have been synced from external sources and have embeddings.

## Related Modules

- **form_llm_agent**: Form field validation and advice
- **criteria_llm_agent**: Grant application criteria evaluation
- **src.services.gemini_embeddings**: Embeddings generation service

## License

Part of the StableAgent Backend project.

