# Real-data experiment results (City of Chicago crime data)

## Data card

- Source: City of Chicago Data Portal, 'Crimes - 2001 to Present' (public records)
- Years used: 2021, 2022, 2023
- Offence types kept: ASSAULT, BATTERY, CRIMINAL SEXUAL ASSAULT, ROBBERY, SEX OFFENSE
- Public-place filter: street / sidewalk / alley / park / parking / transit
- Domestic incidents excluded: yes
- rows raw: 224602
- rows after type and coordinate filter: 224601
- rows after excluding domestic: 133922
- rows after public place filter: 68648
- Incidents per year after filtering: 2021: 21291, 2022: 22327, 2023: 25030

## Experiment A - hotspot prediction (zones fitted on year N, tested on year N+1, equal area)

Primary DBSCAN setting: eps = 300 m, min_samples = 30 (fixed before running). Grid cell = 250 m.

| Fit -> Test | Method | Hit rate | Area covered | PAI |
|---|---|---|---|---|
| 2021 -> 2022 | DBSCAN | 51.9% | 23.7% | 2.19 |
| 2021 -> 2022 | Grid top-N | 57.0% | 23.7% | 2.40 |
| 2021 -> 2022 | K-Means | 39.2% | 23.7% | 1.65 |
| 2022 -> 2023 | DBSCAN | 53.8% | 26.4% | 2.04 |
| 2022 -> 2023 | Grid top-N | 59.3% | 26.4% | 2.25 |
| 2022 -> 2023 | K-Means | 43.7% | 26.4% | 1.66 |

DBSCAN clusters found: 2021->2022: 81 clusters, 45.7% of fit incidents labelled noise; 2022->2023: 86 clusters, 42.3% of fit incidents labelled noise

Hit rate = share of next-year incidents that fall in predicted zones. PAI = hit rate / area fraction (higher is better).

### DBSCAN sensitivity (fit 2022, test 2023)

| eps (m) | min_samples | Clusters | Noise | Hit rate | Area | PAI |
|---|---|---|---|---|---|---|
| 200 | 15 | 201 | 45.2% | 50.2% | 21.0% | 2.39 |
| 200 | 30 | 67 | 75.5% | 21.0% | 5.2% | 4.05 |
| 200 | 60 | 15 | 90.7% | 8.1% | 1.2% | 6.94 |
| 300 | 15 | 99 | 15.2% | 82.7% | 55.9% | 1.48 |
| 300 | 30 | 86 | 42.3% | 53.8% | 26.4% | 2.04 |
| 300 | 60 | 21 | 79.6% | 17.9% | 5.3% | 3.39 |
| 400 | 15 | 42 | 6.0% | 93.1% | 76.8% | 1.21 |
| 400 | 30 | 44 | 20.1% | 77.7% | 51.7% | 1.50 |
| 400 | 60 | 44 | 54.6% | 41.6% | 19.4% | 2.14 |

## Experiment B - risk tier classification (train on 2021->2022, test on 2022->2023)

Rows are (250 m cell x 4 time-of-day bins). Features come only from the earlier year; labels from the following year.
Label rule: 0 incidents = low, exactly 1 incident = medium, 2 or more = high (threshold = 75th percentile of positive training counts).
Test class shares: low 55.2%, medium 24.6%, high 20.2%

| Model | Accuracy | Macro-F1 | Macro-F1 95% CI | Recall (high) |
|---|---|---|---|---|
| Random Forest | 59.4% | 0.497 | 0.491-0.503 | 53.9% |
| Persistence (last year) | 54.3% | 0.475 | 0.468-0.480 | 44.4% |
| Majority class | 55.2% | 0.237 | 0.235-0.239 | 0.0% |

Random Forest confusion matrix (rows = true low/medium/high, columns = predicted): [[12141, 1786, 1271], [4111, 1214, 1458], [1612, 952, 3003]]

Feature importance: dist_to_zone_m 0.212, y_m 0.155, count_neighbours_prev 0.149, x_m 0.145, count_cell_prev 0.143, time_bin 0.066, count_cell_bin_prev 0.064, night_share_prev 0.049, in_zone 0.017
