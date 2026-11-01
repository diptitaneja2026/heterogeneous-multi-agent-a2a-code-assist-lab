# stackexchange-agent

A specialized **Stack Exchange** search agent built on the **LangGraph** framework
and self-served over the **A2A protocol** with the official **`a2a-sdk` (1.x)**.
The root Code Assist agent consumes it as a remote A2A sub-agent.

- **Framework:** LangGraph (no ADK, no LLM — a deterministic tool call)
- **A2A:** `a2a-sdk` 1.x, self-hosted (no LangGraph Platform server, no LangSmith,
  no Postgres/Redis)
- **Deployment target:** GKE

## How it works

A single-node LangGraph `StateGraph`:

```
START -> search -> END
```

The `search` node runs the LangChain `StackExchangeTool` on the latest user
message and returns the results. It's deterministic — there is no model call.
State has a `messages` key.

`app/agent_executor.py` bridges A2A requests to the graph, and `app/server.py`
mounts the A2A routes on a Starlette app and serves:

- **Agent card:** `GET /.well-known/agent-card.json`
- **JSON-RPC endpoint:** `POST /a2a/jsonrpc`

### Backward compatibility (important)

The root's ADK `RemoteA2aAgent` client is pinned to **`a2a-sdk` 0.3.x**
(`google-adk` requires `a2a-sdk<0.4`). A default 1.x server card moves the
endpoint `url` into `supported_interfaces` and a 0.3.x client fails to parse it
(`ValidationError: url Field required`).

To stay on the latest `a2a-sdk` **and** remain consumable by the 0.3.x root, the
server (`app/server.py`):

1. advertises **both** a `1.0` and a `0.3` entry in `supported_interfaces`, which
   makes the served card include the legacy top-level `url`/`preferredTransport`
   a 0.3.x client needs; and
2. creates the JSON-RPC routes with **`enable_v0_3_compat=True`**, so the server
   accepts legacy 0.3 payloads.

This is the backward-compatibility strategy documented for A2A 1.0. Verified
locally: a real `a2a-sdk` 0.3.26 client resolves the card and a legacy
`message/send` call returns a correct 0.3 response.

## Project structure

```
stackexchange-agent/
├── app/
│   ├── agent.py          # LangGraph graph (exposes `graph`)
│   ├── agent_executor.py # A2A AgentExecutor -> graph bridge
│   ├── server.py         # AgentCard + A2A routes (Starlette ASGI `app`)
│   └── __init__.py
├── Dockerfile            # uv-based image, runs uvicorn app.server:app
├── pyproject.toml        # deps: langgraph, langchain-community, stackapi, a2a-sdk[http-server], uvicorn
├── .env.example          # PORT, PUBLIC_URL (no secrets required)
└── tests/unit/           # offline graph, card-compat, and executor tests
```

## Requirements

- [`uv`](https://docs.astral.sh/uv/) for dependency management.

## Run locally

```bash
uv sync
uv run uvicorn app.server:app --host 0.0.0.0 --port 8080
```

Then:
- card: `http://127.0.0.1:8080/.well-known/agent-card.json`
- A2A JSON-RPC: `http://127.0.0.1:8080/a2a/jsonrpc`

Stack Exchange needs no API key, so no `.env` values are required. Set
`PUBLIC_URL` to the externally reachable base URL in production so the card
advertises a reachable endpoint.

## How the root consumes it

The root Code Assist agent references it with `RemoteA2aAgent`. Set
`STACKEXCHANGE_AGENT_URL` in the root's `.env` to this agent's card URL:

```
STACKEXCHANGE_AGENT_URL=https://<deployed-host>/.well-known/agent-card.json
```

## Deploy (GKE) — short version

Full runbook (prereqs, cluster creation, troubleshooting, teardown):
[`deployment/DEPLOY.md`](deployment/DEPLOY.md).

```bash
# 0. config
export PROJECT=YOUR_PROJECT_ID REGION=us-central1 REPO=agents CLUSTER=stackexchange-cluster
export IMAGE=${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/stackexchange-agent:latest

# 1. install kubectl + GKE auth plugin (corp gLinux/Cloudtop: component mgr is disabled)
sudo apt-get install -y kubectl google-cloud-cli-gke-gcloud-auth-plugin
#   (standard install: gcloud components install kubectl gke-gcloud-auth-plugin)

# 2. enable APIs
gcloud services enable artifactregistry.googleapis.com cloudbuild.googleapis.com container.googleapis.com --project=${PROJECT}

# 3. create the Artifact Registry repo
gcloud artifacts repositories create ${REPO} --repository-format=docker --location=${REGION} --project=${PROJECT}

# 4. CREATE THE GKE AUTOPILOT CLUSTER (~5-10 min; wait for RUNNING)
gcloud container clusters create-auto ${CLUSTER} --region=${REGION} --project=${PROJECT}

# 5. build + push image
gcloud builds submit --tag ${IMAGE} --region=${REGION} --project=${PROJECT} .

# 6. get credentials + deploy
gcloud container clusters get-credentials ${CLUSTER} --region=${REGION} --project=${PROJECT}
kubectl apply -f deployment/k8s/deployment.yaml

# 7. advertise the reachable URL (after the LoadBalancer has an IP)
export EXTERNAL_IP=$(kubectl get svc stackexchange-agent -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
kubectl set env deployment/stackexchange-agent PUBLIC_URL=http://${EXTERNAL_IP}
kubectl rollout status deployment/stackexchange-agent

# 8. verify
curl -s http://${EXTERNAL_IP}/.well-known/agent-card.json | python3 -m json.tool
```

Then point the root at the card URL: `STACKEXCHANGE_AGENT_URL=http://<EXTERNAL_IP>/.well-known/agent-card.json`.

## Tests

```bash
uv run pytest tests/unit
```
