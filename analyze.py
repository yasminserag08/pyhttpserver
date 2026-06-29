#!/usr/bin/env python3
"""
analyze.py — parse multiple wrk benchmark runs, aggregate with medians,
and produce a self-contained HTML dashboard.

Usage:
    python3 analyze.py [--runs-dir ./benchmark_runs] [--out report.html]
"""

import argparse
import glob
import json
import os
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

SERVER_HEADER_RE = re.compile(r"^\s{2}(BLOCKING|THREADED|EVENTLOOP_V1|EVENTLOOP_V2)\s+\(port \d+\)")
ROUTE_RE         = re.compile(r"^\s+Route:\s+(\S+)")
CONCURRENCY_RE   = re.compile(r"\[-t\d+\s+-c(\d+)\s+-d\S+\]")
RPS_RE           = re.compile(r"Requests/sec:\s+([\d.]+)")
LATENCY_AVG_RE   = re.compile(r"^\s+Latency\s+([\d.]+\w+)\s+([\d.]+\w+)\s+([\d.]+\w+)")
PERCENTILE_RE    = re.compile(r"^\s+p([\d.]+)\s+([\d.]+)ms")
LUA_MAX_RE       = re.compile(r"^\s+max\s+([\d.]+)ms")

UNIT_MS = {"us": 0.001, "ms": 1.0, "s": 1000.0, "m": 60000.0}


def to_ms(value: float, unit: str) -> float:
    return value * UNIT_MS.get(unit, 1.0)


def _parse_duration(s: str) -> float:
    m = re.match(r"([\d.]+)(\S+)", s)
    if not m:
        return 0.0
    return to_ms(float(m.group(1)), m.group(2))


def parse_file(path: str) -> dict:
    data = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    current_server = current_route = current_c = None
    buf = {}

    def flush():
        if current_server and current_route and current_c is not None and buf:
            data[current_server][current_route][current_c] = dict(buf)

    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = SERVER_HEADER_RE.search(line)
            if m:
                flush(); buf = {}
                current_server = m.group(1)
                current_route = current_c = None
                continue

            m = ROUTE_RE.search(line)
            if m:
                flush(); buf = {}
                current_route = m.group(1)
                current_c = None
                continue

            m = CONCURRENCY_RE.search(line)
            if m:
                flush(); buf = {}
                current_c = int(m.group(1))
                continue

            if current_server is None or current_route is None or current_c is None:
                continue

            m = RPS_RE.search(line)
            if m:
                buf["rps"] = float(m.group(1)); continue

            m = LATENCY_AVG_RE.match(line)
            if m:
                buf["lat_avg"]   = _parse_duration(m.group(1))
                buf["lat_stdev"] = _parse_duration(m.group(2))
                buf["lat_max"]   = _parse_duration(m.group(3))
                continue

            m = PERCENTILE_RE.match(line)
            if m:
                pct = float(m.group(1))
                buf[f"p{pct:g}"] = float(m.group(2))
                continue

            m = LUA_MAX_RE.match(line)
            if m:
                buf["lat_max_lua"] = float(m.group(1)); continue

    flush()
    return data


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_runs(run_data_list: list) -> dict:
    raw = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))
    for run in run_data_list:
        for server, routes in run.items():
            for route, concurrencies in routes.items():
                for c, metrics in concurrencies.items():
                    for k, v in metrics.items():
                        raw[server][route][c][k].append(v)

    agg = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for server, routes in raw.items():
        for route, concurrencies in routes.items():
            for c, metrics in concurrencies.items():
                for k, vals in metrics.items():
                    agg[server][route][c][k] = statistics.median(vals)
    return agg


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

COLORS = {
    "BLOCKING":     "#e05252",
    "THREADED":     "#f0a030",
    "EVENTLOOP_V1": "#4a9eda",
    "EVENTLOOP_V2": "#52b788",
}

SERVER_LABELS = {
    "BLOCKING":     "Blocking",
    "THREADED":     "Threaded",
    "EVENTLOOP_V1": "Event Loop v1",
    "EVENTLOOP_V2": "Event Loop v2 (pool)",
}

# Solid lines, distinct point shapes per server
SERVER_STYLE = {
    "BLOCKING":     {"pointStyle": "circle",   "pointRadius": 5},
    "THREADED":     {"pointStyle": "triangle", "pointRadius": 6},
    "EVENTLOOP_V1": {"pointStyle": "rect",     "pointRadius": 5},
    "EVENTLOOP_V2": {"pointStyle": "star",     "pointRadius": 7},
}


def build_chart_data(agg, route, metric, servers, concurrency_levels):
    datasets = []
    for srv in servers:
        values = [
            round(v, 3) if (v := agg.get(srv, {}).get(route, {}).get(c, {}).get(metric)) is not None else None
            for c in concurrency_levels
        ]
        style = SERVER_STYLE.get(srv, {})
        datasets.append({
            "label":            SERVER_LABELS.get(srv, srv),
            "data":             values,
            "borderColor":      COLORS.get(srv, "#888"),
            "backgroundColor":  COLORS.get(srv, "#888") + "33",
            "tension":          0.3,
            "borderWidth":      2,
            "borderDash":       [],
            "pointStyle":       style.get("pointStyle", "circle"),
            "pointRadius":      style.get("pointRadius", 5),
            "pointHoverRadius": style.get("pointRadius", 5) + 2,
        })
    return {
        "labels":   [str(c) for c in concurrency_levels],
        "datasets": datasets,
    }


def safe_id(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", s)


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def generate_html(agg: dict, run_count: int, runs_dir: str) -> str:
    servers            = [s for s in SERVER_LABELS if s in agg]
    routes             = sorted({r for s in agg.values() for r in s})
    concurrency_levels = sorted({c for s in agg.values() for r in s.values() for c in r})
    percentile_keys    = ["p50", "p99", "p99.9"]

    # Chart groups keyed by safe route id
    route_groups = {}
    for route in routes:
        route_label = route if route != "/" else "/ (fast route)"
        rid    = safe_id(route_label)
        charts = [{
            "title":  f"Requests / sec  —  {route_label}",
            "ylabel": "req/s  (higher is better)",
            "data":   build_chart_data(agg, route, "rps", servers, concurrency_levels),
        }]
        for pct in percentile_keys:
            charts.append({
                "title":  f"{pct} Latency  —  {route_label}",
                "ylabel": "latency (ms)  (lower is better)",
                "data":   build_chart_data(agg, route, pct, servers, concurrency_levels),
            })
        route_groups[rid] = {"label": route_label, "charts": charts}

    # Summary data: all metrics, grouped by route then concurrency
    summary_metrics = [
        ("rps",   "Throughput (req/s)", "higher"),
        ("p50",   "p50 (ms)",           "lower"),
        ("p90",   "p90 (ms)",           "lower"),
        ("p99",   "p99 (ms)",           "lower"),
        ("p99.9", "p99.9 (ms)",         "lower"),
    ]
    summary = {}
    for route in routes:
        rid = safe_id(route if route != "/" else "/ (fast route)")
        label = route if route != "/" else "/ (fast route)"
        rows = []
        for c in concurrency_levels:
            row = {"c": c}
            for srv in servers:
                m = agg.get(srv, {}).get(route, {}).get(c, {})
                row[srv] = {k: m.get(k) for k, *_ in summary_metrics}
            rows.append(row)
        summary[rid] = {"label": label, "rows": rows}

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Server Benchmark Report</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root {{
    --bg:        #0f1117;
    --surface:   #181c27;
    --surface2:  #1f2435;
    --border:    #2a3050;
    --text:      #e2e8f0;
    --muted:     #7a85a0;
    --accent:    #4a9eda;
    --green:     #52b788;
    --font-mono: "JetBrains Mono","Fira Mono","Cascadia Code",monospace;
    --font-sans: "Inter",system-ui,sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--font-sans); font-size: 14px; line-height: 1.6; }}

  /* header */
  header {{ padding: 36px 48px 28px; border-bottom: 1px solid var(--border); }}
  header h1 {{ font-size: 20px; font-weight: 600; letter-spacing: -0.02em; margin-bottom: 4px; }}
  header p  {{ color: var(--muted); font-size: 13px; }}
  .legend {{ display: flex; gap: 20px; flex-wrap: wrap; margin-top: 14px; }}
  .legend-item {{ display: flex; align-items: center; gap: 8px; font-size: 13px; }}
  .legend-dot  {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}

  /* nav */
  nav {{
    display: flex; gap: 8px; padding: 14px 48px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
    position: sticky; top: 0; z-index: 10; overflow-x: auto;
  }}
  nav button {{
    background: none; border: 1px solid var(--border); color: var(--muted);
    padding: 5px 14px; border-radius: 6px; cursor: pointer; font-size: 12px;
    white-space: nowrap; transition: all 0.15s;
  }}
  nav button.active, nav button:hover {{
    border-color: var(--accent); color: var(--accent); background: #4a9eda14;
  }}

  /* main */
  main {{ padding: 32px 48px 64px; max-width: 1400px; }}
  .section {{ display: none; }}
  .section.active {{ display: block; }}
  .section-title {{
    font-size: 12px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--muted);
    margin-bottom: 24px; padding-bottom: 10px; border-bottom: 1px solid var(--border);
  }}

  /* summary */
  .summary-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(520px, 1fr));
    gap: 40px;
  }}
  .route-block h4 {{
    font-size: 13px; font-weight: 600; color: var(--text);
    margin-bottom: 16px;
  }}
  .metric-group {{ margin-bottom: 20px; }}
  .metric-group-label {{
    font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.07em; color: var(--muted); margin-bottom: 6px;
  }}
  .table-wrap {{ border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{
    background: var(--surface2); color: var(--muted);
    font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
    padding: 7px 12px; text-align: right; border-bottom: 1px solid var(--border); white-space: nowrap;
  }}
  th:first-child {{ text-align: left; min-width: 160px; }}
  td {{
    padding: 7px 12px; border-bottom: 1px solid var(--border);
    font-family: var(--font-mono); font-size: 12px; color: var(--muted);
    text-align: right; white-space: nowrap;
  }}
  td:first-child {{ text-align: left; color: var(--text); font-weight: 500; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: var(--surface2); }}
  td.winner {{ color: var(--green); font-weight: 700; }}
  .server-dot {{
    display: inline-block; width: 8px; height: 8px;
    border-radius: 50%; margin-right: 7px; vertical-align: middle; flex-shrink: 0;
  }}

  /* charts */
  .chart-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(560px, 1fr));
    gap: 24px;
  }}
  .chart-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 20px 24px;
  }}
  .chart-card h3 {{ font-size: 13px; font-weight: 500; color: var(--muted); margin-bottom: 14px; }}
  .chart-card h3 strong {{ color: var(--text); display: block; font-size: 14px; margin-bottom: 2px; }}
  .chart-wrap {{ position: relative; height: 240px; }}
</style>
</head>
<body>

<header>
  <h1>Python Web Server — Benchmark Report</h1>
  <p>Median across <strong>{run_count}</strong> runs &nbsp;·&nbsp; {datetime.now().strftime("%Y-%m-%d %H:%M")} &nbsp;·&nbsp; <code>{runs_dir}</code></p>
  <div class="legend" id="legend"></div>
</header>

<nav id="nav"></nav>
<main><div id="sections"></div></main>

<script>
const ROUTE_GROUPS = {json.dumps(route_groups, indent=2)};
const SUMMARY      = {json.dumps(summary, indent=2)};
const SERVERS      = {json.dumps(servers)};
const LABELS       = {json.dumps(SERVER_LABELS)};
const COLORS       = {json.dumps(COLORS)};
const METRICS      = {json.dumps(summary_metrics)};

// Legend
const legendEl = document.getElementById('legend');
SERVERS.forEach(srv => {{
  const item = document.createElement('div');
  item.className = 'legend-item';
  item.innerHTML = `<div class="legend-dot" style="background:${{COLORS[srv]}}"></div><span>${{LABELS[srv]}}</span>`;
  legendEl.appendChild(item);
}});

const nav      = document.getElementById('nav');
const sections = document.getElementById('sections');

function activateTab(id) {{
  nav.querySelectorAll('button').forEach(b => b.classList.toggle('active', b.dataset.tab === id));
  sections.querySelectorAll('.section').forEach(s => s.classList.toggle('active', s.id === 'section-' + id));
}}

function makeBtn(label, id, active) {{
  const btn = document.createElement('button');
  btn.textContent  = label;
  btn.dataset.tab  = id;
  if (active) btn.classList.add('active');
  btn.addEventListener('click', () => activateTab(id));
  nav.appendChild(btn);
}}

function makeSection(id, active) {{
  const sec = document.createElement('div');
  sec.className = 'section' + (active ? ' active' : '');
  sec.id = 'section-' + id;
  sections.appendChild(sec);
  return sec;
}}

// ── Summary ──────────────────────────────────────────────────────────────────
makeBtn('Summary', 'summary', true);
const sumSec = makeSection('summary', true);

const sumTitle = document.createElement('div');
sumTitle.className = 'section-title';
sumTitle.textContent = 'Head-to-head summary — median across all runs';
sumSec.appendChild(sumTitle);

const sumGrid = document.createElement('div');
sumGrid.className = 'summary-grid';

Object.entries(SUMMARY).forEach(([rid, {{ label, rows }}]) => {{
  const block = document.createElement('div');
  block.className = 'route-block';

  const h4 = document.createElement('h4');
  h4.textContent = 'Route: ' + label;
  block.appendChild(h4);

  const concurrencies = rows.map(r => r.c);

  METRICS.forEach(([metric, metricLabel, direction]) => {{
    const group = document.createElement('div');
    group.className = 'metric-group';

    const ml = document.createElement('div');
    ml.className = 'metric-group-label';
    ml.textContent = metricLabel;
    group.appendChild(ml);

    const wrap  = document.createElement('div');
    wrap.className = 'table-wrap';
    const table = document.createElement('table');

    // thead: Server | c10 | c25 | ...
    const thead = document.createElement('thead');
    const hrow  = document.createElement('tr');
    const thS   = document.createElement('th'); thS.textContent = 'Server'; hrow.appendChild(thS);
    concurrencies.forEach(c => {{
      const th = document.createElement('th'); th.textContent = 'c' + c; hrow.appendChild(th);
    }});
    thead.appendChild(hrow); table.appendChild(thead);

    // best value per concurrency column
    const bestPerC = concurrencies.map(c => {{
      const row = rows.find(r => r.c === c);
      const vals = SERVERS.map(s => row?.[s]?.[metric] ?? null).filter(v => v !== null);
      if (!vals.length) return null;
      return direction === 'higher' ? Math.max(...vals) : Math.min(...vals);
    }});

    const tbody = document.createElement('tbody');
    SERVERS.forEach(srv => {{
      const tr = document.createElement('tr');
      const nameTd = document.createElement('td');
      nameTd.innerHTML = `<span class="server-dot" style="background:${{COLORS[srv]}}"></span>${{LABELS[srv]}}`;
      tr.appendChild(nameTd);

      concurrencies.forEach((c, ci) => {{
        const row = rows.find(r => r.c === c);
        const val = row?.[srv]?.[metric] ?? null;
        const td  = document.createElement('td');
        if (val == null) {{
          td.textContent = '—';
        }} else {{
          td.textContent = metric === 'rps' ? val.toFixed(0) : val.toFixed(2);
          if (val === bestPerC[ci]) td.classList.add('winner');
        }}
        tr.appendChild(td);
      }});
      tbody.appendChild(tr);
    }});

    table.appendChild(tbody);
    wrap.appendChild(table);
    group.appendChild(wrap);
    block.appendChild(group);
  }});

  sumGrid.appendChild(block);
}});
sumSec.appendChild(sumGrid);

// ── Chart tabs ───────────────────────────────────────────────────────────────
Object.entries(ROUTE_GROUPS).forEach(([rid, {{ label, charts }}]) => {{
  makeBtn(label, rid, false);
  const sec = makeSection(rid, false);

  const title = document.createElement('div');
  title.className = 'section-title';
  title.textContent = 'Route: ' + label;
  sec.appendChild(title);

  const grid = document.createElement('div');
  grid.className = 'chart-grid';

  charts.forEach(def => {{
    const card   = document.createElement('div');
    card.className = 'chart-card';

    const h3     = document.createElement('h3');
    const parts  = def.title.split('—');
    h3.innerHTML = `<strong>${{parts[0].trim()}}</strong>${{parts[1] ? '— ' + parts[1].trim() : ''}}`;
    card.appendChild(h3);

    const wrap   = document.createElement('div');
    wrap.className = 'chart-wrap';
    const canvas = document.createElement('canvas');
    wrap.appendChild(canvas);
    card.appendChild(wrap);
    grid.appendChild(card);

    new Chart(canvas, {{
      type: 'line',
      data: def.data,
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{
          legend: {{
            labels: {{
              color: '#7a85a0', font: {{ size: 11 }},
              usePointStyle: true, pointStyleWidth: 14, padding: 16,
            }}
          }},
          tooltip: {{
            backgroundColor: '#1f2435', borderColor: '#2a3050', borderWidth: 1,
            titleColor: '#e2e8f0', bodyColor: '#7a85a0',
          }},
        }},
        scales: {{
          x: {{
            title: {{ display: true, text: 'Concurrency (connections)', color: '#7a85a0', font: {{ size: 11 }} }},
            grid:  {{ color: '#2a305060' }},
            ticks: {{ color: '#7a85a0' }},
          }},
          y: {{
            title: {{ display: true, text: def.ylabel, color: '#7a85a0', font: {{ size: 11 }} }},
            grid:  {{ color: '#2a305060' }},
            ticks: {{ color: '#7a85a0' }},
            beginAtZero: false,
          }},
        }},
      }},
    }});
  }});

  sec.appendChild(grid);
}});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", default="./benchmark_runs")
    parser.add_argument("--single",   default=None)
    parser.add_argument("--out",      default="report.html")
    args = parser.parse_args()

    if args.single:
        files = [args.single]
    else:
        pattern = os.path.join(args.runs_dir, "results_run*.txt")
        files   = sorted(glob.glob(pattern))
        if not files:
            if os.path.exists("results.txt"):
                print("No run files found; falling back to results.txt")
                files = ["results.txt"]
            else:
                print(f"ERROR: No result files found in {args.runs_dir}/")
                sys.exit(1)

    print(f"Parsing {len(files)} file(s)...")
    run_data_list = [parse_file(f) for f in files if print(f"  {f}") or True]

    agg  = aggregate_runs(run_data_list) if len(run_data_list) > 1 else run_data_list[0]
    html = generate_html(agg, len(files), args.runs_dir)

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"\nReport written to: {args.out}")
    servers_found = list(agg.keys())
    routes_found  = sorted({r for s in agg.values() for r in s})
    print(f"Servers: {servers_found}")
    print(f"Routes:  {routes_found}")
    for srv in servers_found:
        for route in routes_found:
            c0 = next(iter(agg[srv][route]), None)
            if c0:
                print(f"  [{srv}][{route}][c={c0}] keys: {list(agg[srv][route][c0].keys())}")


if __name__ == "__main__":
    main()