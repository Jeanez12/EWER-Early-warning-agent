# EWER-Agent: Autonomous Early Warning Agent

Project submitted to the **All Things Agentic** hackathon (Google / Devpost), Taskmaster category.

## The Problem

In community-based early warning systems (WANEP-WARN / ECOWARN / CEWARN
methodology), field monitors send raw reports (free text, Kobo forms,
WhatsApp messages). Today, a human must *manually*: read each report,
assess its severity, decide whether it warrants an alert, draft the
formatted alert report, and forward it to the right structure. This
process is slow, depends on human availability, and often misses
progressive escalation trends that are only visible when cross-referencing
multiple signals over time.

## What the Agent Does, Fully Autonomously

1. **Ingestion**: receives a field report via Pub/Sub, running in the
   background continuously, with no chat session involved.
2. **Analysis**: Gemini extracts risk indicators across 7 standard
   categories (security, intercommunity relations, population movement,
   governance, economy, civil society/media, women's/children's safety)
   and computes a composite score.
3. **Memory**: every analysis is stored in Firestore, indexed by
   geographic zone.
4. **Trend Detection (the twist)**: the agent checks whether several
   moderate signals have accumulated in the same zone within a 14-day
   window. If so, it **automatically escalates** the alert level, even if
   no single report on its own would have triggered an alert.
5. **Autonomous Action**: if the threshold is met, whether directly or
   through escalation, the agent drafts a formatted alert report, logs it,
   and sends a notification, with no human validation required.

## Additional Feature: Monthly Report and Mapping

Beyond real-time processing, the agent automatically generates, on the
1st of each month (via **Cloud Scheduler**), a summary report:
- Gemini analyzes all signals from the month and identifies zones with
  rising trends and the dominant indicator categories.
- An **interactive map** of incidents (geolocated by commune, color-coded
  by risk level) is generated and stored on **Cloud Storage**, accessible
  via a public URL included in the report.
- The report is archived in Firestore (`ewer_monthly_reports`) for
  institutional record-keeping.

## Integration with Existing Alert Systems

The agent is not designed to replace early warning systems already in
place (ECOWARN, WANEP-NEWS, or any equivalent national system), but to
connect to them. The `integration_adapter.py` module converts each alert
into a neutral, interoperable schema, and can automatically forward it to
a third-party system via a simple webhook/REST API (configurable via
`EXTERNAL_EWS_ENDPOINT`), without modifying the existing system.

## Architecture

See `docs/architecture.svg` (or the diagram below).

```
[Raw field report]
        │
        ▼
  Pub/Sub topic (ewer-incoming-reports)
        │  (asynchronous push)
        ▼
  Cloud Run service (EWER-Agent, Flask + Google ADK)
        │
        ├──► Gemini API ─── indicator extraction + scoring
        │
        ├──► Firestore ──── persistent memory per zone
        │         │
        │         └──► cumulative escalation detection
        │
        └──► Notification (webhook) ── if threshold is met
```

## Tech Stack (compliant with hackathon requirements)

- **Gemini 3.5 Flash** (via Gemini API, `gemini-3.5-flash`, a generally
  available model). Handles analysis, scoring, and monthly synthesis. Before
  final submission, check https://aistudio.google.com to see if Gemini
  3.5 Pro has become publicly available and update `GEMINI_MODEL` if you
  prefer to use it.
- **Google ADK** (Agent Development Kit): autonomous orchestration of
  the agent (`agent/ewer_adk_agent.py`)
- **Cloud Run**: service hosting
- **Firestore**: persistent memory for reports, alerts, and monthly reports
- **Pub/Sub**: asynchronous background ingestion
- **Cloud Storage**: storage for the monthly interactive maps
- **Cloud Scheduler**: automatic trigger for the monthly report

## Repository Structure

```
ewer-agent/
├── agent/
│   ├── main.py                  # Flask entry point (Cloud Run)
│   ├── ewer_adk_agent.py        # ADK agent + autonomous decision logic
│   ├── gemini_analysis.py       # Indicator extraction via Gemini
│   ├── memory_store.py          # Firestore: storage + escalation detection
│   ├── notifier.py              # Alert formatting and sending
│   ├── integration_adapter.py   # Connection to existing alert systems
│   ├── monthly_report.py        # Monthly synthesis + mapping
│   ├── geo_lookup.py            # Commune coordinates (mapping)
│   ├── indicators.py            # Standard EWER indicator configuration
│   ├── requirements.txt
│   └── Dockerfile
├── deploy/
│   └── deploy.sh              # Full Google Cloud deployment script
├── tests/
│   ├── sample_reports.py      # Fictional reports for pipeline testing
│   └── test_pipeline.py       # Unit tests
├── docs/
│   └── architecture.svg       # Architecture diagram
└── README.md
```

## Deployment Instructions (Reproducible)

### Prerequisites
- A Google Cloud project with billing enabled
- A Gemini API key (https://aistudio.google.com/apikey)
- Google Cloud Shell (recommended, nothing to install) or `gcloud` CLI locally

### Steps

1. **Clone the repository** (in Cloud Shell or locally):
   ```bash
   git clone <REPO_URL>
   cd ewer-agent
   ```

2. **Set environment variables**:
   ```bash
   export PROJECT_ID="your-project-id"
   export GEMINI_API_KEY="your-gemini-api-key"
   ```

3. **Run the full deployment** (enables APIs, creates Firestore, deploys
   to Cloud Run, creates the Pub/Sub topic and subscription):
   ```bash
   bash deploy/deploy.sh
   ```

4. **Test the pipeline** (the script prints the exact commands to run at
   the end of its execution):
   ```bash
   curl -X POST <SERVICE_URL>/ingest \
     -H 'Content-Type: application/json' \
     -d '{"report_text": "Tensions reported between two communities...", "source_id": "test-1"}'
   ```

5. **Test the real asynchronous flow via Pub/Sub**:
   ```bash
   gcloud pubsub topics publish ewer-incoming-reports \
     --message='{"report_text": "...", "source_id": "test-2"}'
   ```

### Local Execution (no deployment, for development)

```bash
cd agent
pip install -r requirements.txt
export GEMINI_API_KEY="your-key"
export GOOGLE_CLOUD_PROJECT="your-project-id"
python main.py
# The service runs on http://localhost:8080
```

## Note on the Demo

The `deploy/deploy.sh` script performs real, observable Google Cloud
actions on Cloud Run, Firestore, and Pub/Sub. The demo video shows live Cloud
Run logs, a Firestore update visible in the console, and the alert being
automatically triggered following the cumulative escalation simulated
with `tests/sample_reports.py`.
