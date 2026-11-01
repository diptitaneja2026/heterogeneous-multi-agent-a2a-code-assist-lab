# Deploying the Stack Exchange agent (GKE or Cloud Run)

End-to-end runbook to build, deploy, and verify the Stack Exchange A2A agent,
then wire it into the root Code Assist agent. The **same image** runs on two
targets:

- **GKE Autopilot** behind a public LoadBalancer (sections 5–9).
- **Cloud Run**, serverless with managed HTTPS (section 13) — public, so it
  behaves like the GKE LoadBalancer.

Sections **0, 1, 3, and 4** (config, prerequisites, Artifact Registry, build) are
**shared**; then follow either the GKE sections or the Cloud Run section.

The agent is a LangGraph graph self-served over A2A with **`a2a-sdk` 1.x**
(unified message API), configured for **0.3 backward compatibility** so the
root's ADK `RemoteA2aAgent` (pinned to `a2a-sdk` 0.3.x) can consume it. There is
**no LangGraph Platform server, no LangSmith license, and no Postgres/Redis** —
just one container.

---

## 0. Configuration (set these once)

The commands below use these values. Change them for your environment.

```bash
export PROJECT=YOUR_PROJECT_ID
export REGION=us-central1
export REPO=agents                       # Artifact Registry repo
export CLUSTER=stackexchange-cluster      # GKE Autopilot cluster
export IMAGE=${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/stackexchange-agent:latest
```

> All `gcloud` commands pass `--project=${PROJECT}` explicitly so you don't have
> to change your global gcloud config (useful if your default project differs).

---

## 1. Prerequisites

### 1.1 Tools

| Tool | Purpose | Check |
|------|---------|-------|
| `gcloud` | GCP CLI | `gcloud version` |
| `kubectl` + `gke-gcloud-auth-plugin` | talk to the cluster | `kubectl version --client` |
| `uv` | local dev/test (optional for deploy) | `uv --version` |

Install `kubectl` and the GKE auth plugin. On a **corp gLinux/Cloudtop** box the
gcloud component manager is disabled, so use apt:

```bash
sudo apt-get install -y kubectl google-cloud-cli-gke-gcloud-auth-plugin
```

(On a standard install you can instead run
`gcloud components install kubectl gke-gcloud-auth-plugin`.)

### 1.2 Authentication

```bash
gcloud auth login                        # if not already logged in
gcloud auth application-default login     # ADC, used by builds/tools
gcloud projects describe ${PROJECT} --format="value(projectId,projectNumber,lifecycleState)"
```

The last command should print your project and `ACTIVE`.

### 1.3 Required APIs

Enable once (safe to re-run):

```bash
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  container.googleapis.com \
  --project=${PROJECT}
```

---

## 2. (Optional) Test locally first

```bash
cd agents/stackexchange-agent
uv sync
uv run pytest tests/unit          # 8 tests should pass
uv run uvicorn app.server:app --host 0.0.0.0 --port 8080
# In another shell:
curl -s http://127.0.0.1:8080/.well-known/agent-card.json | python3 -m json.tool
```

---

## 3. Create the Artifact Registry repository

Docker images live in Artifact Registry. Create a repo once:

```bash
gcloud artifacts repositories create ${REPO} \
  --repository-format=docker \
  --location=${REGION} \
  --description="A2A agent images" \
  --project=${PROJECT}
```

Verify (note: scope the list to `--location`; an all-locations list can error in
some corp proxy setups):

```bash
gcloud artifacts repositories list --location=${REGION} --project=${PROJECT} \
  --format="value(name,format)"
```

---

## 4. Build and push the image (Cloud Build)

Build remotely with Cloud Build so the image pull/push happens inside GCP (avoids
local Docker egress/proxy issues). Run from the agent directory (where the
`Dockerfile` and `.dockerignore` are):

```bash
cd agents/stackexchange-agent
gcloud builds submit \
  --tag ${IMAGE} \
  --region=${REGION} \
  --project=${PROJECT} \
  .
```

For a non-blocking build, add `--async` and poll:

```bash
gcloud builds submit --async --tag ${IMAGE} --region=${REGION} --project=${PROJECT} .
# grab the BUILD_ID from the output, then:
gcloud builds describe BUILD_ID --region=${REGION} --project=${PROJECT} --format="value(status)"
```

Wait for `SUCCESS`.

> Alternative (local Docker): `gcloud auth configure-docker ${REGION}-docker.pkg.dev`
> then `docker build -t ${IMAGE} . && docker push ${IMAGE}`.

---

> Sections 5–9 deploy to **GKE**. To deploy to **Cloud Run** instead, do
> sections 0–4, then jump to **section 13**.

## 5. Create the GKE Autopilot cluster

Autopilot manages nodes for you. Regional cluster:

```bash
gcloud container clusters create-auto ${CLUSTER} \
  --region=${REGION} \
  --project=${PROJECT}
```

This takes ~5–10 minutes. To submit and poll instead of blocking, add `--async`:

```bash
gcloud container clusters create-auto ${CLUSTER} --region=${REGION} --project=${PROJECT} --async
gcloud container clusters describe ${CLUSTER} --region=${REGION} --project=${PROJECT} --format="value(status)"
```

Wait for `RUNNING`.

---

## 6. Get cluster credentials

Points `kubectl` at the new cluster (writes a kubeconfig entry):

```bash
gcloud container clusters get-credentials ${CLUSTER} \
  --region=${REGION} \
  --project=${PROJECT}

kubectl get nodes        # sanity check
```

---

## 7. Deploy the manifests

`deployment/k8s/deployment.yaml` defines a `Deployment` (1 replica, health probes
on the agent-card path) and a `LoadBalancer` `Service` (port 80 -> 8080).

> If your image path differs from the default in the manifest, update the
> `image:` field first (it defaults to
> `us-central1-docker.pkg.dev/YOUR_PROJECT_ID/agents/stackexchange-agent:latest`).

```bash
cd agents/stackexchange-agent
kubectl apply -f deployment/k8s/deployment.yaml
```

Wait for the pod (Autopilot scales up a node on first deploy) and the external IP:

```bash
kubectl get pods -l app=stackexchange-agent -w      # Ctrl-C when READY 1/1
kubectl get svc stackexchange-agent -w              # Ctrl-C when EXTERNAL-IP is assigned
```

Record the external IP:

```bash
export EXTERNAL_IP=$(kubectl get svc stackexchange-agent -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo ${EXTERNAL_IP}
```

---

## 8. Advertise the reachable URL (`PUBLIC_URL`)

The agent card must advertise an endpoint clients can reach. Until the
LoadBalancer exists you don't know the IP, so set `PUBLIC_URL` **after** step 7
and roll the deployment:

```bash
kubectl set env deployment/stackexchange-agent PUBLIC_URL=http://${EXTERNAL_IP}
kubectl rollout status deployment/stackexchange-agent --timeout=180s
```

---

## 9. Verify the live service

Agent card (should show `url: http://<EXTERNAL_IP>/a2a/jsonrpc` and both a `1.0`
and a `0.3` interface, plus a top-level `url`/`preferredTransport`):

```bash
curl -s http://${EXTERNAL_IP}/.well-known/agent-card.json | python3 -m json.tool
```

A2A call (legacy 0.3-style `message/send`, which the compat layer accepts):

```bash
curl -s -X POST http://${EXTERNAL_IP}/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"How do I reverse a list in Python?"}],"messageId":"test-123","kind":"message"}}}'
```

You should get a JSON-RPC `result` containing a `message` with Stack Exchange
text.

---

## 10. Wire the root Code Assist agent

Point the root at this agent's **card URL**:

```
# agents/code-assistant/.env
STACKEXCHANGE_AGENT_URL=http://<EXTERNAL_IP>/.well-known/agent-card.json
```

> The root runs on Agent Runtime, which bakes env vars at deploy time. For the
> **deployed** root to use this agent, redeploy code-assistant after setting the
> variable. Editing `.env` only affects local runs and the next deploy.

---

## 11. Update the app later (redeploy)

After code changes, rebuild the image and roll the deployment:

```bash
cd agents/stackexchange-agent
gcloud builds submit --tag ${IMAGE} --region=${REGION} --project=${PROJECT} .
kubectl rollout restart deployment/stackexchange-agent
kubectl rollout status deployment/stackexchange-agent --timeout=180s
```

(The `:latest` tag is reused; `rollout restart` re-pulls it.)

---

## 12. Teardown (avoid ongoing cost)

The Autopilot cluster and LoadBalancer are billable.

```bash
# Delete the app (releases the LoadBalancer/IP):
kubectl delete -f deployment/k8s/deployment.yaml

# Delete the cluster:
gcloud container clusters delete ${CLUSTER} --region=${REGION} --project=${PROJECT}

# (Optional) delete the image repo:
gcloud artifacts repositories delete ${REPO} --location=${REGION} --project=${PROJECT}
```

---

## 13. Alternative: deploy to Cloud Run

The same container is a stateless HTTP server on `$PORT` — exactly Cloud Run's
contract — so no code or image changes are needed. Do the shared sections first:
**0** (config), **1.1–1.2** (tools/auth), **3** (Artifact Registry), **4** (build
image). Use this instead of sections 5–9.

### 13.1 Enable the Cloud Run API

```bash
gcloud services enable run.googleapis.com --project=${PROJECT}
```

(You don't need `container.googleapis.com` for the Cloud Run path.)

### 13.2 Deploy the image (public)

Public (`--allow-unauthenticated`) matches the GKE LoadBalancer's no-auth
behavior, so the root needs no credentials for this agent. `--port 8080` matches
the container's listen port.

```bash
gcloud run deploy stackexchange-agent \
  --image ${IMAGE} \
  --region ${REGION} \
  --project ${PROJECT} \
  --allow-unauthenticated \
  --port 8080
```

### 13.3 Advertise the reachable URL (`PUBLIC_URL`)

Cloud Run assigns an HTTPS URL. Read it, then set `PUBLIC_URL` so the agent card
advertises a reachable endpoint (same reason as GKE step 8):

```bash
export SVC_URL=$(gcloud run services describe stackexchange-agent \
  --region ${REGION} --project ${PROJECT} --format='value(status.url)')
echo ${SVC_URL}

gcloud run services update stackexchange-agent \
  --region ${REGION} --project ${PROJECT} \
  --set-env-vars PUBLIC_URL=${SVC_URL}
```

> One-shot alternative: if your project uses the deterministic URL scheme
> (`https://stackexchange-agent-<PROJECT_NUMBER>.${REGION}.run.app`), pass
> `--set-env-vars PUBLIC_URL=<that URL>` in 13.2 and skip this update.

### 13.4 Verify

```bash
curl -s ${SVC_URL}/.well-known/agent-card.json | python3 -m json.tool
```

The card's `url` should be `${SVC_URL}/a2a/jsonrpc`, with both a `1.0` and a
`0.3` interface.

### 13.5 Wire the root

```
# agents/code-assistant/.env
STACKEXCHANGE_AGENT_URL=${SVC_URL}/.well-known/agent-card.json
```

Redeploy `code-assistant` for the deployed root to pick it up (same note as
section 10).

### 13.6 Update later / teardown

```bash
# redeploy after a new image build (section 4):
gcloud run deploy stackexchange-agent --image ${IMAGE} --region ${REGION} --project ${PROJECT}

# teardown:
gcloud run services delete stackexchange-agent --region ${REGION} --project ${PROJECT}
```

Cloud Run scales to zero, so there's no idle LoadBalancer cost like GKE.

---

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `gcloud components install` fails: "component manager is disabled" | Corp install. Use `sudo apt-get install -y kubectl google-cloud-cli-gke-gcloud-auth-plugin`. |
| `artifacts repositories list` → `ECP Proxy returned an error` | The all-locations query can fail behind the corp proxy. Scope it: add `--location=${REGION}`. |
| Card `curl` returns empty / non-JSON right after deploy | LoadBalancer/pod still settling. Wait for the pod `READY 1/1` and re-try. |
| `kubectl logs` → "No agent available" | Fresh Autopilot node's log agent not ready yet; transient, retry shortly. |
| 0.3 client fails to parse the card: `ValidationError: url Field required` | The card isn't advertising a `0.3` interface. This build already does; ensure you didn't remove the `0.3` `AgentInterface` in `app/server.py` (that's what makes `agent_card_to_dict` emit the legacy top-level `url`). |
| Root can't reach the agent | Check `STACKEXCHANGE_AGENT_URL` is the **card** URL (`/.well-known/agent-card.json`), the `EXTERNAL_IP` is correct, and `PUBLIC_URL` was set to `http://${EXTERNAL_IP}` (step 8). |
| `uv lock` bakes internal `pkg.dev` URLs (corp Airlock) | `pyproject.toml` already forces public PyPI via `[[tool.uv.index]] url="https://pypi.org/simple" default=true`. Re-run `uv lock` and confirm `grep -c pkg.dev uv.lock` is `0`. |

## Notes

- **No TLS:** the Service exposes plain HTTP. Fine for a lab. For production,
  front it with an HTTPS Ingress + managed certificate and use `https://` in
  `PUBLIC_URL` / `STACKEXCHANGE_AGENT_URL`.
- **Why 0.3 compat:** `google-adk` pins `a2a-sdk<0.4`, so the root client speaks
  A2A 0.3. A default 1.x card moves the endpoint into `supported_interfaces` and
  a 0.3 client can't parse it. Advertising a `0.3` interface + `enable_v0_3_compat=True`
  makes the 1.x server fully consumable by the 0.3 client. See `README.md`.
```
