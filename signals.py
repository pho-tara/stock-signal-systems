# -*- coding: utf-8 -*-
"""
売買シグナル判定ロジック。

考え方:
- ゴールデンクロス/デッドクロス(SMA5とSMA25)
- RSIの売られすぎ/買われすぎからの回復
- MACDのクロス
の3系統をそれぞれ判定し、複数が同時に成立するほど「強いシグナル」として扱う(score)。

これに加えて、参考情報として以下の2つを付加する(scoreには影響しない別枠の情報):
- 出来高確認: クロス系シグナル発生時に出来高が20日平均を大きく上回っていれば、
  そのクロスの信頼度が高いとみなし、根拠(reasons)に追加してscoreを加点する。
- トレンド注意(cautions): 長期線(SMA75)に対して逆行する方向のシグナルが出た場合
  (下降トレンド中のBUY、上昇トレンド中のSELL)、「見せかけの反発/一時的な調整」の
  可能性がある注意書きを追加する。こちらはscoreには加減算しないが、
  trend_cautionフラグとして呼び出し側(通知要否の判定など)から参照できるようにする。
- 52週レンジ内の位置(week52_high/week52_low/range_position): 渡されたデータフレーム
  全期間(呼び出し側で約1年分を取得する想定)の高値・安値に対して、現在の終値が
  どのあたりに位置するか(0=直近安値、1=直近高値)を計算する。あくまで「その銘柄
  自身の直近の値動きの中でどのあたりか」を示す簡易的な参考情報であり、PER/PBRの
  ような企業価値そのものの割安度を示すものではない(そちらはvaluation.pyが担当する)。
  こちらもscoreには一切影響しない。

これは一般的なテクニカル分析の手法を組み合わせたものであり、
将来の値動きを保証するものではない。投資判断は自己責任で行うこと。
"""
import pandas as pd

VOLUME_SURGE_RATIO = 1.5  # 20日平均出来高に対してこの倍率以上なら「出来高急増」とみなす


def _crossed_above(series_a: pd.Series, series_b: pd.Series) -> bool:
    """直近の足でaがbを下から上に抜けたか"""
    if len(series_a) < 2 or len(series_b) < 2:
        return False
    prev_a, prev_b = series_a.iloc[-2], series_b.iloc[-2]
    curr_a, curr_b = series_a.iloc[-1], series_b.iloc[-1]
    if pd.isna(prev_a) or pd.isna(prev_b) or pd.isna(curr_a) or pd.isna(curr_b):
        return False
    return prev_a <= prev_b and curr_a > curr_b


def _crossed_below(series_a: pd.Series, series_b: pd.Series) -> bool:
    """直近の足でaがbを上から下に抜けたか"""
    if len(series_a) < 2 or len(series_b) < 2:
        return False
    prev_a, prev_b = series_a.iloc[-2], series_b.iloc[-2]
    curr_a, curr_b = series_a.iloc[-1], series_b.iloc[-1]
    if pd.isna(prev_a) or pd.isna(prev_b) or pd.isna(curr_a) or pd.isna(curr_b):
        return False
    return prev_a >= prev_b and curr_a < curr_b


def evaluate_signal(df: pd.DataFrame) -> dict:
    """
    指標計算済みのDataFrameを受け取り、直近時点でのシグナル判定結果を返す。

    戻り値:
        {
            "direction": "BUY" | "SELL" | "NONE",
            "score": int (1〜3, 一致した根拠の数),
            "reasons": [str, ...],
            "latest": {close, sma5, sma25, sma75, rsi14, macd, macd_signal,
                       trend, vol_ratio, week52_high, week52_low, range_position}
        }
    """
    latest = df.iloc[-1]
    reasons_buy = []
    reasons_sell = []
    golden_cross = _crossed_above(df["SMA5"], df["SMA25"])
    dead_cross = _crossed_below(df["SMA5"], df["SMA25"])
    macd_golden_cross = _crossed_above(df["MACD"], df["MACD_SIGNAL"])
    macd_dead_cross = _crossed_below(df["MACD"], df["MACD_SIGNAL"])

    # 1) ゴールデンクロス/デッドクロス (SMA5 x SMA25)
    if golden_cross:
        reasons_buy.append("ゴールデンクロス(SMA5がSMA25を上抜け)")
    if dead_cross:
        reasons_sell.append("デッドクロス(SMA5がSMA25を下抜け)")

    # 2) RSIの売られすぎ/買われすぎからの回復
    rsi_series = df["RSI14"]
    if len(rsi_series) >= 2 and not pd.isna(rsi_series.iloc[-2]) and not pd.isna(rsi_series.iloc[-1]):
        if rsi_series.iloc[-2] < 30 <= rsi_series.iloc[-1]:
            reasons_buy.append("RSIが30を上抜け(売られすぎからの反発)")
        if rsi_series.iloc[-2] > 70 >= rsi_series.iloc[-1]:
            reasons_sell.append("RSIが70を下抜け(買われすぎからの反落)")
        if rsi_series.iloc[-1] >= 70:
            reasons_sell.append(f"RSIが買われすぎ水準({rsi_series.iloc[-1]:.1f})")
        if rsi_series.iloc[-1] <= 30:
            reasons_buy.append(f"RSIが売られすぎ水準({rsi_series.iloc[-1]:.1f})")

    # 3) MACDクロス
    if macd_golden_cross:
        reasons_buy.append("MACDがシグナルを上抜け(ゴールデンクロス)")
    if macd_dead_cross:
        reasons_sell.append("MACDがシグナルを下抜け(デッドクロス)")

    # 4) 出来高確認(参考加点): クロス発生時に出来高が20日平均を大きく
    #    上回っていれば、そのクロスの信頼度が高いとみなして根拠を追加する。
    #    (クロス自体が起きていない場合は出来高だけでは根拠にしない)
    vol_ratio = None
    volume = latest.get("Volume")
    vol_sma20 = latest.get("VOL_SMA20")
    if volume is not None and vol_sma20 is not None and not pd.isna(volume) and not pd.isna(vol_sma20) and vol_sma20 > 0:
        vol_ratio = float(volume) / float(vol_sma20)
        if vol_ratio >= VOLUME_SURGE_RATIO:
            if golden_cross or macd_golden_cross:
                reasons_buy.append(f"出来高急増を伴う(直近20日平均比{vol_ratio:.1f}倍)")
            if dead_cross or macd_dead_cross:
                reasons_sell.append(f"出来高急増を伴う(直近20日平均比{vol_ratio:.1f}倍)")

    latest_close = float(latest["Close"])
    sma75 = None if pd.isna(latest.get("SMA75")) else float(latest["SMA75"])
    trend = None
    if sma75 is not None:
        trend = "UP" if latest_close > sma75 else "DOWN"

    # 6) 52週(取得期間全体)レンジ内の位置(参考情報。scoreには影響しない)。
    #    High/Low列が無いデータ(合成テストデータなど)ではCloseで代用する。
    high_col = df["High"] if "High" in df.columns else df["Close"]
    low_col = df["Low"] if "Low" in df.columns else df["Close"]
    week52_high = float(high_col.max()) if len(high_col.dropna()) > 0 else None
    week52_low = float(low_col.min()) if len(low_col.dropna()) > 0 else None
    range_position = None
    if week52_high is not None and week52_low is not None and week52_high > week52_low:
        range_position = (latest_close - week52_low) / (week52_high - week52_low)
        range_position = max(0.0, min(1.0, range_position))

    latest_info = {
        "close": latest_close,
        "sma5": None if pd.isna(latest.get("SMA5")) else float(latest["SMA5"]),
        "sma25": None if pd.isna(latest.get("SMA25")) else float(latest["SMA25"]),
        "sma75": sma75,
        "rsi14": None if pd.isna(latest.get("RSI14")) else float(latest["RSI14"]),
        "macd": None if pd.isna(latest.get("MACD")) else float(latest["MACD"]),
        "macd_signal": None if pd.isna(latest.get("MACD_SIGNAL")) else float(latest["MACD_SIGNAL"]),
        "trend": trend,
        "vol_ratio": vol_ratio,
        "week52_high": week52_high,
        "week52_low": week52_low,
        "range_position": range_position,
    }

    if len(reasons_buy) >= len(reasons_sell) and reasons_buy:
        direction, score, reasons = "BUY", len(reasons_buy), reasons_buy
    elif reasons_sell:
        direction, score, reasons = "SELL", len(reasons_sell), reasons_sell
    else:
        direction, score, reasons = "NONE", 0, []

    # 5) トレンド注意(参考情報。scoreには影響させない):
    #    長期トレンド(SMA75)と逆行する方向のシグナルは、
    #    「見せかけの反発/一時的な調整」の可能性を注意書きとして添える。
    cautions = []
    trend_caution = False
    if direction == "BUY" and trend == "DOWN":
        cautions.append("長期トレンド(SMA75)は下向きです。反発が一時的な戻りにとどまる可能性があります。")
        trend_caution = True
    elif direction == "SELL" and trend == "UP":
        cautions.append("長期トレンド(SMA75)は上向きです。下落が一時的な調整にとどまる可能性があります。")
        trend_caution = True

    return {
        "direction": direction,
        "score": score,
        "reasons": reasons,
        "cautions": cautions,
        "trend_caution": trend_caution,
        "latest": latest_info,
    }
