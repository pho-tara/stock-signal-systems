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


RANGE_POSITION_STYLE = [
    # (上限, 色, ラベル) — position(0〜1)がこの上限以下なら該当
    (0.25, "#0f9d58", "安値圏"),
    (0.75, "#9aa0a6", "中間"),
    (1.01, "#d93025", "高値圏"),
]


def _range_position_bucket(position: float) -> tuple:
    """range_position(0〜1)を(色, ラベル)に分類する(安値圏/中間/高値圏)。"""
    for upper, color, label in RANGE_POSITION_STYLE:
        if position <= upper:
            return color, label
    return RANGE_POSITION_STYLE[-1][1], RANGE_POSITION_STYLE[-1][2]


def _valuation_html(item: dict) -> str:
    """「割安感」の参考情報(52週レンジ内の位置、およびPER/PBR/配当利回り)。

    52週レンジの位置は株価データのみで計算できる簡易的な指標(その銘柄自身の
    直近1年の値動きの中でどのあたりかを示すだけで、企業価値の割安度とは別物)。
    PER/PBR/配当利回りはyfinanceの銘柄情報から取得したもので、より本来の意味での
    割安度に近いが、取得できない銘柄もある(その場合は表示しない)。
    いずれもシグナル判定・スコアには一切影響しない参考情報。
    """
    r = item["result"]
    latest = r["latest"]
    parts = []

    position = latest.get("range_position")
    if position is not None:
        pct = position * 100
        color, label = _range_position_bucket(position)
        parts.append(
            f'<span class="badge" style="background:{color}22;color:{color};border:1px solid {color}55;">'
            f"{label}</span>"
        )
        parts.append(f'<div class="valuation-note">52週レンジ内 {pct:.0f}%の位置</div>')

    valuation = item.get("valuation")
    if valuation:
        bits = []
        per = valuation.get("per")
        pbr = valuation.get("pbr")
        div = valuation.get("dividend_yield_pct")
        if per is not None:
            bits.append(f"PER {per:.1f}倍")
        if pbr is not None:
            note = "(1倍割れ)" if pbr < 1 else ""
            bits.append(f"PBR {pbr:.2f}倍{note}")
        if div is not None:
            bits.append(f"利回り{div:.1f}%")
        if bits:
            parts.append(f'<div class="valuation-note">{"・".join(bits)}</div>')

    if not parts:
        return '<span class="muted">—</span>'
    return "".join(parts)


# 中長期の目線(参考情報): 長期トレンド(SMA75の向き)と52週レンジ内の位置を
# 組み合わせて、中長期で見た大まかな状況を一言でまとめたもの。
# 「判定」列(短期の売買タイミング)とは別枠の情報であり、シグナル判定・スコアには
# 一切影響しない。あくまで機械的な組み合わせであり、投資助言ではない。
MID_LONG_TERM_OUTLOOK = {
    ("UP", "安値圏"): ("#0f9d58", "上昇トレンド中の押し目(中長期の買い場候補)"),
    ("UP", "中間"): ("#0f9d58", "上昇トレンド継続中(中長期は堅調)"),
    ("UP", "高値圏"): ("#b45309", "上昇トレンドだが高値圏(過熱に注意)"),
    ("DOWN", "安値圏"): ("#b45309", "下降トレンド中だが底値圏(反発待ちの可能性)"),
    ("DOWN", "中間"): ("#9aa0a6", "下降トレンド継続中(様子見が無難)"),
    ("DOWN", "高値圏"): ("#d93025", "下降トレンドで戻り待ち(高値圏からの調整中)"),
}


def _mid_long_term_outlook(trend: str | None, position: float | None):
    """trend("UP"/"DOWN")とrange_position(0〜1)から、中長期の目線ラベルを求める。
    どちらかがNone(データ不足)の場合はNoneを返す(呼び出し側は「—」を表示すること)。
    """
    if trend is None or position is None:
        return None
    _, bucket_label = _range_position_bucket(position)
    return MID_LONG_TERM_OUTLOOK.get((trend, bucket_label))


def _outlook_html(r: dict) -> str:
    latest = r["latest"]
    style = _mid_long_term_outlook(latest.get("trend"), latest.get("range_position"))
    if not style:
        return '<span class="muted">—</span>'
    color, label = style
    return f'<div class="outlook-note" style="color:{color};">{html.escape(label)}</div>'


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
      <td class="news-cell">{_valuation_html(item)}</td>
      <td class="outlook-cell">{_outlook_html(r)}</td>
    </tr>
    """


def _table_html(items: list, with_rank: bool = False) -> str:
    rows = "\n".join(
        _row_html(item, rank=(i + 1) if with_rank else None) for i, item in enumerate(items)
    )
    rank_th = "<th>順位</th>" if with_rank else ""
    return f"""
    <div class="table-scroll">
    <table>
      <thead>
        <tr>
          {rank_th}<th>銘柄</th><th>終値</th><th>SMA5</th><th>SMA25</th><th>RSI14</th><th>判定(短期)</th><th class="reasons-th">根拠</th><th>ニュース</th><th>割安度</th><th>中長期の目線</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
    </div>
    """


def _empty_state(message: str) -> str:
    return f'<div class="empty">{message}</div>'


def _refresh_button_html(github_repo: str | None) -> str:
    """
    「日本株テクニカルシグナルチェック」ワークフローの実行ページへの直リンクボタン。
    GitHubにログイン済みの状態でクリックすれば、Actionsタブから探す手間なく
    「Run workflow」ボタンまで1クリックで到達できる(実行の確定自体はGitHub側の
    ボタン操作が必要。ページからワンクリックで自動実行しない理由は下記docstring参照)。
    """
    if not github_repo:
        return ""
    url = f"https://github.com/{github_repo}/actions/workflows/stock-check.yml"
    return f"""
    <div class="refresh-box">
      <a class="refresh-link" href="{html.escape(url)}" target="_blank" rel="noopener">
        今すぐ最新データに更新する（GitHub Actionsを開く）
      </a>
      <div class="refresh-note">
        リンク先で「Run workflow」→ もう一度「Run workflow」を押すと、数分後にこのページが更新されます。
      </div>
    </div>
    """


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
        <h2>買い時ランキング（日経225・{ceiling_label}・買いシグナルのみ）</h2>
        {_table_html(ranking, with_rank=True) if ranking else _empty_state("現在、条件に合う買いシグナル銘柄がありませんでした。")}
        """

    registration_section = _registration_section_html(github_repo)
    refresh_button = _refresh_button_html(github_repo)

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
  .wrap {{ max-width: 1400px; margin: 0 auto; }}
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
  .table-scroll {{ overflow-x: auto; border-radius: 10px; }}
  table {{ width: 100%; min-width: 1180px; border-collapse: collapse; background: var(--card); border-radius: 10px; overflow: hidden; }}
  th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 0.85rem; text-align: left; }}
  th {{ color: var(--muted); font-weight: 500; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.02em; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.rank {{ font-weight: 700; color: var(--muted); }}
  .name-cell {{ min-width: 110px; }}
  .name-cell .name {{ font-weight: 600; }}
  .name-cell .code {{ color: var(--muted); font-size: 0.75rem; }}
  .badge {{ display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 0.78rem; white-space: nowrap; }}
  td.reasons {{ min-width: 260px; max-width: 360px; color: var(--muted); font-size: 0.78rem; line-height: 1.5; }}
  .caution {{ color: #b45309; font-size: 0.72rem; margin-top: 4px; line-height: 1.4; }}
  @media (prefers-color-scheme: dark) {{ .caution {{ color: #fbbf24; }} }}
  .news-cell {{ min-width: 140px; }}
  .news-headline {{ color: var(--muted); font-size: 0.72rem; margin-top: 4px; line-height: 1.4; }}
  .valuation-note {{ color: var(--muted); font-size: 0.72rem; margin-top: 4px; line-height: 1.4; }}
  .outlook-cell {{ min-width: 160px; }}
  .outlook-note {{ font-size: 0.78rem; font-weight: 600; line-height: 1.4; }}
  .muted {{ color: var(--muted); }}
  .method-tag {{
    display: inline-block; margin-left: 4px; padding: 1px 5px; border-radius: 4px;
    font-size: 0.6rem; font-weight: 700; vertical-align: middle;
    background: #1a73e822; color: #1a73e8; border: 1px solid #1a73e855;
  }}
  .empty {{ color: var(--muted); font-size: 0.85rem; padding: 16px; background: var(--card); border-radius: 10px; }}
  .refresh-box {{ margin: 4px 0 20px; }}
  .refresh-link {{
    display: inline-block; padding: 8px 14px; border-radius: 6px; background: #1a73e8; color: #fff;
    font-size: 0.85rem; font-weight: 600; text-decoration: none;
  }}
  .refresh-link:hover {{ background: #1558b0; }}
  .refresh-note {{ color: var(--muted); font-size: 0.72rem; margin-top: 6px; line-height: 1.5; }}
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
    .table-scroll {{ overflow-x: visible; }}
    table {{ min-width: 0; }}
    table, thead, tbody, th, td, tr {{ display: block; }}
    thead {{ display: none; }}
    tr {{ border-bottom: 1px solid var(--border); padding: 10px 0; }}
    td {{ border: none; padding: 3px 0; display: flex; justify-content: space-between; gap: 8px; }}
    td.reasons {{ min-width: 0; max-width: none; display: block; }}
    td.num::before {{ content: attr(data-label); color: var(--muted); }}
    .name-cell {{ display: block; }}
  }}
</style>
</head>
<body>
  <div class="wrap">
    <h1>日本株テクニカルシグナル ダッシュボード</h1>
    <div class="updated">最終更新: {now}</div>
    {refresh_button}

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
      判定結果・シグナルの強さには一切影響しないただの参考表示です。<br>
      「割安度」列のうち「安値圏/中間/高値圏」は、あくまでその銘柄自身の直近52週の値動きの中で
      現在値がどのあたりかを示すだけの簡易的な参考情報で、企業価値そのものの割安・割高を示すものではありません。
      PER・PBR・配当利回りはYahoo Financeの銘柄情報から取得していますが、取得元の都合により
      一部の銘柄で表示されない(「—」のままの)場合があります。<br>
      「判定(短期)」列は数日〜数週間程度の短期的な売買タイミングの参考情報です。「中長期の目線」列は、
      長期トレンド(SMA75の向き)と52週レンジ内の位置を組み合わせた、数ヶ月〜1年程度の
      大まかな状況の目安であり、「判定」列とは別の観点の参考情報です（両者が逆方向を示すこともあります）。
      いずれも機械的な組み合わせによる表示であり投資助言ではなく、シグナル判定・スコアには一切影響しません。
    </div>
  </div>
</body>
</html>
"""
