# Step-by-Step Workflows — Code Assist Heterogeneous Multi-Agent Lab

## Overview of the 8-Task Progression

```mermaid
flowchart LR
    T1["Task 1<br/>Setup & Vertex AI Search<br/>(code-manuals-datastore)"] --> T2["Task 2<br/>github-agent<br/>(ADK + MCP on Agent Runtime)"]
    T2 --> T3["Task 3<br/>stackexchange-agent<br/>(LangGraph + a2a-sdk on Cloud Run)"]
    T3 --> T4["Task 4<br/>bq-agent<br/>(ADK + BigQuery Vector Search on GKE)"]
    T4 --> T5["Task 5<br/>code-assistant Workflow<br/>(Fan-out + JoinNode + Skill Registry)"]
    T5 --> T6["Task 6<br/>Deploy Root & IAM<br/>(Agent Runtime + Gemini Enterprise)"]
    T6 --> T7["Task 7<br/>salesforce-agent<br/>(2LO OAuth + SOSL on Cloud Run)"]
    T7 --> T8["Task 8<br/>Vertex AI Memory Bank<br/>(Per-User Long-Term Memory)"]
```

---

## Task 1: Environment & Vertex AI Search Datastore (`code-manuals-datastore`)

```mermaid
flowchart TD
    A["Copy gs://PROJECT_ID-bucket/agents to ~/agents"] --> B["Install google-agents-cli & run agents-cli setup --agent all"]
    B --> C["POST Discovery Engine dataStores?dataStoreId=code-manuals-datastore"]
    C --> D["POST documents:import from gs://PROJECT_ID-bucket/code_manuals/*"]
    D --> E["Datastore indexed & ready for manual_search_agent"]
```

---

## Task 2: `github-agent` on Vertex AI Agent Runtime

```mermaid
sequenceDiagram
    autonumber
    participant Dev as Developer / agy
    participant Code as github-agent/app/agent.py
    participant CLI as agents-cli
    participant RE as Vertex AI Agent Runtime
    participant MCP as GitHub Copilot MCP Server

    Dev->>Code: Configure McpToolset(StreamableHTTPConnectionParams, tool_filter=GITHUB_TOOL_FILTER)
    Dev->>CLI: agents-cli deploy --project $PROJECT_ID --no-wait --update-env-vars ...
    CLI->>RE: Create/Update ReasoningEngine 123209348863229952
    Dev->>CLI: agents-cli deploy --status
    RE-->>CLI: Write deployment_metadata.json & print GITHUB_AGENT_URL
    Dev->>RE: agents-cli run --url $GITHUB_ENGINE_URL --mode adk "Find google/adk-python"
    RE->>MCP: POST https://api.githubcopilot.com/mcp/ (Authorization: Bearer PAT)
    MCP-->>RE: Repository details
    RE-->>Dev: Final cited response
```

---

## Task 3: `stackexchange-agent` (LangGraph + `a2a-sdk`) on Cloud Run

```mermaid
sequenceDiagram
    autonumber
    participant Dev as Developer / agy
    participant Code as stackexchange-agent/app/
    participant CB as Cloud Build
    participant CR as Cloud Run (us-central1)

    Dev->>Code: Add search node & edges (START -> search -> END) in agent.py
    Dev->>Code: Add 1.0 & 0.3 AgentInterface entries in server.py
    Dev->>CB: gcloud builds submit --tag us-central1-docker.pkg.dev/.../stackexchange-agent:latest
    CB-->>Dev: Image built & pushed
    Dev->>CR: gcloud run deploy stackexchange-agent --allow-unauthenticated --port 8080
    CR-->>Dev: Service URL (SE_URL)
    Dev->>CR: gcloud run services update stackexchange-agent --set-env-vars PUBLIC_URL=$SE_URL
    Dev->>CR: curl $STACKEXCHANGE_AGENT_URL
    CR-->>Dev: Dual-version A2A Agent Card JSON
```

---

## Task 4: `bq-agent` (ADK + BigQuery `VECTOR_SEARCH`) on GKE Autopilot

```mermaid
sequenceDiagram
    autonumber
    participant Dev as Developer / agy
    participant TF as Terraform (single-project)
    participant GKE as GKE Autopilot (bq-agent)
    participant VAI as Vertex AI (text-embedding-004)
    participant BQ as BigQuery (code_assist_bugs.known_bugs)

    Dev->>Dev: Scaffold bq-agent (--deployment-target gke) & implement find_similar_bugs
    Dev->>TF: Edit service.tf (External LoadBalancer) & variables.tf (BigQuery IAM roles)
    Dev->>TF: agents-cli deploy
    TF->>GKE: Create GKE Autopilot cluster, Workload Identity, Deployment & External LB
    GKE-->>Dev: External IP 23.236.62.247:8080
    Dev->>GKE: agents-cli run --url http://23.236.62.247:8080 --mode a2a "memory leak in background worker"
    GKE->>VAI: Embed query using text-embedding-004 (768 floats)
    GKE->>BQ: Run VECTOR_SEARCH(..., top_k => 3, distance_type => 'COSINE')
    BQ-->>GKE: Top 3 matching bugs (BUG-1016, BUG-1051, BUG-1036)
    GKE-->>Dev: Grounded incident report with resolutions & cosine distances
```

---

## Tasks 5 & 6: `code-assistant` Root Graph Workflow & Agent Runtime Deployment

```mermaid
flowchart TB
    Start(["User Incident Query"]) --> QE["query_extractor<br/>Extracts concise search_query"]
    QE --> B1["manual_search_agent<br/>Vertex AI Search + Skill Registry + Dev Knowledge MCP"]
    QE --> B2["github_agent<br/>RemoteA2aAgent (GoogleADCAuth, use_legacy=False)"]
    QE --> B3["stackexchange_agent<br/>CleanQueryRemoteA2aAgent (use_legacy=True)"]
    QE --> B4["salesforce_agent<br/>CleanQueryRemoteA2aAgent (user_id_meta_provider)"]
    QE --> B5["bug_db_agent<br/>RemoteA2aAgent (GKE External LB, use_legacy=False)"]

    B1 -->|"manual_findings"| Merge["merge (JoinNode)<br/>Waits for all 5 branches"]
    B2 -->|"capture_response_to_state('github_findings')"| Merge
    B3 -->|"capture_response_to_state('stackexchange_findings')"| Merge
    B4 -->|"capture_response_to_state('salesforce_findings')"| Merge
    B5 -->|"capture_response_to_state('bug_db_findings')"| Merge

    Merge --> Synth["synthesizer<br/>Produces unified, cited engineering answer"]
    Synth --> End(["Final Response to Engineer"])
```

---

## Tasks 7 & 8: `salesforce-agent` & Per-User Long-Term Memory on Vertex AI Memory Bank

```mermaid
sequenceDiagram
    autonumber
    actor User as Engineer (user@example.com)
    participant Root as code-assistant (Agent Runtime)
    participant SF as salesforce-agent (Cloud Run)
    participant MB as Vertex AI Memory Bank (5069287639622877184)
    participant SFAPI as Salesforce REST/SOSL API

    Note over User,MB: Conversation 1 — Stating a Durable User Preference
    User->>Root: "I'm on the Payments team and I only care about Spanner documents."
    Root->>SF: A2A JSON-RPC + metadata {"user_id": "user@example.com"}
    SF->>SF: _user_scoped_request_converter sets run_request.user_id = "user@example.com"
    SF->>MB: PreloadMemoryTool queries existing memories for "user@example.com"
    SF->>SFAPI: 2LO OAuth token + SOSL search
    SF->>MB: generate_memories_callback -> add_session_to_memory()
    MB-->>MB: Asynchronously extracts & consolidates durable fact ("Payments team, Spanner docs")

    Note over User,MB: Conversation 2 — New Session, Automatic Memory Recall
    User->>Root: "What architecture decision records should I review?"
    Root->>SF: A2A JSON-RPC + metadata {"user_id": "user@example.com"}
    SF->>MB: PreloadMemoryTool loads "Payments team / Spanner" preference for "user@example.com"
    SF->>SFAPI: Tailored SOSL search for Spanner / Payments ADRs
    SF-->>Root: Tailored Salesforce findings
    Root-->>User: Personalized, cited answer
```
