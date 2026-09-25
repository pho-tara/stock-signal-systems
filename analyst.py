# -*- coding: utf-8 -*-
"""
アナリスト予想(目標株価コンセンサス・投資判断レーティング)を
yfinanceの銘柄情報(Ticker().info)から取得する。

PER/PBR/配当利回り(valuation.py)と同じく、株価データ本体の取得(yf.download)
とは別に銘柄ごとの個別リクエストが必要で、低速・不安定(Yahoo Finance側の
仕様変更の影響を受けやすい)ことが知られている。

特に日本株は、米国株に比べてYahoo Finance上にアナリスト予想データ自体が
存在しない銘柄が多く、valuation.py(PER/PBR)よりもさらに「—」表示になる
ケースが多くなる見込みである(このモジュール固有の既知の制約)。

取得に失敗した銘柄や項目は空欄(None)として扱い、処理全体は継続する。
目標株価と現在の終値との比較(上振れ/下振れ率)は、この時点では計算せず、
表示側(dashboard.py)で、既に取得済みの株価データ(latest close)を使って
計算する(二重に価格を取得しない、他の指標と同じ考え方)。

これらの判定はいずれもテクニカルシグナル(signals.py)の判定・スコアには
一切影響しない、表示用の参考情報である。
"""
import sys
import time
import traceback

import yfinance as yf

REQUEST_SLEEP_SECONDS = 0.5


def _as_float(v):
    return float(v) if isinstance(v, (int, float)) else None


def fetch_analyst_estimates(code: str) -> dict | None:
    """yfinanceの銘柄情報(info)から、アナリストの目標株価コンセンサス
    (平均・最高・最低)と投資判断レーティング(recommendationKey)を取得する。

    以下のいずれかに該当する場合はNoneを返す(呼び出し側は表示をスキップすること):
    - 銘柄情報の取得自体に失敗した場合(ネットワークエラー、Yahoo側の仕様変更など)
    - 目標株価・レーティングのいずれも取得できなかった場合
      (日本株はこのケースが米国株よりかなり多い)
    """
    try:
        info = yf.Ticker(code).info
    except Exception as e:
        print(f"[warn] {code}: アナリスト予想の取得に失敗しました: {e}", file=sys.stderr)
        traceback.print_exc()
        return None

    if not info:
        return None

    target_mean = _as_float(info.get("targetMeanPrice"))
    target_high = _as_float(info.get("targetHighPrice"))
    target_low = _as_float(info.get("targetLowPrice"))

    num_analysts = info.get("numberOfAnalystOpinions")
    num_analysts = int(num_analysts) if isinstance(num_analysts, (int, float)) else None

    recommendation_key = info.get("recommendationKey")
    if not isinstance(recommendation_key, str) or recommendation_key.lower() in ("none", ""):
        recommendation_key = None

    if target_mean is None and target_high is None and target_low is None and recommendation_key is None:
        return None

    return {
        "target_mean": target_mean,
        "target_high": target_high,
        "target_low": target_low,
        "num_analysts": num_analysts,
        "recommendation_key": recommendation_key,
    }


def attach_analyst_estimates_for_lists(*item_lists, sleep_seconds: float = REQUEST_SLEEP_SECONDS) -> None:
    """複数の[{"code","name","result"}, ...]リストの各要素に item["analyst"] を追加する。

    ウォッチリスト・保有銘柄・ランキングなど複数のリストにまたがって
    同じ銘柄コードが重複する場合、取得は1回だけ行い結果を使い回す
    (valuation.attach_valuation_for_listsと同じ考え方)。
    """
    cache: dict = {}
    for items in item_lists:
        for item in items:
            code = item.get("code")
            if code is not None and code in cache:
                item["analyst"] = cache[code]
                continue
            estimates = fetch_analyst_estimates(code) if code else None
            item["analyst"] = estimates
            if code is not None:
                cache[code] = estimates
            time.sleep(sleep_seconds)
