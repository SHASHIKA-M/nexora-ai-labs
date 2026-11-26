# NEXORA AI LABS — Autonomous AI Software Studio

A founder-controlled software company that **builds and runs real web applications**.
Give it a client requirement and it will produce an actual project workspace with
frontend, backend, database, tests and documentation — then build it, test it, audit
it and serve it in the browser from an isolated runtime.

This is not a text generator. Every stage writes files to disk and every claim is
backed by a command that actually ran.

```
Client requirement
   │
   ├─ 1. AI CEO .............. requirement analysis
   ├─ 2. AI Product Manager .. technical specification
   ├─ 3. AI UX/UI Designer ... design system + page structure
   ├─ 4. AI Backend Engineer . API and data plan
   ├─ 5. AI Database Engineer  schema implementation
   ├─ 6. AI Backend Engineer . backend source files
   ├─ 7. AI Frontend Engineer  frontend source files
   ├─ 8. AI DevOps Engineer .. install, build, preview
   ├─ 9. AI QA Engineer ...... automated test execution
   ├─ 10. AI Security Engineer  static security audit
   ├─ 11. Founder ............ review, approve, deploy decision
```

Founder approval gates sit in front of code generation, preview, repository work and
deployment. Nothing is published automatically.

---

## Quick start

Requirements: Python 3.11+, Node.js 22+ (Node 20.11 also works), and — for the AI
stages — a local Ollama instance with a model pulled.

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # Windows: Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open <http://127.0.0.1:8000>. Node is required for the build/test/preview engine; the
dashboard reports its availability.

Optional AI (recommended — this is what makes the agents write code):

```bash
ollama pull llama3.2
ollama serve
```

If Ollama is unreachable the platform keeps working: planning falls back to the
deterministic planner and every artefact is labelled `engine=blueprint`. The dashboard
never shows fake AI progress.

---

## The acceptance test: Online Shopping Platform

Run it yourself, end to end:

```bash
# 1. create the project and start the AI pipeline
curl -X POST localhost:8000/api/projects -H 'content-type: application/json' \
  -d '{"name":"Online Shopping Platform","description":"Real online shopping platform: registration, login, product listing, product details, cart, checkout, order management, admin dashboard, database integration.","autostart":true}'

# 2. approve architecture, design and development plan (ids come from the approvals API)
curl localhost:8000/api/projects/1/approvals
curl -X POST localhost:8000/api/approvals/1/decide -H 'content-type: application/json' \
  -d '{"decision":"approve","note":"Approved"}'

# 3. generate, build, test, audit and preview
curl -X POST localhost:8000/api/projects/1/build
```

Or simply use the dashboard: **Projects → create → approve the three planning gates →
Approve & generate code**. The workspace view then shows the working AI employee, the
current phase, files being written, the build and test output, security status, the
completion percentage and the live application.

What the generated application contains (all real, executable files):

| Area | What is generated |
| --- | --- |
| Frontend | ES-module SPA: hash router, home, shop, product detail, account, cart, checkout, orders, order detail, admin dashboard; componentised styles, skeletons, empty and error states, toasts |
| Backend | Express 4 API: auth, catalogue, cart, orders, admin; middleware for sessions, CSRF, rate limiting, security headers, structured errors |
| Database | SQLite schema with constraints and indexes, migration script, idempotent seed with 12 products and demo accounts |
| Tests | 59 unit + integration tests executed with `node --test` against a real HTTP server and a real database |
| Documentation | specification, design system, API reference, security review, deployment notes and founder review — generated from verified artefacts |
| Operations | `.env.example`, `.gitignore`, GitHub Actions workflow, build and seed scripts |

Verification performed by the studio before it asks for approval:

```
npm install            → dependencies installed
npm run db:seed        → schema migrated, 12 products, demo accounts
npm run build          → frontend bundle compiled
npm test               → 59 passed, 0 failed
static security scan   → 11/11 checks passed
preview boot           → HTTP /api/health 200 {"product_count":12}
```

---

## Run the generated application

Every project lives in `generated_projects/<slug>/` as a normal, self-contained repo:

```bash
cd generated_projects/online-shopping-platform
npm install
npm run db:seed
npm run build
npm start          # http://localhost:3000
```

Demo accounts: `demo@shop.test / Demo1234!` (customer) and
`admin@shop.test / Admin1234!` (admin). Change them before any real deployment.

Inside the studio you do not need to leave the console — the **Open live app** button
serves the running application through NEXORA's preview proxy at
`/preview/<slug>/`.

---

## Architecture

```
app/
  main.py             FastAPI surface: legacy MVP routes + platform routes
  models.py           Project, Task, Workspace, WorkspaceEvent, Approval,
                      BuildRun, ProjectFile, AgentRun
  ai.py               Ollama client: generate_reply, schema-validated generate_json,
                      live status probe
  agent_contracts.py  JSON contract + validator for each AI employee
  fallbacks.py        deterministic planners (labelled, never passed off as AI)
  orchestrator.py     the 11-stage pipeline, approval gates, AI repair loop
  personalizer.py     applies AI branding/design output to real source files
  engine.py           install / build / test / seed / security scan / HTTP probes
  sandbox.py          isolated process execution with an explicit allow-list
  workspace.py        safe file IO inside generated_projects + secret scanning
  preview.py          reverse proxy for the running generated application
  codegen/blueprints/ the verified, fully tested application template
```

### Isolation model

Generated code is never imported into the FastAPI process.

* Commands run with `shell=False` through an executable allow-list
  (`npm`, `node`, `npx`, `python3`, `git`) and are rejected if they contain shell
  metacharacters or absolute paths.
* Every working directory must resolve inside `generated_projects`.
* Studio secrets are stripped from the child environment; generated apps receive an
  explicitly scrubbed env plus `PORT`.
* Hard timeouts with process-group kill, output caps (200 KB) and per-file (512 KB) and
  per-workspace (600 files) write limits.
* Previews run on random loopback ports and are only reachable through the proxy, which
  validates the workspace, rewrites session cookies to the preview path and injects a
  "generated application" banner.

### AI contracts

Each agent returns JSON matching a declared schema. `ai.generate_json` validates the
payload, makes one repair attempt with the validator error, and raises on a second
failure so the pipeline records a truthful error instead of inventing data. Every agent
run is stored with its engine (`ai` / `blueprint`), model, status and validation error.

When the AI produces source code it is written to disk and then **proven**: the studio
rebuilds and re-runs the whole suite. A revision that breaks the build is reverted to the
reviewed version and the revert is logged.

---

## API

Platform:

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Status, capabilities, installed blueprints |
| `GET` | `/api/ai/status` | Live Ollama/model probe |
| `POST` | `/api/projects` | Create a project (`autostart` runs the pipeline) |
| `POST` | `/api/projects/{id}/generate` | Run analysis → approval gates |
| `POST` | `/api/projects/{id}/build` | Implementation → build → test → security → preview |
| `GET` | `/api/projects/{id}/dashboard` | Agents, phase, progress, events, builds, approvals |
| `GET` | `/api/projects/{id}/files` · `/file` | File explorer and real source content |
| `PUT` | `/api/projects/{id}/file` | Founder edit (indexed and audited) |
| `GET` | `/api/projects/{id}/approvals` | Checkpoints and payloads |
| `POST` | `/api/approvals/{id}/decide` | `approve` · `revision` · `reject` |
| `POST` | `/api/projects/{id}/revision` | Apply a founder note and re-run the pipeline |
| `POST` | `/api/projects/{id}/preview/start` · `/stop` | Control the isolated preview |
| `GET` | `/api/projects/{id}/builds` | Raw build/test/security output |
| `GET` | `/api/projects/{id}/repository/packet` | Git commands + what is excluded |
| `ANY` | `/preview/{slug}/{path}` | Proxied live application |

Legacy MVP surface (unchanged): `/api/agents`, `/api/projects/{id}/plan`,
`/api/projects/{id}/ai-plan`, `/api/tasks`, `/api/tasks/{id}/approve|execute|review`,
`/api/ai/chat`.

---

## Testing

```bash
pytest -q                                     # studio platform (41 tests)
cd app/codegen/blueprints/shopping && npm test # generated application (59 tests)
```

`tests/test_pipeline_e2e.py` is the acceptance test: it runs the whole pipeline and then
speaks HTTP to the generated server through a real port.

---

## Security notes

* Never commit `.env`. The old example key in this repository's history was a real
  Mistral key — treat it as compromised, rotate it, and prefer local Ollama for code
  generation.
* Generated applications are treated as untrusted code and are always executed in the
  sandbox described above.
* Repository preparation produces commands for you to run. NEXORA does not push to
  GitHub, and publishing requires an approved deployment checkpoint first.
* Local model output can be wrong. Review the founder checklist and the security report
  before approving a deployment.
