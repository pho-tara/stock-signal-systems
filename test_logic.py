# -*- coding: utf-8 -*-
"""
ネットワーク接続なしで、指標計算とシグナル判定ロジックを検証するテスト。
合成データを使い、クロス発生の「その日」に正しくシグナルが検出されるかを確認する。
(急騰・急落が長期間続いた後はRSIが極端な水準になり、
 過熱警戒のSELL/BUY理由が優勢になるのは意図した挙動)
"""
import numpy as np
import pandas as pd

from indicators import add_all_indicators
from signals import evaluate_signal, _crossed_above, _crossed_below


def make_df(prices):
    idx = pd.date_range("2025-01-01", periods=len(prices), freq="B")
    return pd.DataFrame({"Close": prices}, index=idx)


def make_df_with_volume(prices, volumes):
    idx = pd.date_range("2025-01-01", periods=len(prices), freq="B")
    return pd.DataFrame({"Close": prices, "Volume": volumes}, index=idx)


def test_golden_cross_detected_at_the_moment_it_happens():
    np.random.seed(1)
    down = np.linspace(2000, 1500, 100) + np.random.normal(0, 2, 100)
    up = np.linspace(1500, 2000, 40) + np.random.normal(0, 2, 40)
    prices = np.concatenate([down, up])
    df = add_all_indicators(make_df(prices))

    # SMA5がSMA25を上抜けした「最初の日」を探す
    cross_day = None
    for i in range(30, len(df)):
        sub = df.iloc[: i + 1]
        if _crossed_above(sub["SMA5"], sub["SMA25"]):
            cross_day = i
            break
    assert cross_day is not None, "テストデータでゴールデンクロスが発生していない"

    result = evaluate_signal(df.iloc[: cross_day + 1])
    print("=== ゴールデンクロス発生日の判定 ===", result)
    assert result["direction"] == "BUY"
    assert any("ゴールデンクロス" in r for r in result["reasons"])


def test_dead_cross_detected_at_the_moment_it_happens():
    np.random.seed(2)
    up = np.linspace(1500, 2200, 100) + np.random.normal(0, 2, 100)
    down = np.linspace(2200, 1700, 40) + np.random.normal(0, 2, 40)
    prices = np.concatenate([up, down])
    df = add_all_indicators(make_df(prices))

    cross_day = None
    for i in range(30, len(df)):
        sub = df.iloc[: i + 1]
        if _crossed_below(sub["SMA5"], sub["SMA25"]):
            cross_day = i
            break
    assert cross_day is not None, "テストデータでデッドクロスが発生していない"

    result = evaluate_signal(df.iloc[: cross_day + 1])
    print("=== デッドクロス発生日の判定 ===", result)
    assert result["direction"] == "SELL"
    assert any("デッドクロス" in r for r in result["reasons"])


def test_rsi_basic_bounds():
    prices_up = np.linspace(1000, 1200, 60)
    df_up = add_all_indicators(make_df(prices_up))
    assert df_up["RSI14"].iloc[-1] > 60, f"単調上昇でRSIが低すぎる: {df_up['RSI14'].iloc[-1]}"

    prices_down = np.linspace(1200, 1000, 60)
    df_down = add_all_indicators(make_df(prices_down))
    assert df_down["RSI14"].iloc[-1] < 40, f"単調下落でRSIが高すぎる: {df_down['RSI14'].iloc[-1]}"
    print("=== RSI境界チェック ===")
    print("上昇トレンドRSI:", df_up["RSI14"].iloc[-1])
    print("下降トレンドRSI:", df_down["RSI14"].iloc[-1])


def test_trend_caution_flagged_for_buy_against_long_term_downtrend():
    """長期の下落トレンド中に発生したゴールデンクロス(BUY)は、
    SMA75より終値が下にある(=長期トレンドは下向き)ため、
    trend_cautionが立ち、cautionsに注意書きが入ることを確認する。
    (scoreやdirection自体には影響しない、あくまで参考情報)"""
    np.random.seed(10)
    # 長い下落(120営業日)の後、ごく短い戻りでゴールデンクロスだけ起こす。
    # SMA75は下落局面の高い価格を長く引きずるため、戻り始めた時点では
    # 終値がSMA75をまだ大きく下回っている(=典型的な「下落トレンド中の戻り」)。
    down = np.linspace(2000, 1000, 120) + np.random.normal(0, 2, 120)
    up = np.linspace(1000, 1120, 12) + np.random.normal(0, 2, 12)
    prices = np.concatenate([down, up])
    df = add_all_indicators(make_df(prices))

    cross_day = None
    for i in range(80, len(df)):
        sub = df.iloc[: i + 1]
        if _crossed_above(sub["SMA5"], sub["SMA25"]):
            cross_day = i
            break
    assert cross_day is not None, "テストデータでゴールデンクロスが発生していない"

    result = evaluate_signal(df.iloc[: cross_day + 1])
    print("=== 下落トレンド中の戻りで発生したBUYの判定 ===", result)
    assert result["direction"] == "BUY"
    assert result["latest"]["trend"] == "DOWN", result["latest"]
    assert result["trend_caution"] is True, result
    assert result["cautions"], "cautionsに注意書きが入っていない"


def test_no_trend_caution_when_signal_aligns_with_trend():
    """長期トレンドと同じ方向のシグナルには注意書きが付かないことを確認する。
    緩やかな上昇トレンドに波(周期的な上下動)を重ねることで、
    トレンドが既に上向き(SMA75より上)の状態でゴールデンクロスが
    繰り返し発生する状況を作る(いわゆる「押し目からの再上昇」)。"""
    np.random.seed(7)
    n = 260
    t = np.arange(n)
    trend = 1000 + t * 3
    wave = 60 * np.sin(t / 8.0)
    noise = np.random.normal(0, 3, n)
    prices = trend + wave + noise
    df = add_all_indicators(make_df(prices))

    checked_aligned_case = False
    for i in range(120, len(df)):
        sub = df.iloc[: i + 1]
        if _crossed_above(sub["SMA5"], sub["SMA25"]):
            result = evaluate_signal(sub)
            if result["direction"] == "BUY" and result["latest"]["trend"] == "UP":
                assert result["trend_caution"] is False, result
                assert result["cautions"] == [], result
                checked_aligned_case = True
    assert checked_aligned_case, "トレンドと整合するゴールデンクロスがテストデータで発生していない"
    print("=== トレンドと整合する場合はcautionが付かない ===")


def test_volume_surge_adds_reason_and_boosts_score():
    """クロス発生日に出来高が20日平均を大きく上回っていれば、
    出来高確認の根拠が追加され、scoreも1つ増えることを確認する。"""
    np.random.seed(1)
    down = np.linspace(2000, 1500, 100) + np.random.normal(0, 2, 100)
    up = np.linspace(1500, 2000, 40) + np.random.normal(0, 2, 40)
    prices = np.concatenate([down, up])

    cross_day = None
    base_df = add_all_indicators(make_df(prices))
    for i in range(30, len(base_df)):
        sub = base_df.iloc[: i + 1]
        if _crossed_above(sub["SMA5"], sub["SMA25"]):
            cross_day = i
            break
    assert cross_day is not None

    volumes = [1000] * len(prices)
    volumes[cross_day] = 6000  # クロス当日だけ出来高が急増
    df = add_all_indicators(make_df_with_volume(prices, volumes))

    result_without_surge = evaluate_signal(base_df.iloc[: cross_day + 1])
    result_with_surge = evaluate_signal(df.iloc[: cross_day + 1])
    print("=== 出来高急増なし ===", result_without_surge)
    print("=== 出来高急増あり ===", result_with_surge)

    assert result_with_surge["direction"] == "BUY"
    assert any("出来高急増" in r for r in result_with_surge["reasons"])
    assert result_with_surge["score"] == result_without_surge["score"] + 1
    assert result_with_surge["latest"]["vol_ratio"] is not None
    assert result_with_surge["latest"]["vol_ratio"] >= 1.5


def test_range_position_reflects_52week_high_low():
    """52週(取得期間全体)のHigh/Lowに対する終値の位置(range_position)が
    正しく計算されることを確認する。"""
    idx = pd.date_range("2025-01-01", periods=100, freq="B")
    close = np.array([1000.0] * 99 + [1050.0])  # 最終日だけ1050
    high = np.array([1000.0] * 50 + [1200.0] + [1000.0] * 49)  # 51日目に高値1200
    low = np.array([1000.0] * 30 + [800.0] + [1000.0] * 69)    # 31日目に安値800
    df = pd.DataFrame({"Close": close, "High": high, "Low": low}, index=idx)
    df = add_all_indicators(df)
    result = evaluate_signal(df)
    latest = result["latest"]
    print("=== 52週レンジ内の位置 ===", latest["week52_high"], latest["week52_low"], latest["range_position"])
    assert latest["week52_high"] == 1200.0, latest
    assert latest["week52_low"] == 800.0, latest
    expected_position = (1050.0 - 800.0) / (1200.0 - 800.0)
    assert abs(latest["range_position"] - expected_position) < 1e-9, latest


def test_range_position_falls_back_to_close_when_no_high_low():
    """High/Low列が無いデータ(合成テストデータなど)では、Close列で代用して
    range_positionを計算し、エラーにならないことを確認する。"""
    prices_up = np.linspace(1000, 1200, 60)
    df = add_all_indicators(make_df(prices_up))
    result = evaluate_signal(df)
    latest = result["latest"]
    # 単調増加なので、最終日の終値が全期間の最高値と一致し、position=1.0になる
    assert latest["week52_high"] == prices_up.max(), latest
    assert latest["week52_low"] == prices_up.min(), latest
    assert abs(latest["range_position"] - 1.0) < 1e-9, latest


def test_overbought_state_flagged_as_caution():
    # 急騰が続きRSIが極端な水準に達した場合は、過熱警戒(SELL寄り)として
    # 検出されることを確認する(仕様として意図した挙動)
    np.random.seed(3)
    down = np.linspace(2000, 1500, 100) + np.random.normal(0, 2, 100)
    up = np.linspace(1500, 2000, 40) + np.random.normal(0, 2, 40)
    prices = np.concatenate([down, up])
    df = add_all_indicators(make_df(prices))
    result = evaluate_signal(df)
    print("=== 長期急騰後(最終日)の判定 ===", result)
    assert df["RSI14"].iloc[-1] > 70
    assert result["direction"] == "SELL"
    assert any("買われすぎ" in r for r in result["reasons"])


if __name__ == "__main__":
    test_golden_cross_detected_at_the_moment_it_happens()
    test_dead_cross_detected_at_the_moment_it_happens()
    test_rsi_basic_bounds()
    test_trend_caution_flagged_for_buy_against_long_term_downtrend()
    test_no_trend_caution_when_signal_aligns_with_trend()
    test_volume_surge_adds_reason_and_boosts_score()
    test_range_position_reflects_52week_high_low()
    test_range_position_falls_back_to_close_when_no_high_low()
    test_overbought_state_flagged_as_caution()
    print("\nすべてのロジックテストが完了しました（エラーなし）。")
