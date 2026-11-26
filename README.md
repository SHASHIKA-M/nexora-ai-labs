# NEXORA AI LABS — Local AI Company OS (v0.2)

A founder-controlled software-studio MVP powered by a local Ollama model. It includes an AI Executive Office, a directory of specialist AI roles, AI-generated project delegation, task approvals, specialist-written deliverables, and founder review.

## What is implemented

- FastAPI backend and dark web dashboard.
- SQLite project/task persistence.
- Local Ollama integration (default model: `llama3.2`).
- AI CEO endpoint that converts a project brief into specialist tasks.
- 9 specialist role prompts: Product, UX/UI, Frontend, Backend, QA/Security, DevOps, Growth, Support, and Operations.
- Founder approval before a specialist task can run.
- Specialist outputs are saved for founder review; the founder can accept or request a revision.
- Existing SQLite databases are upgraded with `agent_id` and `result` task columns at startup.

## Important capability boundary

This is a role-based multi-agent workflow prototype using one local LLM with different system prompts. It is not nine independent models or a fully autonomous company. It creates plans and text deliverables. It does **not** edit repositories, run generated code, access external accounts, contact customers, spend money, or deploy software. Keep those actions behind separate, explicit founder approval and security controls.

## Requirements

- Windows 10/11 (or another OS supported by Ollama)
- Python 3.10+
- Ollama installed and running
- A model pulled locally, e.g. `llama3.2`

## Windows setup

1. Install Ollama: <https://ollama.com/download/windows>
2. In PowerShell, pull and test the model:

   ```powershell
   ollama pull llama3.2
   ollama run llama3.2
   ```

   Type a test prompt, then `/bye` to exit.

3. Extract this ZIP and open PowerShell in the `nexora_ai_company` folder.
4. Create your local environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

5. Create and activate a virtual environment (recommended):

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

6. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

7. Confirm `.env` contains:

   ```dotenv
   LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://127.0.0.1:11434
   OLLAMA_MODEL=llama3.2
   ```

8. Start Nexora:

   ```powershell
   uvicorn app.main:app --reload
   ```

9. Open <http://127.0.0.1:8000>.

Keep Ollama running while using Nexora. If the dashboard says local AI unavailable, run `ollama list` and `ollama run llama3.2` to check the local service/model.

## Founder workflow

1. Create a project with a meaningful name and description.
2. Select **AI CEO: Analyze & delegate**. The local model creates specialist tasks.
3. Review each task and explicitly approve it.
4. Select **Run AI specialist** to generate that role's deliverable.
5. Read the output and select **Accept deliverable** or **Request revision**.
6. Repeat until the project plan is complete.

The older deterministic `/api/projects/{id}/plan` endpoint remains available as a fallback.

## Main API routes

- `GET /api/health` — application and local model configuration status
- `GET /api/agents` — specialist directory
- `GET /api/projects`, `POST /api/projects` — projects
- `POST /api/projects/{id}/ai-plan` — AI CEO creates a specialist plan
- `POST /api/projects/{id}/plan` — deterministic fallback plan
- `GET /api/tasks` — task board
- `POST /api/tasks/{id}/approve` — founder authorizes specialist work
- `POST /api/tasks/{id}/execute` — run the selected local specialist prompt
- `POST /api/tasks/{id}/review` — accept or request revision
- `POST /api/ai/chat` — founder chat with local AI

## Data and security

- Project and task data is stored in `nexora.db` in the working directory.
- `.env` is local configuration and must not be committed to GitHub.
- Never put API keys or passwords in project descriptions or chat prompts.
- Back up `nexora.db` before making major changes.
- Local model outputs can be wrong; review all outputs before using them.
