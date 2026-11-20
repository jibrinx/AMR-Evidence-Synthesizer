"""Deliberately narrow narrative extraction. Unmapped patterns need manual entry."""

import re

from amr_evidence.models import Estimate

ORGANISMS = {
    "Escherichia coli": r"\b(?:Escherichia\s+coli|E\.\s*coli)\b",
    "Staphylococcus aureus": r"\b(?:Staphylococcus\s+aureus|S\.\s*aureus)\b",
    "Klebsiella pneumoniae": r"\b(?:Klebsiella\s+pneumoniae|K\.\s*pneumoniae)\b",
    "Pseudomonas aeruginosa": r"\b(?:Pseudomonas\s+aeruginosa|P\.\s*aeruginosa)\b",
    "Acinetobacter baumannii": r"\b(?:Acinetobacter\s+baumannii|A\.\s*baumannii)\b",
    "Salmonella": r"\bSalmonella(?:\s+(?:spp\.?|enterica|Typhi))?\b",
}
DRUGS = (
    "ampicillin",
    "amoxicillin",
    "ciprofloxacin",
    "ceftriaxone",
    "cefotaxime",
    "ceftazidime",
    "gentamicin",
    "tetracycline",
    "meropenem",
    "imipenem",
    "chloramphenicol",
    "colistin",
    "vancomycin",
    "erythromycin",
    "trimethoprim",
    "sulfamethoxazole",
    "nitrofurantoin",
    "oxacillin",
    "cefoxitin",
)
PERCENT = r"(?P<pct>\d{1,3}(?:\.\d+)?)\s*%"
PAIR = r"(?P<n>\d+)\s*(?:/|of|out of)\s*(?P<d>\d+)"


def extract_rules(source_id, pages):
    candidates = []
    for page_number, page in enumerate(pages, 1):
        # Preserve literal evidence. Avoid splitting abbreviated species names.
        for part in re.finditer(r"[^\n;]+(?:[;\n]|$)", page):
            quote = part.group().strip()
            if not quote or len(quote) > 2500:
                continue
            if not re.search(r"\bresistan(?:t|ce)\b", quote, re.I):
                continue
            if re.search(
                r"\b(?:not\s+resistant|no\s+resistance|non[- ]?susceptib|intermediate)\b",
                quote,
                re.I,
            ):
                continue
            organisms = [
                (normalized, found.group())
                for normalized, pattern in ORGANISMS.items()
                if (found := re.search(pattern, quote, re.I))
            ]
            drugs = [
                found.group() for drug in DRUGS if (found := re.search(rf"\b{drug}\b", quote, re.I))
            ]
            # Multiple entities or numbers can refer to different groups. Do not guess a mapping.
            percentages = list(re.finditer(PERCENT, quote))
            pairs = list(re.finditer(PAIR, quote, re.I))
            if len(organisms) != 1 or len(drugs) != 1 or len(percentages) > 1 or len(pairs) > 1:
                continue
            if not percentages and not pairs:
                continue
            if re.search(
                r"\b(?:higher|lower|increase|reduction|relative|compared|odds|difference)\b",
                quote,
                re.I,
            ):
                continue
            drug = re.escape(drugs[0])
            organism = re.escape(organisms[0][1])
            tail = (
                rf"\bresistan(?:t|ce)\b(?:\s+rate)?\s+(?:to\s+)?{drug}\s*"
                rf"(?:(?:was|were|of|at)\s*)?[:=]?\s*"
            )
            # Only direct numeric links, not any percentage in a sentence mentioning AMR.
            linked = (
                re.search(tail + rf"(?:{PAIR}\s*[, (]\s*)?{PERCENT}", quote, re.I)
                or re.search(
                    PERCENT + rf"\s+(?:of\s+)?(?:the\s+)?(?:{organism}\s+)?"
                    rf"(?:(?:isolates?|strains?)\s+)?(?:were|was)\s+resistant\s+to\s+{drug}",
                    quote,
                    re.I,
                )
                or re.search(tail + PAIR, quote, re.I)
                or re.search(
                    PAIR + rf"\s+(?:{organism}\s+)?(?:(?:isolates?|strains?)\s+)?"
                    rf"(?:were|was)\s+resistant\s+to\s+{drug}",
                    quote,
                    re.I,
                )
            )
            if not linked:
                continue
            values = {
                "source_id": source_id,
                "page": page_number,
                "quote": quote,
                "organism_raw": organisms[0][1],
                "organism_normalized": organisms[0][0],
                "antibiotic_raw": drugs[0],
                "antibiotic_normalized": drugs[0].lower(),
                "outcome": "resistant",
                "notes": "Narrow rule candidate. Verify number/entity linkage and stratum against source.",
            }
            groups = linked.groupdict()
            if groups.get("pct") is not None:
                values["reported_percentage"] = groups["pct"]
            if groups.get("n") is not None:
                values["numerator"] = int(groups["n"])
                values["denominator"] = int(groups["d"])
            try:
                candidates.append(Estimate.model_validate(values))
            except ValueError:
                continue
    return candidates
