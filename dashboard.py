#!/usr/bin/env python3
"""
Lightweight dry-run dashboard for the Binance USDT-M bot.

Bind: 127.0.0.1:8765
Start: python dashboard.py

Always forces dry-run (never places live orders). Reuses bot/config,
exchange, strategy, runner. Does not change main.py CLI behaviour.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from bot.config import load_settings
from bot.exchange import ExchangeError
from bot.runner import BotRunner, TickResult

HOST = "127.0.0.1"
PORT = 8765
MAX_TICKS = 40

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("dashboard")

app = FastAPI(title="Binance Futures Bot Dashboard", docs_url=None, redoc_url=None)

_lock = threading.Lock()
_runner: BotRunner | None = None
_last: TickResult | None = None
_ticks: deque[dict[str, Any]] = deque(maxlen=MAX_TICKS)
_error: str | None = None
_started_at = time.time()


def _get_runner() -> BotRunner:
    global _runner
    if _runner is None:
        # Dashboard always dry-run; CLI --live is unrelated.
        settings = load_settings(live=False)
        _runner = BotRunner(settings)
        try:
            _runner.exchange.load_markets()
        except ExchangeError as exc:
            logger.warning("load_markets deferred: %s", exc)
    return _runner


def _run_once_locked() -> dict[str, Any]:
    global _last, _error
    runner = _get_runner()
    try:
        result = runner.run_tick()
        _last = result
        _error = None
        payload = result.to_dict()
        _ticks.appendleft(payload)
        return payload
    except (ExchangeError, ValueError, Exception) as exc:  # noqa: BLE001
        _error = str(exc)
        logger.exception("run_once failed: %s", exc)
        raise


def _status_payload() -> dict[str, Any]:
    runner = _get_runner()
    s = runner.settings
    strategy_name = getattr(runner.strategy, "name", type(runner.strategy).__name__)
    base: dict[str, Any] = {
        "ok": True,
        "host": HOST,
        "port": PORT,
        "started_at": _started_at,
        "mode": runner.exchange.mode_label,
        "testnet": s.testnet,
        "dry_run": not s.live,
        "strategy": strategy_name,
        "symbol": s.symbol,
        "timeframe": s.timeframe,
        "error": _error,
        "last": _last.to_dict() if _last else None,
        "ticks": list(_ticks),
    }
    return base


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Binance U本位 · Dry-Run 面板</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
  <style>
    :root {
      --bg: #0f1419;
      --panel: #1a2332;
      --border: #2a3544;
      --text: #e7ecf3;
      --muted: #8b9bb4;
      --accent: #3b82f6;
      --buy: #22c55e;
      --sell: #ef4444;
      --flat: #94a3b8;
      --warn: #f59e0b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
      background: var(--bg); color: var(--text); min-height: 100vh;
    }
    header {
      display: flex; flex-wrap: wrap; align-items: center; gap: 12px;
      padding: 16px 20px; border-bottom: 1px solid var(--border);
      background: #121820;
    }
    header h1 { margin: 0; font-size: 1.15rem; font-weight: 600; }
    .badge {
      display: inline-block; padding: 3px 10px; border-radius: 999px;
      font-size: 0.75rem; font-weight: 600; letter-spacing: 0.02em;
      background: #243044; color: var(--muted);
    }
    .badge.ok { background: #14532d; color: #86efac; }
    .badge.warn { background: #78350f; color: #fcd34d; }
    .btn {
      margin-left: auto; background: var(--accent); color: #fff; border: 0;
      padding: 8px 16px; border-radius: 8px; font-weight: 600; cursor: pointer;
    }
    .btn:disabled { opacity: 0.5; cursor: wait; }
    .btn:hover:not(:disabled) { filter: brightness(1.08); }
    main {
      display: grid; gap: 16px; padding: 16px 20px 32px;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    }
    .card {
      background: var(--panel); border: 1px solid var(--border);
      border-radius: 12px; padding: 16px;
    }
    .card h2 {
      margin: 0 0 12px; font-size: 0.85rem; color: var(--muted);
      text-transform: uppercase; letter-spacing: 0.06em;
    }
    .price { font-size: 1.8rem; font-weight: 700; font-variant-numeric: tabular-nums; }
    .meta-row { display: flex; justify-content: space-between; margin: 6px 0; font-size: 0.9rem; }
    .meta-row span:first-child { color: var(--muted); }
    .side-buy { color: var(--buy); font-weight: 700; }
    .side-sell { color: var(--sell); font-weight: 700; }
    .side-flat { color: var(--flat); font-weight: 700; }
    .wide { grid-column: 1 / -1; }
    canvas { max-height: 260px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
    th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); }
    th { color: var(--muted); font-weight: 600; }
    .err {
      background: #450a0a; color: #fecaca; border: 1px solid #7f1d1d;
      padding: 10px 14px; border-radius: 8px; margin: 0 20px 0; display: none;
    }
    .hint { color: var(--muted); font-size: 0.8rem; margin-top: 8px; }
    code { background: #0b1016; padding: 1px 6px; border-radius: 4px; }
  </style>
</head>
<body>
  <header>
    <h1>Binance U本位 · Dry-Run 面板</h1>
    <span id="modeBadge" class="badge">…</span>
    <span id="strategyBadge" class="badge">…</span>
    <button class="btn" id="runBtn" onclick="runOnce()">跑一次</button>
  </header>
  <div id="errBox" class="err"></div>
  <main>
    <div class="card">
      <h2>行情</h2>
      <div class="price" id="price">—</div>
      <div class="meta-row"><span>Symbol</span><span id="symbol">—</span></div>
      <div class="meta-row"><span>Timeframe</span><span id="tf">—</span></div>
      <div class="meta-row"><span>更新</span><span id="updated">尚未跑过</span></div>
    </div>
    <div class="card">
      <h2>最近信号</h2>
      <div class="meta-row"><span>Side</span><span id="side">—</span></div>
      <div class="meta-row"><span>Reason</span><span id="reason">—</span></div>
      <div class="meta-row"><span>订单意图</span><span id="intent">—</span></div>
      <div id="indicatorBlock"></div>
      <p class="hint">面板强制 DRY-RUN，不会下真单。CLI 仍用 <code>python main.py</code>。</p>
    </div>
    <div class="card wide">
      <h2>最近收盘价</h2>
      <canvas id="chart"></canvas>
    </div>
    <div class="card wide">
      <h2>最近 Tick 日志</h2>
      <div style="overflow-x:auto">
        <table>
          <thead>
            <tr>
              <th>时间</th><th>Side</th><th>价格</th><th>Reason</th><th>消息</th>
            </tr>
          </thead>
          <tbody id="tickBody"></tbody>
        </table>
      </div>
    </div>
  </main>
  <script>
    let chart;
    function fmtTs(ts) {
      if (!ts) return "—";
      const d = new Date(ts * 1000);
      return d.toLocaleString("zh-CN", { hour12: false });
    }
    function sideClass(side) {
      if (side === "buy") return "side-buy";
      if (side === "sell") return "side-sell";
      return "side-flat";
    }
    function renderIndicators(sig) {
      const el = document.getElementById("indicatorBlock");
      if (!sig || !sig.meta) { el.innerHTML = ""; return; }
      const m = sig.meta;
      let rows = "";
      if (m.fast != null && m.slow != null) {
        rows += `<div class="meta-row"><span>快均线 SMA</span><span>${Number(m.fast).toFixed(4)}</span></div>`;
        rows += `<div class="meta-row"><span>慢均线 SMA</span><span>${Number(m.slow).toFixed(4)}</span></div>`;
      }
      if (m.breakout_high != null && m.breakout_low != null) {
        rows += `<div class="meta-row"><span>突破高</span><span>${Number(m.breakout_high).toFixed(4)}</span></div>`;
        rows += `<div class="meta-row"><span>突破低</span><span>${Number(m.breakout_low).toFixed(4)}</span></div>`;
      }
      el.innerHTML = rows;
    }
    function upsertChart(closes) {
      const labels = (closes || []).map(p => {
        const d = new Date(p.t);
        return d.toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit" });
      });
      const data = (closes || []).map(p => p.c);
      if (!chart) {
        const ctx = document.getElementById("chart").getContext("2d");
        chart = new Chart(ctx, {
          type: "line",
          data: {
            labels,
            datasets: [{
              label: "Close",
              data,
              borderColor: "#3b82f6",
              backgroundColor: "rgba(59,130,246,0.12)",
              fill: true,
              tension: 0.2,
              pointRadius: 0,
              borderWidth: 2,
            }],
          },
          options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
              x: { ticks: { color: "#8b9bb4", maxTicksLimit: 8 }, grid: { color: "#2a3544" } },
              y: { ticks: { color: "#8b9bb4" }, grid: { color: "#2a3544" } },
            },
          },
        });
      } else {
        chart.data.labels = labels;
        chart.data.datasets[0].data = data;
        chart.update("none");
      }
    }
    function applyStatus(st) {
      const err = document.getElementById("errBox");
      if (st.error) {
        err.style.display = "block";
        err.textContent = "错误: " + st.error;
      } else {
        err.style.display = "none";
      }
      const mode = document.getElementById("modeBadge");
      mode.textContent = st.mode || "—";
      mode.className = "badge " + (st.dry_run ? "ok" : "warn");
      document.getElementById("strategyBadge").textContent = (st.strategy || "—") + " · " + (st.timeframe || "");
      document.getElementById("symbol").textContent = st.symbol || "—";
      document.getElementById("tf").textContent = st.timeframe || "—";

      const last = st.last;
      if (last) {
        document.getElementById("price").textContent = Number(last.price).toLocaleString(undefined, { maximumFractionDigits: 4 });
        const side = last.signal?.side || "flat";
        document.getElementById("side").innerHTML = `<span class="${sideClass(side)}">${String(side).toUpperCase()}</span>`;
        document.getElementById("reason").textContent = last.signal?.reason || "—";
        document.getElementById("intent").textContent = last.intent_summary || last.message || "—";
        document.getElementById("updated").textContent = fmtTs(last.ts);
        renderIndicators(last.signal);
        upsertChart(last.closes || []);
      }

      const tbody = document.getElementById("tickBody");
      tbody.innerHTML = "";
      (st.ticks || []).forEach(t => {
        const tr = document.createElement("tr");
        const side = t.signal?.side || "";
        tr.innerHTML = `
          <td>${fmtTs(t.ts)}</td>
          <td class="${sideClass(side)}">${String(side).toUpperCase()}</td>
          <td>${Number(t.price).toFixed(4)}</td>
          <td>${t.signal?.reason || ""}</td>
          <td>${t.message || t.intent_summary || ""}</td>`;
        tbody.appendChild(tr);
      });
      if (!(st.ticks || []).length) {
        tbody.innerHTML = `<tr><td colspan="5" style="color:#8b9bb4">还没有 tick。点右上角「跑一次」。</td></tr>`;
      }
    }
    async function refresh() {
      const res = await fetch("/api/status");
      const st = await res.json();
      applyStatus(st);
    }
    async function runOnce() {
      const btn = document.getElementById("runBtn");
      btn.disabled = true;
      btn.textContent = "运行中…";
      try {
        const res = await fetch("/api/run-once", { method: "POST" });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || data.error || res.statusText);
        await refresh();
      } catch (e) {
        const err = document.getElementById("errBox");
        err.style.display = "block";
        err.textContent = "跑一次失败: " + e.message;
        await refresh();
      } finally {
        btn.disabled = false;
        btn.textContent = "跑一次";
      }
    }
    refresh();
    setInterval(refresh, 8000);
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)


@app.get("/api/status")
def api_status() -> dict[str, Any]:
    with _lock:
        return _status_payload()


@app.post("/api/run-once")
def api_run_once() -> dict[str, Any]:
    with _lock:
        try:
            tick = _run_once_locked()
            return {"ok": True, "tick": tick, "status": _status_payload()}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc


def main() -> None:
    logger.info("dashboard listening on http://%s:%s (always DRY-RUN)", HOST, PORT)
    # Preload settings so /api/status works before first click.
    with _lock:
        _get_runner()
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
