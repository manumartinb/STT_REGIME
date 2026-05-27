"""
Build IV_CONVEXITY_NIVEL_STT dashboard:
- data.json: latest values, time series IV_CONV pct_exp + VIX
- evidence/*.png: charts
- cohort tables (IV_CONV cuts, VIX cuts, conjunction)
"""
import pandas as pd, numpy as np, sys, os, json
from bisect import bisect_right, insort
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.stdout.reconfigure(encoding='utf-8')

OUTDIR = r'C:/Users/Administrator/Desktop/BULK OPTIONSTRAT/ESTRATEGIAS/Skew/dashboards/IV_CONVEXITY_NIVEL_STT_DASHBOARD'
EVDIR  = os.path.join(OUTDIR, 'evidence')
os.makedirs(EVDIR, exist_ok=True)

PATH = r'C:/Users/Administrator/Desktop/Backtests DATABASE/STT/STT_CLASSIC_V9_MERGED_T0_mediana.csv'
VIX_PATH = r'C:/Users/Administrator/Desktop/FINAL DATA/VIX_CLOSE_HISTORICAL_PRICES.csv'

pnl_cols = [f'PnL_d{i:03d}' for i in range(1, 31)]
print('Loading STT data ...', flush=True)
df = pd.read_csv(PATH, usecols=['dia','SPX','IV_CONVEXITY','delta_total']+pnl_cols, low_memory=False)
df['dia'] = pd.to_datetime(df['dia']).dt.normalize()
df['year'] = df['dia'].dt.year

vix = pd.read_csv(VIX_PATH, parse_dates=['time']).rename(columns={'time':'dia','close':'VIX_Close'})[['dia','VIX_Close']]
vix['dia']=vix['dia'].dt.normalize()
df = df.merge(vix, on='dia', how='left')

# Expanding pct of IV_CONVEXITY (warmup 30)
df = df.sort_values('dia').reset_index(drop=True)
acc=[]; pct_exp=np.full(len(df), np.nan)
for i,v in enumerate(df['IV_CONVEXITY'].values):
    if not pd.isna(v):
        if len(acc)>=30: pct_exp[i]=100.0*bisect_right(acc,float(v))/len(acc)
        insort(acc,float(v))
df['ivc_pct'] = pct_exp

sub = df.dropna(subset=['ivc_pct','VIX_Close','IV_CONVEXITY']).reset_index(drop=True)
print(f'N={len(sub)}  dias={sub["dia"].dt.date.nunique()}')

# ===================================================================
# data.json: time series for the live chart + cohort summary
# ===================================================================
# Daily aggregation (in case multiple trades per day)
daily = sub.groupby('dia').agg(
    iv_conv_raw=('IV_CONVEXITY','mean'),
    ivc_pct=('ivc_pct','mean'),
    vix=('VIX_Close','mean'),
    n_trades=('IV_CONVEXITY','size'),
).reset_index().sort_values('dia')

latest = daily.iloc[-1]
def banda(p):
    if p >= 80: return 'FAVORABLE'
    if p <= 20: return 'ADVERSO'
    return 'NEUTRAL'

data = {
    'latest': {
        'date': latest['dia'].strftime('%Y-%m-%d'),
        'ivc_raw': float(latest['iv_conv_raw']),
        'ivc_pct': float(latest['ivc_pct']),
        'vix': float(latest['vix']),
        'regime_ivc': banda(latest['ivc_pct']),
    },
    'series': [
        {
            't': r['dia'].strftime('%Y-%m-%d'),
            'p': round(float(r['ivc_pct']), 2),
            'v': round(float(r['vix']), 2),
            'r': round(float(r['iv_conv_raw'])*100, 4),
        }
        for _, r in daily.iterrows()
    ],
    'meta': {
        'dataset': 'STT_CLASSIC_V9_MERGED_T0_mediana',
        'n_trades': int(len(sub)),
        'n_days': int(sub['dia'].dt.date.nunique()),
        'date_min': sub['dia'].min().strftime('%Y-%m-%d'),
        'date_max': sub['dia'].max().strftime('%Y-%m-%d'),
    }
}

# ===================================================================
# Cohort tables
# ===================================================================
RAW_AVG = sub[pnl_cols].mean().mean()
RAW_D20 = sub['PnL_d020'].mean()
RAW_D30 = sub['PnL_d030'].mean()
N_RAW = len(sub)
D_RAW = sub['dia'].dt.date.nunique()

def cohort(d, label):
    if len(d)==0: return None
    avg = d[pnl_cols].mean().mean()
    d20 = d['PnL_d020'].mean()
    d30 = d['PnL_d030'].mean()
    wr30 = (d['PnL_d030']>0).mean()*100
    pos = d['PnL_d030'][d['PnL_d030']>0].sum()
    neg = abs(d['PnL_d030'][d['PnL_d030']<0].sum())
    pf = pos/neg if neg>0 else float('inf')
    return {
        'label': label,
        'n': int(len(d)),
        'days': int(d['dia'].dt.date.nunique()),
        'd20': round(d20, 2),
        'd30': round(d30, 2),
        'avg_d001_d030': round(avg, 2),
        'edge_d001_d030': round(avg - RAW_AVG, 2),
        'wr30': round(wr30, 1),
        'pf30': round(pf, 2) if pf != float('inf') else 999,
    }

# Cortes IV_CONV pct_exp
tbl_ivc = []
tbl_ivc.append(cohort(sub, 'RAW (universo)'))
for thr, lbl in [(70,'TOP30 (P>=70)'),(80,'TOP20 (P>=80)'),(90,'TOP10 (P>=90)')]:
    tbl_ivc.append(cohort(sub[sub['ivc_pct']>=thr], lbl))
for thr, lbl in [(30,'BOT30 (P<=30)'),(20,'BOT20 (P<=20)'),(10,'BOT10 (P<=10)')]:
    tbl_ivc.append(cohort(sub[sub['ivc_pct']<=thr], lbl))

# Cortes VIX (pct rank)
sub['vix_pct'] = sub['VIX_Close'].rank(pct=True) * 100
tbl_vix = []
tbl_vix.append(cohort(sub, 'RAW (universo)'))
for thr, lbl in [(70,'TOP30 (VIX>=P70)'),(80,'TOP20 (VIX>=P80)'),(90,'TOP10 (VIX>=P90)')]:
    tbl_vix.append(cohort(sub[sub['vix_pct']>=thr], lbl))
for thr, lbl in [(30,'BOT30 (VIX<=P30)'),(20,'BOT20 (VIX<=P20)'),(10,'BOT10 (VIX<=P10)')]:
    tbl_vix.append(cohort(sub[sub['vix_pct']<=thr], lbl))

# Conjuncion IV_CONV x VIX 3x3 grid
tbl_joint = []
for ivc_lbl, ivc_lo, ivc_hi in [('IVC bajo (P<=33)', 0, 33),
                                  ('IVC medio (33-66)', 33, 66),
                                  ('IVC alto (>=P66)', 66, 100)]:
    for vix_lbl, vix_lo, vix_hi in [('VIX bajo (<=P33)', 0, 33),
                                     ('VIX medio (33-66)', 33, 66),
                                     ('VIX alto (>=P66)', 66, 100)]:
        ss = sub[(sub['ivc_pct']>=ivc_lo)&(sub['ivc_pct']<=ivc_hi)&(sub['vix_pct']>=vix_lo)&(sub['vix_pct']<=vix_hi)]
        if len(ss)>=20:
            c = cohort(ss, f'{ivc_lbl} & {vix_lbl}')
            tbl_joint.append(c)

# AND cohort: TOP20 IV_CONV AND TOP20 VIX vs each alone
top20_ivc = sub[sub['ivc_pct']>=80]
top20_vix = sub[sub['vix_pct']>=80]
top20_both = sub[(sub['ivc_pct']>=80) & (sub['vix_pct']>=80)]
top20_either = sub[(sub['ivc_pct']>=80) | (sub['vix_pct']>=80)]
tbl_combo = [
    cohort(sub, 'RAW universo'),
    cohort(top20_ivc, 'TOP20 IVC solo'),
    cohort(top20_vix, 'TOP20 VIX solo'),
    cohort(top20_both, 'TOP20 IVC AND TOP20 VIX (interseccion)'),
    cohort(top20_either, 'TOP20 IVC OR TOP20 VIX (union)'),
]

data['baseline'] = {
    'n_trades': N_RAW, 'n_days': D_RAW,
    'mean_d001_d030': round(RAW_AVG, 3),
    'mean_d020': round(RAW_D20, 2),
    'mean_d030': round(RAW_D30, 2),
    'wr_d030': round((sub['PnL_d030']>0).mean()*100, 1),
}
data['tbl_ivc'] = tbl_ivc
data['tbl_vix'] = tbl_vix
data['tbl_joint'] = tbl_joint
data['tbl_combo'] = tbl_combo

# Correlations
r_pearson_ivc_vix = sub['IV_CONVEXITY'].corr(sub['VIX_Close'])
r_spearman_pct_vix = sub['ivc_pct'].rank().corr(sub['VIX_Close'].rank())
r_spearman_ivc_pnl = sub['ivc_pct'].rank().corr(sub['PnL_d030'].rank())
r_spearman_vix_pnl = sub['VIX_Close'].rank().corr(sub['PnL_d030'].rank())
data['stats'] = {
    'r_pearson_ivc_vix': round(float(r_pearson_ivc_vix), 4),
    'r_spearman_pct_vix': round(float(r_spearman_pct_vix), 4),
    'r_spearman_ivc_pnl_d030': round(float(r_spearman_ivc_pnl), 4),
    'r_spearman_vix_pnl_d030': round(float(r_spearman_vix_pnl), 4),
}

with open(os.path.join(OUTDIR, 'data.json'), 'w') as f:
    json.dump(data, f, indent=2)
print(f'[SAVED] data.json')

# ===================================================================
# Charts
# ===================================================================
plt.style.use('dark_background')
COL_BG = '#0d1117'
COL_PAN = '#161b22'

# 1. Time series IV_CONV pct + VIX overlay
fig, ax = plt.subplots(figsize=(13, 6), dpi=130, facecolor=COL_BG)
ax.set_facecolor(COL_PAN)
ax.plot(daily['dia'], daily['ivc_pct'], color='#58a6ff', linewidth=0.7, alpha=0.85, label='IV_CONV pct_exp')
ax.axhline(80, color='#3fb950', linestyle='--', linewidth=0.6, alpha=0.6, label='P80 (FAV)')
ax.axhline(20, color='#f85149', linestyle='--', linewidth=0.6, alpha=0.6, label='P20 (ADV)')
ax.set_ylabel('IV_CONV pct_expanding (0-100)', color='#58a6ff')
ax.tick_params(axis='y', labelcolor='#58a6ff')
ax.grid(alpha=0.2)
ax.set_xlabel('Fecha')
ax2 = ax.twinx()
ax2.plot(daily['dia'], daily['vix'], color='#ff9f43', linewidth=0.6, alpha=0.55, label='VIX')
ax2.set_ylabel('VIX', color='#ff9f43')
ax2.tick_params(axis='y', labelcolor='#ff9f43')
ax.legend(loc='upper left', fontsize=9)
ax2.legend(loc='upper right', fontsize=9)
ax.set_title('STT - IV_CONVEXITY pct_expanding y VIX (2019-2025)')
fig.tight_layout()
fig.savefig(os.path.join(EVDIR, 'stt_ivc_vix_timeseries.png'), facecolor=COL_BG)
plt.close(fig)
print('[SAVED] timeseries chart')

# 2. PnL d001-d030 trajectory by IV_CONV cut
fig, ax = plt.subplots(figsize=(12, 6.5), dpi=130, facecolor=COL_BG)
ax.set_facecolor(COL_PAN)
xs = list(range(1, 31))
ax.plot(xs, [sub[f'PnL_d{i:03d}'].mean() for i in xs], color='white', linewidth=2.0, label=f'RAW N={len(sub)}')
for thr, lbl, col in [(90,'TOP10 (>=P90)','#3fb950'),(80,'TOP20 (>=P80)','#58e078'),(70,'TOP30 (>=P70)','#a3e635')]:
    s = sub[sub['ivc_pct']>=thr]
    ax.plot(xs, [s[f'PnL_d{i:03d}'].mean() for i in xs], color=col, linewidth=1.4, label=f'{lbl} N={len(s)}')
for thr, lbl, col in [(30,'BOT30 (<=P30)','#fcad6a'),(20,'BOT20 (<=P20)','#f85149'),(10,'BOT10 (<=P10)','#c0282f')]:
    s = sub[sub['ivc_pct']<=thr]
    ax.plot(xs, [s[f'PnL_d{i:03d}'].mean() for i in xs], color=col, linewidth=1.4, label=f'{lbl} N={len(s)}')
ax.axhline(0, color='gray', linewidth=0.5, alpha=0.5)
ax.set_xlabel('dia tras entrada (d001..d030)')
ax.set_ylabel('mean PnL acumulado (pts)')
ax.set_title('STT - PnL trayectoria por corte IV_CONVEXITY pct_expanding')
ax.legend(loc='upper left', fontsize=8)
ax.grid(alpha=0.2)
fig.tight_layout()
fig.savefig(os.path.join(EVDIR, 'stt_pnl_trajectory_ivc.png'), facecolor=COL_BG)
plt.close(fig)
print('[SAVED] trajectory chart')

# 3. Joint 3x3 heatmap (mean d030 per cell)
fig, ax = plt.subplots(figsize=(8.5, 6.5), dpi=130, facecolor=COL_BG)
ax.set_facecolor(COL_PAN)
ivc_labels = ['IVC bajo (P<=33)', 'IVC medio', 'IVC alto (>=P66)']
vix_labels = ['VIX bajo (P<=33)', 'VIX medio', 'VIX alto (>=P66)']
mat = np.full((3,3), np.nan)
n_mat = np.zeros((3,3), dtype=int)
ivc_ranges = [(0,33),(33,66),(66,100)]
vix_ranges = [(0,33),(33,66),(66,100)]
for i, (ilo, ihi) in enumerate(ivc_ranges):
    for j, (vlo, vhi) in enumerate(vix_ranges):
        ss = sub[(sub['ivc_pct']>=ilo)&(sub['ivc_pct']<=ihi)&(sub['vix_pct']>=vlo)&(sub['vix_pct']<=vhi)]
        if len(ss)>=20:
            mat[i,j] = ss['PnL_d030'].mean()
            n_mat[i,j] = len(ss)
vmax = np.nanmax(np.abs(mat))
im = ax.imshow(mat, cmap='RdYlGn', vmin=-vmax, vmax=vmax, aspect='auto')
for i in range(3):
    for j in range(3):
        v = mat[i,j]
        n = n_mat[i,j]
        if not np.isnan(v):
            ax.text(j, i, f'{v:+.1f}\nN={n}', ha='center', va='center', fontsize=11, color='black', fontweight='bold')
ax.set_xticks(range(3)); ax.set_xticklabels(vix_labels)
ax.set_yticks(range(3)); ax.set_yticklabels(ivc_labels)
ax.set_xlabel('VIX percentil')
ax.set_ylabel('IV_CONV percentil expanding')
ax.set_title('STT - mean PnL_d030 por celda IV_CONV x VIX')
plt.colorbar(im, ax=ax, label='mean PnL_d030 (pts)')
fig.tight_layout()
fig.savefig(os.path.join(EVDIR, 'stt_joint_heatmap.png'), facecolor=COL_BG)
plt.close(fig)
print('[SAVED] joint heatmap')

# 4. AND/OR composite vs RAW
fig, ax = plt.subplots(figsize=(11, 6), dpi=130, facecolor=COL_BG)
ax.set_facecolor(COL_PAN)
xs = list(range(1, 31))
ax.plot(xs, [sub[f'PnL_d{i:03d}'].mean() for i in xs], color='white', linewidth=2.0, label=f'RAW N={N_RAW}')
ax.plot(xs, [top20_ivc[f'PnL_d{i:03d}'].mean() for i in xs], color='#58a6ff', linewidth=1.5, label=f'TOP20 IVC solo N={len(top20_ivc)}')
ax.plot(xs, [top20_vix[f'PnL_d{i:03d}'].mean() for i in xs], color='#ff9f43', linewidth=1.5, label=f'TOP20 VIX solo N={len(top20_vix)}')
ax.plot(xs, [top20_both[f'PnL_d{i:03d}'].mean() for i in xs], color='#3fb950', linewidth=2.0, label=f'AND: TOP20 IVC & TOP20 VIX N={len(top20_both)}')
ax.plot(xs, [top20_either[f'PnL_d{i:03d}'].mean() for i in xs], color='#bc8cff', linewidth=1.3, linestyle='--', label=f'OR: TOP20 IVC | TOP20 VIX N={len(top20_either)}')
ax.axhline(0, color='gray', linewidth=0.5, alpha=0.5)
ax.set_xlabel('dia tras entrada (d001..d030)')
ax.set_ylabel('mean PnL acumulado (pts)')
ax.set_title('STT - Conjuncion IV_CONV x VIX (AND, OR) vs cada uno solo')
ax.legend(loc='upper left', fontsize=9)
ax.grid(alpha=0.2)
fig.tight_layout()
fig.savefig(os.path.join(EVDIR, 'stt_and_or_composite.png'), facecolor=COL_BG)
plt.close(fig)
print('[SAVED] AND/OR composite chart')

print('\n=== Summary ===')
print(f'Latest: {data["latest"]}')
print(f'Stats: {data["stats"]}')
print(f'Baseline: {data["baseline"]}')
print(f'IVC AND VIX cohort: N={len(top20_both)}, d30={top20_both["PnL_d030"].mean():.2f}, edge vs raw={top20_both["PnL_d030"].mean()-RAW_D30:.2f}')
