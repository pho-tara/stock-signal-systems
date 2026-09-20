# -*- coding: utf-8 -*-
"""
ウォッチリスト・保有銘柄・買い時ランキングの状況を表示する
静的HTMLダッシュボードを生成する。
GitHub Pages (docs/index.html) での公開を想定。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

BADGE_STYLE = {
    "BUY": ("#0f9d58", "買いシグナル"),
    "SELL": ("#d93025", "売りシグナル"),
    "NONE": ("#9aa0a6", "様子見"),
}


def _fmt(v, digits=1):
    if v is None:
        return "—"
    return f"{v:,.{digits}f}"


def _badge_html(r: dict) -> str:
    color, label = BADGE_STYLE[r["direction"]]
    strong = "（強）" if r["score"] >= 2 else ""
    return (
        f'<span class="badge" style="background:{color}22;color:{color};border:1px solid {color}55;">'
        f"{label}{strong}</span>"
    )


def _row_html(item: dict, rank: int | None = None) -> str:
    r = item["result"]
    latest = r["latest"]
    reasons = "・".join(r["reasons"]) if r["reasons"] else "特筆すべき根拠なし"
    rank_cell = f'<td class="num rank">{rank}</td>' if rank is not None else ""
    return f"""
    <tr>
      {rank_cell}
      <td class="name-cell">
        <div class="name">{item['name']}</div>
        <div class="code">{item['code']}</div>
      </td>
      <td class="num">{_fmt(latest['close'], 1)}</td>
      <td class="num">{_fmt(latest['sma5'], 1)}</td>
      <td class="num">{_fmt(latest['sma25'], 1)}</td>
      <td class="num">{_fmt(latest['rsi14'], 1)}</td>
      <td>{_badge_html(r)}</td>
      <td class="reasons">{reasons}</td>
    </tr>
    """


def _table_html(items: list, with_rank: bool = False) -> str:
    rows = "\n".join(
        _row_html(item, rank=(i + 1) if with_rank else None) for i, item in enumerate(items)
    )
    rank_th = "<th>順位</th>" if with_rank else ""
    return f"""
    <table>
      <thead>
        <tr>
          {rank_th}<th>銘柄</th><th>終値</th><th>SMA5</th><th>SMA25</th><th>RSI14</th><th>判定</th><th>根拠</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
    """


def _empty_state(message: str) -> str:
    return f'<div class="empty">{message}</div>'


def build_dashboard_html(results: list, holdings: list | None = None, ranking: list | None = None,
                          ranking_price_ceiling: float | None = None) -> str:
    """
    results: ウォッチリストの [{"code", "name", "result"}, ...]
    holdings: 保有銘柄の [{"code", "name", "result"}, ...] (Noneまたは空リストなら非表示)
    ranking: 買い時ランキングの [{"code", "name", "result"}, ...] (Noneまたは空リストなら非表示)
    ranking_price_ceiling: ランキングの価格上限(表示用)
    """
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    buy_count = sum(1 for i in results if i["result"]["direction"] == "BUY")
    sell_count = sum(1 for i in results if i["result"]["direction"] == "SELL")

    watchlist_section = f"""
    <h2>ウォッチリスト</h2>
    <div class="summary">
      <div class="stat"><div class="num">{len(results)}</div><div class="label">監視銘柄数</div></div>
      <div class="stat"><div class="num" style="color:#0f9d58">{buy_count}</div><div class="label">買いシグナル</div></div>
      <div class="stat"><div class="num" style="color:#d93025">{sell_count}</div><div class="label">売りシグナル</div></div>
    </div>
    {_table_html(results) if results else _empty_state("表示できるデータがありません。")}
    """

    holdings_section = ""
    if holdings:
        holdings_section = f"""
        <h2>保有銘柄</h2>
        {_table_html(holdings)}
        """

    ranking_section = ""
    if ranking is not None:
        ceiling_label = f"{ranking_price_ceiling:,.0f}円以下" if ranking_price_ceiling else ""
        ranking_section = f"""
        <h2>買い時ランキング（日経225・{ceiling_label}）</h2>
        {_table_html(ranking, with_rank=True) if ranking else _empty_state("条件に合う銘柄がありませんでした。")}
        """

    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>日本株テクニカルシグナル ダッシュボード</title>
<style>
  :root {{
    --bg: #ffffff; --fg: #1a1a1a; --muted: #6b7280; --border: #e5e7eb; --card: #f9fafb;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #0f1115; --fg: #e8eaed; --muted: #9aa0a6; --border: #2a2d34; --card: #171a21; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 24px 16px 64px; background: var(--bg); color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Sans", "Noto Sans JP", sans-serif;
  }}
  .wrap {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 4px; }}
  h2 {{ font-size: 1.05rem; margin: 32px 0 12px; }}
  h2:first-of-type {{ margin-top: 20px; }}
  .updated {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 8px; }}
  .summary {{ display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }}
  .stat {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 12px 16px; min-width: 120px;
  }}
  .stat .num {{ font-size: 1.5rem; font-weight: 600; }}
  .stat .label {{ color: var(--muted); font-size: 0.8rem; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--card); border-radius: 10px; overflow: hidden; }}
  th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 0.85rem; text-align: left; }}
  th {{ color: var(--muted); font-weight: 500; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.02em; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.rank {{ font-weight: 700; color: var(--muted); }}
  .name-cell .name {{ font-weight: 600; }}
  .name-cell .code {{ color: var(--muted); font-size: 0.75rem; }}
  .badge {{ display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 0.78rem; white-space: nowrap; }}
  .reasons {{ color: var(--muted); font-size: 0.78rem; }}
  .empty {{ color: var(--muted); font-size: 0.85rem; padding: 16px; background: var(--card); border-radius: 10px; }}
  .disclaimer {{ margin-top: 24px; color: var(--muted); font-size: 0.75rem; line-height: 1.6; }}
  @media (max-width: 640px) {{
    table, thead, tbody, th, td, tr {{ display: block; }}
    thead {{ display: none; }}
    tr {{ border-bottom: 1px solid var(--border); padding: 10px 0; }}
    td {{ border: none; padding: 3px 0; display: flex; justify-content: space-between; gap: 8px; }}
    td.num::before {{ content: attr(data-label); color: var(--muted); }}
    .name-cell {{ display: block; }}
  }}
</style>
</head>
<body>
  <div class="wrap">
    <h1>日本株テクニカルシグナル ダッシュボード</h1>
    <div class="updated">最終更新: {now}</div>

    {watchlist_section}
    {holdings_section}
    {ranking_section}

    <div class="disclaimer">
      本ダッシュボードはSMA/RSI/MACDなど一般的なテクニカル指標に基づく機械的な参考情報であり、
      投資助言ではありません。将来の値動きを保証するものではなく、投資判断はご自身の責任で行ってください。
    </div>
  </div>
</body>
</html>
"""
