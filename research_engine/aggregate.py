#!/usr/bin/env python3
"""Aggregate individual BTCI Research Engine reports, never silently promote evidence."""
import datetime,json,pathlib,sys,hashlib
base=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else "downloaded")
out=pathlib.Path(sys.argv[2] if len(sys.argv)>2 else "research_engine_out")
out.mkdir(parents=True,exist_ok=True)
reports=[]
for f in sorted(base.rglob("RESULT.json")):
    try:
        v=json.loads(f.read_text(encoding="utf-8"))
        reports.append({"path":str(f),"result":v})
    except Exception as e:reports.append({"path":str(f),"error":str(e)})
tracks={r.get("result",{}).get("track") for r in reports}
expected={"audit","h41","treasury","mvrv"}
status="COMPLETE_STAGING" if expected<=tracks and not any(r.get("result",{}).get("status")=="FAIL_CLOSED" or "error" in r for r in reports) else "INCOMPLETE_OR_FAILED"
warnings=[{"track":r.get("result",{}).get("track"),"status":r.get("result",{}).get("status")} for r in reports if r.get("result",{}).get("status","").startswith("WARN")]
overall={"schema":"BTCI_RESEARCH_ENGINE_RUN_V0_1","status":status,"mode":"RESEARCH_ONLY","utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"expected_tracks":sorted(expected),"received_tracks":sorted(t for t in tracks if t),"warnings":warnings,"new_strict_PIT_promotions":0,"model_training_authorized":False,"predictive_edge_proven":False,"portfolio_writeback":False,"main_writeback":False,"R2_writeback":False,"runs":reports}
(out/"ENGINE_REPORT.json").write_text(json.dumps(overall,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
lines=["# BTCI Research Engine — сводный отчёт","","**Статус:** "+status,"","**Режим:** RESEARCH_ONLY.","","**Исходный BTCI:** v8.18d7; 684 дат; 31 исходное MVRV-свидетельство — без изменения.","","## Проверенные задания",""]
for r in reports:
    t=r.get("result",{})
    lines.append("- "+str(t.get("track","?"))+": "+str(t.get("status","ERROR"))+", HTTP-источников "+str(t.get("source_successes",0)))
lines+=["","## Строгая научная оценка","","- Новых PIT-допусков: **0**.","- Модели 13/26/52 недель не обучались.","- Прогностическое преимущество не доказано.","- Файлы Spot/Earn/Futures/NAV/MASTER/Detector и торговые лимиты не изменялись.","- Негативные результаты не удалялись.","","⚠️ Отчёты GitHub Actions отражают выполнение кода, не состоятельность прогноза."]
(out/"ENGINE_REPORT_RU.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
print("ENGINE_SUMMARY",json.dumps({"status":status,"tracks":sorted(t for t in tracks if t),"warnings":warnings},ensure_ascii=False),flush=True)
sys.exit(0 if status=="COMPLETE_STAGING" else 1)
