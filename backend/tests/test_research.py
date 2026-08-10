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
    build_search_query,
    build_research_framework,
    canonicalize_url,
    classify_source_type,
    finalize_research_markdown,
    parse_research_request,
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
    assert request.query == "现在的 agent 行业行情"

    named = parse_research_request(
        "了解 OpenAI Agents SDK 现在的情况，创建 阶段2验收.md 保存到输出目录"
    )
    assert named is not None
    assert named.query == "OpenAI Agents SDK 现在的情况"


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
