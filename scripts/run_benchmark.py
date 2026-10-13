"""Phase 4 entry point: python scripts/run_benchmark.py  [--quick]  -> results.json, docs/error_cdf.png, summary table."""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import bench


def main():
    quick = '--quick' in sys.argv
    res = bench.run_benchmark(max_steps=200 if quick else None, run_filter=(lambda rid, m: rid.endswith('1') ) if quick else None,
                              progress=lambda f: print(f'\rprogress {f * 100:5.1f}%', end='', flush=True))
    print()
    out = ROOT / ('results_quick.json' if quick else 'results.json')
    out.write_text(json.dumps(res, indent=1))
    (ROOT / 'docs').mkdir(exist_ok=True)
    bench.plot_cdf(res, ROOT / 'docs' / ('error_cdf_quick.png' if quick else 'error_cdf.png'))
    txt = bench.summary_table(res)
    print(txt)
    print(f'\nwrote {out.name}, docs/error_cdf.png  ({res["seconds"]} s, {res["dataset"]["runs"]} runs)')
    (ROOT / 'docs' / 'benchmark_summary.txt').write_text(txt + '\n')


if __name__ == '__main__':
    main()
