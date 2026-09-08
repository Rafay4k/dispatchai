"""
DispatchAI API.

Endpoints:
  GET  /loads              -> sample open loads
  GET  /carriers            -> sample carrier pool
  POST /match/{load_id}     -> ranked carrier matches for a load
  POST /checkin/{carrier_id} -> simulate an AI check-in call/message

The check-in endpoint is a MOCK: it does not place a real call or hit a real
LLM (no network access in this environment). It's structured so swapping in
Twilio for the call and the OpenAI/Claude API for the conversation is a
drop-in change - the interface (input: carrier + load, output: structured
status) stays the same.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random

from matching import Load, Carrier, rank_carriers

app = FastAPI(title="DispatchAI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- sample data (stand-ins for a real loads/carriers database) ----

LOADS = {
    "L-1001": Load("L-1001", "Chicago, IL", "Dallas, TX", "dry_van", 2200, 41.8781, -87.6298),
    "L-1002": Load("L-1002", "Atlanta, GA", "Miami, FL", "reefer", 1400, 33.7490, -84.3880),
    "L-1003": Load("L-1003", "Denver, CO", "Phoenix, AZ", "flatbed", 1800, 39.7392, -104.9903),
}

CARRIERS = [
    Carrier("C-01", "Midwest Freight Co", ["dry_van"], [("Chicago, IL", "Dallas, TX")], 96, 2150, 41.85, -87.65),
    Carrier("C-02", "Sunbelt Logistics", ["reefer", "dry_van"], [("Atlanta, GA", "Orlando, FL")], 91, 1380, 33.80, -84.30),
    Carrier("C-03", "Rocky Mountain Haulers", ["flatbed"], [], 88, 1750, 39.70, -104.80),
    Carrier("C-04", "All-Lane Transport", ["dry_van", "flatbed"], [("Chicago, IL", "Houston, TX")], 82, 2000, 41.60, -87.90),
    Carrier("C-05", "Peach State Carriers", ["dry_van"], [("Atlanta, GA", "Miami, FL")], 78, 1600, 33.75, -84.39),
    Carrier("C-06", "Desert Route Trucking", ["flatbed", "dry_van"], [("Denver, CO", "Phoenix, AZ")], 94, 1820, 39.75, -104.99),
]


@app.get("/loads")
def get_loads():
    return [vars(l) for l in LOADS.values()]


@app.get("/carriers")
def get_carriers():
    return [vars(c) for c in CARRIERS]


@app.post("/match/{load_id}")
def match_load(load_id: str, top_n: int = 5):
    load = LOADS.get(load_id)
    if not load:
        raise HTTPException(404, f"load {load_id} not found")
    results = rank_carriers(load, CARRIERS, top_n=top_n)
    return [
        {
            "carrier_id": r.carrier.carrier_id,
            "carrier_name": r.carrier.name,
            "score": r.score,
            "breakdown": r.breakdown,
            "reason": r.reason,
        }
        for r in results
    ]


class CheckinRequest(BaseModel):
    load_id: str


@app.post("/checkin/{carrier_id}")
def checkin(carrier_id: str, req: CheckinRequest):
    """Mocked AI check-in. Swap this body for a Twilio call + LLM prompt
    in production; the response shape is what the dashboard consumes."""
    carrier = next((c for c in CARRIERS if c.carrier_id == carrier_id), None)
    if not carrier:
        raise HTTPException(404, f"carrier {carrier_id} not found")

    statuses = [
        ("on_time", "Driver reports on schedule, ETA as planned."),
        ("delayed", "Driver reports a 45 minute delay due to traffic."),
        ("at_pickup", "Driver has arrived at pickup and is loading."),
        ("exception", "Driver reports a mechanical issue - needs dispatcher attention."),
    ]
    status, message = random.choice(statuses)

    return {
        "carrier_id": carrier_id,
        "carrier_name": carrier.name,
        "load_id": req.load_id,
        "status": status,
        "message": message,
        "needs_human": status == "exception",
    }
