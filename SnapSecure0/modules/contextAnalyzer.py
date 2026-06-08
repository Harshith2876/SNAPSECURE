import re


CATEGORY_KEYWORDS = {
    'Authentication': (
        'login',
        'sign in',
        'verification code',
        'authentication code',
        'one time password',
        'otp',
        'do not share this code',
        'microsoft verification',
        'security code',
        'two factor',
        '2fa',
    ),
    'Banking': (
        'transaction successful',
        'amount debited',
        'available balance',
        'upi ref',
        'account',
        'a/c',
        'bank',
        'credited',
        'debited',
        'payment',
        'upi',
        'transfer',
        'balance',
    ),
    'Identity': (
        'aadhaar',
        'pan',
        'passport',
        'date of birth',
        'dob',
        'government id',
        'identity',
    ),
}


def _normalize_line(line):
    return " ".join((line or "").lower().split())


def _group_ocr_lines(extracted):
    grouped = {}
    for item in extracted or []:
        line_key = item.get('line_key')
        if not line_key:
            continue
        grouped.setdefault(line_key, []).append(item)

    ordered_lines = []
    for line_key in sorted(grouped.keys()):
        items = sorted(grouped[line_key], key=lambda item: item.get('word_index', 0))
        line_text = " ".join(item['text'] for item in items).strip()
        if line_text:
            ordered_lines.append(line_text)

    return ordered_lines


def _collect_category_cues(lines, keywords):
    cues = []
    normalized_lines = [_normalize_line(line) for line in lines]

    for keyword in keywords:
        normalized_keyword = _normalize_line(keyword)
        for line in normalized_lines:
            if normalized_keyword in line:
                if keyword not in cues:
                    cues.append(keyword)
                break

    return cues


def _extract_masked_accounts(lines):
    matches = []
    pattern = re.compile(
        r'\b(?:a/c|account|acct|from\s+a/c|account\s+ending)\b[^0-9A-Za-zXx]*([Xx*]{2,}\d{2,6})',
        flags=re.IGNORECASE,
    )

    for line in lines:
        for match in pattern.finditer(line):
            value = match.group(1).replace('*', 'X').upper()
            if value not in matches:
                matches.append(value)

    return matches


def analyze_context(text, extracted, findings):
    lines = _group_ocr_lines(extracted)
    all_lines = lines or [text]

    categories = []
    cues_by_category = {}
    score_boost = 0
    derived_findings = []

    for category, keywords in CATEGORY_KEYWORDS.items():
        cues = _collect_category_cues(all_lines, keywords)
        if cues:
            categories.append(category)
            cues_by_category[category] = cues[:4]

    finding_types = {finding['type'] for finding in findings}

    if 'Authentication' in categories and 'OTP' in finding_types:
        score_boost += 2

    if 'Banking' in categories:
        score_boost += 1
        if 'Transaction ID' in finding_types:
            score_boost += 1
        if 'OTP' in finding_types:
            score_boost += 1

    for masked_value in _extract_masked_accounts(all_lines):
        derived_findings.append({'type': 'Masked Account Number', 'value': masked_value})

    if derived_findings:
        score_boost += 1

    primary_category = categories[0] if categories else 'General'

    return {
        'primary_category': primary_category,
        'categories': categories,
        'cues': cues_by_category,
        'score_boost': score_boost,
        'derived_findings': derived_findings,
    }
