# DispatchAI

AI copilot for freight brokers — automates carrier check-in calls, matches loads to carriers, and drafts rate confirmations, cutting hours of repetitive dispatch work down to minutes.

## What's in this repo

- `backend/matching.py` — the core matching engine. Scores every carrier against an open load on lane history, equipment fit, on-time reliability, deadhead distance, and rate fit, then returns a ranked, explainable list.
- `backend/main.py` — FastAPI service exposing `/loads`, `/carriers`, `/match/{load_id}`, and `/checkin/{carrier_id}`.
- `frontend/index.html` — single-file React dashboard (no build step) to pick a load, see ranked carrier matches, and simulate an AI check-in.

The check-in endpoint is currently mocked (random status generator) since this environment has no outbound network access. In production, swap it for:
- **Twilio** for the actual voice/SMS call to the carrier
- **OpenAI/Claude API** for the conversational logic and parsing the driver's response into structured status

The matching engine and the API/dashboard around it are fully real and don't need any external API keys to run.

## Running it

```bash
cd backend
pip install fastapi uvicorn
uvicorn main:app --reload --port 8000
```

Then open `frontend/index.html` in a browser (it calls `http://localhost:8000`).

## Why the matching engine is the hard part

Anyone can wire up a chatbot. The part that actually saves a broker time is deciding, out of dozens of carriers, which ones are worth calling first for a given load — that's a judgment call brokers currently make from memory. `matching.py` turns that into a transparent, weighted score (lane history, equipment, reliability, deadhead distance, rate fit) so it can run automatically but still be explained to a human ("recommended because: has run this exact lane before; excellent on-time record").
