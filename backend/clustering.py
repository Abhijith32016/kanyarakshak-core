"""
clustering.py

Applies DBSCAN clustering to incident location data to identify
statistically dense "high-risk zones", as opposed to K-Means.

WHY DBSCAN OVER K-MEANS (be ready to explain this if asked):
- K-Means requires you to pre-specify the number of clusters (k). We have
  no principled way to know "how many risk zones exist" in advance.
- K-Means assumes roughly spherical, similarly-sized clusters. Real
  incident data clusters irregularly (along streets, around specific
  areas) — not neat circles.
- DBSCAN groups points by density and automatically labels sparse,
  isolated points as noise (-1) rather than forcing them into a cluster.
  This matches our data generation exactly: dense zones + scattered
  background noise.
- We use the haversine metric (not plain Euclidean) because lat/lng
  coordinates are on a sphere — Euclidean distance on raw degrees
  distorts real-world distance, especially at scale.

Run: python clustering.py
Requires: incidents.csv (from generate_synthetic_data.py)
Output: incidents_clustered.csv, cluster_summary.json, clusters_map.png
"""

import json
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

EARTH_RADIUS_KM = 6371.0088


def run_dbscan(df, eps_meters=400, min_samples=8):
    """
    eps_meters: max distance between two points to be considered neighbors.
                400m is a reasonable "same general area" radius for an
                urban safety-zone use case — tune based on real data later.
    min_samples: min points required to form a dense region (a real cluster,
                 not a coincidence of 2-3 random points).
    """
    coords_rad = np.radians(df[["latitude", "longitude"]].values)
    eps_rad = (eps_meters / 1000) / EARTH_RADIUS_KM  # convert meters -> radians

    db = DBSCAN(eps=eps_rad, min_samples=min_samples, metric="haversine")
    labels = db.fit_predict(coords_rad)
    df = df.copy()
    df["cluster_id"] = labels
    return df


def summarize_clusters(df):
    summary = []
    for cluster_id in sorted(df["cluster_id"].unique()):
        if cluster_id == -1:
            continue  # noise, not a real cluster
        cluster_points = df[df["cluster_id"] == cluster_id]
        centroid_lat = cluster_points["latitude"].mean()
        centroid_lng = cluster_points["longitude"].mean()

        # Risk-relevant stats: incident count and % occurring at night (22:00-05:00)
        hours = pd.to_datetime(cluster_points["timestamp"]).dt.hour
        night_pct = ((hours >= 22) | (hours < 5)).mean() * 100

        summary.append({
            "cluster_id": int(cluster_id),
            "incident_count": int(len(cluster_points)),
            "centroid_lat": round(float(centroid_lat), 6),
            "centroid_lng": round(float(centroid_lng), 6),
            "night_incident_pct": round(float(night_pct), 1),
            "dominant_zone_hint": cluster_points["zone_hint"].mode().iloc[0],
        })
    return sorted(summary, key=lambda c: c["incident_count"], reverse=True)


def plot_clusters(df, out_path="clusters_map.png"):
    plt.figure(figsize=(8, 8))
    noise = df[df["cluster_id"] == -1]
    clustered = df[df["cluster_id"] != -1]

    plt.scatter(noise["longitude"], noise["latitude"], c="lightgray", s=15, label="Noise (unclustered)")
    scatter = plt.scatter(
        clustered["longitude"], clustered["latitude"],
        c=clustered["cluster_id"], cmap="tab10", s=25, label="Clustered incidents"
    )
    plt.title("DBSCAN Clustering of Synthetic Incident Data — High-Risk Zones")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=120)
    print(f"Saved cluster visualization -> {out_path}")


if __name__ == "__main__":
    df = pd.read_csv("incidents.csv")
    clustered_df = run_dbscan(df)

    n_clusters = len(set(clustered_df["cluster_id"])) - (1 if -1 in clustered_df["cluster_id"].values else 0)
    n_noise = (clustered_df["cluster_id"] == -1).sum()

    print(f"DBSCAN found {n_clusters} clusters and {n_noise} noise points out of {len(df)} incidents.")

    clustered_df.to_csv("incidents_clustered.csv", index=False)

    summary = summarize_clusters(clustered_df)
    with open("cluster_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\nCluster summary:")
    for c in summary:
        print(f"  Cluster {c['cluster_id']}: {c['incident_count']} incidents, "
              f"{c['night_incident_pct']}% at night, near '{c['dominant_zone_hint']}'")

    plot_clusters(clustered_df)