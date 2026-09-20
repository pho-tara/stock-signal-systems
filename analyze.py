# -*- coding: utf-8 -*-
"""
メイン実行スクリプト。GitHub Actionsから定期的に呼び出される想定。

処理の流れ:
1. watchlist.py の銘柄について yfinance で株価データを取得・指標計算・シグナル判定
2. holdings.py の保有銘柄についても同様に判定(登録があれば)
3. nikkei225.py のユニバースから、価格上限以下で「買い時」な銘柄をランキング
4. ダッシュボードに表示する銘柄(ウォッチリスト・保有銘柄・ランキング上位)について、
   Googleニュースの見出しからキーワードベースでポジティブ/ネガティブを判定(無料・参考情報)
5. BUYまたはSELLが出た銘柄(ウォッチリスト・保有銘柄)があればLINEへ通知
6. すべての結果を docs/index.html に書き出す(GitHub Pagesで公開)

実行方法:
    pip install -r requirements.txt
    python analyze.py
"""
import os
import sys
import time
import traceback

import pandas as pd
import yfinance as yf

from watchlist import WATCHLIST
from holdings import HOLDINGS
from nikkei225 import NIKKEI225
from indicators import add_all_indicators
from signals import evaluate_signal
from notify import send_line_broadcast
from dashboard import build_dashboard_html
from ranking import build_ranking
from news_sentiment import attach_news_sentiment

MIN_ROWS_REQUIRED = 80  # SMA75計算に必要な最低営業日数

# 買い時ランキングの設定
RANKING_PRICE_CEILING = 1500  # この価格(円)以下の銘柄のみを対象にする
RANKING_TOP_N = 20            # ダッシュボードに表示する上位件数


def fetch_and_evaluate(code: str):
    """1銘柄分のデータ取得〜シグナル判定"""
    df = yf.download(code, period="9mo", interval="1d", progress=False, auto_adjust=True)
    if df is None or df.empty:
        raise RuntimeError(f"{code}: データを取得できませんでした")

    # yfinanceがMultiIndex列を返すケースに対応
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if len(df) < MIN_ROWS_REQUIRED:
        raise RuntimeError(f"{code}: データ件数が不足しています({len(df)}件)")

    df = add_all_indicators(df)
    result = evaluate_signal(df)
    return result


def process_list(items, label, notify_lines):
    """WATCHLISTまたはHOLDINGSを処理して結果リストを返す"""
    results = []
    for item in items:
        code, name = item["code"], item["name"]
        try:
            result = fetch_and_evaluate(code)
        except Exception as e:
            print(f"[warn] {code} ({name}) の処理でエラー: {e}", file=sys.stderr)
            traceback.print_exc()
            continue

        results.append({"code": code, "name": name, "result": result})

        if result["direction"] in ("BUY", "SELL"):
            direction_label = "🟢買いシグナル" if result["direction"] == "BUY" else "🔴売りシグナル"
            reasons = " / ".join(result["reasons"])
            notify_lines.append(
                f"{direction_label} {name}({code}) [{label}]\n"
                f"終値: {result['latest']['close']:.1f}\n"
                f"根拠: {reasons}"
            )

        time.sleep(1)  # yfinanceへの過度なリクエストを避けるための小休止

    return results


def main():
    notify_lines = []

    watch_results = process_list(WATCHLIST, "ウォッチ", notify_lines)
    holdings_results = process_list(HOLDINGS, "保有", notify_lines) if HOLDINGS else []

    ranking_results = []
    try:
        ranking_results = build_ranking(
            NIKKEI225, price_ceiling=RANKING_PRICE_CEILING, top_n=RANKING_TOP_N
        )
    except Exception as e:
        print(f"[warn] ランキング生成に失敗しました: {e}", file=sys.stderr)
        traceback.print_exc()

    # ダッシュボードに実際に表示される銘柄だけニュース判定する
    # (日経225全銘柄ではなく、ランキング上位N件・ウォッチリスト・保有銘柄のみ。
    #  無料のGoogleニュース検索を使うため、件数を絞ってリクエスト数を抑える)
    #
    # USE_AI_NEWS=true の場合のみ、Claude API(Haiku)によるAI判定を使う。
    # コスト削減のため、通常はGitHub Actions側で「平日朝の実行だけtrue」に
    # なるよう .github/workflows/stock-check.yml で設定している。
    # false、またはAPIキー未設定・呼び出し失敗時は無料のキーワード判定を使う。
    use_ai_news = os.environ.get("USE_AI_NEWS", "").strip().lower() == "true"
    print(f"[info] ニュース判定方式: {'AI(Claude API)' if use_ai_news else 'キーワードベース(無料)'}")
    try:
        attach_news_sentiment(watch_results, use_ai=use_ai_news)
        attach_news_sentiment(holdings_results, use_ai=use_ai_news)
        attach_news_sentiment(ranking_results, use_ai=use_ai_news)
    except Exception as e:
        print(f"[warn] ニュース判定処理に失敗しました: {e}", file=sys.stderr)
        traceback.print_exc()

    if notify_lines:
        message = "【日本株テクニカルシグナル】\n\n" + "\n\n".join(notify_lines)
        send_line_broadcast(message)
    else:
        print("[info] 本日はシグナル該当銘柄がありませんでした")

    if watch_results or holdings_results:
        os.makedirs("docs", exist_ok=True)
        # GitHub Actions実行時は "owner/repo" が自動で環境変数に入っている
        github_repo = os.environ.get("GITHUB_REPOSITORY")
        html = build_dashboard_html(
            watch_results,
            holdings=holdings_results,
            ranking=ranking_results,
            ranking_price_ceiling=RANKING_PRICE_CEILING,
            github_repo=github_repo,
        )
        with open("docs/index.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("[info] ダッシュボードを docs/index.html に出力しました")
    else:
        print("[error] 全銘柄でデータ取得に失敗しました", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
