# -*- coding: utf-8 -*-
"""
テクニカル指標の計算ロジック。
pandasのみに依存し、外部ライブラリ(ta, ta-lib等)は使わない。
"""
import pandas as pd


def sma(close: pd.Series, window: int) -> pd.Series:
    """単純移動平均線"""
    return close.rolling(window=window).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """RSI (Wilderの平滑化方式)"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi_value = 100 - (100 / (1 + rs))
    # 損失が完全にゼロ(avg_loss=0)の場合はRSI=100とする
    rsi_value = rsi_value.where(avg_loss != 0, 100.0)
    return rsi_value


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD線・シグナル線・ヒストグラムを返す"""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    OHLCVデータフレーム(Close列必須)にすべてのテクニカル指標列を追加して返す。
    Volume列がある場合は、出来高の20日移動平均(VOL_SMA20)も追加する
    (クロス系シグナルが出来高の増加を伴っているかの確認に使う)。
    """
    out = df.copy()
    out["SMA5"] = sma(out["Close"], 5)
    out["SMA25"] = sma(out["Close"], 25)
    out["SMA75"] = sma(out["Close"], 75)
    out["RSI14"] = rsi(out["Close"], 14)
    macd_line, signal_line, hist = macd(out["Close"])
    out["MACD"] = macd_line
    out["MACD_SIGNAL"] = signal_line
    out["MACD_HIST"] = hist
    if "Volume" in out.columns:
        out["VOL_SMA20"] = out["Volume"].rolling(window=20, min_periods=20).mean()
    else:
        out["VOL_SMA20"] = float("nan")
    return out
