# -*- coding: utf-8 -*-
"""
株価データの鮮度(表示している終値が、実際に直近の営業日のものかどうか)を判定する。

このダッシュボードは静的HTMLとして生成されるため、ページを開いた時点では
「表示されている株価データが、実際にいつのものか」が分からない。
yfinance側の一時的な不調(古いキャッシュが返ってくる、取得が一部失敗するなど)で、
気づかないまま古いデータを見続けてしまうことを防ぐための参考情報を計算する。

単純に「本日から何日前か」で判定すると、土日や日本の祝日(特にゴールデンウィークの
ような連休)の直後は、正常な状態でも数日分古い日付になってしまい誤判定する。
そのため、日本の祝日を認識できるjpholidayライブラリを使って「直近の実際の営業日」を
土日・祝日をスキップしながら逆算し、そのいずれかと一致していれば「新鮮」とみなす。

このモジュールの判定結果は表示用の参考情報であり、テクニカルシグナル(signals.py)
の判定・スコアには一切影響しない。
"""
from datetime import date, datetime, timedelta

import jpholiday

# 万一の無限ループ防止(通常は数日以内の遡りで見つかる)。
MAX_LOOKBACK_DAYS = 30


def is_trading_day(d: date) -> bool:
    """土日・日本の祝日ではない日を「営業日」とみなす簡易判定。
    (年末年始の東証独自の休場日など、祝日カレンダーだけでは拾えないごく一部の
    例外もあるが、ここでは一般的な祝日判定で近似する。過剰検知を避けるための
    参考情報であり、判定に多少の誤差があっても実害は小さい)。"""
    return d.weekday() < 5 and not jpholiday.is_holiday(d)


def most_recent_trading_day_on_or_before(d: date) -> date:
    """dを含めて遡り、直近の営業日を返す。"""
    cur = d
    for _ in range(MAX_LOOKBACK_DAYS):
        if is_trading_day(cur):
            return cur
        cur -= timedelta(days=1)
    return cur  # 万一見つからなくても最後の値を返す(呼び出し側は許容範囲を広めに取る)


def expected_latest_trading_dates(today: date) -> set:
    """当日の実行タイミングが「寄り付き前の朝実行」「大引け後の実行」の
    どちらであっても許容できるよう、「本日までの直近営業日」と
    「その1つ前の営業日」の両方を許容範囲とする。"""
    d1 = most_recent_trading_day_on_or_before(today)
    d2 = most_recent_trading_day_on_or_before(d1 - timedelta(days=1))
    return {d1, d2}


def parse_date(date_str) -> date | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def is_data_fresh(latest_date_str, today: date | None = None):
    """latest_date_str("YYYY-MM-DD")が、todayを基準に見て「直近の営業日」の
    データとして自然な範囲かどうかを判定する。

    戻り値: True(新鮮) / False(古い可能性がある) / None(latest_date_strが
    読み取れず判定不能。呼び出し側は表示を省略すること)。
    """
    if today is None:
        today = date.today()
    latest_date = parse_date(latest_date_str)
    if latest_date is None:
        return None
    return latest_date in expected_latest_trading_dates(today)
