# -*- coding: utf-8 -*-
"""
freshness.py (株価データの鮮度判定ロジック)の単体テスト。
ネットワーク接続は不要(jpholidayはオフラインで祝日を計算するライブラリ)。
pytest等のテストフレームワークには依存せず、`python test_freshness.py` で実行できる。
"""
from datetime import date, timedelta

import jpholiday

from freshness import (
    expected_latest_trading_dates,
    is_data_fresh,
    is_trading_day,
    most_recent_trading_day_on_or_before,
    parse_date,
)


def _find_coming_of_age_day(year: int) -> date:
    """「成人の日」(1月の第2月曜、必ず祝日かつ必ず月曜)を検索して返す。
    連休(祝日+週末)をまたぐ逆算のテストに使う、具体的な日付が毎年ズレても
    テストが壊れないようにするためのヘルパー。"""
    for day in range(8, 15):  # 第2月曜は必ずこの範囲に入る
        d = date(year, 1, day)
        if d.weekday() == 0 and jpholiday.is_holiday(d):
            return d
    raise AssertionError(f"{year}年の成人の日が見つかりませんでした")


def test_is_trading_day_excludes_weekends_and_holidays():
    monday_holiday = _find_coming_of_age_day(2027)
    assert is_trading_day(monday_holiday) is False, "祝日なのに営業日と判定されている"
    saturday = monday_holiday - timedelta(days=2)
    assert saturday.weekday() == 5
    assert is_trading_day(saturday) is False, "土曜なのに営業日と判定されている"
    # 前週の金曜は通常営業日のはず(前後が別の祝日と重ならない年で検証)
    friday = monday_holiday - timedelta(days=3)
    assert friday.weekday() == 4
    assert is_trading_day(friday) is True, "平日の金曜が営業日と判定されなかった"
    print("=== 土日・祝日の除外判定 ===")


def test_most_recent_trading_day_skips_weekend_and_holiday_together():
    """「祝日の月曜」から遡ると、間の土日もまとめて飛ばして
    前週の金曜(営業日)にたどり着くことを確認する(連休をまたぐケース)。"""
    monday_holiday = _find_coming_of_age_day(2027)
    friday_before = monday_holiday - timedelta(days=3)
    result = most_recent_trading_day_on_or_before(monday_holiday)
    print("=== 祝日の月曜から遡った結果 ===", result, "(期待値:", friday_before, ")")
    assert result == friday_before


def test_expected_latest_trading_dates_allows_monday_run_to_see_friday_close():
    """月曜(祝日でない通常の月曜)を基準日とした場合、月曜自身の終値
    (大引け後実行を想定)と、前週金曜の終値(寄り付き前実行を想定)の
    どちらも「新鮮」として許容されることを確認する。"""
    # 適当な非祝日の月曜を探す(通常の週であればどの週でもよい)
    d = date(2027, 3, 1)
    while d.weekday() != 0 or not is_trading_day(d):
        d += timedelta(days=1)
    monday = d
    friday_before = monday - timedelta(days=3)
    allowed = expected_latest_trading_dates(monday)
    print("=== 月曜基準の許容日付 ===", allowed)
    assert monday in allowed
    assert friday_before in allowed
    assert len(allowed) == 2


def test_is_data_fresh_true_for_recent_trading_day():
    monday = date(2027, 3, 1)
    while monday.weekday() != 0 or not is_trading_day(monday):
        monday += timedelta(days=1)
    friday_before = monday - timedelta(days=3)
    assert is_data_fresh(friday_before.strftime("%Y-%m-%d"), today=monday) is True
    print("=== 月曜に前週金曜のデータは新鮮 ===")


def test_is_data_fresh_false_for_stale_date():
    today = date(2027, 6, 15)
    stale_date = today - timedelta(days=10)
    result = is_data_fresh(stale_date.strftime("%Y-%m-%d"), today=today)
    print("=== 10日前のデータ ===", result)
    assert result is False


def test_is_data_fresh_none_when_unparseable():
    assert is_data_fresh(None) is None
    assert is_data_fresh("") is None
    assert is_data_fresh("not-a-date") is None
    print("=== 日付が読み取れない場合はNone ===")


def test_parse_date_roundtrip():
    d = date(2026, 9, 25)
    assert parse_date(d.strftime("%Y-%m-%d")) == d
    assert parse_date(None) is None
    assert parse_date("invalid") is None
    print("=== 日付文字列のパース ===")


if __name__ == "__main__":
    test_is_trading_day_excludes_weekends_and_holidays()
    test_most_recent_trading_day_skips_weekend_and_holiday_together()
    test_expected_latest_trading_dates_allows_monday_run_to_see_friday_close()
    test_is_data_fresh_true_for_recent_trading_day()
    test_is_data_fresh_false_for_stale_date()
    test_is_data_fresh_none_when_unparseable()
    test_parse_date_roundtrip()
    print("\nfreshness.py のロジックテストが完了しました(エラーなし)。")
