import re


def _append_unique(findings, finding_type, value, source="nlp", confidence=0.72):
    value = " ".join((value or "").split()).strip(" ,;:-")
    value = re.split(
        r"\b(?:and|you\s+can|contact|phone|mobile|email|transaction|upi|pass|password|mail)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" ,;:-")
    if not value:
        return
    if finding_type == "NLP Location" and _looks_like_bank_or_financial_org(value):
        return

    normalized_value = value.lower()
    duplicate = False
    for finding in findings:
        if finding["type"] != finding_type:
            continue
        existing = finding["value"].lower()
        if normalized_value == existing or normalized_value in existing or existing in normalized_value:
            duplicate = True
            break

    if not duplicate:
        findings.append(
            {
                "type": finding_type,
                "value": value,
                "source": source,
                "confidence": confidence,
            }
        )


def _load_spacy_model():
    try:
        import spacy
    except Exception as exc:
        return None, f"spaCy could not be imported; using local NLP fallback patterns. Details: {exc}"

    for model_name in ("en_core_web_sm", "en_core_web_md"):
        try:
            return spacy.load(model_name), f"spaCy model loaded: {model_name}"
        except OSError:
            continue
        except Exception as exc:
            return None, f"spaCy model could not be loaded; using fallback NLP patterns. Details: {exc}"

    return None, "spaCy is installed, but no English NER model was found; using fallback patterns."


def _looks_like_bank_or_financial_org(value):
    normalized = " ".join((value or "").lower().split())
    return any(
        keyword in normalized
        for keyword in (
            "bank",
            "state bank",
            "bank of india",
            "hdfc",
            "icici",
            "sbi",
            "axis",
            "kotak",
            "canara",
            "union bank",
            "punjab national",
        )
    )


def _spacy_entities(text):
    nlp, status = _load_spacy_model()
    findings = []

    if not nlp:
        return findings, status

    entity_type_map = {
        "PERSON": "NLP Person Name",
        "ORG": "NLP Organization",
        "GPE": "NLP Location",
        "LOC": "NLP Location",
        "DATE": "NLP Date",
    }

    doc = nlp(text)
    for entity in doc.ents:
        finding_type = entity_type_map.get(entity.label_)
        if not finding_type:
            continue
        if _looks_like_bank_or_financial_org(entity.text):
            finding_type = "NLP Organization"
        elif finding_type == "NLP Location":
            window_start = max(0, entity.start_char - 24)
            window_end = min(len(text), entity.end_char + 24)
            nearby_text = text[window_start:window_end]
            if _looks_like_bank_or_financial_org(nearby_text):
                continue
        if len(entity.text.strip()) < 3:
            continue
        _append_unique(findings, finding_type, entity.text, source="spacy", confidence=0.82)

    return findings, status


def _fallback_entities(text):
    findings = []

    label_patterns = (
        (
            "NLP Person Name",
            r"\b(?:my\s+name\s+is|name|full name|account holder|customer name|card holder)\b"
            r"\s*[:=\-]?\s*("
            r"(?!(?:and|you|can|contact|phone|mobile|email)\b)[A-Za-z][A-Za-z.'-]{1,30}"
            r"(?:\s+(?!(?:and|you|can|contact|phone|mobile|email)\b)[A-Za-z][A-Za-z.'-]{1,30}){0,3}"
            r")",
        ),
        (
            "NLP Person Name",
            r"\b(?:submitted by|student name|employee name|patient name|customer)\b"
            r"\s*[:=\-]?\s*([A-Za-z][A-Za-z.'-]{1,30}(?:\s+[A-Za-z][A-Za-z.'-]{1,30}){0,3})",
        ),
        (
            "NLP Address",
            r"\b(?:address|addr|billing address|shipping address|location)\b"
            r"\s*[:=\-]?\s*([A-Za-z0-9][A-Za-z0-9\s,./#-]{8,90})",
        ),
        (
            "NLP Organization",
            r"\b([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,3}\s+(?:Bank|University|College|Hospital|Company|Ltd|Limited|Pvt)(?:\s+of\s+[A-Z][A-Za-z]+)?)\b",
        ),
        (
            "NLP Organization",
            r"\b((?:State\s+Bank\s+of\s+India|Bank\s+of\s+India|Punjab\s+National\s+Bank|Union\s+Bank\s+of\s+India|Canara\s+Bank|Axis\s+Bank|HDFC\s+Bank|ICICI\s+Bank|Kotak\s+Bank|SBI))\b",
        ),
        (
            "NLP Location",
            r"\b(?:city|state(?!\s+bank\b)|place|location)\b\s*[:=\-]?\s*([A-Za-z][A-Za-z\s.'-]{2,40})",
        ),
        (
            "NLP Date",
            r"\b(?:date|dob|date of birth|birth date|issued on)\b\s*[:=\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        ),
    )

    for finding_type, pattern in label_patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            _append_unique(findings, finding_type, match.group(1), source="nlp-fallback", confidence=0.68)

    for match in re.finditer(
        r"\b([A-Za-z][A-Za-z.'-]{1,20}\s+(?:Reddy|Kumar|Sharma|Rao|Naidu|Singh|Patel|Gupta|Charan))\b",
        text,
        flags=re.IGNORECASE,
    ):
        _append_unique(findings, "NLP Person Name", match.group(1), source="nlp-fallback", confidence=0.7)

    return findings


def analyze_nlp(text, extracted=None):
    spacy_findings, status = _spacy_entities(text)
    fallback_findings = _fallback_entities(text)

    findings = []
    for finding in spacy_findings + fallback_findings:
        _append_unique(
            findings,
            finding["type"],
            finding["value"],
            source=finding.get("source", "nlp"),
            confidence=finding.get("confidence", 0.7),
        )

    return {
        "findings": findings,
        "entity_count": len(findings),
        "status": status,
    }
