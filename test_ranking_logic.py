# -*- coding: utf-8 -*-
"""
ranking.py のロジックをネットワーク接続なしで検証するテスト。
yfinance.download をダミー実装に差し替えて、
「価格上限フィルタ」「買いシグナル優先の並び替え」が正しく動くかを確認する。
"""
import numpy as np
import pandas as pd

import ranking


def _make_price_series(n, start, end, seed):
    rng = np.random.default_rng(seed)
    return np.linspace(start, end, n) + rng.normal(0, start * 0.005, n)


def fake_download(codes, **kwargs):
    """
    渡された銘柄コードそれぞれについて、
    ・code の末尾文字で「上昇/下降/横ばい」のパターンを決め
    ・価格帯も文字列長から適当にばらけさせる
    合成データを返す簡易モック。
    """
    idx = pd.date_range("2025-01-01", periods=100, freq="B")
    frames = {}
    for i, code in enumerate(codes):
        seed = abs(hash(code)) % (2**31)
        if i % 3 == 0:
            # 明確な上昇トレンド(ゴールデンクロスが起きやすい)
            down = _make_price_series(60, 1000, 700, seed)
            up = _make_price_series(40, 700, 1000, seed + 1)
            prices = np.concatenate([down, up])
        elif i % 3 == 1:
            # 明確な下降トレンド
            up = _make_price_series(60, 700, 1000, seed)
            down = _make_price_series(40, 1000, 700, seed + 1)
            prices = np.concatenate([up, down])
        else:
            # 横ばい
            prices = _make_price_series(100, 900, 950, seed)

        # 価格水準を銘柄ごとに変える(1500円フィルタのテスト用)
        price_level = 500 + (i * 250) % 3000
        prices = prices / prices.mean() * price_level

        df = pd.DataFrame(
            {"Open": prices, "High": prices * 1.01, "Low": prices * 0.99, "Close": prices, "Volume": 1000},
            index=idx,
        )
        frames[code] = df

    return pd.concat(frames, axis=1)


def test_price_ceiling_filters_out_expensive_stocks():
    ranking.yf.download = fake_download  # モックに差し替え
    universe = [{"code": f"TEST{i}.T", "name": f"テスト{i}"} for i in range(12)]

    result = ranking.build_ranking(universe, price_ceiling=1500, top_n=20)
    print("=== 1500円フィルタ後の候補数 ===", len(result))
    for item in result:
        assert item["result"]["latest"]["close"] <= 1500, "価格上限を超えた銘柄が混入している"


def test_buy_signals_ranked_above_sell_signals():
    ranking.yf.download = fake_download
    universe = [{"code": f"TEST{i}.T", "name": f"テスト{i}"} for i in range(12)]

    result = ranking.build_ranking(universe, price_ceiling=100000, top_n=20)
    directions = [item["result"]["direction"] for item in result]
    print("=== ランキング順の判定 ===", directions)

    # BUYが出た銘柄は、SELLが出た銘柄より必ず上位に来ているはず
    if "BUY" in directions and "SELL" in directions:
        first_buy_idx = directions.index("BUY")
        last_sell_idx = max(i for i, d in enumerate(directions) if d == "SELL")
        assert first_buy_idx < last_sell_idx or directions.count("SELL") == directions[first_buy_idx:].count("SELL")
        # より厳密に: BUYの最後のインデックスが、SELLの最初のインデックスより前であること
        buy_indices = [i for i, d in enumerate(directions) if d == "BUY"]
        sell_indices = [i for i, d in enumerate(directions) if d == "SELL"]
        assert max(buy_indices) < min(sell_indices), "SELL銘柄がBUY銘柄より上位に来ている"


if __name__ == "__main__":
    test_price_ceiling_filters_out_expensive_stocks()
    test_buy_signals_ranked_above_sell_signals()
    print("\nranking.py のロジックテストが完了しました（エラーなし）。")
