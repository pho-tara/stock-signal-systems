# -*- coding: utf-8 -*-
"""
news_sentiment.py のキーワード判定ロジック・AI判定へのフォールバック処理の単体テスト。
ネットワーク接続は使わない(score_headlines関数、および
ANTHROPIC_API_KEY未設定時のフォールバック挙動だけをテストする)。
pytest等のテストフレームワークには依存せず、`python test_news_sentiment.py` で実行できる。
"""
import os

import news_sentiment
from news_sentiment import (
    attach_news_sentiment_for_lists,
    get_ai_news_sentiment,
    get_news_sentiment,
    score_headlines,
)


def test_positive_headline():
    result = score_headlines(["A社、上期営業利益が過去最高益を更新"])
    assert result["sentiment"] == "POSITIVE", result
    assert result["positive_count"] >= 1
    assert result["negative_count"] == 0
    assert result["method"] == "KEYWORD"
    print("=== ポジティブ見出しの判定 ===", result)


def test_negative_headline():
    result = score_headlines(["B社、通期業績を下方修正 特別損失を計上"])
    assert result["sentiment"] == "NEGATIVE", result
    assert result["negative_count"] >= 1
    print("=== ネガティブ見出しの判定 ===", result)


def test_neutral_when_no_keywords():
    result = score_headlines(["C社、新工場の完成式典を開催"])
    assert result["sentiment"] == "NEUTRAL", result
    assert result["positive_count"] == 0
    assert result["negative_count"] == 0
    print("=== キーワードなし(中立)の判定 ===", result)


def test_neutral_when_tied():
    """好材料・悪材料の両方のキーワードを含む見出しは、
    どちらの票にも数えず(見出し単位でNEUTRAL扱い)、全体もNEUTRALになる。"""
    result = score_headlines(["D社、増益も一部事業で減益 明暗分かれる"])
    assert result["sentiment"] == "NEUTRAL", result
    assert result["positive_count"] == result["negative_count"] == 0, result
    print("=== 好材料・悪材料が拮抗した場合の判定 ===", result)


def test_headline_with_multiple_keywords_counts_as_one_vote():
    """1つの見出しに好材料キーワードが複数含まれていても、
    見出し単位では1票としてしか数えない(以前の「キーワード出現回数」方式では
    "増収増益"が"増収"と"増益"の2件として水増しされていた問題の修正確認)。"""
    result = score_headlines(["F社、増収増益で過去最高益を更新し株価は続伸"])
    assert result["sentiment"] == "POSITIVE", result
    assert result["positive_count"] == 1, result
    assert result["negative_count"] == 0, result
    print("=== 1見出し内の複数キーワードは1票として扱う ===", result)


def test_empty_headlines_is_neutral():
    result = score_headlines([])
    assert result["sentiment"] == "NEUTRAL"
    assert result["sample_headline"] is None
    print("=== 見出しが取得できなかった場合の判定 ===", result)


def test_multiple_headlines_majority_wins():
    # 見出し単位の多数決: 好材料見出し2件・悪材料見出し1件なのでPOSITIVEになる。
    # ("増収増益で最高益"は複数の好材料キーワードを含むが、見出しとしては1票)
    headlines = [
        "E社、増収増益で最高益",
        "E社、株式分割を発表",
        "E社、一部製品をリコール",
    ]
    result = score_headlines(headlines)
    assert result["sentiment"] == "POSITIVE", result
    assert result["positive_count"] == 2, result
    assert result["negative_count"] == 1, result
    print("=== 複数見出しの多数決判定 ===", result)


def test_ai_sentiment_returns_none_without_api_key():
    """ANTHROPIC_API_KEYが未設定なら、AI判定は呼ばずにNoneを返す。"""
    had_key = "ANTHROPIC_API_KEY" in os.environ
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        result = get_ai_news_sentiment("A社", ["A社、最高益を更新"])
        assert result is None, result
        print("=== APIキー未設定時、AI判定はNoneを返す ===", result)
    finally:
        if had_key:
            os.environ["ANTHROPIC_API_KEY"] = saved


def test_ai_sentiment_returns_none_without_headlines():
    """見出しが1件も無ければ、APIキーがあってもAI判定は呼ばずにNoneを返す。"""
    saved = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "dummy-key-for-test"
    try:
        result = get_ai_news_sentiment("A社", [])
        assert result is None, result
        print("=== 見出しが無い場合、AI判定はNoneを返す ===", result)
    finally:
        if saved is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = saved


def test_get_news_sentiment_falls_back_to_keyword_without_api_key():
    """use_ai=True でもANTHROPIC_API_KEYが無ければ、キーワード判定にフォールバックする。"""
    had_key = "ANTHROPIC_API_KEY" in os.environ
    saved_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    original_fetch = news_sentiment.fetch_headlines
    news_sentiment.fetch_headlines = lambda company_name, max_items=5: ["テスト社、上方修正を発表"]
    try:
        result = get_news_sentiment("テスト社", use_ai=True)
        assert result["method"] == "KEYWORD", result
        assert result["sentiment"] == "POSITIVE", result
        print("=== APIキー未設定時、get_news_sentimentはキーワード判定にフォールバック ===", result)
    finally:
        news_sentiment.fetch_headlines = original_fetch
        if had_key:
            os.environ["ANTHROPIC_API_KEY"] = saved_key


def test_get_news_sentiment_default_is_keyword():
    """use_ai を指定しない場合はデフォルトでキーワード判定になる。"""
    original_fetch = news_sentiment.fetch_headlines
    news_sentiment.fetch_headlines = lambda company_name, max_items=5: ["テスト社、上方修正を発表"]
    try:
        result = get_news_sentiment("テスト社")
        assert result["method"] == "KEYWORD", result
        print("=== use_ai省略時はキーワード判定がデフォルト ===", result)
    finally:
        news_sentiment.fetch_headlines = original_fetch


def test_attach_news_sentiment_for_lists_dedupes_by_code():
    """同じ銘柄コードが複数のリストに登場する場合、
    ニュース取得(get_news_sentiment)は銘柄コードごとに1回だけ呼ばれ、
    2回目以降はキャッシュされた結果が使い回されることを確認する。"""
    call_count = {"n": 0}
    original = news_sentiment.get_news_sentiment

    def fake_get_news_sentiment(company_name, use_ai=False):
        call_count["n"] += 1
        return {"sentiment": "POSITIVE", "method": "KEYWORD", "sample_headline": company_name,
                "positive_count": 1, "negative_count": 0, "headline_count": 1}

    news_sentiment.get_news_sentiment = fake_get_news_sentiment
    try:
        watch = [{"code": "7203.T", "name": "トヨタ自動車", "result": {}}]
        ranking = [
            {"code": "7203.T", "name": "トヨタ自動車", "result": {}},  # ウォッチリストと重複
            {"code": "9984.T", "name": "ソフトバンクグループ", "result": {}},
        ]
        attach_news_sentiment_for_lists(watch, ranking, sleep_seconds=0)

        assert call_count["n"] == 2, f"重複銘柄があるのに呼び出し回数が想定と異なる: {call_count['n']}"
        assert watch[0]["news"]["sentiment"] == "POSITIVE"
        assert ranking[0]["news"] == watch[0]["news"], "同じ銘柄コードの結果が使い回されていない"
        assert ranking[1]["news"]["sentiment"] == "POSITIVE"
        print("=== 銘柄コード重複時のニュース取得キャッシュ ===", "call_count=", call_count["n"])
    finally:
        news_sentiment.get_news_sentiment = original


if __name__ == "__main__":
    test_positive_headline()
    test_negative_headline()
    test_neutral_when_no_keywords()
    test_neutral_when_tied()
    test_headline_with_multiple_keywords_counts_as_one_vote()
    test_empty_headlines_is_neutral()
    test_multiple_headlines_majority_wins()
    test_ai_sentiment_returns_none_without_api_key()
    test_ai_sentiment_returns_none_without_headlines()
    test_get_news_sentiment_falls_back_to_keyword_without_api_key()
    test_get_news_sentiment_default_is_keyword()
    test_attach_news_sentiment_for_lists_dedupes_by_code()
    print("\nnews_sentiment.py のロジックテストが完了しました(エラーなし)。")
