"""
generate_synthetic_data.py

Generates a synthetic dataset of safety-incident reports around Hyderabad,
for prototyping geospatial clustering and risk scoring.

WHY SYNTHETIC DATA: real incident-location datasets for personal safety
raise privacy/ethical concerns and are hard to source publicly with proper
licensing. We simulate plausible data instead: incidents clustered around
a few known "risk-prone" area types (isolated stretches, poorly-lit roads)
plus background random noise, with realistic time-of-day patterns
(more incidents late night / early morning).

Run: python generate_synthetic_data.py
Output: incidents.csv
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

np.random.seed(42)

# A few real, named Hyderabad-area coordinates used as "high-risk zone centers"
# (illustrative for prototyping only — not based on real incident data)
RISK_ZONE_CENTERS = [
    {"name": "Isolated stretch near HITEC City outskirts", "lat": 17.4483, "lng": 78.3915},
    {"name": "Under-lit road near Begumpet", "lat": 17.4400, "lng": 78.4675},
    {"name": "Secluded area near Uppal", "lat": 17.4064, "lng": 78.5591},
    {"name": "Poorly lit stretch near Miyapur", "lat": 17.4959, "lng": 78.3641},
]

# City-wide bounding box for background/random incidents (rough Hyderabad extent)
CITY_LAT_RANGE = (17.30, 17.55)
CITY_LNG_RANGE = (78.30, 78.60)


def sample_time_of_day():
    """Incidents are more likely late night / early morning — sample from a
    weighted distribution rather than uniform across 24 hours."""
    hour_weights = np.array([
        6, 5, 4, 3, 2, 2, 1, 1,   # 00:00–07:00 (high early-morning risk)
        1, 1, 1, 1, 1, 1, 1, 1,   # 08:00–15:00 (daytime, low)
        2, 2, 3, 4, 5, 6, 7, 8,   # 16:00–23:00 (rising into night)
    ], dtype=float)
    hour_weights /= hour_weights.sum()
    hour = np.random.choice(np.arange(24), p=hour_weights)
    minute = np.random.randint(0, 60)
    return hour, minute


def generate_dataset(n_clustered=260, n_background=90, days_span=180):
    rows = []
    start_date = datetime(2026, 1, 1)

    # Clustered incidents: sampled tightly around each risk zone center
    # (Gaussian noise ~ a few hundred meters, roughly 0.003-0.006 deg)
    per_zone = n_clustered // len(RISK_ZONE_CENTERS)
    for zone in RISK_ZONE_CENTERS:
        for _ in range(per_zone):
            lat = zone["lat"] + np.random.normal(0, 0.004)
            lng = zone["lng"] + np.random.normal(0, 0.004)
            hour, minute = sample_time_of_day()
            day_offset = np.random.randint(0, days_span)
            ts = start_date + timedelta(days=int(day_offset), hours=int(hour), minutes=int(minute))
            rows.append({"latitude": lat, "longitude": lng, "timestamp": ts, "zone_hint": zone["name"]})

    # Background incidents: scattered randomly across the whole city (noise)
    for _ in range(n_background):
        lat = np.random.uniform(*CITY_LAT_RANGE)
        lng = np.random.uniform(*CITY_LNG_RANGE)
        hour, minute = sample_time_of_day()
        day_offset = np.random.randint(0, days_span)
        ts = start_date + timedelta(days=int(day_offset), hours=int(hour), minutes=int(minute))
        rows.append({"latitude": lat, "longitude": lng, "timestamp": ts, "zone_hint": "background/unclustered"})

    df = pd.DataFrame(rows)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["incident_id"] = [f"INC{i:04d}" for i in range(len(df))]
    return df[["incident_id", "latitude", "longitude", "timestamp", "zone_hint"]]


if __name__ == "__main__":
    df = generate_dataset()
    df.to_csv("incidents.csv", index=False)
    print(f"Generated {len(df)} synthetic incidents -> incidents.csv")
    print(df.head())