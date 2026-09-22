# -*- coding: utf-8 -*-
"""
ウォッチリスト・保有銘柄・買い時ランキングの状況を表示する
静的HTMLダッシュボードを生成する。
GitHub Pages (docs/index.html) での公開を想定。
"""
import html
from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

BADGE_STYLE = {
    "BUY": ("#0f9d58", "買いシグナル"),
    "SELL": ("#d93025", "売りシグナル"),
    "NONE": ("#9aa0a6", "様子見"),
}

NEWS_BADGE_STYLE = {
    "POSITIVE": ("#0f9d58", "ポジティブ"),
    "NEGATIVE": ("#d93025", "ネガティブ"),
    "NEUTRAL": ("#9aa0a6", "中立"),
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


def _news_badge_html(news: dict | None) -> str:
    """ニュースのポジティブ/ネガティブ判定バッジ(キーワードベース、または任意でAI判定・参考情報)。"""
    if not news:
        return '<span class="muted">—</span>'
    sentiment = news.get("sentiment", "NEUTRAL")
    color, label = NEWS_BADGE_STYLE.get(sentiment, NEWS_BADGE_STYLE["NEUTRAL"])
    method_tag = '<span class="method-tag">AI</span>' if news.get("method") == "AI" else ""
    badge = (
        f'<span class="badge" style="background:{color}22;color:{color};border:1px solid {color}55;">'
        f"{label}</span>{method_tag}"
    )
    headline = news.get("sample_headline")
    if not headline:
        return badge
    short = headline if len(headline) <= 38 else headline[:37] + "…"
    return (
        f"{badge}"
        f'<div class="news-headline" title="{html.escape(headline)}">{html.escape(short)}</div>'
    )


def _cautions_html(r: dict) -> str:
    """長期トレンド(SMA75)に逆行するシグナルの注意書き(参考情報、scoreには影響しない)。"""
    cautions = r.get("cautions") or []
    if not cautions:
        return ""
    text = "・".join(cautions)
    return f'<div class="caution">⚠ {html.escape(text)}</div>'


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
      <td class="reasons">{reasons}{_cautions_html(r)}</td>
      <td class="news-cell">{_news_badge_html(item.get('news'))}</td>
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
          {rank_th}<th>銘柄</th><th>終値</th><th>SMA5</th><th>SMA25</th><th>RSI14</th><th>判定</th><th>根拠</th><th>ニュース</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
    """


def _empty_state(message: str) -> str:
    return f'<div class="empty">{message}</div>'


def _registration_section_html(github_repo: str | None) -> str:
    """
    ダッシュボード上から、GitHub Issueフォーム(登録画面)を
    入力内容を自動入力した状態で開けるようにするセクション。
    実際のファイル書き換えはこれまで通りGitHub Actions側のIssue処理が行う。
    """
    if not github_repo:
        return ""

    return f"""
    <h2>銘柄・設定の登録</h2>
    <p class="reg-desc">
      入力して「GitHubで登録する」を押すと、内容が自動入力された状態でGitHubの登録画面が新しいタブで開きます。
      内容を確認して「Submit new issue」を押すと、数十秒後に自動で反映されます。
    </p>
    <div class="reg-grid">
      <div class="reg-card">
        <h3>保有銘柄を追加</h3>
        <input type="text" id="reg-add-holding-code" placeholder="証券コード（例: 7203）">
        <input type="text" id="reg-add-holding-name" placeholder="銘柄名（例: トヨタ自動車）">
        <button onclick="regOpen('add-holding.yml', {{
          code: document.getElementById('reg-add-holding-code').value,
          name: document.getElementById('reg-add-holding-name').value
        }})">GitHubで登録する</button>
      </div>
      <div class="reg-card">
        <h3>保有銘柄を削除</h3>
        <input type="text" id="reg-remove-holding-code" placeholder="証券コード（例: 7203）">
        <button onclick="regOpen('remove-holding.yml', {{
          code: document.getElementById('reg-remove-holding-code').value
        }})">GitHubで登録する</button>
      </div>
      <div class="reg-card">
        <h3>監視銘柄を追加</h3>
        <input type="text" id="reg-add-watchlist-code" placeholder="証券コード（例: 7203）">
        <input type="text" id="reg-add-watchlist-name" placeholder="銘柄名（例: トヨタ自動車）">
        <button onclick="regOpen('add-watchlist.yml', {{
          code: document.getElementById('reg-add-watchlist-code').value,
          name: document.getElementById('reg-add-watchlist-name').value
        }})">GitHubで登録する</button>
      </div>
      <div class="reg-card">
        <h3>監視銘柄を削除</h3>
        <input type="text" id="reg-remove-watchlist-code" placeholder="証券コード（例: 7203）">
        <button onclick="regOpen('remove-watchlist.yml', {{
          code: document.getElementById('reg-remove-watchlist-code').value
        }})">GitHubで登録する</button>
      </div>
      <div class="reg-card">
        <h3>買い時ランキングの価格上限を変更</h3>
        <input type="text" id="reg-price-ceiling" placeholder="価格上限（円）例: 1500">
        <button onclick="regOpen('set-price-ceiling.yml', {{
          price: document.getElementById('reg-price-ceiling').value
        }})">GitHubで登録する</button>
      </div>
    </div>
    <script>
      function regOpen(template, fields) {{
        var repo = {github_repo!r};
        if (!repo) {{
          alert('GitHubリポジトリ情報が取得できませんでした。Issuesタブから直接登録してください。');
          return;
        }}
        var url = 'https://github.com/' + repo + '/issues/new?template=' + encodeURIComponent(template);
        for (var key in fields) {{
          var val = (fields[key] || '').trim();
          if (!val) continue;
          url += '&' + encodeURIComponent(key) + '=' + encodeURIComponent(val);
        }}
        window.open(url, '_blank');
      }}
    </script>
    """


def build_dashboard_html(results: list, holdings: list | None = None, ranking: list | None = None,
                          ranking_price_ceiling: float | None = None, github_repo: str | None = None) -> str:
    """
    results: ウォッチリストの [{"code", "name", "result"}, ...]
    holdings: 保有銘柄の [{"code", "name", "result"}, ...] (Noneまたは空リストなら非表示)
    ranking: 買い時ランキングの [{"code", "name", "result"}, ...] (Noneまたは空リストなら非表示)
    ranking_price_ceiling: ランキングの価格上限(表示用)
    github_repo: "owner/repo" 形式のGitHubリポジトリ名(ダッシュボードからの登録フォーム用。Noneなら非表示)
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

    registration_section = _registration_section_html(github_repo)

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
  .caution {{ color: #b45309; font-size: 0.72rem; margin-top: 4px; line-height: 1.4; }}
  @media (prefers-color-scheme: dark) {{ .caution {{ color: #fbbf24; }} }}
  .news-cell {{ min-width: 140px; }}
  .news-headline {{ color: var(--muted); font-size: 0.72rem; margin-top: 4px; line-height: 1.4; }}
  .muted {{ color: var(--muted); }}
  .method-tag {{
    display: inline-block; margin-left: 4px; padding: 1px 5px; border-radius: 4px;
    font-size: 0.6rem; font-weight: 700; vertical-align: middle;
    background: #1a73e822; color: #1a73e8; border: 1px solid #1a73e855;
  }}
  .empty {{ color: var(--muted); font-size: 0.85rem; padding: 16px; background: var(--card); border-radius: 10px; }}
  .disclaimer {{ margin-top: 24px; color: var(--muted); font-size: 0.75rem; line-height: 1.6; }}
  .reg-desc {{ color: var(--muted); font-size: 0.82rem; line-height: 1.6; margin: 0 0 16px; }}
  .reg-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
  .reg-card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 14px 16px; display: flex; flex-direction: column; gap: 8px;
  }}
  .reg-card h3 {{ font-size: 0.85rem; margin: 0 0 2px; font-weight: 600; }}
  .reg-card input {{
    width: 100%; padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px;
    background: var(--bg); color: var(--fg); font-size: 0.85rem;
  }}
  .reg-card button {{
    padding: 8px 12px; border: none; border-radius: 6px; background: #1a73e8; color: #fff;
    font-size: 0.85rem; font-weight: 600; cursor: pointer;
  }}
  .reg-card button:hover {{ background: #1558b0; }}
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
    {registration_section}

    <div class="disclaimer">
      本ダッシュボードはSMA/RSI/MACDなど一般的なテクニカル指標に基づく機械的な参考情報であり、
      投資助言ではありません。将来の値動きを保証するものではなく、投資判断はご自身の責任で行ってください。<br>
      「⚠」の注意書きは、長期トレンド(SMA75)と逆方向のシグナルである場合に表示される参考情報です
      (シグナルの強さ自体には影響しませんが、LINE通知の要否判定には使われます)。<br>
      LINE通知は、根拠が2つ以上そろった場合のみ送信されます(長期トレンドに逆行する注意がある場合は3つ以上)。
      ダッシュボードにはそれ未満のシグナルも引き続きすべて表示されます。<br>
      「ニュース」列は、Googleニュースの見出しに含まれるキーワード(好材料/悪材料に関する単語)の有無を
      見出し単位で多数決しただけの簡易判定であり、文脈やニュアンスは考慮されていません
      (「AI」表示がある場合はAI(Claude API)による判定です)。
      判定結果・シグナルの強さには一切影響しないただの参考表示です。
    </div>
  </div>
</body>
</html>
"""
