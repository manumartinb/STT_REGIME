"""
STT_REGIME daily chart refresh (worker ligero para V2 PERMA MASTER DAILY PIPELINE).

Refresca SOLO el grafico/panel vivo del dashboard STT_REGIME:
  - data.json -> 'series' + 'latest' + 'meta.chart_*' desde la ultima fecha de
    mercado disponible en SKEW_PUT_ENRICHED @dte160 + SP_SPX_CLOSE.
  - NO toca las tablas/deciles/stats (estudio backtest frozen) ni los PNGs.
  - git add data.json + commit + push origin main (SSH).

Senales (percentil expanding 0-100, ex-ante; RAW suavizado mediana movil 3d antes de percentilizar):
  IV_CONV  = smooth3((iv_5d+iv_30d)/2 - iv_15d) @dte160 (rho +0.84 con trade-specific)
  IV ATM   = smooth3(iv_50d) @dte160
  PUT SKEW = smooth3(skew_25d_vs50) @dte160 (recalc local del raw, homogeneo con IV ATM)
Secundario del chart: SPX close.

Exit codes (compatibles con run_dashboard_generic de V2):
  0 = data.json actualizado y pusheado
  3 = sin cambios (idempotente, no commit)
  2 = warn de datos (fuente vacia/incompleta)
  1 = error
"""
import sys, os, json, subprocess
from datetime import datetime
from bisect import bisect_right, insort
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

DIR  = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(DIR, 'data.json')
PS_PATH  = r'C:/Users/Administrator/Desktop/BULK OPTIONSTRAT/ESTRATEGIAS/Skew/SKEW_PUT_ENRICHED.csv'
SPX_PATH = r'C:/Users/Administrator/Desktop/FINAL DATA/SP_SPX_CLOSE_HISTORICAL_PRICES.csv'
PARQUET_DIR = r'C:/Users/Administrator/Desktop/FINAL DATA/HIST AND STREAMING DATA/UPDATED HISTORICAL DAYS PARQUET'
sys.path.insert(0, DIR)
import stt_heal  # saneamiento dias glitch r=0 (autocontenido, no-op si no hay glitch)

def log(m): print(f"[STT-REFRESH {datetime.now():%H:%M:%S}] {m}", flush=True)

def expanding_pct(v, w=30):
    acc=[]; out=np.full(len(v), np.nan)
    for i,x in enumerate(v):
        if not pd.isna(x):
            if len(acc)>=w: out[i]=100.0*bisect_right(acc,float(x))/len(acc)
            insort(acc,float(x))
    return out

def smooth3(s):
    # Mediana movil trailing 3d (hoy + 2 dias previos), ex-ante. IDENTICA a update_dashboard.py.
    return pd.Series(s).rolling(3, min_periods=1).median().values

def banda(p):
    if p>=80: return 'FAVORABLE'
    if p<=20: return 'ADVERSO'
    return 'NEUTRAL'

def git(args):
    return subprocess.run(['git','-C',DIR]+args, capture_output=True, text=True)

def main():
    try:
        if not os.path.isfile(DATA):
            log(f"data.json no existe en {DIR} -> regenera primero con update_dashboard.py"); return 1
        data = json.load(open(DATA, encoding='utf-8'))

        ps = pd.read_csv(PS_PATH, usecols=['trade_date','dte_target','iv_5d','iv_15d','iv_30d','iv_50d',
                                           'skew_25d_vs50','underlying_price','strike_hit_50d','expiration_used'])
        ps['dia'] = pd.to_datetime(ps['trade_date']).dt.normalize()
        ps = ps[ps['dte_target']==160].sort_values('dia').reset_index(drop=True)
        if len(ps) < 100:
            log(f"SKEW_PUT_ENRICHED @dte160 insuficiente (N={len(ps)})"); return 2
        # SANEAR dias glitch r=0 (forward colapsado) desde parquet crudo con tasa real. No-op si no hay.
        ps = stt_heal.heal(ps, PARQUET_DIR, log=log)
        # Suavizado 3d ex-ante del RAW antes de percentilizar. BLOQUE IDENTICO a update_dashboard.py
        # (seccion panel): mata outliers de 1 dia en la fuente. PUT SKEW recalc local del raw.
        ps['ivc_raw'] = (ps['iv_5d']+ps['iv_30d'])/2 - ps['iv_15d']
        ps['ivc_d'] = expanding_pct(smooth3(ps['ivc_raw'].values))
        ps['atm_d'] = expanding_pct(smooth3(ps['iv_50d'].values))
        ps['ps_d']  = expanding_pct(smooth3(ps['skew_25d_vs50'].values))

        spx = pd.read_csv(SPX_PATH, usecols=['time','close'])
        spx['dia'] = pd.to_datetime(spx['time']).dt.normalize()
        ps = ps.merge(spx[['dia','close']].rename(columns={'close':'spx'}), on='dia', how='left')

        dser = ps.dropna(subset=['ivc_d','atm_d','ps_d']).reset_index(drop=True)
        if dser.empty:
            log("serie diaria vacia tras dropna"); return 2

        series = [{'t':r['dia'].strftime('%Y-%m-%d'), 'ivc':round(float(r['ivc_d']),2),
                   'vix':round(float(r['atm_d']),2), 'ps':round(float(r['ps_d']),2),
                   'spx':(round(float(r['spx']),2) if pd.notna(r['spx']) else None)} for _,r in dser.iterrows()]
        last = dser.iloc[-1]
        latest = {'date':last['dia'].strftime('%Y-%m-%d'),
                  'ivc_pct':float(last['ivc_d']),'regime_ivc':banda(last['ivc_d']),
                  'vix_pct':float(last['atm_d']),'regime_vix':banda(last['atm_d']),
                  'ps_pct':float(last['ps_d']),'regime_ps':banda(last['ps_d']),
                  'vix_raw':float(last['iv_50d']),'ivc_raw':float(last['ivc_raw'])}

        data['series'] = series
        data['latest'] = latest
        data.setdefault('meta',{})['chart_date_max'] = latest['date']
        data['meta']['chart_n_days'] = int(len(dser))

        json.dump(data, open(DATA,'w',encoding='utf-8'), indent=2)
        log(f"data.json patched: series={len(series)} dias, latest={latest['date']} "
            f"(IVC {latest['ivc_pct']:.1f} / IVATM {latest['vix_pct']:.1f} / PS {latest['ps_pct']:.1f})")

        # ---- git push (SSH) ----
        git(['add','data.json'])
        if git(['diff','--cached','--quiet']).returncode == 0:
            log("sin cambios en data.json -> idempotente (no commit)"); return 3
        c = git(['-c','user.email=noreply@anthropic.com','-c','user.name=manumartinb',
                 'commit','-m',f"daily chart refresh {latest['date']}"])
        if c.returncode != 0:
            log(f"commit fallo: {c.stderr.strip()}"); return 1
        p = git(['push','origin','main'])
        if p.returncode != 0:
            log(f"push fallo: {p.stderr.strip()}"); return 1
        log("pushed -> https://manumartinb.github.io/STT_REGIME/")
        return 0
    except Exception as e:
        log(f"ERROR {type(e).__name__}: {e}"); return 1

if __name__ == '__main__':
    sys.exit(main())
