# Heterogeneous Multi-Agent System over A2A ("Code Assist")

- **Lab URL**: [https://explore.qwiklabs.com/classrooms/21504/labs/115873](https://explore.qwiklabs.com/classrooms/21504/labs/115873)
- **GCP Project**: `qwiklabs-gcp-01-da944a54194d` (`306082515579`)
- **Region**: `us-central1` (Model Endpoint: `global`, `gemini-3.5-flash`)

This repository contains the complete implementation, **Step-by-Step Runbook**, **High-Level Design (HLD)**, **Low-Level Design (LLD)**, and **Per-Step Workflows** for the **Code Assist** heterogeneous multi-agent system built over the **Agent2Agent (A2A)** protocol.

---

## Repository Layout

| Path | Description |
| :--- | :--- |
| [`RUNBOOK.md`](./RUNBOOK.md) | Consolidated step-by-step execution runbook with all commands executed by Antigravity (`agy`), HLD, LLD, and Mermaid workflows. |
| [`docs/HLD.md`](./docs/HLD.md) | Detailed High-Level Design: multi-runtime topology, A2A protocol variants (`0.3` vs `1.x`, ADK A2A extension), cross-runtime authentication/authorization, and user-scoped Memory Bank architecture. |
| [`docs/LLD.md`](./docs/LLD.md) | Detailed Low-Level Design: class diagrams, module specifications, callbacks, BigQuery `VECTOR_SEARCH` SQL, GKE Terraform configs, and user-ID metadata propagation. |
| [`docs/WORKFLOW.md`](./docs/WORKFLOW.md) | Detailed sequence and control-flow diagrams for every lab task (Tasks 1–8). |
| [`agents/github-agent/`](./agents/github-agent) | Task 2: ADK specialist connecting to the remote GitHub Copilot MCP server (`StreamableHTTPConnectionParams` + `GITHUB_TOOL_FILTER`), deployed to Vertex AI Agent Runtime. |
| [`agents/stackexchange-agent/`](./agents/stackexchange-agent) | Task 3: Deterministic LangGraph `StateGraph` wrapped in `a2a-sdk` 1.x advertising dual `1.0` & `0.3` `AgentInterface` entries, deployed to Cloud Run. |
| [`agents/bq-agent/`](./agents/bq-agent) | Task 4: ADK specialist generated with Antigravity (`find_similar_bugs` using `text-embedding-004` + BigQuery `VECTOR_SEARCH`), deployed to GKE Autopilot with an external LoadBalancer and Workload Identity. |
| [`agents/salesforce-agent/`](./agents/salesforce-agent) | Tasks 7 & 8: ADK specialist with 2-Legged OAuth (`client_credentials`) SOSL search over Salesforce Files and user-scoped long-term memory on Vertex AI Memory Bank (`PreloadMemoryTool` + `add_session_to_memory`). |
| [`agents/code-assistant/`](./agents/code-assistant) | Tasks 5 & 6: Root ADK 2.0 `Workflow` orchestrator (`query_extractor` -> 5 parallel branches -> `JoinNode` `merge` -> `synthesizer`) with `GoogleADCAuth`, `capture_response_to_state`, `user_id_meta_provider`, Vertex AI Search (`code-manuals-datastore`), and Skill Registry (`using-developer-knowledge-mcp`). |

---

## Deployed Endpoints & Resources Summary

| Component | Runtime / Service | Resource / Endpoint |
| :--- | :--- | :--- |
| **Code Manuals Datastore** | Vertex AI Search (Discovery Engine) | `projects/qwiklabs-gcp-01-da944a54194d/locations/global/collections/default_collection/dataStores/code-manuals-datastore` |
| **Developer Knowledge Skill** | Vertex AI Skill Registry | `projects/306082515579/locations/us-central1/skills/using-developer-knowledge-mcp` |
| **`github-agent`** | Vertex AI Agent Runtime | `https://us-central1-aiplatform.googleapis.com/reasoningEngines/v1/projects/306082515579/locations/us-central1/reasoningEngines/123209348863229952/api/a2a/app/.well-known/agent-card.json` |
| **`stackexchange-agent`** | Cloud Run (`us-central1`) | `https://stackexchange-agent-306082515579.us-central1.run.app/.well-known/agent-card.json` |
| **`bq-agent`** | GKE Autopilot (`us-central1`) | `http://23.236.62.247:8080/a2a/app/.well-known/agent-card.json` |
| **`salesforce-agent`** | Cloud Run (`us-central1`) | `https://salesforce-agent-306082515579.us-central1.run.app/a2a/app/.well-known/agent-card.json` |
| **Salesforce Memory Bank** | Vertex AI Memory Bank (`us-central1`) | `MEMORY_BANK_ID=5069287639622877184` (`salesforce-agent-memory`) |
| **`code-assistant` (Root)** | Vertex AI Agent Runtime | `projects/306082515579/locations/us-central1/reasoningEngines/1260368254774280192` |
