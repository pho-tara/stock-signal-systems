# -*- coding: utf-8 -*-
"""
valuation.py (PER・PBR・配当利回りの取得ロジック)の単体テスト。
ネットワーク接続は使わない(yfinance.Tickerをダミー実装に差し替える)。
pytest等のテストフレームワークには依存せず、`python test_valuation.py` で実行できる。
"""
import valuation
from valuation import attach_valuation_for_lists, fetch_valuation_metrics


class _FakeTicker:
    def __init__(self, info):
        self.info = info


def test_fetch_valuation_metrics_normal_case():
    """PER・PBR・現在値と年間配当金額(dividendRate)から配当利回りを計算できる。"""
    fake_info = {"trailingPE": 15.2, "priceToBook": 1.3, "dividendRate": 60.0, "currentPrice": 3000.0}
    original = valuation.yf.Ticker
    valuation.yf.Ticker = lambda code: _FakeTicker(fake_info)
    try:
        result = fetch_valuation_metrics("TEST.T")
        print("=== 通常ケース ===", result)
        assert result["per"] == 15.2, result
        assert result["pbr"] == 1.3, result
        assert abs(result["dividend_yield_pct"] - 2.0) < 1e-9, result  # 60/3000*100=2.0%
    finally:
        valuation.yf.Ticker = original


def test_fetch_valuation_metrics_missing_dividend_fields_gives_none_yield():
    """dividendRateまたはcurrentPriceが無ければ配当利回りはNoneになる(PER/PBRは取得できる)。"""
    fake_info = {"trailingPE": 10.0, "priceToBook": 0.8}
    original = valuation.yf.Ticker
    valuation.yf.Ticker = lambda code: _FakeTicker(fake_info)
    try:
        result = fetch_valuation_metrics("TEST.T")
        print("=== 配当情報なし ===", result)
        assert result["per"] == 10.0, result
        assert result["pbr"] == 0.8, result
        assert result["dividend_yield_pct"] is None, result
    finally:
        valuation.yf.Ticker = original


def test_fetch_valuation_metrics_returns_none_when_all_fields_missing():
    """PER/PBR/配当のいずれも取得できない場合はNoneを返す。"""
    fake_info = {"someOtherField": 123}
    original = valuation.yf.Ticker
    valuation.yf.Ticker = lambda code: _FakeTicker(fake_info)
    try:
        result = fetch_valuation_metrics("TEST.T")
        print("=== 全項目取得不可 ===", result)
        assert result is None, result
    finally:
        valuation.yf.Ticker = original


def test_fetch_valuation_metrics_returns_none_on_exception():
    """info取得自体が例外を起こした場合(ネットワークエラーなど)もNoneを返し、
    呼び出し側の処理を止めない。"""
    original = valuation.yf.Ticker

    def raise_error(code):
        raise RuntimeError("network error")

    valuation.yf.Ticker = raise_error
    try:
        result = fetch_valuation_metrics("TEST.T")
        print("=== 例外発生時 ===", result)
        assert result is None, result
    finally:
        valuation.yf.Ticker = original


def test_attach_valuation_for_lists_dedupes_by_code():
    """同じ銘柄コードが複数のリストに登場する場合、
    fetch_valuation_metrics相当の取得は銘柄コードごとに1回だけ行われることを確認する。"""
    call_count = {"n": 0}
    original = valuation.fetch_valuation_metrics

    def fake_fetch(code):
        call_count["n"] += 1
        return {"per": 10.0, "pbr": 1.0, "dividend_yield_pct": 2.0}

    valuation.fetch_valuation_metrics = fake_fetch
    try:
        watch = [{"code": "7203.T", "name": "トヨタ自動車", "result": {}}]
        ranking = [
            {"code": "7203.T", "name": "トヨタ自動車", "result": {}},  # ウォッチリストと重複
            {"code": "9984.T", "name": "ソフトバンクグループ", "result": {}},
        ]
        attach_valuation_for_lists(watch, ranking, sleep_seconds=0)

        assert call_count["n"] == 2, f"重複銘柄があるのに呼び出し回数が想定と異なる: {call_count['n']}"
        assert watch[0]["valuation"]["per"] == 10.0
        assert ranking[0]["valuation"] == watch[0]["valuation"], "同じ銘柄コードの結果が使い回されていない"
        assert ranking[1]["valuation"]["per"] == 10.0
        print("=== 銘柄コード重複時の取得キャッシュ ===", "call_count=", call_count["n"])
    finally:
        valuation.fetch_valuation_metrics = original


if __name__ == "__main__":
    test_fetch_valuation_metrics_normal_case()
    test_fetch_valuation_metrics_missing_dividend_fields_gives_none_yield()
    test_fetch_valuation_metrics_returns_none_when_all_fields_missing()
    test_fetch_valuation_metrics_returns_none_on_exception()
    test_attach_valuation_for_lists_dedupes_by_code()
    print("\nvaluation.py のロジックテストが完了しました(エラーなし)。")
