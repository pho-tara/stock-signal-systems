# -*- coding: utf-8 -*-
"""
analyst.py (アナリスト予想: 目標株価コンセンサス・投資判断レーティングの取得ロジック)の単体テスト。
ネットワーク接続は使わない(yfinance.Tickerをダミー実装に差し替える)。
pytest等のテストフレームワークには依存せず、`python test_analyst.py` で実行できる。
"""
import analyst
from analyst import attach_analyst_estimates_for_lists, fetch_analyst_estimates


class _FakeTicker:
    def __init__(self, info):
        self.info = info


def test_fetch_analyst_estimates_normal_case():
    """目標株価(平均・最高・最低)・アナリスト数・投資判断レーティングを取得できる。"""
    fake_info = {
        "targetMeanPrice": 3500.0,
        "targetHighPrice": 4000.0,
        "targetLowPrice": 3000.0,
        "numberOfAnalystOpinions": 12,
        "recommendationKey": "buy",
    }
    original = analyst.yf.Ticker
    analyst.yf.Ticker = lambda code: _FakeTicker(fake_info)
    try:
        result = fetch_analyst_estimates("TEST.T")
        print("=== 通常ケース ===", result)
        assert result["target_mean"] == 3500.0, result
        assert result["target_high"] == 4000.0, result
        assert result["target_low"] == 3000.0, result
        assert result["num_analysts"] == 12, result
        assert result["recommendation_key"] == "buy", result
    finally:
        analyst.yf.Ticker = original


def test_fetch_analyst_estimates_treats_none_recommendation_as_missing():
    """recommendationKeyが"none"(Yahoo側の「データなし」を表す文字列)の場合は
    Noneとして扱う(そのまま画面に「none」と表示してしまわないようにする)。"""
    fake_info = {
        "targetMeanPrice": 1000.0,
        "recommendationKey": "none",
    }
    original = analyst.yf.Ticker
    analyst.yf.Ticker = lambda code: _FakeTicker(fake_info)
    try:
        result = fetch_analyst_estimates("TEST.T")
        print("=== recommendationKey=none ===", result)
        assert result["target_mean"] == 1000.0, result
        assert result["recommendation_key"] is None, result
    finally:
        analyst.yf.Ticker = original


def test_fetch_analyst_estimates_returns_none_when_all_fields_missing():
    """目標株価・レーティングのいずれも取得できない場合はNoneを返す
    (日本株はこのケースが米国株よりかなり多い)。"""
    fake_info = {"someOtherField": 123}
    original = analyst.yf.Ticker
    analyst.yf.Ticker = lambda code: _FakeTicker(fake_info)
    try:
        result = fetch_analyst_estimates("TEST.T")
        print("=== 全項目取得不可 ===", result)
        assert result is None, result
    finally:
        analyst.yf.Ticker = original


def test_fetch_analyst_estimates_returns_none_on_exception():
    """info取得自体が例外を起こした場合(ネットワークエラーなど)もNoneを返し、
    呼び出し側の処理を止めない。"""
    original = analyst.yf.Ticker

    def raise_error(code):
        raise RuntimeError("network error")

    analyst.yf.Ticker = raise_error
    try:
        result = fetch_analyst_estimates("TEST.T")
        print("=== 例外発生時 ===", result)
        assert result is None, result
    finally:
        analyst.yf.Ticker = original


def test_attach_analyst_estimates_for_lists_dedupes_by_code():
    """同じ銘柄コードが複数のリストに登場する場合、
    fetch_analyst_estimates相当の取得は銘柄コードごとに1回だけ行われることを確認する。"""
    call_count = {"n": 0}
    original = analyst.fetch_analyst_estimates

    def fake_fetch(code):
        call_count["n"] += 1
        return {"target_mean": 100.0, "target_high": 120.0, "target_low": 80.0,
                "num_analysts": 5, "recommendation_key": "hold"}

    analyst.fetch_analyst_estimates = fake_fetch
    try:
        watch = [{"code": "7203.T", "name": "トヨタ自動車", "result": {}}]
        ranking = [
            {"code": "7203.T", "name": "トヨタ自動車", "result": {}},  # ウォッチリストと重複
            {"code": "9984.T", "name": "ソフトバンクグループ", "result": {}},
        ]
        attach_analyst_estimates_for_lists(watch, ranking, sleep_seconds=0)

        assert call_count["n"] == 2, f"重複銘柄があるのに呼び出し回数が想定と異なる: {call_count['n']}"
        assert watch[0]["analyst"]["target_mean"] == 100.0
        assert ranking[0]["analyst"] == watch[0]["analyst"], "同じ銘柄コードの結果が使い回されていない"
        assert ranking[1]["analyst"]["target_mean"] == 100.0
        print("=== 銘柄コード重複時の取得キャッシュ ===", "call_count=", call_count["n"])
    finally:
        analyst.fetch_analyst_estimates = original


if __name__ == "__main__":
    test_fetch_analyst_estimates_normal_case()
    test_fetch_analyst_estimates_treats_none_recommendation_as_missing()
    test_fetch_analyst_estimates_returns_none_when_all_fields_missing()
    test_fetch_analyst_estimates_returns_none_on_exception()
    test_attach_analyst_estimates_for_lists_dedupes_by_code()
    print("\nanalyst.py のロジックテストが完了しました(エラーなし)。")
