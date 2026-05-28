# STT REGIME - IV_CONV / VIX / PUT SKEW NIVEL

Dashboard de 3 senales de regimen validadas contra STT V9 (PUT BWB +K1 -2K2 +K3,
DTE 150-170, 1,629 trades + 1,223 dias unicos, 2019-2025).

**Live:** https://manumartinb.github.io/IV_CONVEXITY_NIVEL_STT/

## Las 3 senales (percentil expanding 0-100, ex-ante)

| Senal | Definicion | r vs PnL_d030 |
|---|---|---|
| IV_CONV | `(iv_k1+iv_k3)/2 - iv_k2` (concavidad PUT smile, Werner) | +0.32 |
| VIX | nivel VIX (percentil expanding) | +0.39 |
| PUT SKEW NIVEL | `skew_25d_vs50_pct_expanding` @ dte160 | +0.25 |

Bandas: FAVORABLE >=80, NEUTRAL 20-80, ADVERSO <=20.

## Hallazgos clave

- **PUT SKEW NIVEL converge con Batman LT** (puts caros = favorable) y es la senal
  menos solapada con IVC (rho ~+0.20): el par IVC + PUT SKEW es el mejor para combinar.
- **VIX** es el predictor mas fuerte en solitario pero se solapa con IVC (rho ~+0.51)
  y PUT SKEW (rho ~+0.60).
- **Triple AND** (las 3 >=P80): cohorte mas selectiva (N pequeno, WR alto).
- **SDEX descartado**: no transfiere a STT (r=-0.11, patron en U).
- **BB sobre IV_CONV descartado**: inferior a pct_expanding (BB-90 r=+0.19 vs
  pct_exp +0.32; BB largo ~200 converge pero no supera).
- VIX expanding mantiene poder (gate r_d030 +0.39 vs rank +0.42).

## Estructura del estudio

- **Seccion A - SOLAS**: cortes percentil (TOP/BOT) de cada senal vs RAW.
- **Seccion B - 2 a 2**: joint terciles 3x3 + composite AND/OR (oro) y AND/OR BOT (hierro).
- **Seccion C - 3 a 3**: triple AND, >=2 de 3, OR, hierro triple.
- **Seccion D - correlaciones**: matriz 3x3 + r vs PnL.

Todas las tablas y charts en doble panel **mean + median**.

## Archivos

- `index.html` - dashboard (lee data.json)
- `data.json` - datos serializados
- `evidence/` - PNGs (trayectorias, heatmaps, composites)
- `update_dashboard.py` - regenera data.json + evidencia desde el CSV madre

## Fuentes

- `Backtests DATABASE/STT/STT_CLASSIC_V9_MERGED_T0_mediana.csv`
- `FINAL DATA/VIX_CLOSE_HISTORICAL_PRICES.csv`
- `Skew/SKEW_PUT_ENRICHED.csv` (col `skew_25d_vs50_pct_expanding`, dte_target=160)
