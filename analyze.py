# -*- coding: utf-8 -*-
"""
メイン実行スクリプト。GitHub Actionsから定期的に呼び出される想定。

処理の流れ:
1. watchlist.py の銘柄について yfinance で株価データを取得・指標計算・シグナル判定
   (複数銘柄をまとめて1回のリクエストで取得し、実行時間を短縮している)
2. holdings.py の保有銘柄についても同様に判定(登録があれば)
3. nikkei225.py のユニバースから、価格上限以下で「買い時」な銘柄をランキング
4. ダッシュボードに表示する銘柄(ウォッチリスト・保有銘柄・ランキング上位)について、
   Googleニュースの見出しからキーワードベースでポジティブ/ネガティブを判定(無料・参考情報)。
   同じ銘柄が複数のリストに重複して登場する場合は、1回の実行内でニュース取得結果を
   使い回してリクエスト数・AI利用料を節約する。
5. 同じくダッシュボードに表示する銘柄について、「割安感」の参考情報も付加する。
   52週レンジ内の位置(株価データのみで計算・追加リクエストなし)はsignals.py側で、
   PER・PBR・配当利回り(yfinanceの銘柄情報からの追加取得)はvaluation.py側で計算・取得する。
   こちらも同じ銘柄の重複取得は1回にまとめる。
6. 一定以上の強さ(score>=2)のBUY/SELLシグナルが出た銘柄(ウォッチリスト・保有銘柄)が
   あればLINEへ通知する。ただし長期トレンドと逆行する注意(trend_caution)がある場合は、
   より強い根拠(score>=3)が揃うまで通知を見送り、ノイズの多い通知を減らす。
7. すべての結果を docs/index.html に書き出す(GitHub Pagesで公開)

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
from news_sentiment import attach_news_sentiment_for_lists
from valuation import attach_valuation_for_lists

MIN_ROWS_REQUIRED = 80  # SMA75計算に必要な最低営業日数
MIN_SCORE_TO_NOTIFY = 2       # LINE通知するシグナルの最低スコア(根拠の数)
MIN_SCORE_TO_NOTIFY_AGAINST_TREND = 3  # 長期トレンドに逆行する注意がある場合の最低スコア

# 買い時ランキングの設定
RANKING_PRICE_CEILING = 1500  # この価格(円)以下の銘柄のみを対象にする
RANKING_TOP_N = 20            # ダッシュボードに表示する上位件数

CHUNK_SIZE = 40          # 一度に問い合わせる銘柄数(ranking.pyと同じ考え方)
SLEEP_BETWEEN_CHUNKS = 2  # チャンク間の待機秒数(レート制限対策)


def _chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _extract_ticker_df(batch_df: pd.DataFrame, code: str) -> pd.DataFrame:
    """yfinanceの複数銘柄DataFrame(group_by='ticker')から1銘柄分を取り出す"""
    if isinstance(batch_df.columns, pd.MultiIndex):
        if code not in batch_df.columns.get_level_values(0):
            raise RuntimeError(f"{code}: バッチ結果に含まれていません")
        sub = batch_df[code].copy()
    else:
        # 銘柄数が1つしかなかった場合はMultiIndexにならないことがある
        sub = batch_df.copy()
    sub = sub.dropna(how="all")
    return sub


def _should_notify(result: dict) -> bool:
    """このシグナルをLINE通知すべきかどうかを判定する。

    根拠が1つだけの弱いシグナルは通知しない(ダッシュボードには表示され続ける)。
    さらに、長期トレンド(SMA75)に逆行する注意が出ている場合は、
    より強い根拠が揃うまで通知を見送る。
    """
    if result["direction"] not in ("BUY", "SELL"):
        return False
    threshold = MIN_SCORE_TO_NOTIFY_AGAINST_TREND if result.get("trend_caution") else MIN_SCORE_TO_NOTIFY
    return result["score"] >= threshold


def process_list(items, label, notify_lines):
    """WATCHLISTまたはHOLDINGSを処理して結果リストを返す。

    銘柄ごとに個別リクエストするのではなく、まとめて1回のyf.downloadで取得することで
    実行時間とリクエスト数を抑えている(ranking.pyのバッチ取得と同じ考え方)。
    """
    results = []
    if not items:
        return results

    name_map = {item["code"]: item["name"] for item in items}

    for chunk in _chunked(items, CHUNK_SIZE):
        codes = [item["code"] for item in chunk]
        try:
            batch_df = yf.download(
                codes, period="1y", interval="1d", group_by="ticker",
                auto_adjust=True, threads=True, progress=False,
            )
        except Exception as e:
            print(f"[warn] バッチ取得に失敗: {codes} -> {e}", file=sys.stderr)
            traceback.print_exc()
            continue

        for code in codes:
            name = name_map[code]
            try:
                df = _extract_ticker_df(batch_df, code)
                if df is None or df.empty:
                    raise RuntimeError("データを取得できませんでした")
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                if len(df) < MIN_ROWS_REQUIRED:
                    raise RuntimeError(f"データ件数が不足しています({len(df)}件)")
                df = add_all_indicators(df)
                result = evaluate_signal(df)
            except Exception as e:
                print(f"[warn] {code} ({name}) の処理でエラー: {e}", file=sys.stderr)
                traceback.print_exc()
                continue

            results.append({"code": code, "name": name, "result": result})

            if _should_notify(result):
                direction_label = "🟢買いシグナル" if result["direction"] == "BUY" else "🔴売りシグナル"
                reasons = " / ".join(result["reasons"])
                notify_lines.append(
                    f"{direction_label} {name}({code}) [{label}]\n"
                    f"終値: {result['latest']['close']:.1f}\n"
                    f"根拠: {reasons}"
                )

        if len(items) > CHUNK_SIZE:
            time.sleep(SLEEP_BETWEEN_CHUNKS)

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
    # ウォッチリスト・保有銘柄・ランキングのいずれかに同じ銘柄が重複していても、
    # attach_news_sentiment_for_lists()が1回の実行内でニュース取得結果を使い回すため、
    # 重複リクエスト(および有効時のAI利用料)は発生しない。
    #
    # USE_AI_NEWS=true の場合のみ、Claude API(Haiku)によるAI判定を使う。
    # コスト削減のため、通常はGitHub Actions側で「平日朝の実行だけtrue」に
    # なるよう .github/workflows/stock-check.yml で設定している。
    # false、またはAPIキー未設定・呼び出し失敗時は無料のキーワード判定を使う。
    use_ai_news = os.environ.get("USE_AI_NEWS", "").strip().lower() == "true"
    print(f"[info] ニュース判定方式: {'AI(Claude API)' if use_ai_news else 'キーワードベース(無料)'}")
    try:
        attach_news_sentiment_for_lists(watch_results, holdings_results, ranking_results, use_ai=use_ai_news)
    except Exception as e:
        print(f"[warn] ニュース判定処理に失敗しました: {e}", file=sys.stderr)
        traceback.print_exc()

    # 「割安感」の参考情報のうちPER・PBR・配当利回りを付加する
    # (52週レンジ内の位置はevaluate_signal内で既に計算済み)。
    # yfinanceの銘柄情報取得はニュース取得よりさらに不安定なことがあるため、
    # 失敗しても処理全体を止めないようにする。
    try:
        attach_valuation_for_lists(watch_results, holdings_results, ranking_results)
    except Exception as e:
        print(f"[warn] 割安度(PER/PBR)判定処理に失敗しました: {e}", file=sys.stderr)
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
