import re


def _append_unique(findings, finding_type, matches):
    seen = {(finding["type"], finding["value"]) for finding in findings}
    for match in matches:
        key = (finding_type, match)
        if key not in seen:
            findings.append({"type": finding_type, "value": match})
            seen.add(key)


def _group_ocr_lines(extracted):
    grouped = {}
    for item in extracted or []:
        line_key = item.get("line_key")
        if not line_key:
            continue
        grouped.setdefault(line_key, []).append(item)

    ordered_lines = []
    for line_key in sorted(grouped.keys()):
        items = sorted(grouped[line_key], key=lambda item: item.get("word_index", 0))
        line_text = " ".join(item["text"] for item in items).strip()
        if line_text:
            ordered_lines.append(line_text)

    return ordered_lines


def _normalize_token(token):
    return re.sub(r"[^A-Z0-9\-]", "", token.upper())


def _is_phone_like(token):
    digits = re.sub(r"\D", "", token)
    return len(digits) == 10 and digits[:1] in {"6", "7", "8", "9"}


def _is_transaction_like(token):
    cleaned = _normalize_token(token)
    if len(cleaned) < 12:
        return False
    if _is_phone_like(cleaned):
        return False

    has_letter = any(char.isalpha() for char in cleaned)
    digit_count = sum(char.isdigit() for char in cleaned)
    length = len(cleaned)

    if length == 12 and digit_count == 12:
        return True
    if 12 <= length <= 16 and has_letter and digit_count >= 4:
        return True
    if cleaned.startswith("UTR") and length >= 12 and digit_count >= 6:
        return True
    return False


def _extract_transaction_candidates(lines):
    findings = []
    label_pattern = re.compile(
        r"\b(?:transaction\s*(?:id|number|no)?|txn\s*(?:id|number|no)?|utr|reference\s*(?:id|number|no)?)\b",
        flags=re.IGNORECASE,
    )
    blocked_tail_pattern = re.compile(
        r"\b(?:name|email|phone|mobile|amount|date|time|status|bank|account)\b",
        flags=re.IGNORECASE,
    )

    for index, line in enumerate(lines):
        if not label_pattern.search(line):
            continue

        candidate_lines = [line]
        if index + 1 < len(lines):
            candidate_lines.append(lines[index + 1])
        if index + 2 < len(lines):
            candidate_lines.append(lines[index + 2])

        best_candidate = None
        best_score = None

        for candidate_line_index, candidate_line in enumerate(candidate_lines):
            search_area = candidate_line
            if candidate_line_index == 0:
                split_match = label_pattern.search(candidate_line)
                if split_match:
                    search_area = candidate_line[split_match.end() :]
                if blocked_tail_pattern.search(search_area):
                    continue

            for raw_token in re.findall(r"[A-Za-z0-9\-]{6,}", search_area):
                if not _is_transaction_like(raw_token):
                    continue

                normalized = _normalize_token(raw_token)
                digit_count = sum(char.isdigit() for char in normalized)
                has_letter = any(char.isalpha() for char in normalized)
                score = (
                    candidate_line_index,
                    0 if has_letter else 1,
                    -digit_count,
                    len(normalized),
                )

                if best_score is None or score < best_score:
                    best_score = score
                    best_candidate = raw_token

        if best_candidate:
            findings.append(best_candidate)

    return findings


def _extract_transaction_from_text(text):
    findings = []
    patterns = (
        r'\b(?:transaction\s*(?:id|number|no)?|txn\s*(?:id|number|no)?|utr|reference\s*(?:id|number|no)?)\b'
        r'[\s:=\-]{0,8}(?:is[\s:=\-]{0,4})?([A-Za-z0-9\-]{8,20})\b',
        r'\b(?:transaction\s*(?:id|number|no)?|txn\s*(?:id|number|no)?|utr|reference)\b'
        r'[\w\s:=\-]{0,40}?\b([A-Za-z0-9\-]{8,20})\b',
    )

    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = match.group(1).strip()
            if _is_transaction_like(value):
                findings.append(value)

    return findings


def _extract_transaction_from_layout(extracted):
    if not extracted:
        return []

    findings = []
    label_pattern = re.compile(
        r'(?:transaction|txn|utr|reference)',
        flags=re.IGNORECASE,
    )

    for item in extracted:
        item_text = item.get('text', '')
        if not label_pattern.search(item_text):
            continue

        bbox = item.get('bbox') or []
        if not bbox:
            continue

        item_left = min(point[0] for point in bbox)
        item_right = max(point[0] for point in bbox)
        item_bottom = max(point[1] for point in bbox)

        candidates = []
        for other in extracted:
            other_text = (other.get('text') or '').strip()
            if not _is_transaction_like(other_text):
                continue

            other_bbox = other.get('bbox') or []
            if not other_bbox:
                continue

            other_left = min(point[0] for point in other_bbox)
            other_right = max(point[0] for point in other_bbox)
            other_top = min(point[1] for point in other_bbox)

            horizontal_overlap = min(item_right, other_right) - max(item_left, other_left)
            horizontal_gap = min(abs(other_left - item_left), abs(other_right - item_right))
            vertical_gap = other_top - item_bottom

            if vertical_gap < -10 or vertical_gap > 260:
                continue
            if horizontal_overlap < -60 and horizontal_gap > 180:
                continue

            normalized = _normalize_token(other_text)
            digit_count = sum(char.isdigit() for char in normalized)
            has_letter = any(char.isalpha() for char in normalized)
            candidates.append((
                max(vertical_gap, 0),
                horizontal_gap,
                0 if has_letter else 1,
                -digit_count,
                other_text,
            ))

        if candidates:
            candidates.sort()
            findings.append(candidates[0][4])

    return findings


def _is_otp_like(token):
    digits = re.sub(r"\D", "", token)
    return len(digits) in {4, 5, 6, 7, 8}


def _extract_otp_candidates(lines):
    findings = []
    label_pattern = re.compile(
        r"\b(?:otp|one[\s-]*time\s+password|verification\s+code|auth(?:entication)?\s+code|security\s+code)\b",
        flags=re.IGNORECASE,
    )
    ignore_pattern = re.compile(
        r"\b(?:transaction|reference|utr|amount|balance|account|a/c|phone|mobile|email|date|time)\b",
        flags=re.IGNORECASE,
    )

    for index, line in enumerate(lines):
        if not label_pattern.search(line):
            continue

        candidate_lines = [line]
        if index + 1 < len(lines):
            candidate_lines.append(lines[index + 1])

        best_candidate = None
        best_score = None

        for candidate_line_index, candidate_line in enumerate(candidate_lines):
            if candidate_line_index > 0 and ignore_pattern.search(candidate_line):
                continue

            search_area = candidate_line
            if candidate_line_index == 0:
                split_match = label_pattern.search(candidate_line)
                if split_match:
                    search_area = candidate_line[split_match.end() :]

            for raw_token in re.findall(r"\b\d{4,8}\b", search_area):
                if not _is_otp_like(raw_token):
                    continue

                score = (
                    candidate_line_index,
                    abs(len(raw_token) - 6),
                )
                if best_score is None or score < best_score:
                    best_score = score
                    best_candidate = raw_token

        if best_candidate:
            findings.append(best_candidate)

    return findings


def _extract_otp_from_text(text):
    findings = []
    patterns = (
        r'\b(?:otp|one[\s-]*time\s+password|verification\s+code|auth(?:entication)?\s+code|security\s+code)\b'
        r'[\s:=\-]{0,8}(?:is[\s:=\-]{0,4})?(\d{4,8})\b',
        r'\b(?:your\s+)?(?:otp|verification\s+code|authentication\s+code)\b'
        r'[\w\s:=\-]{0,30}?\b(\d{4,8})\b',
    )

    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = match.group(1).strip()
            if _is_otp_like(value):
                findings.append(value)

    return findings


def _extract_otp_from_layout(extracted):
    if not extracted:
        return []

    findings = []
    label_pattern = re.compile(
        r'(?:otp|verification|auth(?:entication)?|security\s+code)',
        flags=re.IGNORECASE,
    )

    for item in extracted:
        item_text = item.get('text', '')
        if not label_pattern.search(item_text):
            continue

        bbox = item.get('bbox') or []
        if not bbox:
            continue

        item_left = min(point[0] for point in bbox)
        item_right = max(point[0] for point in bbox)
        item_top = min(point[1] for point in bbox)
        item_bottom = max(point[1] for point in bbox)

        candidates = []
        for other in extracted:
            other_text = (other.get('text') or '').strip()
            if not re.fullmatch(r'\d{4,8}', other_text):
                continue

            other_bbox = other.get('bbox') or []
            if not other_bbox:
                continue

            other_left = min(point[0] for point in other_bbox)
            other_right = max(point[0] for point in other_bbox)
            other_top = min(point[1] for point in other_bbox)

            horizontal_overlap = min(item_right, other_right) - max(item_left, other_left)
            horizontal_gap = min(abs(other_left - item_left), abs(other_right - item_right))
            vertical_gap = other_top - item_bottom

            if vertical_gap < -10 or vertical_gap > 220:
                continue
            if horizontal_overlap < -40 and horizontal_gap > 140:
                continue

            candidates.append((max(vertical_gap, 0), horizontal_gap, other_text))

        if candidates:
            candidates.sort(key=lambda value: (value[0], value[1], abs(len(value[2]) - 6)))
            findings.append(candidates[0][2])

    return findings


def _append_contextual_matches(findings, finding_type, pattern, text, group_index=0):
    matches = []
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        value = match.group(group_index).strip()
        if value:
            matches.append(value)
    _append_unique(findings, finding_type, matches)


def _extract_banking_amounts(lines, text):
    amount_pattern = re.compile(
        r"(?<![A-Za-z0-9])(?:rs\.?|inr|₹)?\s*(\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?|\d{3,}(?:\.\d{1,2})?)(?![A-Za-z0-9])",
        flags=re.IGNORECASE,
    )
    transaction_label = re.compile(
        r"\b(?:debited|credited|debit|credit|paid|received|transferred|withdrawn|deposited|amount)\b",
        flags=re.IGNORECASE,
    )
    balance_label = re.compile(
        r"\b(?:available\s+balance|avail(?:able)?\s+bal|current\s+balance|closing\s+balance|balance)\b",
        flags=re.IGNORECASE,
    )
    transaction_amounts = []
    balance_amounts = []

    for line in lines or [text]:
        for match in amount_pattern.finditer(line):
            value = match.group(0).strip()
            digits = re.sub(r"\D", "", value)
            if len(digits) < 2:
                continue

            window_start = max(0, match.start() - 45)
            window_end = min(len(line), match.end() + 45)
            before_text = line[window_start:match.start()]
            after_text = line[match.end():window_end]

            if balance_label.search(before_text):
                balance_amounts.append(value)
            elif transaction_label.search(before_text) or transaction_label.search(after_text):
                transaction_amounts.append(value)

    return transaction_amounts, balance_amounts


def detect_sensitive_data(text, extracted=None):
    findings = []
    ocr_lines = _group_ocr_lines(extracted)

    # Aadhaar number pattern (XXXX XXXX XXXX)
    aadhaar = re.findall(r'\b\d{4}\s?\d{4}\s?\d{4}\b(?!\s?\d)', text)
    _append_unique(findings, 'Aadhaar Number', aadhaar)

    # PAN number pattern (ABCDE1234F)
    pan = re.findall(r'\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b', text)
    _append_unique(findings, 'PAN Number', pan)

    # Phone number pattern (Indian mobile numbers)
    phone = re.findall(r'\b[6-9]\d{9}\b', text)
    _append_unique(findings, 'Phone Number', phone)

    # Email pattern
    email = re.findall(r'\b[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}\b', text)
    _append_unique(findings, 'Email', email)

    # Credit card pattern
    card = re.findall(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', text)
    _append_unique(findings, 'Credit Card', card)

    # UPI ID pattern
    upi = re.findall(
        r'\b[\w.\-]{2,}@(?![\w.\-]*\.[A-Za-z]{2,}\b)'
        r'(?:paytm|upi|okaxis|okhdfcbank|okicici|oksbi|ybl|ibl|axl|waicici|apl)\b',
        text,
        flags=re.IGNORECASE,
    )
    _append_unique(findings, 'UPI ID', upi)

    # IP Address pattern
    ip = re.findall(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', text)
    _append_unique(findings, 'IP Address', ip)

    # GST number pattern (22AAAAA0000A1Z5)
    gst = re.findall(r'\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b', text)
    _append_unique(findings, 'GST Number', gst)

    # Passport number pattern (A1234567)
    passport = re.findall(r'\b[A-PR-WYa-pr-wy][1-9]\d{7}\b', text)
    _append_unique(findings, 'Passport Number', passport)

    # Date of birth pattern (DD/MM/YYYY or DD-MM-YYYY)
    dob = re.findall(r'\b\d{2}[/-]\d{2}[/-]\d{4}\b', text)
    _append_unique(findings, 'Date of Birth', dob)

    # IFSC code pattern (SBIN0001234)
    ifsc = re.findall(r'\b[A-Z]{4}0[A-Z0-9]{6}\b', text)
    _append_unique(findings, 'IFSC Code', ifsc)

    # Transaction reference detection uses OCR line context to avoid grabbing unrelated values.
    _append_unique(findings, 'Transaction ID', _extract_transaction_candidates(ocr_lines))
    _append_unique(findings, 'Transaction ID', _extract_transaction_from_text(text))
    _append_unique(findings, 'Transaction ID', _extract_transaction_from_layout(extracted))

    # OTP / verification-code detection based on nearby labels and next-line context.
    _append_unique(findings, 'OTP', _extract_otp_candidates(ocr_lines))
    _append_unique(findings, 'OTP', _extract_otp_from_text(text))
    _append_unique(findings, 'OTP', _extract_otp_from_layout(extracted))

    # Password-like fields based on nearby labels
    _append_contextual_matches(
        findings,
        'Password',
        r'\b(?:password|passcode|passwd|pwd|pass|mpin|pin)\b'
        r'\s*[:=\-]?\s*([^\s,;]{3,})',
        text,
        1,
    )

    transaction_amounts, balance_amounts = _extract_banking_amounts(ocr_lines, text)
    _append_unique(findings, 'Transaction Amount', transaction_amounts)
    _append_unique(findings, 'Available Balance', balance_amounts)

    return findings
