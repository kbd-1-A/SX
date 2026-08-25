"""联网研究工具：使用假 Provider 验证来源与引用边界，不依赖外网。"""

import asyncio
from datetime import datetime, timezone

import pytest

import app.tools.research as research_mod
from app.tools.research import (
    HtmlSearchProvider,
    ResearchError,
    ResearchSource,
    SearchResult,
    So360SearchProvider,
    build_search_query,
    build_research_framework,
    canonicalize_url,
    classify_source_type,
    finalize_research_markdown,
    is_relevant_search_result,
    parse_research_request,
    refine_research_query,
    research_public_sources,
)


class FakeProvider:
    def __init__(self, results, pages):
        self.results = results
        self.pages = pages
        self.queries = []
        self.read_urls = []

    def search(self, query, limit):
        self.queries.append((query, limit))
        return self.results

    def read(self, url):
        self.read_urls.append(url)
        return self.pages[url]


def source_result(number: int, domain: str = "example.com"):
    return SearchResult(
        title=f"agent 行业 topic 来源 {number}",
        url=f"https://{domain}/article?utm_source=test&id={number}",
        snippet="公开资料摘要",
    )


def test_parse_research_request_removes_file_action_clause():
    request = parse_research_request(
        "我想了解一下现在的 agent 行业行情，创建一个 md 文件放在桌面"
    )

    assert request is not None
    assert request.query == "agent 行业行情"

    named = parse_research_request(
        "了解 OpenAI Agents SDK 现在的情况，创建 阶段2验收.md 保存到输出目录"
    )
    assert named is not None
    assert named.query == "OpenAI Agents SDK"


def test_parse_research_request_does_not_mark_plain_document_as_research():
    assert parse_research_request("把这段聊天整理成 md 文件") is None


def test_search_query_quotes_named_product_and_dates_broad_topics():
    now = datetime(2026, 8, 10, tzinfo=timezone.utc)

    assert build_search_query("OpenAI Agents SDK 现在的情况", now) == '"OpenAI Agents SDK"'
    assert build_search_query("agent 行业行情", now) == "agent 行业行情 2026"


def test_bing_html_result_parser_extracts_title_url_and_snippet(monkeypatch):
    page = """
    <li class="b_algo">
      <h2><a href="https://example.com/report"><strong>Agent</strong> report</a></h2>
      <div class="b_caption"><p>Public market summary.</p></div>
    </li>
    """
    monkeypatch.setattr(research_mod, "_fetch_html", lambda *args, **kwargs: page)

    results = HtmlSearchProvider(endpoint="https://cn.bing.com/search").search("agent", 3)

    assert results == [
        SearchResult(
            title="Agent report",
            url="https://example.com/report",
            snippet="Public market summary.",
        )
    ]


def test_canonicalize_url_removes_tracking_and_rejects_private_hosts(monkeypatch):
    assert canonicalize_url("https://example.com/a?utm_source=x&id=1#section") == "https://example.com/a?id=1"
    assert canonicalize_url("file:///C:/secret.txt") is None
    assert canonicalize_url("http://127.0.0.1:8000/private") is None
    monkeypatch.setattr(
        research_mod.socket,
        "getaddrinfo",
        lambda *args: [(None, None, None, None, ("127.0.0.1", 0))],
    )
    assert canonicalize_url("https://internal.example/private") is None


def test_research_reads_unique_public_sources_and_records_retrieval_time(monkeypatch):
    result_one = source_result(1, "example.com")
    result_duplicate = SearchResult("重复", result_one.url, "")
    result_two = source_result(2, "example.org")
    pages = {
        "https://example.com/article?id=1": "官方公开正文 " * 80,
        "https://example.org/article?id=2": "行业组织公开正文 " * 80,
    }
    provider = FakeProvider([result_one, result_duplicate, result_two], pages)
    now = datetime(2026, 8, 10, 12, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(research_mod, "RESEARCH_MIN_SOURCES", 2)

    result = asyncio.run(
        research_public_sources("agent 行业", provider=provider, now=now)
    )

    assert result.retrieved_at == "2026-08-10 12:30:00 +0000"
    assert [source.citation_id for source in result.sources] == [1, 2]
    assert [source.domain for source in result.sources] == ["example.com", "example.org"]
    assert set(provider.read_urls) == set(pages)


def test_research_requires_minimum_sources(monkeypatch):
    result = source_result(1)
    provider = FakeProvider([result], {"https://example.com/article?id=1": "短"})
    monkeypatch.setattr(research_mod, "RESEARCH_MIN_SOURCES", 1)

    with pytest.raises(ResearchError) as exc:
        asyncio.run(research_public_sources("topic", provider=provider))
    assert exc.value.code == "insufficient_research_sources"


def test_finalize_research_markdown_keeps_only_verified_citations_and_appends_sources():
    result = research_mod.ResearchResult(
        query="topic",
        retrieved_at="2026-08-10 12:30:00 +0000",
        sources=(
            ResearchSource(
                1,
                "官方来源",
                "https://example.com/a",
                "example.com",
                "正文",
                source_type="official",
            ),
        ),
    )

    draft = "# 报告\n\n事实 [S1]，错误 [S9]，链接 https://bad.example/x。"
    finalized = finalize_research_markdown(draft, result)

    assert "[S1]" in finalized
    assert "[未验证来源]" in finalized
    assert "[未验证链接已移除]" in finalized
    assert "https://example.com/a" in finalized
    assert "检索时间：2026-08-10 12:30:00 +0000" in finalized


def test_secondary_only_numeric_claim_is_marked_unverified():
    result = research_mod.ResearchResult(
        query="topic",
        retrieved_at="2026-08-10 12:30:00 +0000",
        sources=(
            ResearchSource(
                1,
                "二手报告",
                "https://example.com/a",
                "example.com",
                "正文",
                source_type="secondary",
            ),
        ),
    )

    finalized = finalize_research_markdown("# 报告\n\n市场增长 20% [S1]", result)

    assert "未由官方来源独立核实" in finalized
    assert "二手来源" in finalized


def test_source_type_classifies_brand_owned_docs_and_github_as_official():
    assert classify_source_type(
        "https://openai.github.io/openai-agents-python/", "OpenAI Agents SDK"
    ) == "official"
    assert classify_source_type(
        "https://github.com/openai/openai-agents-python", "OpenAI Agents SDK"
    ) == "official"
    assert classify_source_type("https://example.com/report", "OpenAI Agents SDK") == "secondary"


def test_research_framework_clearly_disclaims_realtime_claims():
    framework = build_research_framework("agent 行业", "联网搜索暂时不可用。")

    assert "联网检索未完成" in framework
    assert "不包含实时行情" in framework
    assert "待核实问题" in framework


def test_parse_research_request_extracts_core_topic_from_casual_phrasing():
    request = parse_research_request("分析一下ai销售行情 创建txt文件放到桌面上")

    assert request is not None
    assert request.query == "ai销售行情"

    casual = parse_research_request("帮我查查现在AI行业怎么样，创建文档放到桌面")
    assert casual is not None
    assert casual.query == "AI行业"


def test_parse_research_request_detects_analyze_recent_topic():
    # 用户说"分析最近X"应触发研究，主题应提炼为 X 而不是沿用历史话题
    request = parse_research_request("帮我分析一下 最近的ai模型，创建 txt 文件放到桌面")

    assert request is not None
    assert request.query == "ai模型"
    assert "销售" not in request.query


def test_parse_research_request_recent_phrasing_variants():
    variants = [
        ("帮我分析一下最近 AI 模型，创建 txt 文件放到桌面", "AI 模型"),
        ("分析一下近期的数字人技术，创建 md 放桌面", "数字人技术"),
        ("帮我分析一下 ai 模型，创建 txt 文件放到桌面", "ai 模型"),
    ]
    for text, expected in variants:
        request = parse_research_request(text)
        assert request is not None, text
        assert request.query == expected, (text, request.query)


def test_search_query_strips_filler_words_and_keeps_core_topic():
    now = datetime(2026, 8, 10, tzinfo=timezone.utc)

    assert build_search_query("ai销售行情", now) == "ai销售行情 2026"
    assert build_search_query("分析一下ai销售行情", now) == "ai销售行情 2026"


def test_relevance_uses_bigram_windows_and_ignores_filler():
    assert is_relevant_search_result(
        SearchResult("AI销售 市场规模 报告", "https://example.com/a", "2026 年 AI 销售数据"),
        "分析一下ai销售行情",
    )
    # 只有噪音词“分析”命中 → 不相关
    assert not is_relevant_search_result(
        SearchResult("分析 这个词是什么意思", "https://example.com/b", "词典解释"),
        "ai销售行情",
    )


def test_so360_parser_extracts_real_url_from_data_mdurl(monkeypatch):
    page = """
    <li class="res-list">
      <h3 class="res-title">
        <a href="https://www.so.com/link?m=abc123" data-mdurl="https://www.toutiao.com/article/7599873726498325032/"
           rel="noopener">2026年AI营销趋势预测</a>
      </h3>
      <p class="res-desc">某行业报告摘要，2026 年 AI 营销。</p>
    </li>
    <li class="res-list">
      <h3 class="res-title"><a href="https://www.so.com/link?m=def456" data-mdurl="https://www.163.com/dy/article/x.html">网易 AI 分析</a></h3>
      <p class="res-desc">正文摘要。</p>
    </li>
    """
    monkeypatch.setattr(research_mod, "_fetch_html", lambda *args, **kwargs: page)

    results = So360SearchProvider(endpoint="https://www.so.com/s").search("AI 营销 2026", 5)

    assert len(results) == 2
    assert results[0].title == "2026年AI营销趋势预测"
    assert results[0].url == "https://www.toutiao.com/article/7599873726498325032/"
    assert "AI 营销" in results[0].snippet
    assert results[1].url == "https://www.163.com/dy/article/x.html"


def test_refine_research_query_strips_verbs_and_file_words():
    assert refine_research_query("分析一下ai销售行情") == "ai销售行情"
    assert refine_research_query("帮我查查现在AI行业怎么样") == "AI行业"
    assert refine_research_query("OpenAI Agents SDK 现在的情况") == "OpenAI Agents SDK"


def test_research_retries_with_refined_query_when_first_search_irrelevant(monkeypatch):
    noise = SearchResult("分析 词典解释", "https://example.com/dict", "词典")
    relevant = SearchResult("2026 AI 销售 市场 报告", "https://example.com/report", "AI 销售 数据")
    pages = {"https://example.com/report": "官方公开正文 " * 80}

    class RetryProvider:
        def __init__(self):
            self.queries = []
            self.results = [[noise], [relevant]]
            self.index = 0

        def search(self, query, limit):
            self.queries.append(query)
            out = self.results[min(self.index, 1)]
            self.index += 1
            return out

        def read(self, url):
            return pages[url]

    provider = RetryProvider()
    monkeypatch.setattr(research_mod, "RESEARCH_MIN_SOURCES", 1)

    result = asyncio.run(
        research_public_sources("ai销售行情", provider=provider)
    )

    assert len(provider.queries) == 2
    assert provider.queries[0] != provider.queries[1]
    assert [s.citation_id for s in result.sources] == [1]
