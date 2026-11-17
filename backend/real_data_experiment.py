#!/usr/bin/env python3
"""
real_data_experiment.py

Real-data validation of the KanyaRakshak risk pipeline on public Chicago crime data.

WHAT THIS DOES
  1. Downloads incident records (date, offence type, place type, lat/lng) from the City of Chicago
     open-data portal (or reads a CSV you exported from the portal).
  2. Keeps street-type personal-safety offences (robbery, assault, battery, sexual offences),
     non-domestic, in public places.
  3. EXPERIMENT A  - hotspot prediction: DBSCAN zones built from year N are tested on year N+1.
                     Compared with a grid-count baseline and a K-Means baseline at EQUAL AREA.
  4. EXPERIMENT B  - risk tier classification (Random Forest) with forward-in-time evaluation:
                     features from year N, labels from year N+1. Train on (Y1 -> Y2), test on (Y2 -> Y3).
                     Compared with a "same as last year" persistence baseline and a majority baseline.
  5. Sensitivity of DBSCAN to eps / min_samples, and writes tables + a map.

USAGE
  python real_data_experiment.py --download            # downloads 3 years, then runs everything
  python real_data_experiment.py --csv my_export.csv   # use a portal CSV export instead

  Optional: --start-year 2021  --cell 250  --eps 300  --min-samples 30  --all-locations  --outdir results

NOTES
  * The primary configuration (eps, min-samples) is fixed in advance via the defaults; the
    sensitivity table reports the other settings, so nothing is cherry-picked.
  * Coordinates are projected to local metres (equirectangular), accurate to well under 0.1% at city scale.
  * The dataset does not record the victim's gender, so this validates the METHOD on street-level
    personal-safety offences in general. It is not a women-specific or Hyderabad result.
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request, urllib.error
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree
from sklearn.cluster import DBSCAN, KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support, confusion_matrix

API = "https://data.cityofchicago.org/resource/ijzp-q8t2.csv"   # Crimes - 2001 to Present
TYPES = ["ROBBERY", "ASSAULT", "BATTERY", "CRIM SEXUAL ASSAULT", "CRIMINAL SEXUAL ASSAULT", "SEX OFFENSE"]
PUBLIC_KEYS = [r"STREET", r"SIDEWALK", r"ALLEY", r"PARK", r"PARKING", r"\bCTA\b", r"\bBUS\b", r"\bTRAIN\b", r"PLATFORM"]   # regex; word boundaries stop "BUS" matching "BUSINESS"
BINS = 4   # 0: 22-05 night, 1: 05-12, 2: 12-18, 3: 18-22
BIN_NAMES = ["night (22-05)", "morning (05-12)", "afternoon (12-18)", "evening (18-22)"]
R_EARTH = 6371008.8
CLASSES = ["low", "medium", "high"]


# ---------------------------------------------------------------- data access
def download(y0, y1, out_csv):
    select = "date,primary_type,location_description,domestic,latitude,longitude"
    types = ",".join("'%s'" % t for t in TYPES)
    where = ("date between '%d-01-01T00:00:00' and '%d-12-31T23:59:59' AND latitude IS NOT NULL "
             "AND primary_type in(%s)") % (y0, y1, types)
    token = os.environ.get("SOCRATA_APP_TOKEN")
    headers = {"X-App-Token": token} if token else {}
    frames, offset, page = [], 0, 50000
    while True:
        q = {"$select": select, "$where": where, "$order": "id", "$limit": page, "$offset": offset}
        req = urllib.request.Request(API + "?" + urllib.parse.urlencode(q), headers=headers)
        chunk = None
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    chunk = pd.read_csv(r)
                break
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt == 3:
                    raise
                print("  retrying after error:", e); time.sleep(4 * (attempt + 1))
        print("  downloaded %d rows (offset %d)" % (len(chunk), offset))
        if len(chunk) == 0:
            break
        frames.append(chunk); offset += page
        if len(chunk) < page:
            break
    df = pd.concat(frames, ignore_index=True)
    df.to_csv(out_csv, index=False)
    print("Saved %d rows -> %s" % (len(df), out_csv))
    return out_csv


def parse_dates(s):
    try:
        return pd.to_datetime(s, format="ISO8601")
    except Exception:
        return pd.to_datetime(s, format="%m/%d/%Y %I:%M:%S %p", errors="coerce")


def load_clean(csv, all_locations):
    df = pd.read_csv(csv)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    need = ["date", "primary_type", "latitude", "longitude"]
    miss = [c for c in need if c not in df.columns]
    if miss:
        sys.exit("Missing columns in CSV: %s" % miss)
    card = {"rows_raw": int(len(df))}
    df["date"] = parse_dates(df["date"])
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df.dropna(subset=["date", "latitude", "longitude"])
    df = df[df["latitude"].between(41.6, 42.1) & df["longitude"].between(-87.95, -87.5)]
    df["primary_type"] = df["primary_type"].astype(str).str.upper().str.strip()
    df = df[df["primary_type"].isin(TYPES)]
    card["rows_after_type_and_coordinate_filter"] = int(len(df))
    if "domestic" in df.columns:
        dom = df["domestic"].astype(str).str.lower().isin(["true", "y", "1", "yes"])
        df = df[~dom]
    card["rows_after_excluding_domestic"] = int(len(df))
    if (not all_locations) and "location_description" in df.columns:
        loc = df["location_description"].astype(str).str.upper()
        keep = np.zeros(len(df), dtype=bool)
        for k in PUBLIC_KEYS:
            keep |= loc.str.contains(k, regex=True).values
        df = df[keep]
    card["rows_after_public_place_filter"] = int(len(df))
    df["year"] = df["date"].dt.year
    df["hour"] = df["date"].dt.hour
    h = df["hour"].values
    df["tbin"] = np.where((h >= 22) | (h < 5), 0, np.where(h < 12, 1, np.where(h < 18, 2, 3)))
    return df.reset_index(drop=True), card


# ---------------------------------------------------------------- geometry helpers
class Geo:
    def __init__(self, df, cell):
        self.lat0, self.lon0 = df["latitude"].mean(), df["longitude"].mean()
        self.cell = cell
        x, y = self.project(df["latitude"].values, df["longitude"].values)
        self.minx, self.miny = x.min(), y.min()
        df["x"], df["y"] = x, y
        df["ix"] = np.floor((x - self.minx) / cell).astype(int)
        df["iy"] = np.floor((y - self.miny) / cell).astype(int)
        self.nx, self.ny = int(df["ix"].max()) + 1, int(df["iy"].max()) + 1
        keys = df["ix"] * self.ny + df["iy"]
        self.cell_keys = np.unique(keys.values)                       # universe U of cells that ever had an incident
        self.key_to_idx = {k: i for i, k in enumerate(self.cell_keys)}
        df["cidx"] = keys.map(self.key_to_idx).astype(int)
        cx_i, cy_i = self.cell_keys // self.ny, self.cell_keys % self.ny
        self.cx_i, self.cy_i = cx_i, cy_i
        self.centers = np.column_stack([self.minx + (cx_i + 0.5) * cell, self.miny + (cy_i + 0.5) * cell])

    def project(self, lat, lon):
        x = R_EARTH * np.cos(np.radians(self.lat0)) * np.radians(lon - self.lon0)
        y = R_EARTH * np.radians(lat - self.lat0)
        return x, y


def grid_counts(sub, geo):
    arr = np.zeros((geo.nx, geo.ny, BINS), dtype=np.int32)
    np.add.at(arr, (sub["ix"].values, sub["iy"].values, sub["tbin"].values), 1)
    return arr


def cell_counts(sub, geo):
    out = np.zeros((len(geo.cell_keys), BINS), dtype=np.int32)
    np.add.at(out, (sub["cidx"].values, sub["tbin"].values), 1)
    return out


def neighbour_sum(total_grid, geo):
    p = np.pad(total_grid, 1)
    s = np.zeros_like(total_grid)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            s += p[1 + dx: 1 + dx + geo.nx, 1 + dy: 1 + dy + geo.ny]
    return s[geo.cx_i, geo.cy_i]


# ---------------------------------------------------------------- zone builders
def dbscan_zone(sub, geo, eps, min_samples):
    xy = sub[["x", "y"]].values
    db = DBSCAN(eps=eps, min_samples=min_samples, algorithm="kd_tree").fit(xy)
    core = xy[db.core_sample_indices_]
    n_cl = len(set(db.labels_)) - (1 if -1 in db.labels_ else 0)
    noise = float((db.labels_ == -1).mean())
    if len(core) == 0:
        return np.zeros(len(geo.centers), bool), np.full(len(geo.centers), 1e5), n_cl, noise
    dist, _ = cKDTree(core).query(geo.centers)
    return dist <= eps, dist, n_cl, noise


def grid_zone(cnt_total, n_cells):
    mask = np.zeros(len(cnt_total), bool)
    if n_cells > 0:
        mask[np.argsort(-cnt_total, kind="stable")[:n_cells]] = True
    return mask


def kmeans_zone(sub, geo, k, n_cells):
    if n_cells <= 0 or k <= 0:
        return np.zeros(len(geo.centers), bool)
    km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(sub[["x", "y"]].values)
    dist, _ = cKDTree(km.cluster_centers_).query(geo.centers)
    lo, hi = 0.0, 40000.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if (dist <= mid).sum() < n_cells:
            lo = mid
        else:
            hi = mid
    return dist <= hi


def zone_metrics(mask, test_sub):
    hit = float(mask[test_sub["cidx"].values].mean())
    area = float(mask.mean())
    return {"hit_rate": hit, "area_fraction": area, "pai": (hit / area) if area > 0 else float("nan")}


# ---------------------------------------------------------------- experiment A
def experiment_a(df, geo, years, eps, ms):
    out = []
    for fy, ty in [(years[0], years[1]), (years[1], years[2])]:
        feat, test = df[df.year == fy], df[df.year == ty]
        zone, dist, n_cl, noise = dbscan_zone(feat, geo, eps, ms)
        n_cells = int(zone.sum())
        cnt_tot = cell_counts(feat, geo).sum(1)
        row = {"fit_year": fy, "test_year": ty, "n_fit_incidents": int(len(feat)), "n_test_incidents": int(len(test)),
               "dbscan_clusters": int(n_cl), "dbscan_noise_fraction": noise, "zone_cells": n_cells}
        row["DBSCAN"] = zone_metrics(zone, test)
        row["Grid top-N"] = zone_metrics(grid_zone(cnt_tot, n_cells), test)
        row["K-Means"] = zone_metrics(kmeans_zone(feat, geo, max(n_cl, 1), n_cells), test)
        out.append(row)
    return out


def sensitivity(df, geo, years):
    feat, test = df[df.year == years[1]], df[df.year == years[2]]
    rows = []
    for eps in (200, 300, 400):
        for ms in (15, 30, 60):
            zone, _, n_cl, noise = dbscan_zone(feat, geo, eps, ms)
            m = zone_metrics(zone, test)
            rows.append({"eps_m": eps, "min_samples": ms, "clusters": int(n_cl), "noise_fraction": noise, **m})
    return rows


# ---------------------------------------------------------------- experiment B
def build_features(feat, lab_counts, geo, eps, ms):
    zone, dist, _, _ = dbscan_zone(feat, geo, eps, ms)
    cf = cell_counts(feat, geo)
    tot = cf.sum(1)
    nb = neighbour_sum(grid_counts(feat, geo).sum(2), geo)
    night_share = cf[:, 0] / np.maximum(tot, 1)
    rows = []
    for b in range(BINS):
        rows.append(np.column_stack([geo.centers[:, 0], geo.centers[:, 1], np.full(len(tot), b), cf[:, b], tot, nb,
                                     night_share, np.minimum(dist, 1e4), zone.astype(int)]))
    X = np.vstack(rows)
    lab = np.concatenate([lab_counts[:, b] for b in range(BINS)])
    persist = np.concatenate([cf[:, b] for b in range(BINS)])
    return X, lab, persist


def to_class(counts, t_high):
    c = np.zeros(len(counts), dtype=int)
    c[(counts >= 1) & (counts < t_high)] = 1
    c[counts >= t_high] = 2
    return c


FEATURE_NAMES = ["x_m", "y_m", "time_bin", "count_cell_bin_prev", "count_cell_prev", "count_neighbours_prev",
                 "night_share_prev", "dist_to_zone_m", "in_zone"]


def bootstrap_f1(y, preds, n=500, seed=0):
    rng = np.random.default_rng(seed)
    idx = np.arange(len(y)); vals = {k: [] for k in preds}
    for _ in range(n):
        s = rng.choice(idx, size=len(idx), replace=True)
        for k, p in preds.items():
            vals[k].append(f1_score(y[s], p[s], average="macro", zero_division=0))
    return {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k, v in vals.items()}


def experiment_b(df, geo, years, eps, ms):
    y1, y2, y3 = years
    c1, c2, c3 = (cell_counts(df[df.year == y], geo) for y in (y1, y2, y3))
    Xtr, ltr, _ = build_features(df[df.year == y1], c2, geo, eps, ms)
    Xte, lte, pers_te = build_features(df[df.year == y2], c3, geo, eps, ms)
    pos = ltr[ltr > 0]
    t_high = int(max(2, np.ceil(np.percentile(pos, 75)))) if len(pos) else 2
    ytr, yte = to_class(ltr, t_high), to_class(lte, t_high)
    rf = RandomForestClassifier(n_estimators=300, min_samples_leaf=3, class_weight="balanced_subsample",
                                random_state=42, n_jobs=-1).fit(Xtr, ytr)
    p_rf = rf.predict(Xte)
    p_pers = to_class(pers_te, t_high)
    p_maj = np.full(len(yte), np.bincount(ytr).argmax())
    preds = {"Random Forest": p_rf, "Persistence (last year)": p_pers, "Majority class": p_maj}
    res = {"t_high": t_high, "n_train_rows": int(len(ytr)), "n_test_rows": int(len(yte)),
           "class_share_test": {CLASSES[i]: float((yte == i).mean()) for i in range(3)}, "models": {}}
    ci = bootstrap_f1(yte, preds)
    for name, p in preds.items():
        pr, rc, f1, _ = precision_recall_fscore_support(yte, p, labels=[0, 1, 2], zero_division=0)
        res["models"][name] = {"accuracy": float(accuracy_score(yte, p)), "macro_f1": float(f1_score(yte, p, average="macro", zero_division=0)),
                               "macro_f1_ci95": ci[name],
                               "per_class": {CLASSES[i]: {"precision": float(pr[i]), "recall": float(rc[i]), "f1": float(f1[i])} for i in range(3)}}
    res["rf_confusion_matrix_rows_true_cols_pred"] = confusion_matrix(yte, p_rf, labels=[0, 1, 2]).tolist()
    res["rf_feature_importance"] = dict(zip(FEATURE_NAMES, [float(v) for v in rf.feature_importances_]))
    return res


# ---------------------------------------------------------------- output
def make_map(df, geo, years, eps, ms, path):
    feat, test = df[df.year == years[1]], df[df.year == years[2]]
    zone, _, n_cl, _ = dbscan_zone(feat, geo, eps, ms)
    fig, ax = plt.subplots(figsize=(8, 9), dpi=150)
    s = test.sample(min(len(test), 15000), random_state=0)
    ax.scatter(s["x"], s["y"], s=1.5, c="#555555", alpha=0.35, label="%d incidents (test year)" % years[2])
    zc = geo.centers[zone]
    ax.scatter(zc[:, 0], zc[:, 1], s=9, marker="s", c="#C00000", alpha=0.35,
               label="DBSCAN zones from %d (%d clusters)" % (years[1], n_cl))
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([]); ax.legend(loc="lower left", markerscale=4)
    ax.set_title("Zones learned on %d, incidents observed in %d" % (years[1], years[2]))
    plt.tight_layout(); plt.savefig(path); plt.close()


def pct(x): return "%.1f%%" % (100 * x)
def fnum(x): return "n/a" if x != x else "%.2f" % x


def write_summary(path, card, a_rows, sens, b, args, years, type_counts):
    L = ["# Real-data experiment results (City of Chicago crime data)", ""]
    L += ["## Data card", "", "- Source: City of Chicago Data Portal, 'Crimes - 2001 to Present' (public records)",
          "- Years used: %d, %d, %d" % tuple(years),
          "- Offence types kept: %s" % ", ".join(sorted(type_counts.index)),
          "- Public-place filter: %s" % ("none (all locations)" if args.all_locations else "street / sidewalk / alley / park / parking / transit"),
          "- Domestic incidents excluded: yes"]
    for k, v in card.items():
        if k != "per_year":
            L.append("- %s: %d" % (k.replace("_", " "), v))
    L.append("- Incidents per year after filtering: " + ", ".join("%d: %d" % (y, n) for y, n in card["per_year"].items()))
    L += ["", "## Experiment A - hotspot prediction (zones fitted on year N, tested on year N+1, equal area)", "",
          "Primary DBSCAN setting: eps = %d m, min_samples = %d (fixed before running). Grid cell = %d m." % (args.eps, args.min_samples, args.cell), "",
          "| Fit -> Test | Method | Hit rate | Area covered | PAI |", "|---|---|---|---|---|"]
    for r in a_rows:
        for m in ("DBSCAN", "Grid top-N", "K-Means"):
            L.append("| %d -> %d | %s | %s | %s | %s |" % (r["fit_year"], r["test_year"], m, pct(r[m]["hit_rate"]), pct(r[m]["area_fraction"]), fnum(r[m]["pai"])))
    L += ["", "DBSCAN clusters found: " + "; ".join("%d->%d: %d clusters, %s of fit incidents labelled noise" % (r["fit_year"], r["test_year"], r["dbscan_clusters"], pct(r["dbscan_noise_fraction"])) for r in a_rows),
          "", "Hit rate = share of next-year incidents that fall in predicted zones. PAI = hit rate / area fraction (higher is better).",
          "", "### DBSCAN sensitivity (fit %d, test %d)" % (years[1], years[2]), "",
          "| eps (m) | min_samples | Clusters | Noise | Hit rate | Area | PAI |", "|---|---|---|---|---|---|---|"]
    for s in sens:
        L.append("| %d | %d | %d | %s | %s | %s | %s |" % (s["eps_m"], s["min_samples"], s["clusters"], pct(s["noise_fraction"]), pct(s["hit_rate"]), pct(s["area_fraction"]), fnum(s["pai"])))
    L += ["", "## Experiment B - risk tier classification (train on %d->%d, test on %d->%d)" % (years[0], years[1], years[1], years[2]), "",
          "Rows are (250 m cell x 4 time-of-day bins). Features come only from the earlier year; labels from the following year.",
          "Label rule: 0 incidents = low, %s = medium, %d or more = high (threshold = 75th percentile of positive training counts)." % (("exactly 1 incident" if b["t_high"] == 2 else "1 to %d incidents" % (b["t_high"] - 1)), b["t_high"]),
          "Test class shares: " + ", ".join("%s %s" % (k, pct(v)) for k, v in b["class_share_test"].items()), "",
          "| Model | Accuracy | Macro-F1 | Macro-F1 95% CI | Recall (high) |", "|---|---|---|---|---|"]
    for name, m in b["models"].items():
        L.append("| %s | %s | %.3f | %.3f-%.3f | %s |" % (name, pct(m["accuracy"]), m["macro_f1"], m["macro_f1_ci95"][0], m["macro_f1_ci95"][1], pct(m["per_class"]["high"]["recall"])))
    L += ["", "Random Forest confusion matrix (rows = true low/medium/high, columns = predicted): %s" % b["rf_confusion_matrix_rows_true_cols_pred"],
          "", "Feature importance: " + ", ".join("%s %.3f" % (k, v) for k, v in sorted(b["rf_feature_importance"].items(), key=lambda kv: -kv[1])), ""]
    open(path, "w", encoding="utf-8").write("\n".join(l for l in L if l is not None))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv"); ap.add_argument("--download", action="store_true")
    ap.add_argument("--start-year", type=int, default=2021); ap.add_argument("--cell", type=int, default=250)
    ap.add_argument("--eps", type=float, default=300); ap.add_argument("--min-samples", type=int, default=30)
    ap.add_argument("--all-locations", action="store_true"); ap.add_argument("--outdir", default="results")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    years = [args.start_year, args.start_year + 1, args.start_year + 2]
    csv = args.csv
    if args.download:
        csv = download(years[0], years[2], os.path.join(args.outdir, "chicago_raw.csv"))
    if not csv:
        sys.exit("Give --download or --csv <file>")
    df, card = load_clean(csv, args.all_locations)
    df = df[df.year.isin(years)].reset_index(drop=True)
    card["per_year"] = {int(y): int((df.year == y).sum()) for y in years}
    if min(card["per_year"].values()) < 2000:
        sys.exit("Too few incidents in some year: %s" % card["per_year"])
    geo = Geo(df, args.cell)
    type_counts = df["primary_type"].value_counts()
    print("Incidents per year:", card["per_year"], "| cells in study area:", len(geo.cell_keys))
    a = experiment_a(df, geo, years, args.eps, args.min_samples)
    sens = sensitivity(df, geo, years)
    b = experiment_b(df, geo, years, args.eps, args.min_samples)
    make_map(df, geo, years, args.eps, args.min_samples, os.path.join(args.outdir, "zones_map.png"))
    flat_card = {k: v for k, v in card.items() if k != "per_year"}
    write_summary(os.path.join(args.outdir, "results_summary.md"), card, a, sens, b, args, years, type_counts)
    with open(os.path.join(args.outdir, "results.json"), "w") as f:
        json.dump({"args": vars(args), "years": years, "data_card": card, "offence_counts": type_counts.to_dict(),
                   "experiment_a": a, "sensitivity": sens, "experiment_b": b}, f, indent=2, default=float)
    print(open(os.path.join(args.outdir, "results_summary.md"), encoding="utf-8").read())
    print("\nDone. Send me results/results_summary.md and results/results.json (and zones_map.png).")


if __name__ == "__main__":
    main()
