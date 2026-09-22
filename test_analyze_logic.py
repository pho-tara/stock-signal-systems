# -*- coding: utf-8 -*-
"""
analyze.py のロジック(LINE通知要否の判定、バッチ取得の補助関数)を
ネットワーク接続なしで検証するテスト。
pytest等のテストフレームワークには依存せず、`python test_analyze_logic.py` で実行できる。
"""
import pandas as pd

from analyze import _chunked, _extract_ticker_df, _should_notify


def _result(direction, score, trend_caution=False):
    return {"direction": direction, "score": score, "trend_caution": trend_caution, "reasons": []}


def test_should_notify_false_when_no_signal():
    assert _should_notify(_result("NONE", 0)) is False
    print("=== NONEは通知しない ===")


def test_should_notify_false_for_weak_signal():
    """根拠が1つだけ(score=1)の弱いシグナルは通知しない。"""
    assert _should_notify(_result("BUY", 1)) is False
    assert _should_notify(_result("SELL", 1)) is False
    print("=== score=1の弱いシグナルは通知しない ===")


def test_should_notify_true_for_score_two_without_caution():
    assert _should_notify(_result("BUY", 2, trend_caution=False)) is True
    assert _should_notify(_result("SELL", 2, trend_caution=False)) is True
    print("=== score=2でトレンド注意がなければ通知する ===")


def test_should_notify_requires_higher_score_when_trend_caution():
    """長期トレンドに逆行する注意がある場合は、score=2では通知せず、
    score=3以上そろって初めて通知する。"""
    assert _should_notify(_result("BUY", 2, trend_caution=True)) is False
    assert _should_notify(_result("BUY", 3, trend_caution=True)) is True
    print("=== トレンド逆行時はscore=3以上でのみ通知する ===")


def test_chunked_splits_into_expected_sizes():
    items = list(range(10))
    chunks = list(_chunked(items, 4))
    assert chunks == [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9]], chunks
    print("=== チャンク分割 ===", chunks)


def test_extract_ticker_df_from_multiindex_batch():
    idx = pd.date_range("2025-01-01", periods=5, freq="B")
    codes = ["AAAA.T", "BBBB.T"]
    frames = {
        code: pd.DataFrame({"Close": [100 + i for i in range(5)], "Volume": [1000] * 5}, index=idx)
        for code in codes
    }
    batch_df = pd.concat(frames, axis=1)

    sub = _extract_ticker_df(batch_df, "AAAA.T")
    assert list(sub["Close"]) == [100, 101, 102, 103, 104], sub
    print("=== MultiIndexバッチからの1銘柄抽出 ===")


def test_extract_ticker_df_raises_when_code_missing():
    idx = pd.date_range("2025-01-01", periods=3, freq="B")
    frames = {"AAAA.T": pd.DataFrame({"Close": [1, 2, 3]}, index=idx)}
    batch_df = pd.concat(frames, axis=1)
    try:
        _extract_ticker_df(batch_df, "ZZZZ.T")
        raised = False
    except RuntimeError:
        raised = True
    assert raised, "バッチ結果に含まれない銘柄コードでRuntimeErrorが発生していない"
    print("=== バッチ結果に含まれない銘柄コードはエラーになる ===")


if __name__ == "__main__":
    test_should_notify_false_when_no_signal()
    test_should_notify_false_for_weak_signal()
    test_should_notify_true_for_score_two_without_caution()
    test_should_notify_requires_higher_score_when_trend_caution()
    test_chunked_splits_into_expected_sizes()
    test_extract_ticker_df_from_multiindex_batch()
    test_extract_ticker_df_raises_when_code_missing()
    print("\nanalyze.py のロジックテストが完了しました(エラーなし)。")
