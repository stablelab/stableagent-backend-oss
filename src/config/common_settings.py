import os
import google.auth
from google.cloud import aiplatform
import json
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

# --------------------------------------------------
# Project & Vertex AI Configuration
# --------------------------------------------------
# Allow overrides via environment; fall back to defaults
PROJECT_ID = os.environ.get("PROJECT_ID") or "pegasus-394017"
LOCATION = os.environ.get("LOCATION") or "us-central1"
DEPLOYED_ON_GCLOUD = os.environ.get("DEPLOYED_ON_GCLOUD")

# Retrieve Google credentials and initialize Vertex AI.

env_type = os.environ.get("ENV_TYPE")
# Use default Google auth if deployed on GCloud or in production/staging
# Otherwise, load from local .gcloud.json file for local development
if DEPLOYED_ON_GCLOUD == "true" or env_type in ["production", "staging"]:
    credentials, inferred_project = google.auth.default()
else:
    # load_credentials_from_dict returns (credentials, project_id)
    print("Loading credentials from .gcloud.json")
    credentials, inferred_project = google.auth.load_credentials_from_dict(
        json.load(open(".gcloud.json")), scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    print(credentials.service_account_email)
    # If PROJECT_ID not explicitly set, derive from the key
    if not os.environ.get("PROJECT_ID") and inferred_project:
        PROJECT_ID = inferred_project

aiplatform.init(
    project=PROJECT_ID,
    location=LOCATION,
    credentials=credentials,
)

# --------------------------------------------------
# Database Configuration
# --------------------------------------------------
DATABASE_HOST = os.environ.get("DATABASE_HOST")
DATABASE_PORT = os.environ.get("DATABASE_PORT")
DATABASE_NAME = os.environ.get("DATABASE_NAME")
DATABASE_USER = os.environ.get("DATABASE_USER")
DATABASE_PASSWORD = os.environ.get("DATABASE_PASSWORD")

# Growth Database Configuration (for auth and user management)
GROWTH_DATABASE_HOST = os.environ.get("GROWTH_DATABASE_HOST")
GROWTH_DATABASE_PORT = os.environ.get("GROWTH_DATABASE_PORT", "5432")
GROWTH_DATABASE_NAME = os.environ.get("GROWTH_DATABASE_NAME")
GROWTH_DATABASE_USER = os.environ.get("GROWTH_DATABASE_USER")
GROWTH_DATABASE_PASSWORD = os.environ.get("GROWTH_DATABASE_PASSWORD")

# --------------------------------------------------
# API Key Configuration
# --------------------------------------------------
REQUIRED_API_KEY = os.environ.get("STABLELAB_TOKEN")

# --------------------------------------------------
# LLM Provider Configuration
# --------------------------------------------------
# Available providers: "vertex_ai", "openai"
DEFAULT_PROVIDER = os.environ.get("DEFAULT_LLM_PROVIDER", "vertex_ai")

# Provider-specific API keys
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") 
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# Provider-specific model names
VERTEX_DEFAULT_MODEL = os.environ.get("VERTEX_DEFAULT_MODEL")
OPENAI_MODEL_NAME = os.environ.get("OPENAI_MODEL_NAME")

# --------------------------------------------------
# LangSmith Configuration
# --------------------------------------------------
# Enable LangSmith tracing for observability
LANGSMITH_TRACING = os.environ.get("LANGSMITH_TRACING", "false").lower() == "true"
LANGSMITH_API_KEY = os.environ.get("LANGSMITH_API_KEY")
LANGSMITH_PROJECT = os.environ.get("LANGSMITH_PROJECT", "growth-chat")
LANGSMITH_ENDPOINT = os.environ.get("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
LANGSMITH_WORKSPACE_ID = os.environ.get("LANGSMITH_WORKSPACE_ID")  # Required for org-scoped API keys

# --------------------------------------------------
# Debug Configuration
# --------------------------------------------------
# Controls whether to save final conversation states to pickle files (default: disabled)
SAVE_FINAL_STATES = os.environ.get("SAVE_FINAL_STATES", "false").lower() in ("true", "1", "yes", "on") 