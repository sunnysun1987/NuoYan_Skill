from pathlib import Path

from ivd_research.evidence import build_draft_evidence_card
from ivd_research.review_excel import export_review
from ivd_research.scenarios.pubmed_pmc import (
    EFETCH_BATCH_SIZE,
    NCBIClient,
    _fetch_pubmed_article_batches,
    format_pmc_text,
    format_pubmed_text,
    material_filename,
    parse_pmc_articles,
    parse_pubmed_articles,
)
from ivd_research.status import create_task_directories
from ivd_research.jsonl import append_jsonl
from ivd_research.jsonl import write_json
from ivd_research.models import Material


PUBMED_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345678</PMID>
      <Article>
        <Journal>
          <Title>Journal of Test Medicine</Title>
          <ISOAbbreviation>J Test Med</ISOAbbreviation>
          <JournalIssue>
            <PubDate><Year>2026</Year><Month>06</Month><Day>16</Day></PubDate>
          </JournalIssue>
        </Journal>
        <ArticleTitle>Plasma p-tau217 for Alzheimer disease diagnosis</ArticleTitle>
        <Abstract>
          <AbstractText Label="Background">p-tau217 is associated with Alzheimer pathology.</AbstractText>
          <AbstractText Label="Methods">A blood-based assay was evaluated.</AbstractText>
        </Abstract>
        <KeywordList>
          <Keyword>Alzheimer disease</Keyword>
          <Keyword>blood biomarkers</Keyword>
        </KeywordList>
        <AuthorList>
          <Author><ForeName>Alice</ForeName><LastName>Wang</LastName></Author>
        </AuthorList>
      </Article>
      <MeshHeadingList>
        <MeshHeading><DescriptorName>Alzheimer Disease</DescriptorName></MeshHeading>
      </MeshHeadingList>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1000/test.2026.1</ArticleId>
        <ArticleId IdType="pmc">PMC1234567</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""


PMC_XML = """<?xml version="1.0"?>
<pmc-articleset>
  <article>
    <front>
      <journal-meta>
        <journal-title-group><journal-title>PMC Test Journal</journal-title></journal-title-group>
      </journal-meta>
      <article-meta>
        <article-id pub-id-type="pmid">12345678</article-id>
        <article-id pub-id-type="pmcid">PMC1234567</article-id>
        <article-id pub-id-type="doi">10.1000/test.2026.1</article-id>
        <title-group><article-title>Plasma p-tau217 full text evidence</article-title></title-group>
        <contrib-group>
          <contrib contrib-type="author"><name><surname>Wang</surname><given-names>Alice</given-names></name></contrib>
        </contrib-group>
        <pub-date><year>2026</year><month>06</month><day>16</day></pub-date>
        <abstract><p>This full text article evaluates p-tau217 performance.</p></abstract>
      </article-meta>
    </front>
    <body>
      <sec><title>Results</title><p>The assay showed clinically relevant discrimination.</p></sec>
    </body>
  </article>
</pmc-articleset>
"""


PMC_DATE_PRIORITY_XML = """<?xml version="1.0"?>
<pmc-articleset>
  <article>
    <front>
      <journal-meta>
        <journal-title-group><journal-title>PMC Date Journal</journal-title></journal-title-group>
      </journal-meta>
      <article-meta>
        <article-id pub-id-type="pmid">42247843</article-id>
        <article-id pub-id-type="pmc">13264343</article-id>
        <article-id pub-id-type="doi">10.1016/j.tjpad.2026.100615</article-id>
        <title-group><article-title>Plasma brain-derived p-Tau217 date priority</article-title></title-group>
        <pub-date pub-type="collection"><month>8</month><year>2026</year></pub-date>
        <pub-date pub-type="epub"><day>06</day><month>6</month><year>2026</year></pub-date>
        <abstract><p>Date priority article.</p></abstract>
      </article-meta>
    </front>
    <body><p>Full text.</p></body>
  </article>
</pmc-articleset>
"""


def test_parse_pubmed_articles_extracts_evidence_fields():
    articles = parse_pubmed_articles(PUBMED_XML)

    assert len(articles) == 1
    article = articles[0]
    assert article["pmid"] == "12345678"
    assert article["pmcid"] == "PMC1234567"
    assert article["doi"] == "10.1000/test.2026.1"
    assert "p-tau217" in article["title"]
    assert "Background" in article["abstract"]
    assert article["abstract_sections"] == [
        {"label": "Background", "text": "p-tau217 is associated with Alzheimer pathology."},
        {"label": "Methods", "text": "A blood-based assay was evaluated."},
    ]
    assert "blood biomarkers" in article["keywords"]
    assert "Alzheimer Disease" in article["mesh_terms"]
    formatted = format_pubmed_text(
        {
            **article,
            "similar_articles": [
                {
                    "title": "Related AD biomarker study",
                    "pmid": "87654321",
                    "pmcid": "PMC7654321",
                    "doi": "10.1000/related",
                    "relation_reason_zh": "PubMed Similar articles 推荐，需人工复核主题相关性。",
                }
            ],
        }
    )
    assert "12345678" in formatted
    assert "Similar articles" in formatted
    assert "87654321" in formatted


def test_evidence_card_markdown_contains_translation_and_parameters(tmp_path: Path):
    task_dir = tmp_path / "task"
    create_task_directories(task_dir)
    material = Material(
        material_id="MAT-000001",
        task_id="TASK-1",
        source_scenario="pubmed_literature",
        material_type="literature",
        title="Plasma amyloid beta 42/40 for Alzheimer disease diagnosis",
        collection_time="2026-06-17T00:00:00+08:00",
        raw_fields={
            "pmid": "12345678",
            "abstract_sections": [
                {
                    "label": "Results",
                    "text": "The assay showed AUC 0.92, sensitivity 91%, and specificity 88% for Alzheimer disease pathology.",
                }
            ],
            "abstract": "The assay showed AUC 0.92, sensitivity 91%, and specificity 88%.",
        },
    )
    append_jsonl(task_dir / "data" / "materials.jsonl", material.model_dump(mode="json"))
    card = build_draft_evidence_card(task_dir, material.model_dump(mode="json"), "EC-000001")
    write_json(task_dir / "staging" / "evidence_cards" / "EC-000001.json", card.model_dump(mode="json"))

    from ivd_research.evidence import commit_staged_evidence

    commit_staged_evidence(task_dir)
    markdown = (task_dir / "evidence_cards" / "markdown" / "EC-000001.md").read_text(encoding="utf-8")

    assert "## 中文阅读版" not in markdown
    assert "## 参数要点" in markdown
    assert "AUC" in markdown


def test_parse_pmc_articles_extracts_fulltext_fields():
    articles = parse_pmc_articles(PMC_XML)

    assert len(articles) == 1
    article = articles[0]
    assert article["pmid"] == "12345678"
    assert article["pmcid"] == "PMC1234567"
    assert article["doi"] == "10.1000/test.2026.1"
    assert "full text" in article["title"]
    assert "clinically relevant" in article["full_visible_text"]
    assert article["abstract_sections"] == [
        {"label": "", "text": "This full text article evaluates p-tau217 performance."}
    ]
    assert "PMC1234567" in format_pmc_text(article)


def test_material_filename_uses_safe_title():
    filename = material_filename(
        "MAT-000001",
        "Aβ42/Aβ40: plasma * diagnostic? evidence <review>",
        "PMC",
        ".pdf",
    )

    assert filename.endswith("_PMC.pdf")
    assert "/" not in filename
    assert "*" not in filename
    assert filename.startswith("MAT-000001_Aβ42 Aβ40")


def test_parse_pmc_articles_prefers_epub_date_over_collection_issue():
    article = parse_pmc_articles(PMC_DATE_PRIORITY_XML)[0]

    assert article["publication_date"] == "2026-6-06"
    assert article["issue_date"] == "2026-8"
    assert article["date_source"] == "PMC epub/ppub 优先；collection 仅作为刊期"


def test_pubmed_material_flows_to_evidence_card_and_review(tmp_path: Path):
    task_dir = tmp_path / "task"
    create_task_directories(task_dir)
    write_json(
        task_dir / "task.json",
        {
            "task_id": "TEST",
            "topic": "test",
            "task_dir": str(task_dir),
            "created_at": "2026-06-16T00:00:00+08:00",
            "workflow_version": "test",
            "taxonomy_version": "test",
            "scenario_statuses": {},
        },
    )
    article = parse_pubmed_articles(PUBMED_XML)[0]
    text_path = task_dir / "extracted_text" / "literature" / "MAT-000001_pubmed.txt"
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(format_pubmed_text(article), encoding="utf-8")
    material = Material(
        material_id="MAT-000001",
        task_id="TEST",
        source_scenario="pubmed_literature",
        material_type="literature",
        title=article["title"],
        source_url=article["pubmed_url"],
        search_keyword_or_query="p-tau217 Alzheimer",
        collection_path={"scenario_id": "pubmed_literature"},
        collection_time="2026-06-16T00:00:00+08:00",
        adapter_id="pubmed_literature",
        adapter_version="2.0.0",
        raw_fields={**article, "fulltext_status": "pmcid_available", "pdf_status": "not_attempted"},
        extracted_text_status="completed",
        extracted_text_path=str(text_path.relative_to(task_dir)),
    )
    append_jsonl(task_dir / "data" / "materials.jsonl", material.model_dump(mode="json"))

    card = build_draft_evidence_card(task_dir, material.model_dump(mode="json"), "EC-000001")
    append_jsonl(task_dir / "data" / "evidence_cards.jsonl", card.model_dump(mode="json"))
    review = export_review(task_dir)

    assert "PMID：12345678" in "；".join(card.key_facts)
    assert "PMCID：PMC1234567" in "；".join(card.key_facts)
    assert "Abstract[Background]：p-tau217 is associated with Alzheimer pathology." in card.key_facts
    assert "Abstract[Methods]：A blood-based assay was evaluated." in card.key_facts
    assert "Keywords：Alzheimer disease；blood biomarkers" in card.key_facts
    assert Path(review["review_path"]).exists()


def test_fetch_pubmed_article_batches_avoids_large_efetch_requests(tmp_path: Path):
    class FakeClient:
        def __init__(self):
            self.calls = []

        def efetch(self, db, ids, *, rettype, retmode):
            self.calls.append(list(ids))
            return "<PubmedArticleSet>" + "".join(
                f"<PubmedArticle><MedlineCitation><PMID>{pmid}</PMID><Article><ArticleTitle>Title {pmid}</ArticleTitle></Article></MedlineCitation></PubmedArticle>"
                for pmid in ids
            ) + "</PubmedArticleSet>"

    task_dir = tmp_path / "task"
    create_task_directories(task_dir)
    ids = [str(index) for index in range(EFETCH_BATCH_SIZE * 2 + 5)]
    client = FakeClient()

    articles, paths = _fetch_pubmed_article_batches(
        client,
        task_dir,
        db="pubmed",
        ids=ids,
        material_id="MAT-000001",
        raw_subdir="pubmed",
        filename_stem="pubmed_efetch",
        parser=parse_pubmed_articles,
    )

    assert [len(call) for call in client.calls] == [EFETCH_BATCH_SIZE, EFETCH_BATCH_SIZE, 5]
    assert len(articles) == len(ids)
    assert len(paths) == len(ids)


def test_esearch_all_uses_count_instead_of_fixed_cap():
    class FakeClient(NCBIClient):
        def __init__(self):
            super().__init__()
            self.retmax_calls = []

        def _esearch_xml(self, db, term, *, retmax):
            self.retmax_calls.append(retmax)
            ids = "".join(f"<Id>{index}</Id>" for index in range(1, retmax + 1))
            return f"<eSearchResult><Count>205</Count><IdList>{ids}</IdList></eSearchResult>"

    client = FakeClient()
    result = client.esearch("pubmed", "p-tau217", retmax="all")

    assert client.retmax_calls == [0, 205]
    assert result["retmax"] == 205
    assert len(result["ids"]) == 205
