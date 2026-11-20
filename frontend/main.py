"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.
"""

import json
import os
from pathlib import Path
import uuid

import google.auth
import google.auth.transport.requests
from google.protobuf.json_format import MessageToDict
import httpx
from a2a.client import ClientConfig, create_client
from a2a.utils.constants import TransportProtocol, VERSION_HEADER, PROTOCOL_VERSION_1_0
from a2a.types import Message, Role, Part, SendMessageRequest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Resolve AGENT_ENGINE_RESOURCE_NAME from environment or fallback to deployment_metadata.json
RESOURCE = os.environ.get("AGENT_ENGINE_RESOURCE_NAME")
if not RESOURCE:
    meta_path = Path(__file__).resolve().parent.parent / "deployment_metadata.json"
    if meta_path.is_file():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                RESOURCE = json.load(f).get("remote_agent_runtime_id")
        except Exception:
            pass

if not RESOURCE:
    RESOURCE = "projects/418081633286/locations/us-east1/reasoningEngines/8417991864136761344"

# The agent's app directory (matches agent_directory in agents-cli-manifest.yaml).
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
# Location is embedded in the resource name: projects/<p>/locations/<loc>/reasoningEngines/<id>.
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

# A2A endpoint for an Agent Runtime deployment, via the Agent Engine HTTP passthrough.
A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

# The agent tags its A2UI data parts with this mime type.
_A2UI_MIME = "application/json+a2ui"

# One set of ADC credentials, refreshed per request (access tokens expire ~1h).
_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        VERSION_HEADER: PROTOCOL_VERSION_1_0,
        "Content-Type": "application/json",
    }


app = FastAPI()


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


# Reuse ONE A2A context per user so the agent remembers the conversation.
_contexts: dict[str, str] = {}


def _extract_from_part(p) -> list[dict]:
    """Extract text or a2ui structured items from an A2A Part object."""
    out = []
    # If protobuf Part
    if hasattr(p, "WhichOneof"):
        content_kind = p.WhichOneof("content")
        if content_kind == "text" and p.text:
            out.append({"kind": "text", "text": p.text})
        elif content_kind == "data":
            data_dict = MessageToDict(p.data)
            # data_dict may be wrapped in {"kind": "data", "metadata": {...}, "data": {...}}
            if "data" in data_dict and isinstance(data_dict["data"], dict):
                actual_data = data_dict["data"]
            else:
                actual_data = data_dict
            out.append({"kind": "a2ui", "data": actual_data})
        elif content_kind == "raw" and getattr(p, "media_type", None) == _A2UI_MIME:
            try:
                parsed = json.loads(p.raw.decode("utf-8"))
                out.append({"kind": "a2ui", "data": parsed})
            except Exception:
                pass
        return out

    # If dict or legacy object
    if isinstance(p, dict):
        if "text" in p and p["text"]:
            out.append({"kind": "text", "text": p["text"]})
        elif "data" in p:
            out.append({"kind": "a2ui", "data": p["data"]})
        return out

    # Fallback attribute inspection
    text = getattr(p, "text", None)
    if text:
        out.append({"kind": "text", "text": text})
    data = getattr(p, "data", None)
    if data:
        out.append({"kind": "a2ui", "data": data})

    return out


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as http_client:
        config = ClientConfig(
            httpx_client=http_client,
            supported_protocol_bindings=[
                TransportProtocol.JSONRPC,
                TransportProtocol.HTTP_JSON,
            ],
        )
        a2a_client = await create_client(A2A_BASE, config)

        msg = Message(
            message_id=str(uuid.uuid4()),
            role=Role.ROLE_USER,
            parts=[Part(text=message)],
            context_id=_contexts.get(user_id, ""),
        )

        async for chunk in a2a_client.send_message(SendMessageRequest(message=msg)):
            # Update context if present
            if chunk.HasField("artifact_update"):
                if chunk.artifact_update.context_id:
                    _contexts[user_id] = chunk.artifact_update.context_id
                for p in chunk.artifact_update.artifact.parts:
                    parts.extend(_extract_from_part(p))
            elif chunk.HasField("task"):
                if chunk.task.context_id:
                    _contexts[user_id] = chunk.task.context_id
                for artifact in chunk.task.artifacts:
                    for p in artifact.parts:
                        parts.extend(_extract_from_part(p))
            elif chunk.HasField("message"):
                for p in chunk.message.parts:
                    parts.extend(_extract_from_part(p))

    if not parts:
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]

    return JSONResponse({"parts": parts})


# Serve the chat UI (keep this mount last so /chat wins).
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
