# -*- coding: utf-8 -*-
"""
ニュース見出しからのポジティブ/ネガティブ判定(無料のキーワード判定 + 任意でAI判定)。

仕組み:
1. Googleニュースの検索RSS(無料・APIキー不要)から、銘柄名で検索した
   最新ニュースの見出しを取得する。
2a. [無料・デフォルト] 見出しの中に好材料/悪材料を示すキーワードが
    含まれているかを数え、多い方を判定結果とする(単純な件数比較なので精度は高くない)。
2b. [任意・有料] use_ai=True かつ ANTHROPIC_API_KEY が設定されている場合は、
    Claude API(Haiku)に見出し全体を読ませて判定させる(より精度が高いが、
    API利用料が発生する)。API呼び出しに失敗した場合は自動的に2aへフォールバックする。

コスト削減のため、analyze.py 側で「平日朝の実行だけAI判定を使う」といった
呼び分けができるように、use_ai は呼び出し側から渡す設計にしている。

この判定はあくまで参考情報であり、テクニカルシグナル(signals.py)の
判定ロジックには一切影響しません(スコアに加算されたりしません)。
"""
import json
import os
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests

AI_MODEL = "claude-haiku-4-5-20251001"
AI_MAX_TOKENS = 200

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=ja&gl=JP&ceid=JP:ja"
REQUEST_TIMEOUT = 10
MAX_HEADLINES = 5

# 好材料キーワード(部分一致)。必要に応じて自由に追加・削除してください。
POSITIVE_KEYWORDS = [
    "上方修正", "増収増益", "増収", "増益", "最高益", "過去最高", "黒字転換",
    "好決算", "好調", "受注好調", "増配", "復配", "自己株式取得", "自社株買い",
    "株式分割", "業務提携", "資本提携", "新製品", "好材料", "上場来高値",
    "続伸", "急騰", "買い増し", "格上げ", "黒字",
]

# 悪材料キーワード(部分一致)。必要に応じて自由に追加・削除してください。
NEGATIVE_KEYWORDS = [
    "下方修正", "減収減益", "減収", "減益", "赤字転落", "赤字", "特別損失",
    "減配", "無配", "不祥事", "リコール", "自主回収", "訴訟", "提訴",
    "経営再建", "民事再生", "破産", "破綻", "上場廃止", "粉飾", "情報漏洩",
    "個人情報流出", "逮捕", "撤退", "急落", "続落", "格下げ",
]


def fetch_headlines(company_name: str, max_items: int = MAX_HEADLINES) -> list:
    """Googleニュース検索RSSから、会社名に関する直近の見出しを取得する。
    取得に失敗した場合は空リストを返す(呼び出し側の処理は継続させる)。
    """
    query = quote(f"{company_name} 株")
    url = GOOGLE_NEWS_RSS.format(query=query)
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        titles = [item.findtext("title") for item in root.findall(".//item")]
        return [t.strip() for t in titles if t and t.strip()][:max_items]
    except Exception as e:
        print(f"[warn] {company_name}: ニュース取得に失敗しました: {e}", file=sys.stderr)
        return []


def _classify_headline(headline: str) -> str:
    """1件の見出しを "POSITIVE" / "NEGATIVE" / "NEUTRAL" に分類する。

    好材料・悪材料どちらのキーワードも含まない場合、または両方を含む場合
    (例: "増益も一部事業で減益")は、判定が割れているためNEUTRAL扱いにする。
    """
    has_positive = any(kw in headline for kw in POSITIVE_KEYWORDS)
    has_negative = any(kw in headline for kw in NEGATIVE_KEYWORDS)
    if has_positive and not has_negative:
        return "POSITIVE"
    if has_negative and not has_positive:
        return "NEGATIVE"
    return "NEUTRAL"


def score_headlines(headlines: list) -> dict:
    """見出しのリストからポジティブ/ネガティブを判定する。

    見出し内のキーワード「出現回数」ではなく、見出し1件につき1票の多数決とする。
    (例えば「増収増益」は"増収"と"増益"の両方に部分一致するが、
    これは同じ1つの見出しなので1票としてしか数えない。以前の実装は
    キーワードのヒット数をそのまま数えていたため、キーワードが重なりやすい
    見出しの影響が不当に大きくなる問題があった)
    """
    positive_hits = []
    negative_hits = []
    for headline in headlines:
        label = _classify_headline(headline)
        if label == "POSITIVE":
            positive_hits.append(headline)
        elif label == "NEGATIVE":
            negative_hits.append(headline)

    pos_count = len(positive_hits)
    neg_count = len(negative_hits)
    if pos_count > neg_count:
        sentiment = "POSITIVE"
    elif neg_count > pos_count:
        sentiment = "NEGATIVE"
    else:
        sentiment = "NEUTRAL"

    # 表示用に、判定の根拠になった見出しを1件だけ添える
    sample_headline = None
    if sentiment == "POSITIVE" and positive_hits:
        sample_headline = positive_hits[0]
    elif sentiment == "NEGATIVE" and negative_hits:
        sample_headline = negative_hits[0]
    elif headlines:
        sample_headline = headlines[0]

    return {
        "sentiment": sentiment,
        "positive_count": pos_count,
        "negative_count": neg_count,
        "headline_count": len(headlines),
        "sample_headline": sample_headline,
        "method": "KEYWORD",
    }


def get_ai_news_sentiment(company_name: str, headlines: list) -> dict | None:
    """Claude API(Haiku)で見出し全体を読ませてポジティブ/ネガティブを判定する。
    以下の場合はNoneを返す(呼び出し側はキーワード判定にフォールバックすること):
    - ANTHROPIC_API_KEY が未設定
    - anthropicライブラリが未インストール
    - 見出しが1件も取得できていない
    - API呼び出し・応答のパースに失敗した場合
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or not headlines:
        return None

    try:
        import anthropic
    except ImportError:
        print(
            "[warn] anthropicライブラリが見つかりません(pip install anthropic が必要です)。"
            "キーワード判定にフォールバックします。",
            file=sys.stderr,
        )
        return None

    headline_lines = "\n".join(f"- {h}" for h in headlines)
    prompt = (
        f"以下は日本株「{company_name}」に関する直近のニュース見出しです。\n\n"
        f"{headline_lines}\n\n"
        "これらの見出し全体を踏まえて、この銘柄にとって好材料寄りかどうかを判定してください。\n"
        "説明文は書かず、次のJSON形式のみを1行で出力してください:\n"
        '{"sentiment": "POSITIVE または NEGATIVE または NEUTRAL", "reason": "20文字程度の日本語の短い理由"}'
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=AI_MODEL,
            max_tokens=AI_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # コードブロックで囲まれて返ってきた場合に対応
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
        data = json.loads(text)
        sentiment = str(data.get("sentiment", "")).upper()
        if sentiment not in ("POSITIVE", "NEGATIVE", "NEUTRAL"):
            raise ValueError(f"想定外のsentiment値: {sentiment!r}")
        return {
            "sentiment": sentiment,
            "positive_count": None,
            "negative_count": None,
            "headline_count": len(headlines),
            "sample_headline": data.get("reason") or headlines[0],
            "method": "AI",
        }
    except Exception as e:
        print(f"[warn] {company_name}: AIニュース判定に失敗しました: {e}", file=sys.stderr)
        return None


def get_news_sentiment(company_name: str, use_ai: bool = False) -> dict:
    """会社名からニュースを取得し、判定結果を返す。

    use_ai=True かつ AI判定が使える状態であればAI判定を使い、
    そうでなければ(または失敗すれば)無料のキーワード判定にフォールバックする。
    取得自体に失敗した場合はNEUTRAL扱いにする。
    """
    try:
        headlines = fetch_headlines(company_name)
    except Exception as e:
        print(f"[warn] {company_name}: ニュース判定でエラー: {e}", file=sys.stderr)
        traceback.print_exc()
        headlines = []

    if use_ai:
        ai_result = get_ai_news_sentiment(company_name, headlines)
        if ai_result is not None:
            return ai_result

    return score_headlines(headlines)


def attach_news_sentiment(items: list, use_ai: bool = False, sleep_seconds: float = 0.3) -> None:
    """[{"code","name","result"}, ...] の各要素に item["news"] を追加する(破壊的更新)。

    ウォッチリスト・保有銘柄・ランキングなど複数のリストにまたがって
    同じ銘柄が重複する場合は、attach_news_sentiment_for_lists() を使うと
    ニュース取得・AI判定を1回にまとめて重複リクエストを削減できる。
    """
    attach_news_sentiment_for_lists(items, use_ai=use_ai, sleep_seconds=sleep_seconds)


def attach_news_sentiment_for_lists(*item_lists, use_ai: bool = False, sleep_seconds: float = 0.3) -> None:
    """複数の[{"code","name","result"}, ...]リストをまとめて処理する。

    同じ銘柄コードがウォッチリスト・保有銘柄・ランキングなど複数のリストに
    重複して登場する場合、1回の実行内ではニュース取得・AI判定を1回だけ行い、
    結果を使い回す(無料枠のリクエスト数、およびAI利用時のトークン消費を節約する)。
    """
    cache: dict = {}
    for items in item_lists:
        for item in items:
            code = item.get("code")
            if code is not None and code in cache:
                item["news"] = cache[code]
                continue
            news = get_news_sentiment(item["name"], use_ai=use_ai)
            item["news"] = news
            if code is not None:
                cache[code] = news
            time.sleep(sleep_seconds)
