"""Bounded NCBI E-utilities adapter, with no arbitrary remote URL support."""

import re
import time

import requests
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from amr_evidence.models import Study

DEFAULT_QUERY = (
    "Nigeria[Title/Abstract] AND "
    "(antimicrobial resistance[Title/Abstract] OR antibiotic resistance[Title/Abstract] "
    "OR drug resistance, bacterial[MeSH Terms])"
)
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


def xml_text(element):
    return "".join(element.itertext()).strip() if element is not None else ""


def parse_articles(xml):
    try:
        root = ET.fromstring(xml)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise ValueError("PubMed returned malformed or unsafe XML.") from exc
    error = root.find(".//ERROR")
    if error is not None:
        raise ValueError("PubMed returned an error. Refine the query and retry.")
    articles = []
    for item in root.findall(".//PubmedArticle"):
        article = item.find(".//Article")
        if article is None:
            continue
        pmid = xml_text(item.find("./MedlineCitation/PMID"))
        doi = next(
            (
                xml_text(node)
                for node in item.findall(".//ArticleId")
                if node.get("IdType") == "doi"
            ),
            None,
        )
        date = article.find("./Journal/JournalIssue/PubDate")
        year_text = " ".join(date.itertext()) if date is not None else ""
        match = re.search(r"\b(18|19|20|21)\d{2}\b", year_text)
        abstract = "\n".join(
            (f"{node.get('Label')}: " if node.get("Label") else "") + xml_text(node)
            for node in article.findall("./Abstract/AbstractText")
        )
        authors = "; ".join(
            " ".join(
                part
                for part in (
                    xml_text(author.find("ForeName")),
                    xml_text(author.find("LastName")),
                    xml_text(author.find("CollectiveName")),
                )
                if part
            )
            for author in article.findall("./AuthorList/Author")
        )
        if not pmid:
            continue
        study = Study(
            title=xml_text(article.find("ArticleTitle")) or f"PubMed {pmid}",
            pmid=pmid,
            doi=doi,
            year=int(match.group()) if match else None,
            authors=authors or None,
            journal=xml_text(article.find("./Journal/Title")) or None,
        )
        articles.append({"study": study.model_dump(), "abstract": abstract})
    return articles


class PubMed:
    def __init__(self, email="", session=None, timeout=20):
        self.email = email
        self.session = session or requests.Session()
        self.timeout = timeout
        self.last_request = 0.0

    def _get(self, endpoint, params):
        delay = 0.36 - (time.monotonic() - self.last_request)
        if delay > 0:
            time.sleep(delay)
        self.last_request = time.monotonic()
        params = {**params, "tool": "amr_evidence_synthesizer"}
        if self.email:
            params["email"] = self.email
        try:
            response = self.session.get(
                BASE + endpoint, params=params, timeout=self.timeout, allow_redirects=False
            )
            response.raise_for_status()
            if response.status_code != 200 or len(response.content) > 5_000_000:
                raise ValueError("Unexpected or oversized PubMed response.")
            return response
        except requests.RequestException as exc:
            raise ValueError("PubMed is unavailable or rate-limited. Try again later.") from exc

    def search(self, query=DEFAULT_QUERY, limit=20, start_year=None, end_year=None):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 2000:
            raise ValueError("Enter a PubMed query of 1–2000 characters.")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Search limit must be 1–100.")
        params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": limit}
        if start_year is not None or end_year is not None:
            if start_year is None or end_year is None or not 1800 <= start_year <= end_year <= 2200:
                raise ValueError("Supply a valid inclusive year range.")
            params.update(datetype="pdat", mindate=start_year, maxdate=end_year)
        try:
            search = self._get("esearch.fcgi", params).json()
            ids = search["esearchresult"]["idlist"]
            if not isinstance(ids, list) or any(not re.fullmatch(r"\d{1,12}", str(i)) for i in ids):
                raise ValueError("Invalid PubMed identifiers.")
            if not ids:
                return []
            response = self._get(
                "efetch.fcgi", {"db": "pubmed", "id": ",".join(ids[:limit]), "retmode": "xml"}
            )
            return parse_articles(response.content)
        except (KeyError, TypeError, ET.ParseError) as exc:
            raise ValueError("PubMed returned an unreadable response.") from exc


def import_article(store, article):
    if not article["abstract"].strip():
        raise ValueError("No abstract is available. Upload authorized full text instead.")
    study = Study.model_validate(article["study"])
    study_id = store.add_study(study)
    return store.add_source(
        study_id, f"PubMed {study.pmid} abstract", [article["abstract"]], "abstract"
    )
