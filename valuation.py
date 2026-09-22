# -*- coding: utf-8 -*-
"""
「割安感」の参考情報のうち、株価データだけでは分からない
企業の財務指標(PER・PBR・配当利回り)をyfinanceの銘柄情報から取得する。

もう一つの「割安感」の指標である52週レンジ内の位置(直近安値/高値に対する現在値の
位置)は、既に取得済みの株価データだけで計算できるため signals.py 側で計算している
(week52_high / week52_low / range_position)。こちらは企業価値そのものとは無関係の、
あくまで自分自身の過去の値動きとの相対比較にすぎない。

このモジュールが扱うPER(株価収益率)・PBR(株価純資産倍率)・配当利回りは、
より本来の意味での「割安度」に近い指標だが、取得には銘柄ごとに個別の追加リクエスト
(yfinanceの Ticker().info)が必要で、株価データ本体の取得(yf.download)に比べて
低速・不安定(Yahoo Finance側の仕様変更の影響を受けやすい)であることが知られている。
そのため、取得に失敗した銘柄や項目は空欄(None)として扱い、処理全体は継続する。

配当利回りは、yfinanceのバージョンによって「info」内の値の単位(小数か%か)が
変わることがあり誤表示のリスクがあるため、直接は使わず、
「年間配当金額(dividendRate、円建ての実額)÷ 現在の終値」で自前計算する
(単位のブレが起きない、より確実な方法)。

これらの判定はいずれもテクニカルシグナル(signals.py)の判定・スコアには
一切影響しない、表示用の参考情報である。
"""
import sys
import time
import traceback

import yfinance as yf

REQUEST_SLEEP_SECONDS = 0.5


def fetch_valuation_metrics(code: str) -> dict | None:
    """yfinanceの銘柄情報(info)からPER・PBRを取得し、配当利回りは
    「年間配当金額 ÷ 現在の終値」で自前計算する。

    以下のいずれかに該当する場合はNoneを返す(呼び出し側は表示をスキップすること):
    - 銘柄情報の取得自体に失敗した場合(ネットワークエラー、Yahoo側の仕様変更など)
    - PER・PBR・配当利回りのいずれも取得できなかった場合
    """
    try:
        info = yf.Ticker(code).info
    except Exception as e:
        print(f"[warn] {code}: 銘柄情報(PER/PBR等)の取得に失敗しました: {e}", file=sys.stderr)
        traceback.print_exc()
        return None

    if not info:
        return None

    per = info.get("trailingPE")
    pbr = info.get("priceToBook")
    dividend_rate = info.get("dividendRate")
    price = info.get("currentPrice") or info.get("regularMarketPrice")

    dividend_yield_pct = None
    if isinstance(dividend_rate, (int, float)) and isinstance(price, (int, float)) and price > 0:
        dividend_yield_pct = dividend_rate / price * 100

    per = float(per) if isinstance(per, (int, float)) else None
    pbr = float(pbr) if isinstance(pbr, (int, float)) else None

    if per is None and pbr is None and dividend_yield_pct is None:
        return None

    return {
        "per": per,
        "pbr": pbr,
        "dividend_yield_pct": dividend_yield_pct,
    }


def attach_valuation_for_lists(*item_lists, sleep_seconds: float = REQUEST_SLEEP_SECONDS) -> None:
    """複数の[{"code","name","result"}, ...]リストの各要素に item["valuation"] を追加する。

    ウォッチリスト・保有銘柄・ランキングなど複数のリストにまたがって
    同じ銘柄コードが重複する場合、銘柄情報の取得は1回だけ行い結果を使い回す
    (news_sentiment.attach_news_sentiment_for_listsと同じ考え方)。
    """
    cache: dict = {}
    for items in item_lists:
        for item in items:
            code = item.get("code")
            if code is not None and code in cache:
                item["valuation"] = cache[code]
                continue
            metrics = fetch_valuation_metrics(code) if code else None
            item["valuation"] = metrics
            if code is not None:
                cache[code] = metrics
            time.sleep(sleep_seconds)
