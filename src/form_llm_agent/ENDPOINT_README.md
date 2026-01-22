# Form Process Endpoint

AI-powered form field validation for blockchain/web3/crypto grant applications.

## Endpoint

```
POST /form/process
```

## Authentication

```
Authorization: Bearer your_token
Content-Type: application/json
```

## Request Format

```json
{
  "id_requested": "field_id",
  "values": {
    "field_id": "current_value"
  },
  "form": {
    "title": "Form Title",
    "steps": [
      {
        "fields": [
          {
            "id": "field_id",
            "type": "text",
            "label": "Field Label",
            "description": "Field description",
            "props": {
              "evaluationInstructions": "Validation criteria for this field"
            },
            "validation": {"required": true}
          }
        ]
      }
    ]
  }
}
```

## Example Request

```bash
curl -X POST "https://your-api.com/form/process" \
  -H "Authorization: Bearer your_token" \
  -H "Content-Type: application/json" \
  -d '{
    "id_requested": "project_title",
    "values": {
      "project_title": "My DeFi Protocol"
    },
    "form": {
      "title": "Grant Application",
      "steps": [
        {
          "fields": [
            {
              "id": "project_title",
              "type": "text",
              "label": "Project Title",
              "description": "Brief title for your blockchain project",
              "props": {
                "evaluationInstructions": "Title should be clear, specific, and relevant to blockchain/DeFi/web3"
              },
              "validation": {"required": true, "maxLength": 100}
            }
          ]
        }
      ]
    }
  }'
```

## Response Format

Server-Sent Events stream:

```
data: {"id": "advice_project_title", "field_id": "project_title", "response": "Great title! 'My DeFi Protocol' clearly indicates a decentralized finance project.", "type": "advice", "is_error": false, "is_clear": true, "server_error": false, "note": null}

data: [DONE]
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier (advice_{field_id}) |
| `field_id` | string | Original field ID |
| `response` | string | AI feedback/advice (empty if field is clear) |
| `type` | string | "advice" or "issue" |
| `is_error` | boolean | AI detected validation issue |
| `is_clear` | boolean | Field value meets criteria |
| `server_error` | boolean | System/server error occurred |
| `note` | string\|null | Additional context |

## Multi-Field Processing

Process multiple fields at once:

```json
{
  "id_requested": ["project_title", "project_description"],
  "values": {
    "project_title": "My DeFi Protocol",
    "project_description": "A decentralized exchange for..."
  },
  "form": { ... }
}
```

## Error Types

- **AI Validation Error**: `is_error: true, server_error: false`
  - Field content doesn't meet criteria
  - AI-detected issues with input

- **System Error**: `is_error: true, server_error: true`
  - Field not found in form
  - API/processing failures
  - Server-side issues

## Quick Integration

### JavaScript/Fetch

```javascript
const response = await fetch('/form/process', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    id_requested: 'project_title',
    values: { project_title: 'My DeFi Protocol' },
    form: { /* form structure */ }
  })
});

const reader = response.body.getReader();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  const chunk = new TextDecoder().decode(value);
  const lines = chunk.split('\n');
  
  for (const line of lines) {
    if (line.startsWith('data: ') && !line.includes('[DONE]')) {
      const data = JSON.parse(line.slice(6));
      console.log('AI Feedback:', data.response);
    }
  }
}
```

### Python/Requests

```python
import requests
import json

response = requests.post(
    'https://your-api.com/form/process',
    headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    },
    json={
        'id_requested': 'project_title',
        'values': {'project_title': 'My DeFi Protocol'},
        'form': { # form structure }
    },
    stream=True
)

for line in response.iter_lines():
    if line.startswith(b'data: ') and b'[DONE]' not in line:
        data = json.loads(line[6:])
        print(f"AI Feedback: {data['response']}")
```

## Context

The AI is specialized for **blockchain/web3/crypto grant applications** and provides domain-specific feedback for:
- DeFi protocols
- NFT projects  
- Web3 infrastructure
- Crypto tooling
- Blockchain research

All responses are tailored to the grant application context with relevant industry knowledge.
