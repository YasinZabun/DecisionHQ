# Decision HQ — AI Council System

Submit your critical decisions to a council of 8 AI personas that debate, challenge each other, and synthesize a final verdict.

## How It Works

```
Input (text / PDF / image)
        ↓
  [The Chair] Ego-check analysis & hidden directive
        ↓
  8 Council Members — Parallel opening positions
        ↓
  [The Chair] Socratic challenges per member (per round)
        ↓
  8 Council Members — Defense & deepening
        ↓
  [The Chair] Final JSON synthesis report
```

## Council Members

| # | Persona | Domain |
|---|---------|--------|
| 1 | **Macro Predictor** | History, sociology, politics, macro cycles |
| 2 | **Wealth Alchemist** | ROI, opportunity cost, asymmetric gains |
| 3 | **Grit & Craft** | Discipline, deep work, long-term risk |
| 4 | **The Hacker** | Shortcuts, leverage, 80/20 tactics |
| 5 | **The Executioner** | Operational reality, first concrete step |
| 6 | **The Cynic** | Murphy scenarios, failure analysis |
| 7 | **Legal & Ethics Guard** | Law, regulation, ethical boundaries |
| 8 | **Human Factor** | Mental health, burnout, sustainability |

## Setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file:

```env
AZURE_OPENAI_API_KEY=your_key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-01
```

## Usage

```python
import asyncio
from orchestrator import DecisionHQOrchestrator

orchestrator = DecisionHQOrchestrator("config.yaml")

result = asyncio.run(orchestrator.run_pipeline(
    raw_text="I'm thinking of leaving my job to start my own company.",
    pdf_path="business_plan.pdf",   # optional
    image_path="chart.png"          # optional
))
```

The result is a JSON object:

```json
{
  "ego_check_analysis": "...",
  "consensus_status": "Full Consensus | Split Decision",
  "member_arguments": { ... },
  "risk_clusters": "...",
  "first_move": "...",
  "worst_case_scenario": "...",
  "legal_guardrails": "...",
  "human_sustainability_check": "...",
  "action_plan": "..."
}
```

## Configuration

All agents' model and temperature can be adjusted via `config.yaml`:

```yaml
system_settings:
  max_debate_rounds: 3   # number of debate rounds

agents:
  legal_ethics_guard:
    temperature: 0.3     # kept low for precise analysis
```
