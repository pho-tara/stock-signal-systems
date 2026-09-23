# -*- coding: utf-8 -*-
"""
日経225ユニバースから、指定した株価上限以下で「最も買い時」な銘柄を
ランキングするロジック。

複数銘柄をまとめてyfinanceに問い合わせることで、
225銘柄でもリクエスト数を抑えて実行時間を短縮している。
"""
import sys
import time
import traceback

import pandas as pd
import yfinance as yf

from indicators import add_all_indicators
from signals import evaluate_signal

CHUNK_SIZE = 40          # 一度に問い合わせる銘柄数
SLEEP_BETWEEN_CHUNKS = 2  # チャンク間の待機秒数(レート制限対策)
MIN_ROWS_REQUIRED = 80


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


def build_ranking(universe: list, price_ceiling: float, top_n: int = 20) -> list:
    """
    universe: [{"code": str, "name": str}, ...] 例: NIKKEI225
    price_ceiling: この価格以下の銘柄のみを対象にする
    top_n: 上位何件を返すか

    戻り値: [{"code", "name", "result"}, ...] を「買い時」順にソートしたリスト
            (price_ceiling以下、かつdirection=="BUY"(買いシグナル)の銘柄のみが対象。
             該当銘柄がtop_n未満の場合は、その件数だけを返す)
    """
    candidates = []

    for chunk in _chunked(universe, CHUNK_SIZE):
        codes = [item["code"] for item in chunk]
        name_map = {item["code"]: item["name"] for item in chunk}

        try:
            batch_df = yf.download(
                codes,
                period="1y",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )
        except Exception as e:
            print(f"[warn] チャンク取得に失敗: {codes} -> {e}", file=sys.stderr)
            traceback.print_exc()
            time.sleep(SLEEP_BETWEEN_CHUNKS)
            continue

        for code in codes:
            try:
                df = _extract_ticker_df(batch_df, code)
                if df is None or df.empty or len(df) < MIN_ROWS_REQUIRED:
                    continue
                df = add_all_indicators(df)
                result = evaluate_signal(df)

                close = result["latest"]["close"]
                if close is None or close > price_ceiling:
                    continue

                # ランキングは「買い時」を探すためのものなので、
                # 買いシグナル(BUY)が出ている銘柄のみを対象にする。
                # (様子見や売りシグナルの銘柄は、たとえ株価上限を満たしていても除外する)
                if result["direction"] != "BUY":
                    continue

                candidates.append({"code": code, "name": name_map[code], "result": result})
            except Exception as e:
                print(f"[warn] {code} の評価でエラー: {e}", file=sys.stderr)
                continue

        time.sleep(SLEEP_BETWEEN_CHUNKS)

    def _rank_key(item):
        r = item["result"]
        if r["direction"] == "BUY":
            base = 100 + r["score"]
            # 長期トレンド(SMA75)に逆行する注意が出ているBUYは、
            # 見せかけの反発の可能性があるため、同スコア帯の中では少し順位を下げる。
            if r.get("trend_caution"):
                base -= 1
        elif r["direction"] == "NONE":
            base = 0
        else:  # SELL
            base = -100 - r["score"]
        rsi = r["latest"]["rsi14"]
        rsi_bonus = -(rsi if rsi is not None else 50)  # RSIが低いほど上位(売られすぎ=買い場)
        return (base, rsi_bonus)

    candidates.sort(key=_rank_key, reverse=True)
    return candidates[:top_n]
