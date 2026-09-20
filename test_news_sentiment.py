# -*- coding: utf-8 -*-
"""
news_sentiment.py のキーワード判定ロジック・AI判定へのフォールバック処理の単体テスト。
ネットワーク接続は使わない(score_headlines関数、および
ANTHROPIC_API_KEY未設定時のフォールバック挙動だけをテストする)。
pytest等のテストフレームワークには依存せず、`python test_news_sentiment.py` で実行できる。
"""
import os

import news_sentiment
from news_sentiment import get_ai_news_sentiment, get_news_sentiment, score_headlines


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
    result = score_headlines(["D社、増益も一部事業で減益 明暗分かれる"])
    assert result["sentiment"] == "NEUTRAL", result
    assert result["positive_count"] == result["negative_count"] == 1
    print("=== 好材料・悪材料が拮抗した場合の判定 ===", result)


def test_empty_headlines_is_neutral():
    result = score_headlines([])
    assert result["sentiment"] == "NEUTRAL"
    assert result["sample_headline"] is None
    print("=== 見出しが取得できなかった場合の判定 ===", result)


def test_multiple_headlines_majority_wins():
    # キーワードは部分一致で数えるため、1つの見出しに複数キーワードが
    # 含まれることもある(例: "増収増益"は"増収"と"増益"の両方にヒット)。
    # ここでは正確な件数ではなく、好材料側が優勢になることだけを確認する。
    headlines = [
        "E社、増収増益で最高益",
        "E社、株式分割を発表",
        "E社、一部製品をリコール",
    ]
    result = score_headlines(headlines)
    assert result["sentiment"] == "POSITIVE", result
    assert result["positive_count"] > result["negative_count"], result
    assert result["negative_count"] >= 1, result
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


if __name__ == "__main__":
    test_positive_headline()
    test_negative_headline()
    test_neutral_when_no_keywords()
    test_neutral_when_tied()
    test_empty_headlines_is_neutral()
    test_multiple_headlines_majority_wins()
    test_ai_sentiment_returns_none_without_api_key()
    test_ai_sentiment_returns_none_without_headlines()
    test_get_news_sentiment_falls_back_to_keyword_without_api_key()
    test_get_news_sentiment_default_is_keyword()
    print("\nnews_sentiment.py のロジックテストが完了しました(エラーなし)。")
