import os
import sys
import vertexai
from vertexai import agent_engines
from dotenv import load_dotenv

# Load local environment variables if available
load_dotenv()

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Setup Vertex configurations
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
STAGING_BUCKET = os.getenv("STAGING_BUCKET", "gs://arthavest-hack-staging")

if not GOOGLE_CLOUD_PROJECT:
    raise ValueError("GOOGLE_CLOUD_PROJECT environment variable must be set.")

if not STAGING_BUCKET.startswith("gs://"):
    raise ValueError("STAGING_BUCKET must start with 'gs://'")

# Initialize Vertex AI SDK
vertexai.init(
    project=GOOGLE_CLOUD_PROJECT,
    location=GOOGLE_CLOUD_LOCATION,
    staging_bucket=STAGING_BUCKET,
)

# Import the wrapper class
from agent_engine_app import ArthaVestAgent

print(
    f"Starting deployment to project '{GOOGLE_CLOUD_PROJECT}' in location '{GOOGLE_CLOUD_LOCATION}'..."
)
print(f"Staging bucket: {STAGING_BUCKET}")

# Create remote Reasoning Engine
remote = agent_engines.create(
    ArthaVestAgent(),
    requirements=[
        "langgraph",
        "langchain-google-vertexai",
        "langchain-core",
        "langchain-google-genai",
        "sqlalchemy",
        "psycopg2-binary",
        "pydantic",
        "pydantic-settings",
        "python-dotenv",
        "requests",
        "rich",
        "pandas",
        "numpy",
        "arize-phoenix",
        "arize-phoenix-otel",
        "openinference-instrumentation-langchain",
    ],
    display_name="ArthaVest Trust-First Agent",
    description="Observable, eval-gated financial agent. Refuses low-conviction trades.",
    extra_packages=["app"],
    env_vars={
        "ARIZE_ENABLED": os.getenv("ARIZE_ENABLED", "true"),
        "PHOENIX_API_KEY": os.getenv("PHOENIX_API_KEY", ""),
        "PHOENIX_COLLECTOR_ENDPOINT": os.getenv("PHOENIX_COLLECTOR_ENDPOINT", ""),
        "PHOENIX_PROJECT_NAME": os.getenv("PHOENIX_PROJECT_NAME", "arthavest"),
        "USE_VERTEX": "true",
        "DEPLOYED": "true",
        "DISABLE_MCP_FALLBACK": "true",
        "MCP_SERVER_URL": os.getenv(
            "MCP_SERVER_URL", ""
        ),
    },
)

print("\n--- DEPLOYMENT SUCCESSFUL ---")
print("HOSTED RESOURCE:", remote.resource_name)
