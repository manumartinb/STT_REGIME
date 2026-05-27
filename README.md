# IV_CONVEXITY NIVEL - STT V9 Dashboard

Dashboard de la concavidad de la PUT smile + VIX, validado contra STT V9
(PUT BWB +K1 -2K2 +K3, DTE 150-170, 1,629 trades + 1,223 dias unicos, 2019-2025).

**Live:** https://manumartinb.github.io/IV_CONVEXITY_NIVEL_STT/

## Que mide

`IV_CONVEXITY = (iv_k1 + iv_k3)/2 - iv_k2` sobre las 3 patas PUT del BWB
(formula canonica Werner). Mide cuanto esta el body K2 IV deprimido respecto
a las alas K1/K3 en la smile de puts. Rankeado por percentil expanding
(ex-ante, sin lookahead).

## Hallazgos clave

- IV_CONV TOP10% (P>=90): edge +2.64 pts mean d001-d030 vs RAW (+1.40)
- LOYO neto: 6/7 anos positivos (2025 invierte)
- r(IV_CONV pct, VIX) = +0.64 — fuerte correlacion con regimen VIX
- Partial r controlando VIX: +0.13 (senal pura Werner real pero modesta)
- VIX solo es predictor mas fuerte (r=+0.42 vs IV_CONV r=+0.32)
- Setup de oro: AND TOP20 IVC + TOP20 VIX (interseccion)
- Comportamiento regimen-dependiente: IV_CONV manda en bear, VIX manda en bull

## Estructura

- `index.html` - dashboard principal (lee data.json)
- `data.json` - datos serializados (latest, series, tablas, stats)
- `evidence/` - PNGs (trayectorias, heatmap, conjuncion AND/OR)
- `update_dashboard.py` - script para regenerar data.json + evidencia

## Fuente

Dataset madre: `C:\Users\Administrator\Desktop\Backtests DATABASE\STT\STT_CLASSIC_V9_MERGED_T0_mediana.csv`
