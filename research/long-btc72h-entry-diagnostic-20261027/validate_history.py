"""Cross-interval OHLC checks on available complete groups, never impute gaps."""
import json,pathlib,math
R=pathlib.Path(__file__).parent/'history'
checks=[]
for symbol,small,large,n in [('BTCUSDT','1h','4h',4),('BTCUSDT','4h','1d',6),('ETHUSDT','4h','1d',6)]:
    a=json.loads((R/f'{symbol}_{small}.json').read_text())['rows'];b=json.loads((R/f'{symbol}_{large}.json').read_text())['rows'];step=3600000 if small=='1h' else 14400000;bytime={r[0]:r for r in a};checked=0;mismatches=[];skipped=0
    for row in b:
        group=[bytime.get(row[0]+i*step) for i in range(n)]
        if any(x is None for x in group):skipped+=1;continue
        expected=[float(group[0][1]),max(float(x[2]) for x in group),min(float(x[3]) for x in group),float(group[-1][4])]
        actual=list(map(float,row[1:5]));checked+=1
        if not all(math.isclose(x,y,rel_tol=1e-10,abs_tol=1e-8) for x,y in zip(expected,actual)):mismatches.append(row[0])
    checks.append(dict(symbol=symbol,aggregation=small+'->'+large,checked=checked,skipped_incomplete=skipped,mismatches=mismatches))
(R/'cross_interval_checks.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks,indent=2));assert not any(c['mismatches'] for c in checks)
