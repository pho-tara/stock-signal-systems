# -*- coding: utf-8 -*-
"""
dashboard.py のうち、HTML生成ではなく「判定ロジック」にあたる部分
(52週レンジの3分類、中長期の目線ラベル)の単体テスト。
pytest等のテストフレームワークには依存せず、`python test_dashboard.py` で実行できる。
"""
from datetime import date

from dashboard import (
    MID_LONG_TERM_OUTLOOK,
    _analyst_html,
    _data_basis_date,
    _data_freshness_html,
    _mid_long_term_outlook,
    _range_position_bucket,
    _stale_row_note,
    build_dashboard_html,
)


def test_range_position_bucket_boundaries():
    assert _range_position_bucket(0.0)[1] == "安値圏"
    assert _range_position_bucket(0.25)[1] == "安値圏"
    assert _range_position_bucket(0.26)[1] == "中間"
    assert _range_position_bucket(0.75)[1] == "中間"
    assert _range_position_bucket(0.76)[1] == "高値圏"
    assert _range_position_bucket(1.0)[1] == "高値圏"
    print("=== 52週レンジ3分類の境界値 ===")


def test_mid_long_term_outlook_covers_all_combinations():
    """UP/DOWN × 3分類の6通りすべてに、意味のあるラベルが定義されていることを確認する。"""
    for trend in ("UP", "DOWN"):
        for position in (0.1, 0.5, 0.9):
            result = _mid_long_term_outlook(trend, position)
            assert result is not None, (trend, position)
            color, label = result
            assert label, (trend, position)
    assert len(MID_LONG_TERM_OUTLOOK) == 6
    print("=== 中長期の目線: 全組み合わせに定義あり ===")


def test_mid_long_term_outlook_none_when_data_missing():
    """trendまたはrange_positionが無い(None)場合は判定できず、Noneを返す。"""
    assert _mid_long_term_outlook(None, 0.5) is None
    assert _mid_long_term_outlook("UP", None) is None
    assert _mid_long_term_outlook(None, None) is None
    print("=== データ不足時はNone ===")


def test_mid_long_term_outlook_up_low_range_is_buy_candidate():
    """上昇トレンド中に52週安値圏まで下げている場合は「押し目」の目安になる。"""
    color, label = _mid_long_term_outlook("UP", 0.1)
    assert "押し目" in label or "買い場" in label, label
    print("=== 上昇トレンド+安値圏 ===", label)


def test_mid_long_term_outlook_down_high_range_is_caution():
    """下降トレンド中に52週高値圏にある場合は警戒的なラベルになる。"""
    color, label = _mid_long_term_outlook("DOWN", 0.9)
    assert "調整" in label or "戻り" in label, label
    print("=== 下降トレンド+高値圏 ===", label)


def _make_item(close=1000.0, analyst=None, latest_date=None, code="TEST.T"):
    result = {
        "direction": "NONE", "score": 0, "reasons": [], "cautions": [], "trend_caution": False,
        "latest": {
            "close": close, "sma5": None, "sma25": None, "sma75": None, "rsi14": None,
            "macd": None, "macd_signal": None, "trend": None, "vol_ratio": None,
            "week52_high": None, "week52_low": None, "range_position": None,
            "latest_date": latest_date,
        },
    }
    return {"code": code, "name": "テスト銘柄", "result": result, "analyst": analyst}


def test_analyst_html_shows_dash_when_no_data():
    """アナリスト予想が取得できなかった(None)銘柄は「—」表示になる。"""
    html_out = _analyst_html(_make_item(analyst=None))
    assert "—" in html_out
    print("=== アナリスト予想なし ===")


def test_analyst_html_shows_upside_percentage():
    """目標株価(平均)と現在の終値から、現値比の上振れ率が計算されて表示される。"""
    item = _make_item(close=1000.0, analyst={
        "target_mean": 1200.0, "target_high": 1400.0, "target_low": 1000.0,
        "num_analysts": 8, "recommendation_key": "buy",
    })
    html_out = _analyst_html(item)
    print("=== 上振れ率あり ===", html_out)
    assert "1,200円" in html_out
    assert "+20.0%" in html_out, html_out
    assert "買い" in html_out
    assert "8" in html_out


def test_analyst_html_shows_downside_percentage():
    """目標株価が現在値より低い場合は、マイナスの下振れ率として表示される。"""
    item = _make_item(close=1000.0, analyst={
        "target_mean": 800.0, "target_high": 900.0, "target_low": 700.0,
        "num_analysts": 3, "recommendation_key": "underperform",
    })
    html_out = _analyst_html(item)
    print("=== 下振れ率 ===", html_out)
    assert "-20.0%" in html_out, html_out
    assert "弱気" in html_out


def test_analyst_html_unknown_recommendation_key_falls_back_gracefully():
    """未知のrecommendationKeyでもエラーにならず、そのままラベルとして表示する。"""
    item = _make_item(analyst={
        "target_mean": None, "target_high": None, "target_low": None,
        "num_analysts": None, "recommendation_key": "some_future_value",
    })
    html_out = _analyst_html(item)
    print("=== 未知のレーティング値 ===", html_out)
    assert "some_future_value" in html_out


def test_data_basis_date_picks_majority_date():
    """複数銘柄のうち多数派の日付を、ページ全体のデータ基準日として採用する。"""
    items = [
        _make_item(latest_date="2026-09-25", code="A.T"),
        _make_item(latest_date="2026-09-25", code="B.T"),
        _make_item(latest_date="2026-09-24", code="C.T"),  # 1銘柄だけ古い
    ]
    basis = _data_basis_date(items)
    print("=== 多数派の基準日 ===", basis)
    assert basis == "2026-09-25"


def test_data_basis_date_tie_breaks_to_newer_date():
    """同数の場合は、より新しい日付を優先する。"""
    items = [
        _make_item(latest_date="2026-09-25", code="A.T"),
        _make_item(latest_date="2026-09-24", code="B.T"),
    ]
    basis = _data_basis_date(items)
    print("=== 同数タイブレークの基準日 ===", basis)
    assert basis == "2026-09-25"


def test_data_basis_date_none_when_no_dates_available():
    """latest_dateが1件も無い場合はNoneを返す(古いバージョンのデータ等)。"""
    items = [_make_item(latest_date=None, code="A.T")]
    assert _data_basis_date(items) is None
    print("=== 基準日データなし ===")


def test_stale_row_note_flags_row_older_than_basis_date():
    """ページ全体の基準日より古いデータの銘柄には、個別の注意書きが付く。"""
    item = _make_item(latest_date="2026-09-24", code="C.T")
    note = _stale_row_note(item, basis_date="2026-09-25")
    print("=== 個別の古いデータ注意書き ===", note)
    assert "2026-09-25" in note
    assert "2026-09-24" in note
    assert "古い可能性があります" in note


def test_stale_row_note_empty_when_matching_basis_date():
    """基準日と一致する銘柄には、個別の注意書きは表示されない。"""
    item = _make_item(latest_date="2026-09-25", code="A.T")
    note = _stale_row_note(item, basis_date="2026-09-25")
    assert note == ""
    print("=== 基準日と一致する場合は注意書きなし ===")


def test_data_freshness_html_shows_warning_when_basis_date_is_stale():
    """基準日そのものが直近の営業日として不自然に古い場合は、警告文が表示される。"""
    html_out = _data_freshness_html("2026-09-01", today=date(2026, 9, 25))
    print("=== 基準日が古い場合の表示 ===", html_out)
    assert "2026-09-01" in html_out
    assert "直近の営業日のものではない可能性があります" in html_out


def test_data_freshness_html_no_warning_when_basis_date_is_fresh():
    """基準日が直近の営業日相当であれば、警告文は表示されない。"""
    # 2026-09-25(金)を基準日・当日として指定(通常の平日なので新鮮)
    html_out = _data_freshness_html("2026-09-25", today=date(2026, 9, 25))
    print("=== 基準日が新鮮な場合の表示 ===", html_out)
    assert "2026-09-25" in html_out
    assert "直近の営業日のものではない可能性があります" not in html_out


def test_data_freshness_html_empty_when_no_basis_date():
    assert _data_freshness_html(None) == ""
    print("=== 基準日なしの場合は非表示 ===")


def test_dashboard_renders_outlook_column_without_error():
    """ダッシュボードのHTML生成が、中長期の目線列を含めてエラーなく完了することを確認する。"""
    result = {
        "direction": "BUY", "score": 1, "reasons": ["ゴールデンクロス(SMA5がSMA25を上抜け)"],
        "cautions": [], "trend_caution": False,
        "latest": {
            "close": 1000.0, "sma5": 990.0, "sma25": 980.0, "sma75": 900.0, "rsi14": 55.0,
            "macd": 1.0, "macd_signal": 0.5, "trend": "UP", "vol_ratio": None,
            "week52_high": 1200.0, "week52_low": 800.0, "range_position": 0.5,
        },
    }
    result["latest"]["latest_date"] = "2026-09-25"
    items = [{"code": "TEST.T", "name": "テスト銘柄", "result": result, "news": None, "valuation": None,
              "analyst": {"target_mean": 1100.0, "target_high": 1300.0, "target_low": 900.0,
                          "num_analysts": 5, "recommendation_key": "buy"}}]
    html_out = build_dashboard_html(items, holdings=[], ranking=[], ranking_price_ceiling=1500, github_repo=None)
    assert "中長期の目線" in html_out
    assert "上昇トレンド継続中" in html_out
    assert "アナリスト予想" in html_out
    assert "目標株価(平均) 1,100円" in html_out
    assert "データ基準日: 2026-09-25" in html_out
    print("=== ダッシュボード生成(中長期の目線列・アナリスト予想列・データ基準日を含む) ===")


def test_dashboard_flags_outlier_row_with_stale_data():
    """複数銘柄のうち1銘柄だけデータ日付が古い場合、その行にだけ個別の注意書きが表示される。"""
    fresh_item = _make_item(latest_date="2026-09-25", code="1111.T")
    stale_item = _make_item(latest_date="2026-09-18", code="2222.T")
    html_out = build_dashboard_html([fresh_item, stale_item], holdings=[], ranking=[],
                                     ranking_price_ceiling=1500, github_repo=None)
    print("=== 一部銘柄だけ古いデータの場合 ===")
    assert "データ基準日: 2026-09-25" in html_out
    assert "この銘柄のデータはページ全体の基準日" in html_out
    assert html_out.count("この銘柄のデータはページ全体の基準日") == 1, "古い銘柄だけに注意書きが付くはず"


if __name__ == "__main__":
    test_range_position_bucket_boundaries()
    test_mid_long_term_outlook_covers_all_combinations()
    test_mid_long_term_outlook_none_when_data_missing()
    test_mid_long_term_outlook_up_low_range_is_buy_candidate()
    test_mid_long_term_outlook_down_high_range_is_caution()
    test_analyst_html_shows_dash_when_no_data()
    test_analyst_html_shows_upside_percentage()
    test_analyst_html_shows_downside_percentage()
    test_analyst_html_unknown_recommendation_key_falls_back_gracefully()
    test_data_basis_date_picks_majority_date()
    test_data_basis_date_tie_breaks_to_newer_date()
    test_data_basis_date_none_when_no_dates_available()
    test_stale_row_note_flags_row_older_than_basis_date()
    test_stale_row_note_empty_when_matching_basis_date()
    test_data_freshness_html_shows_warning_when_basis_date_is_stale()
    test_data_freshness_html_no_warning_when_basis_date_is_fresh()
    test_data_freshness_html_empty_when_no_basis_date()
    test_dashboard_renders_outlook_column_without_error()
    test_dashboard_flags_outlier_row_with_stale_data()
    print("\ndashboard.py のロジックテストが完了しました(エラーなし)。")
