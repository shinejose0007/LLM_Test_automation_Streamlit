# LLM Task Automation Lab (Streamlit) — v2 (Updated)

This project is a **research demo** for **safe LLM-driven task automation** 

## Included features (13)
1) Tool registry with typed schemas (Pydantic)
2) Policy engine (config/policy.json)
3) RBAC permissions (Admin/Researcher/Viewer)
4) Context firewall + prompt-injection patterns
5) Hybrid RAG (per-project KB) + evidence panel
6) Approval workflow for high-risk tools
7) Audit logs with tamper-evident hash chain
8) Benchmarking suite (accuracy/latency/injection)
9) Observability metrics + export
10) Multi-user org/project workspaces
11) Safer ingestion (text + PDF upload)
12) Explainability / trace (planner JSON, evidence, tool trace)
13) Attack simulation lab + DSR workspace pages

## Run on Windows (PowerShell)
```powershell
cd path\to\LLM_Task_Automation_SnT_v2
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# optional planner config
copy .env.example .env
notepad .env

streamlit run app.py
```

## Accounts
- Use **Login/Register** to create an account before using the app.

##Outputs
<p align="center"><img src="001.JPG" width="1000"></p>
<p align="center"><img src="1.JPG" width="1000"></p>
<p align="center"><img src="2.JPG" width="1000"></p>
<p align="center"><img src="3.JPG" width="1000"></p>
<p align="center"><img src="4.JPG" width="1000"></p>

<p align="center"><img src="6.JPG" width="1000"></p>
<p align="center"><img src="7.JPG" width="1000"></p>
<p align="center"><img src="8.JPG" width="1000"></p>
<p align="center"><img src="9.JPG" width="1000"></p>
<p align="center"><img src="10.JPG" width="1000"></p>




**Author:** Shine Jose
**License:** MIT (see LICENSE file)

This repository is provided as sample educational content by Shine Jose..... Use and modify freely.....
- The **first registered user** becomes **Admin** automatically.

### Patch v2_3
Fixed external LLM planning base URL normalization (normalize_base_url NameError).
