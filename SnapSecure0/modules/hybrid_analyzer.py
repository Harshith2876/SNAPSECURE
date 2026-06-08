from modules.ml_classifier import classify_sensitive_lines, classify_sensitivity
from modules.nlp_analyzer import analyze_nlp


def _append_unique(findings, candidate):
    seen = {(finding["type"], finding["value"]) for finding in findings}
    key = (candidate["type"], candidate["value"])
    if key not in seen:
        findings.append(candidate)


def enrich_with_hybrid_analysis(text, extracted, findings, context):
    enriched_findings = list(findings)
    context = dict(context or {})

    nlp_result = analyze_nlp(text, extracted)
    for finding in nlp_result["findings"]:
        _append_unique(enriched_findings, finding)

    document_ml = classify_sensitivity(text)
    ml_line_findings = classify_sensitive_lines(extracted)
    for finding in ml_line_findings:
        _append_unique(enriched_findings, finding)

    hybrid_boost = int(document_ml.get("score_boost", 0) or 0)
    if nlp_result["entity_count"] >= 3:
        hybrid_boost += 1
    if ml_line_findings:
        hybrid_boost += 1

    context["nlp"] = {
        "engine_status": nlp_result["status"],
        "entity_count": nlp_result["entity_count"],
    }
    context["ml"] = {
        "label": document_ml["label"],
        "confidence": document_ml["confidence"],
        "engine": document_ml["engine"],
        "signals": document_ml["signals"],
        "line_findings": len(ml_line_findings),
    }
    context["hybrid_score_boost"] = hybrid_boost
    context["score_boost"] = int(context.get("score_boost", 0) or 0) + hybrid_boost

    return enriched_findings, context
