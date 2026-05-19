"""
全库 Golden Eval 脚本
用法：
  1. 先启动服务：C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base serve-api --host 127.0.0.1 --port 8000
  2. 在另一个终端运行：C:\Python314\python.exe scripts\run_full_baseline.py
"""
import sys, json, time
sys.path.insert(0, r'src')
from pathlib import Path
from enterprise_agent_kb.generated_tests import run_golden_tests_for_document

workspace = Path(r'knowledge_base')
doc_ids = ['DOC-000003', 'DOC-000004', 'DOC-000005', 'DOC-000009', 'DOC-000012', 'DOC-000013']

all_results = {}
for doc_id in doc_ids:
    print(f"\n{'='*60}", flush=True)
    print(f"[{doc_id}] Running golden eval...", flush=True)
    start = time.time()
    try:
        result = run_golden_tests_for_document(workspace, doc_id)
        elapsed = time.time() - start
        all_results[doc_id] = {
            'success': result.get('success', False),
            'passed': result.get('passed', 0),
            'failed': result.get('failed', 0),
            'total': result.get('total', 0),
            'elapsed': round(elapsed, 1),
            'eval_run_id': result.get('eval_run_id', ''),
        }
        print(f"[{doc_id}] {result.get('passed',0)}/{result.get('total',0)} passed ({elapsed:.0f}s)", flush=True)
    except Exception as e:
        elapsed = time.time() - start
        all_results[doc_id] = {'success': False, 'error': str(e), 'elapsed': round(elapsed, 1)}
        print(f"[{doc_id}] ERROR: {e} ({elapsed:.0f}s)", flush=True)

# Summary report
print(f"\n\n{'='*60}")
print("FULL BASELINE REPORT")
print(f"{'='*60}")
total_passed = 0
total_cases = 0
for doc_id in doc_ids:
    r = all_results.get(doc_id, {})
    p = r.get('passed', 0)
    t = r.get('total', 0)
    total_passed += p
    total_cases += t
    rate = f"{p/t*100:.1f}%" if t > 0 else "N/A"
    err = f" ERROR: {r['error']}" if 'error' in r else ""
    print(f"  {doc_id}: {p}/{t} passed ({rate}){err}")

overall_rate = f"{total_passed/total_cases*100:.1f}%" if total_cases > 0 else "N/A"
print(f"\n  TOTAL: {total_passed}/{total_cases} passed ({overall_rate})")

# Save report
report_path = workspace / "baseline_report.json"
report_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding='utf-8')
print(f"\nReport saved to: {report_path}")
