import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen.canvas import Canvas

from amr_evidence.extraction import extract_rules
from amr_evidence.intake import MAX_BYTES, read_upload
from amr_evidence.pubmed import PubMed, import_article, parse_articles

XML = b"""<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID>
<Article><ArticleTitle>[TEST ONLY] <i>technical</i> fixture</ArticleTitle>
<Journal><Title>Test journal</Title><JournalIssue><PubDate><Year>2024</Year><Month>Nov</Month><Day>20</Day></PubDate></JournalIssue></Journal>
<Abstract><AbstractText Label="RESULTS">[TEST ONLY] resistance text.</AbstractText></Abstract>
<AuthorList><Author><ForeName>A</ForeName><LastName>Test</LastName></Author></AuthorList>
</Article></MedlineCitation><PubmedData><ArticleIdList>
<ArticleId IdType="doi">10.1000/test</ArticleId></ArticleIdList></PubmedData>
</PubmedArticle></PubmedArticleSet>"""


def make_pdf(pages=1, text=True, encrypted=False):
    buffer = io.BytesIO()
    canvas = Canvas(buffer, encrypt=StandardEncryption("password") if encrypted else None)
    for _ in range(pages):
        if text:
            canvas.drawString(
                30,
                700,
                "[TEST ONLY] Text based PDF content for a parser regression test, not evidence.",
            )
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def test_pdf_and_text():
    pages, kind = read_upload("test.pdf", make_pdf())
    assert kind == "pdf" and "TEST ONLY" in pages[0]
    assert read_upload("test.txt", b"\xef\xbb\xbfUTF8 text") == (["UTF8 text"], "text")


@pytest.mark.parametrize(
    "name,content",
    [
        ("x.txt", b""),
        ("x.txt", b"\xff"),
        ("x.txt", b"\x00bad"),
        ("x.exe", b"test"),
        ("x.pdf", b"not pdf"),
        ("x.txt", b"x" * (MAX_BYTES + 1)),
        ("x.pdf", b"%PDF-damaged"),
    ],
)
def test_bad_uploads(name, content):
    with pytest.raises(ValueError):
        read_upload(name, content)


@pytest.mark.parametrize(
    "data",
    [
        lambda: make_pdf(text=False),
        lambda: make_pdf(encrypted=True),
        lambda: make_pdf(pages=101),
    ],
)
def test_unsupported_pdfs(data):
    with pytest.raises(ValueError):
        read_upload("test.pdf", data())


def test_pubmed_xml():
    record = parse_articles(XML)[0]
    assert record["study"]["year"] == 2024
    assert record["study"]["title"] == "[TEST ONLY] technical fixture"
    assert record["abstract"].startswith("RESULTS:")
    assert record["study"]["doi"] == "10.1000/test"


@pytest.mark.parametrize(
    "xml",
    [
        b"<invalid>",
        b"<result><ERROR>bad</ERROR></result>",
        b'<!DOCTYPE a [<!ENTITY x "secret">]><a>&x;</a>',
    ],
)
def test_xml_errors(xml):
    with pytest.raises(ValueError):
        parse_articles(xml)


def test_pubmed_mock_search(store, monkeypatch):
    monkeypatch.setattr("amr_evidence.pubmed.time.sleep", lambda _: None)
    search_response = Mock(status_code=200, content=b"{}")
    search_response.json.return_value = {"esearchresult": {"idlist": ["123"]}}
    fetch_response = Mock(status_code=200, content=XML)
    session = Mock()
    session.get.side_effect = [search_response, fetch_response]
    result = PubMed(email="test@example.org", session=session).search("Nigeria", 1, 2020, 2024)
    assert len(result) == 1
    assert session.get.call_args_list[0].kwargs["params"]["tool"] == "amr_evidence_synthesizer"
    sid = import_article(store, result[0])
    assert store.source(sid)["kind"] == "abstract"
    with pytest.raises(ValueError, match="No abstract"):
        import_article(store, {**result[0], "abstract": ""})


@pytest.mark.parametrize(
    "query,limit,start,end",
    [
        ("", 1, None, None),
        ("x", 0, None, None),
        ("x", True, None, None),
        ("x", 1, 2025, 2020),
        ("x", 1, 2020, None),
    ],
)
def test_search_validation(query, limit, start, end):
    with pytest.raises(ValueError):
        PubMed().search(query, limit, start, end)


def test_search_empty_and_network_error():
    session = Mock()
    response = Mock(status_code=200, content=b"{}")
    response.json.return_value = {"esearchresult": {"idlist": []}}
    session.get.return_value = response
    assert PubMed(session=session).search("test") == []
    session.get.side_effect = requests.Timeout("technical timeout")
    with pytest.raises(ValueError, match="unavailable"):
        PubMed(session=session).search("test")


def test_rules_explicit(candidate):
    results = extract_rules(candidate.source_id, [candidate.quote])
    assert len(results) == 1
    assert results[0].numerator == 3 and results[0].denominator == 10
    assert results[0].reported_percentage == "30"


@pytest.mark.parametrize(
    "text",
    [
        "[TEST ONLY] Escherichia coli ciprofloxacin susceptibility was 90%.",
        "[TEST ONLY] Escherichia coli ciprofloxacin resistance was measured; 30% of patients were male.",
        "[TEST ONLY] Escherichia coli and Klebsiella pneumoniae resistance to ciprofloxacin was 30%.",
        "[TEST ONLY] Escherichia coli resistance to ciprofloxacin and ampicillin was 30%.",
        "[TEST ONLY] Escherichia coli were not resistant to ciprofloxacin (30%).",
        "[TEST ONLY] Escherichia coli were intermediate or resistant to ciprofloxacin (30%).",
        "[TEST ONLY] Escherichia coli were non-susceptible to ciprofloxacin (30%).",
        "[TEST ONLY] Escherichia coli resistance to ciprofloxacin was evaluated in 30% of samples.",
        "[TEST ONLY] Escherichia coli resistance to ciprofloxacin was 30% higher than last year.",
    ],
)
def test_rules_false_positives(text):
    assert extract_rules(1, [text]) == []


def test_rules_no_denominator_inference():
    text = "[TEST ONLY] Escherichia coli resistance to ciprofloxacin was 30%."
    value = extract_rules(1, [text])[0]
    assert value.denominator is None and value.numerator is None


def test_real_abstract_is_attributed_negative_example():
    path = Path(__file__).parent / "fixtures" / "pubmed_example.json"
    assert path.exists()
    value = json.loads(path.read_text())
    assert value["study"]["pmid"] and value["study"]["doi"]
    assert value["source_url"].startswith("https://pubmed.ncbi.nlm.nih.gov/")
    assert extract_rules(1, [value["abstract_excerpt"]]) == []
