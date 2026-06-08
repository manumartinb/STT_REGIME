"""
stt_heal.py -- Saneamiento "al vuelo" de dias con glitch r=0 para STT_REGIME.

CONTEXTO (diagnostico junio 2026):
  El pipeline que genera los parquets 30MIN calcula la IV con Black-Scholes usando la
  tasa 'r'. Cuando ThetaData no entrega la tasa, el generador (V19, linea 563) la pone a
  r=0.0 en vez de la tasa real (~4%). Resultado esos dias: toda la curva de IV sale
  sesgada a la baja y el forward colapsa (strike ATM mal). SKEW_PUT_ENRICHED hereda el
  sesgo. NO es dato de mercado corrupto: los precios (mid) son correctos; solo la tasa.

QUE HACE ESTE MODULO (opcion A2 selectiva, autocontenida en el dashboard STT):
  - Detecta SOLO los dias glitch (forward colapsado HOY pero normal en los vecinos).
    Asi NO toca los dias ZIRP 2020-2021 (r=0 correcto: tasas reales a cero).
  - Para esos dias, recalcula iv_5d/iv_15d/iv_25d/iv_30d/iv_50d y skew_25d_vs50 desde el
    PARQUET 30MIN crudo (precios reales), re-invirtiendo la IV con la tasa correcta
    (forward-fill de la r del dia bueno mas reciente). Interpola IV vs delta (replica el
    metodo del generador; paridad verificada +-0.0002 en dias buenos).
  - Dias buenos: NO se tocan (pasan tal cual).

SELF-DISABLING: si se arregla la fuente (r correcta), los dias dejan de tener forward
  colapsado -> el detector no dispara -> este modulo es un no-op. Cero conflicto.

SIN dependencias nuevas (norm.cdf via math.erf, IV por biseccion) para que el worker
  diario del Master Pipeline no pueda fallar por imports.
"""
from __future__ import annotations
import os, math
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

# Deltas (put, en valor absoluto) que el dashboard necesita -> columnas iv_Xd
DELTA_TARGETS = {"iv_5d": 0.05, "iv_15d": 0.15, "iv_25d": 0.25, "iv_30d": 0.30, "iv_50d": 0.50}

# Deteccion del glitch: se mira la TASA 'r' del parquet directamente (no el proxy carry).
# El carry colapsa solo cuando el strike ATM tambien se desplaza (may-jun 2026); en marzo
# 2026 r=0 pero el strike fue correcto -> el carry no lo delata. La r SI lo delata siempre.
R_GLITCH_MAX = 0.005       # r ~ 0 -> glitch (en regimen de tasas altas)
# Solo se considera glitch a partir de esta fecha: antes (2020-mar a 2022-abr) r=0 era REAL
# (ZIRP: la Fed tenia las tasas a cero). Desde 2023 la tasa real es ~4-5%, asi que r=0 es bug.
GLITCH_CUTOFF = "2023-01-01"


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_put(S: float, K: float, T: float, r: float, sig: float) -> float:
    if sig <= 0 or T <= 0:
        return max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def _put_delta(S: float, K: float, T: float, r: float, sig: float) -> float:
    if sig <= 0 or T <= 0:
        return -1.0 if K > S else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * math.sqrt(T))
    return _norm_cdf(d1) - 1.0


def _iv_put(price: float, S: float, K: float, T: float, r: float) -> float:
    """IV por biseccion (sin scipy). NaN si no converge / sin valor intrinseco."""
    if price is None or not np.isfinite(price) or price <= 0 or T <= 0:
        return float("nan")
    lo, hi = 1e-4, 5.0
    flo = _bs_put(S, K, T, r, lo) - price
    fhi = _bs_put(S, K, T, r, hi) - price
    if flo * fhi > 0:
        return float("nan")
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        fm = _bs_put(S, K, T, r, mid) - price
        if abs(fm) < 1e-6:
            return mid
        if flo * fm < 0:
            hi = mid; fhi = fm
        else:
            lo = mid; flo = fm
    return 0.5 * (lo + hi)


def _day_rate(parquet_dir: str, day_str: str, _cache: dict) -> float:
    """Mediana de la tasa 'r' del parquet 30MIN de un dia. NaN si no se puede leer.
    Cacheado en _cache para no releer."""
    if day_str in _cache:
        return _cache[day_str]
    val = float("nan")
    try:
        t = pq.read_table(os.path.join(parquet_dir, f"30MINDATA_{day_str}.parquet"), columns=["r"])
        s = t.column("r").to_pandas().dropna()
        if len(s):
            val = float(s.median())
    except Exception:
        pass
    _cache[day_str] = val
    return val


def rate_series(df: pd.DataFrame, parquet_dir: str, _cache: dict) -> pd.Series:
    """Serie de tasa 'r' por dia (solo lee parquets de fechas >= GLITCH_CUTOFF; antes NaN
    para no escanear ZIRP innecesariamente)."""
    cutoff = pd.Timestamp(GLITCH_CUTOFF)
    out = []
    for d in pd.to_datetime(df["dia"]):
        out.append(_day_rate(parquet_dir, d.strftime("%Y-%m-%d"), _cache) if d >= cutoff else float("nan"))
    return pd.Series(out, index=df.index, dtype=float)


def detect_glitch_days(df: pd.DataFrame, r_by_day: pd.Series) -> pd.Index:
    """Glitch = fecha >= cutoff con tasa r ~ 0. (ZIRP < 2023 queda fuera por construccion
    de r_by_day, que es NaN antes del cutoff.)"""
    glitch = r_by_day.notna() & (r_by_day < R_GLITCH_MAX)
    return df.index[glitch.fillna(False)]


def _recompute_day(parquet_path: str, expiration: str, day: pd.Timestamp,
                   r_use: float) -> dict | None:
    """Recalcula iv_Xd + skew_25d_vs50 desde el parquet crudo con la tasa r_use."""
    try:
        d = pd.read_parquet(parquet_path)
    except Exception:
        return None
    d = d[(d["snapshot_time_et"] == "10:30:00") & (d["expiration"] == expiration)
          & (d["right"] == "P")]
    if len(d) < 8:
        return None
    S = float(pd.to_numeric(d["underlying_price"], errors="coerce").iloc[0])
    T = (pd.to_datetime(expiration) - pd.to_datetime(day)).days / 365.0
    if not np.isfinite(S) or T <= 0:
        return None
    Ks = pd.to_numeric(d["strike"], errors="coerce").values
    px = pd.to_numeric(d["mid"], errors="coerce").values
    deltas, ivs = [], []
    for K, p in zip(Ks, px):
        iv = _iv_put(p, S, float(K), T, r_use)
        if np.isfinite(iv):
            deltas.append(_put_delta(S, float(K), T, r_use, iv)); ivs.append(iv)
    if len(deltas) < 8:
        return None
    order = np.argsort(deltas)
    dl = np.array(deltas)[order]; iv = np.array(ivs)[order]
    out = {}
    for col, dt in DELTA_TARGETS.items():
        out[col] = float(np.interp(-dt, dl, iv))   # interp IV vs delta (replica generador)
    out["skew_25d_vs50"] = out["iv_25d"] - out["iv_50d"]
    return out


def heal(df: pd.DataFrame, parquet_dir: str, log=lambda m: None) -> pd.DataFrame:
    """Sana in-place (copia) los dias glitch de df. Requiere columnas:
    trade-date (indice 'dia' datetime), underlying_price, strike_hit_50d,
    expiration_used, iv_5d/iv_15d/iv_25d/iv_30d/iv_50d, skew_25d_vs50.
    Dias buenos intactos. NO lanza: si algo falla en un dia, lo deja como estaba."""
    if "dia" not in df.columns or "expiration_used" not in df.columns:
        return df
    df = df.reset_index(drop=True).copy()
    cache: dict = {}
    r_by_day = rate_series(df, parquet_dir, cache)
    glitch_idx = detect_glitch_days(df, r_by_day)
    if len(glitch_idx) == 0:
        return df
    # r de referencia para cada dia glitch: forward-fill de la ultima r VALIDA (>0) de la
    # propia serie; si no hay anterior, la primera valida posterior.
    valid = r_by_day.where(r_by_day > R_GLITCH_MAX)
    r_ff = valid.ffill().bfill()
    healed = 0
    for i in glitch_idx:
        r_use = r_ff.iloc[i]
        if not np.isfinite(r_use) or r_use <= 0:
            continue
        day = pd.to_datetime(df.at[i, "dia"])
        exp = str(df.at[i, "expiration_used"])
        pp = os.path.join(parquet_dir, f"30MINDATA_{day.strftime('%Y-%m-%d')}.parquet")
        rec = _recompute_day(pp, exp, day, float(r_use))
        if rec is None:
            continue
        for col, val in rec.items():
            if col in df.columns and np.isfinite(val):
                df.at[i, col] = val
        healed += 1
    if healed:
        log(f"[stt_heal] sanados {healed} dia(s) glitch r=0 con tasa real (forward-fill)")
    return df
