# Local Travel Concierge 🌿✈️

A conversational AI travel concierge agent built with Google Agent Development Kit (ADK) and Gemini on Google Cloud Agent Platform. It helps travelers discover authentic, in-depth cultural itineraries, explore hidden gems and culinary spots, view real-time weather and time, calculate travel budgets, and preview destinations with AI-generated postcard imagery.

![Local Travel Concierge Demo](demo.gif)

---

## What This Agent Does

Based on the actual implementation in [`app/agent.py`](app/agent.py), the agent provides:

1. **Travel Catalog Search & Inspection (Firestore Database)**:
   - Queries verified regional attractions and hidden gems stored in Google Cloud Firestore (`attractions` collection).
   - Retrieves in-depth details such as best seasons, estimated duration, cultural vibe, and highlight tags.
   - Allows dynamically registering new recommended spots to the catalog.

2. **Personalized Long-Term Memory (Vertex AI Memory Bank)**:
   - Connected to a managed Memory Bank on Agent Engine.
   - Persists traveler preferences across sessions (favorite travel pace, preferred transit modes).
   - Dedicated `user_allergies` memory topic strictly tracks dietary restrictions, medical food allergies, and health boundaries to ensure traveler safety in food recommendations.

3. **Live Weather & Destination Time**:
   - Queries real-time weather metrics (temperature, apparent temperature, humidity, wind speed, condition) via public geocoding and weather APIs.
   - Provides accurate local destination time in destination timezones (e.g. `Asia/Taipei`, `Asia/Tokyo`).

4. **Travel Budget Estimation**:
   - Calculates customizable multi-day travel budget breakdowns (lodging, dining, transit, activities, emergency buffer) supporting multiple currencies (TWD, JPY) across budget levels (budget, moderate, luxury).

5. **Google Maps Geocoding & Nearby Places**:
   - Resolves addresses or landmark names into latitude/longitude coordinates.
   - Finds nearby tourist spots within a given radius using Google Maps Places API.

6. **Postcard Image Generation & Cloud Storage**:
   - Generates scenic, atmospheric travel postcards using the `gemini-3.1-flash-lite-image` model in the global region.
   - Saves generated images as ADK artifacts (`tool_context.save_artifact`) and simultaneously uploads them to a public Google Cloud Storage bucket to return public HTTPS URLs.

7. **Code Execution Sandbox**:
   - Runs Python code safely within an isolated `AgentEngineSandboxCodeExecutor` environment on Vertex AI Agent Engine for on-the-fly math, data processing, and schedule estimations.

8. **Rich A2UI Display Cards**:
   - Leverages `A2uiSchemaManager` (v0.8 Basic Catalog) and `after_model_callback` to emit structured A2UI card layouts (Cards, Columns, Rows, Text, Images) natively rendered in both the ADK Web Playground and the included frontend chat UI.

---

## Architecture & Wired Google Cloud Services

| Service / Component | Role in Project | Implementation Details |
| :--- | :--- | :--- |
| **Google Cloud Firestore** | Attraction Catalog Database | Stores and queries document collections in `attractions` (`google-cloud-firestore`) |
| **Vertex AI Agent Engine (Agent Runtime)** | Agent Host & Execution | Hosts containerized ADK agent serving A2A protocol (`agents-cli deploy`) |
| **Vertex AI Memory Bank** | Cross-Session Memory | `PreloadMemoryTool` + `after_agent_callback` persisting user preferences & allergies |
| **Vertex AI Code Sandbox** | Safe Python Code Execution | `AgentEngineSandboxCodeExecutor` on Agent Engine |
| **Google Cloud Storage (GCS)** | Public Asset Hosting | Public bucket for generated destination postcards (`google-cloud-storage`) |
| **Gemini Image Generation** | Multimodal Postcard Visuals | `gemini-3.1-flash-lite-image` (global region) via Google GenAI SDK |
| **Google Maps API** | Location Intelligence | Geocoding and Nearby Places REST lookup |
| **Cloud Run** | Chat UI Web Hosting | Hosts minimal FastAPI proxy talking A2A to deployed Agent Platform runtime |
| **A2UI v0.8 (Basic Catalog)** | Rich Conversational UI | Structured Card/Column/Row/Text rendering without external frontend frameworks |

> **Note on planned vs. implemented features:**
> RAG Engine document grounding mentioned in early concept notes was evaluated and kept optional; the current production agent is grounded directly on Firestore, live weather APIs, Google Maps APIs, and the Vertex AI Memory Bank.

---

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── a2ui_utils.py         # A2UI callback and data-part handler
│   ├── agent.py              # Root agent definition, tools, memory, sandbox, prompts
│   ├── fast_api_app.py       # Local ADK FastAPI wrapper
│   └── vendor/               # A2UI SDK modules
├── frontend/
│   ├── main.py               # Minimal FastAPI proxy communicating via A2A protocol
│   ├── requirements.txt      # Frontend dependencies
│   └── static/
│       └── index.html        # Lightweight chat interface with built-in A2UI card renderer
├── agents-cli-manifest.yaml  # Agent manifest configuration
├── deployment_metadata.json  # Agent Runtime & Memory Bank resource IDs
├── demo.gif                  # Recorded demo interaction
└── README.md
```

---

## Local Setup & Run Instructions

### Prerequisites
- Python 3.11+
- Google Cloud CLI (`gcloud`) authenticated with Application Default Credentials:
  ```bash
  gcloud auth application-default login
  gcloud config set project <YOUR_PROJECT_ID>
  ```
- `uv` package manager (optional, but recommended for ADK development)

### 1. Run with ADK Web Playground (Local Agent Testing)

Install agent dependencies and start the interactive playground with your Memory Bank service configured:

```bash
# Navigate to the project root
uv run adk web . --port 8080 --reload_agents --memory_service_uri=agentengine://<MEMORY_BANK_ID>
```

Open your browser to port 8080 to test prompts, inspect tool invocations, and review Memory Bank state.

### 2. Run the Minimal Chat Frontend Locally

The frontend talks to your deployed Agent Runtime via the A2A protocol:

```bash
cd frontend
pip install -r requirements.txt

# Export the deployed agent resource name (found in deployment_metadata.json)
export AGENT_ENGINE_RESOURCE_NAME="projects/<PROJECT_NUMBER>/locations/<LOCATION>/reasoningEngines/<ENGINE_ID>"
export AGENT_DIRECTORY="app"
export PORT=8080

python main.py
```

Visit the designated port in your browser to chat and view rendered A2UI cards.

---

## Deployment Commands (Reference)

### Deploy Agent to Agent Platform
```bash
agents-cli deploy --project <PROJECT_ID> --region us-east1 --update-env-vars GOOGLE_MAPS_API_KEY=<KEY>
```

### Deploy Frontend to Cloud Run
```bash
cd frontend
gcloud run deploy local-travel-concierge-frontend \
  --source . \
  --region us-east1 \
  --set-env-vars AGENT_ENGINE_RESOURCE_NAME="<RESOURCE_NAME>",AGENT_DIRECTORY="app" \
  --allow-unauthenticated
```
