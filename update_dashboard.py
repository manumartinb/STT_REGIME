"""
Build IV_CONVEXITY_NIVEL_STT dashboard (v2: mean + median dual everywhere)
- data.json: latest, time series, cohort tables (con mean Y median)
- evidence/*.png: charts con doble panel mean | median
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

df = df.sort_values('dia').reset_index(drop=True)
acc=[]; pct_exp=np.full(len(df), np.nan)
for i,v in enumerate(df['IV_CONVEXITY'].values):
    if not pd.isna(v):
        if len(acc)>=30: pct_exp[i]=100.0*bisect_right(acc,float(v))/len(acc)
        insort(acc,float(v))
df['ivc_pct'] = pct_exp
sub = df.dropna(subset=['ivc_pct','VIX_Close','IV_CONVEXITY']).reset_index(drop=True)
sub['vix_pct'] = sub['VIX_Close'].rank(pct=True) * 100
print(f'N={len(sub)}  dias={sub["dia"].dt.date.nunique()}')

daily = sub.groupby('dia').agg(
    iv_conv_raw=('IV_CONVEXITY','mean'),
    ivc_pct=('ivc_pct','mean'),
    vix=('VIX_Close','mean'),
).reset_index().sort_values('dia')
latest = daily.iloc[-1]
def banda(p):
    if p >= 80: return 'FAVORABLE'
    if p <= 20: return 'ADVERSO'
    return 'NEUTRAL'

def cohort(d, label):
    if len(d)==0: return None
    avg_mean = d[pnl_cols].mean().mean()
    avg_med  = d[pnl_cols].median().mean()
    pos = d['PnL_d030'][d['PnL_d030']>0].sum()
    neg = abs(d['PnL_d030'][d['PnL_d030']<0].sum())
    pf = pos/neg if neg>0 else float('inf')
    return {
        'label': label, 'n': int(len(d)), 'days': int(d['dia'].dt.date.nunique()),
        'd20_mean': round(d['PnL_d020'].mean(), 2), 'd20_med': round(d['PnL_d020'].median(), 2),
        'd30_mean': round(d['PnL_d030'].mean(), 2), 'd30_med': round(d['PnL_d030'].median(), 2),
        'avg_mean': round(avg_mean, 2), 'avg_med': round(avg_med, 2),
        'wr30': round((d['PnL_d030']>0).mean()*100, 1),
        'pf30': round(pf, 2) if pf != float('inf') else 999,
    }

RAW_AVG_MEAN = sub[pnl_cols].mean().mean()
RAW_AVG_MED  = sub[pnl_cols].median().mean()

data = {
    'latest': {'date': latest['dia'].strftime('%Y-%m-%d'), 'ivc_raw': float(latest['iv_conv_raw']),
               'ivc_pct': float(latest['ivc_pct']), 'vix': float(latest['vix']), 'regime_ivc': banda(latest['ivc_pct'])},
    'series': [{'t': r['dia'].strftime('%Y-%m-%d'), 'p': round(float(r['ivc_pct']),2),
                'v': round(float(r['vix']),2), 'r': round(float(r['iv_conv_raw'])*100,4)} for _, r in daily.iterrows()],
    'meta': {'dataset': 'STT_CLASSIC_V9_MERGED_T0_mediana', 'n_trades': int(len(sub)),
             'n_days': int(sub['dia'].dt.date.nunique()), 'date_min': sub['dia'].min().strftime('%Y-%m-%d'),
             'date_max': sub['dia'].max().strftime('%Y-%m-%d')},
}

tbl_ivc = [cohort(sub, 'RAW (universo)')]
for thr, lbl in [(70,'TOP30 (P>=70)'),(80,'TOP20 (P>=80)'),(90,'TOP10 (P>=90)')]:
    tbl_ivc.append(cohort(sub[sub['ivc_pct']>=thr], lbl))
for thr, lbl in [(30,'BOT30 (P<=30)'),(20,'BOT20 (P<=20)'),(10,'BOT10 (P<=10)')]:
    tbl_ivc.append(cohort(sub[sub['ivc_pct']<=thr], lbl))

tbl_vix = [cohort(sub, 'RAW (universo)')]
for thr, lbl in [(70,'TOP30 (VIX>=P70)'),(80,'TOP20 (VIX>=P80)'),(90,'TOP10 (VIX>=P90)')]:
    tbl_vix.append(cohort(sub[sub['vix_pct']>=thr], lbl))
for thr, lbl in [(30,'BOT30 (VIX<=P30)'),(20,'BOT20 (VIX<=P20)'),(10,'BOT10 (VIX<=P10)')]:
    tbl_vix.append(cohort(sub[sub['vix_pct']<=thr], lbl))

tbl_joint = []
for ivc_lbl, ilo, ihi in [('IVC bajo (P<=33)',0,33),('IVC medio (33-66)',33,66),('IVC alto (>=P66)',66,100)]:
    for vix_lbl, vlo, vhi in [('VIX bajo (<=P33)',0,33),('VIX medio (33-66)',33,66),('VIX alto (>=P66)',66,100)]:
        ss = sub[(sub['ivc_pct']>=ilo)&(sub['ivc_pct']<=ihi)&(sub['vix_pct']>=vlo)&(sub['vix_pct']<=vhi)]
        if len(ss)>=20:
            tbl_joint.append(cohort(ss, f'{ivc_lbl} & {vix_lbl}'))

top20_ivc = sub[sub['ivc_pct']>=80]; top20_vix = sub[sub['vix_pct']>=80]
top20_both = sub[(sub['ivc_pct']>=80)&(sub['vix_pct']>=80)]; top20_either = sub[(sub['ivc_pct']>=80)|(sub['vix_pct']>=80)]
tbl_combo = [cohort(sub,'RAW universo'), cohort(top20_ivc,'TOP20 IVC solo'), cohort(top20_vix,'TOP20 VIX solo'),
             cohort(top20_both,'TOP20 IVC AND TOP20 VIX (interseccion)'), cohort(top20_either,'TOP20 IVC OR TOP20 VIX (union)')]

# SETUP DE HIERRO: cohortes BOT20 (lo peor)
bot20_ivc = sub[sub['ivc_pct']<=20]; bot20_vix = sub[sub['vix_pct']<=20]
bot20_both = sub[(sub['ivc_pct']<=20)&(sub['vix_pct']<=20)]; bot20_either = sub[(sub['ivc_pct']<=20)|(sub['vix_pct']<=20)]
tbl_iron = [cohort(sub,'RAW universo'), cohort(bot20_ivc,'BOT20 IVC solo'), cohort(bot20_vix,'BOT20 VIX solo'),
            cohort(bot20_both,'BOT20 IVC AND BOT20 VIX (interseccion)'), cohort(bot20_either,'BOT20 IVC OR BOT20 VIX (union)')]

data['baseline'] = {'n_trades': len(sub), 'n_days': int(sub['dia'].dt.date.nunique()),
    'mean_d001_d030': round(RAW_AVG_MEAN,3), 'med_d001_d030': round(RAW_AVG_MED,3),
    'mean_d020': round(sub['PnL_d020'].mean(),2), 'med_d020': round(sub['PnL_d020'].median(),2),
    'mean_d030': round(sub['PnL_d030'].mean(),2), 'med_d030': round(sub['PnL_d030'].median(),2),
    'wr_d030': round((sub['PnL_d030']>0).mean()*100,1)}
data['tbl_ivc']=tbl_ivc; data['tbl_vix']=tbl_vix; data['tbl_joint']=tbl_joint; data['tbl_combo']=tbl_combo; data['tbl_iron']=tbl_iron
data['stats'] = {
    'r_pearson_ivc_vix': round(float(sub['IV_CONVEXITY'].corr(sub['VIX_Close'])),4),
    'r_spearman_pct_vix': round(float(sub['ivc_pct'].rank().corr(sub['VIX_Close'].rank())),4),
    'r_spearman_ivc_pnl_d030': round(float(sub['ivc_pct'].rank().corr(sub['PnL_d030'].rank())),4),
    'r_spearman_vix_pnl_d030': round(float(sub['VIX_Close'].rank().corr(sub['PnL_d030'].rank())),4),
}
with open(os.path.join(OUTDIR, 'data.json'), 'w') as f:
    json.dump(data, f, indent=2)
print('[SAVED] data.json')

# ===================================================================
plt.style.use('dark_background')
COL_BG='#0d1117'; COL_PAN='#161b22'
xs = list(range(1, 31))

# 1. Time series
fig, ax = plt.subplots(figsize=(13, 6), dpi=130, facecolor=COL_BG)
ax.set_facecolor(COL_PAN)
ax.plot(daily['dia'], daily['ivc_pct'], color='#58a6ff', linewidth=0.7, alpha=0.85, label='IV_CONV pct_exp')
ax.axhline(80, color='#3fb950', linestyle='--', linewidth=0.6, alpha=0.6, label='P80')
ax.axhline(20, color='#f85149', linestyle='--', linewidth=0.6, alpha=0.6, label='P20')
ax.set_ylabel('IV_CONV pct_expanding', color='#58a6ff'); ax.tick_params(axis='y', labelcolor='#58a6ff')
ax.grid(alpha=0.2); ax.set_xlabel('Fecha')
ax2 = ax.twinx(); ax2.plot(daily['dia'], daily['vix'], color='#ff9f43', linewidth=0.6, alpha=0.55, label='VIX')
ax2.set_ylabel('VIX', color='#ff9f43'); ax2.tick_params(axis='y', labelcolor='#ff9f43')
ax.legend(loc='upper left', fontsize=9); ax2.legend(loc='upper right', fontsize=9)
ax.set_title('STT - IV_CONVEXITY pct_expanding y VIX (2019-2025)')
fig.tight_layout(); fig.savefig(os.path.join(EVDIR,'stt_ivc_vix_timeseries.png'),facecolor=COL_BG); plt.close(fig)
print('[SAVED] timeseries')

# 2. Trajectory DUAL mean | median
fig, axes = plt.subplots(1, 2, figsize=(16, 6.5), dpi=120, facecolor=COL_BG)
cut_defs = [(90,'TOP10 (>=P90)','#3fb950'),(80,'TOP20 (>=P80)','#58e078'),(70,'TOP30 (>=P70)','#a3e635'),
            (30,'BOT30 (<=P30)','#fcad6a'),(20,'BOT20 (<=P20)','#f85149'),(10,'BOT10 (<=P10)','#c0282f')]
for ax, agg, title in [(axes[0],'mean','MEAN'),(axes[1],'median','MEDIAN')]:
    ax.set_facecolor(COL_PAN)
    aggf = (lambda s: s.mean()) if agg=='mean' else (lambda s: s.median())
    ax.plot(xs, [aggf(sub[f'PnL_d{i:03d}']) for i in xs], color='white', linewidth=2.0, label=f'RAW N={len(sub)}')
    for thr, lbl, col in cut_defs:
        s = sub[sub['ivc_pct']>=thr] if 'TOP' in lbl else sub[sub['ivc_pct']<=thr]
        ax.plot(xs, [aggf(s[f'PnL_d{i:03d}']) for i in xs], color=col, linewidth=1.3, label=f'{lbl} N={len(s)}')
    ax.axhline(0, color='gray', linewidth=0.5, alpha=0.5)
    ax.set_xlabel('dia tras entrada (d001..d030)'); ax.set_ylabel(f'{title} PnL acumulado (pts)')
    ax.set_title(f'STT - PnL trayectoria por IV_CONV cut [{title}]')
    ax.legend(loc='upper left', fontsize=7.5); ax.grid(alpha=0.2)
fig.tight_layout(); fig.savefig(os.path.join(EVDIR,'stt_pnl_trajectory_ivc.png'),facecolor=COL_BG); plt.close(fig)
print('[SAVED] trajectory dual (IVC)')

# 2b. Trajectory DUAL por cortes VIX
fig, axes = plt.subplots(1, 2, figsize=(16, 6.5), dpi=120, facecolor=COL_BG)
vix_cut_defs = [(90,'TOP10 (VIX>=P90)','#3fb950'),(80,'TOP20 (VIX>=P80)','#58e078'),(70,'TOP30 (VIX>=P70)','#a3e635'),
                (30,'BOT30 (VIX<=P30)','#fcad6a'),(20,'BOT20 (VIX<=P20)','#f85149'),(10,'BOT10 (VIX<=P10)','#c0282f')]
for ax, agg, title in [(axes[0],'mean','MEAN'),(axes[1],'median','MEDIAN')]:
    ax.set_facecolor(COL_PAN)
    aggf = (lambda s: s.mean()) if agg=='mean' else (lambda s: s.median())
    ax.plot(xs, [aggf(sub[f'PnL_d{i:03d}']) for i in xs], color='white', linewidth=2.0, label=f'RAW N={len(sub)}')
    for thr, lbl, col in vix_cut_defs:
        s = sub[sub['vix_pct']>=thr] if 'TOP' in lbl else sub[sub['vix_pct']<=thr]
        ax.plot(xs, [aggf(s[f'PnL_d{i:03d}']) for i in xs], color=col, linewidth=1.3, label=f'{lbl} N={len(s)}')
    ax.axhline(0, color='gray', linewidth=0.5, alpha=0.5)
    ax.set_xlabel('dia tras entrada (d001..d030)'); ax.set_ylabel(f'{title} PnL acumulado (pts)')
    ax.set_title(f'STT - PnL trayectoria por VIX cut [{title}]')
    ax.legend(loc='upper left', fontsize=7.5); ax.grid(alpha=0.2)
fig.tight_layout(); fig.savefig(os.path.join(EVDIR,'stt_pnl_trajectory_vix.png'),facecolor=COL_BG); plt.close(fig)
print('[SAVED] trajectory dual (VIX)')

# 3. Joint heatmap DUAL mean | median
fig, axes = plt.subplots(1, 2, figsize=(17, 6.8), dpi=120, facecolor=COL_BG)
ivc_labels=['IVC bajo (P<=33)','IVC medio','IVC alto (>=P66)']; vix_labels=['VIX bajo (P<=33)','VIX medio','VIX alto (>=P66)']
ivc_ranges=[(0,33),(33,66),(66,100)]; vix_ranges=[(0,33),(33,66),(66,100)]
for ax, agg, title in [(axes[0],'mean','MEAN'),(axes[1],'median','MEDIAN')]:
    ax.set_facecolor(COL_PAN)
    mat=np.full((3,3),np.nan); nmat=np.zeros((3,3),dtype=int)
    for i,(ilo,ihi) in enumerate(ivc_ranges):
        for j,(vlo,vhi) in enumerate(vix_ranges):
            ss=sub[(sub['ivc_pct']>=ilo)&(sub['ivc_pct']<=ihi)&(sub['vix_pct']>=vlo)&(sub['vix_pct']<=vhi)]
            if len(ss)>=20:
                mat[i,j]= ss['PnL_d030'].mean() if agg=='mean' else ss['PnL_d030'].median()
                nmat[i,j]=len(ss)
    vmax=10.0
    im=ax.imshow(mat,cmap='RdYlGn',vmin=-vmax,vmax=vmax,aspect='auto')
    for i in range(3):
        for j in range(3):
            if not np.isnan(mat[i,j]):
                ax.text(j,i,f'{mat[i,j]:+.1f}\nN={nmat[i,j]}',ha='center',va='center',fontsize=11,color='black',fontweight='bold')
    ax.set_xticks(range(3)); ax.set_xticklabels(vix_labels,fontsize=9)
    ax.set_yticks(range(3)); ax.set_yticklabels(ivc_labels,fontsize=9)
    ax.set_xlabel('VIX percentil'); ax.set_ylabel('IV_CONV percentil expanding')
    ax.set_title(f'STT - PnL_d030 por celda IVC x VIX [{title}]')
    plt.colorbar(im,ax=ax,label=f'{title} PnL_d030 (pts)')
fig.tight_layout(); fig.savefig(os.path.join(EVDIR,'stt_joint_heatmap.png'),facecolor=COL_BG); plt.close(fig)
print('[SAVED] joint heatmap dual')

# 4. AND/OR composite DUAL
fig, axes = plt.subplots(1, 2, figsize=(16, 6), dpi=120, facecolor=COL_BG)
for ax, agg, title in [(axes[0],'mean','MEAN'),(axes[1],'median','MEDIAN')]:
    ax.set_facecolor(COL_PAN)
    aggf = (lambda s: s.mean()) if agg=='mean' else (lambda s: s.median())
    ax.plot(xs, [aggf(sub[f'PnL_d{i:03d}']) for i in xs], color='white', linewidth=2.0, label=f'RAW N={len(sub)}')
    ax.plot(xs, [aggf(top20_ivc[f'PnL_d{i:03d}']) for i in xs], color='#58a6ff', linewidth=1.5, label=f'TOP20 IVC N={len(top20_ivc)}')
    ax.plot(xs, [aggf(top20_vix[f'PnL_d{i:03d}']) for i in xs], color='#ff9f43', linewidth=1.5, label=f'TOP20 VIX N={len(top20_vix)}')
    ax.plot(xs, [aggf(top20_both[f'PnL_d{i:03d}']) for i in xs], color='#3fb950', linewidth=2.0, label=f'AND N={len(top20_both)}')
    ax.plot(xs, [aggf(top20_either[f'PnL_d{i:03d}']) for i in xs], color='#bc8cff', linewidth=1.3, linestyle='--', label=f'OR N={len(top20_either)}')
    ax.axhline(0, color='gray', linewidth=0.5, alpha=0.5)
    ax.set_xlabel('dia tras entrada (d001..d030)'); ax.set_ylabel(f'{title} PnL acumulado (pts)')
    ax.set_title(f'STT - Conjuncion IVC x VIX [{title}]')
    ax.legend(loc='upper left', fontsize=8.5); ax.grid(alpha=0.2)
fig.tight_layout(); fig.savefig(os.path.join(EVDIR,'stt_and_or_composite.png'),facecolor=COL_BG); plt.close(fig)
print('[SAVED] and/or dual (oro)')

# 5. SETUP DE HIERRO (BOT20) DUAL
fig, axes = plt.subplots(1, 2, figsize=(16, 6), dpi=120, facecolor=COL_BG)
for ax, agg, title in [(axes[0],'mean','MEAN'),(axes[1],'median','MEDIAN')]:
    ax.set_facecolor(COL_PAN)
    aggf = (lambda s: s.mean()) if agg=='mean' else (lambda s: s.median())
    ax.plot(xs, [aggf(sub[f'PnL_d{i:03d}']) for i in xs], color='white', linewidth=2.0, label=f'RAW N={len(sub)}')
    ax.plot(xs, [aggf(bot20_ivc[f'PnL_d{i:03d}']) for i in xs], color='#58a6ff', linewidth=1.5, label=f'BOT20 IVC N={len(bot20_ivc)}')
    ax.plot(xs, [aggf(bot20_vix[f'PnL_d{i:03d}']) for i in xs], color='#ff9f43', linewidth=1.5, label=f'BOT20 VIX N={len(bot20_vix)}')
    ax.plot(xs, [aggf(bot20_both[f'PnL_d{i:03d}']) for i in xs] if len(bot20_both)>0 else [np.nan]*len(xs), color='#f85149', linewidth=2.0, label=f'AND N={len(bot20_both)}')
    ax.plot(xs, [aggf(bot20_either[f'PnL_d{i:03d}']) for i in xs], color='#bc8cff', linewidth=1.3, linestyle='--', label=f'OR N={len(bot20_either)}')
    ax.axhline(0, color='gray', linewidth=0.5, alpha=0.5)
    ax.set_xlabel('dia tras entrada (d001..d030)'); ax.set_ylabel(f'{title} PnL acumulado (pts)')
    ax.set_title(f'STT - Setup de HIERRO (BOT20 IVC x VIX) [{title}]')
    ax.legend(loc='lower left', fontsize=8.5); ax.grid(alpha=0.2)
fig.tight_layout(); fig.savefig(os.path.join(EVDIR,'stt_iron_composite.png'),facecolor=COL_BG); plt.close(fig)
print('[SAVED] iron composite dual')

print('\n=== Summary ===')
print(f'Latest: {data["latest"]}')
print(f'Baseline mean_d030={data["baseline"]["mean_d030"]}  med_d030={data["baseline"]["med_d030"]}')
red = [c for c in tbl_joint if 'alto' in c['label'] and 'VIX bajo' in c['label']]
print(f'Red cell: {red}')
