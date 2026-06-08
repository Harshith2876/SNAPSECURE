import re


TRAINING_EXAMPLES = [
    ("Your OTP is 482913. Do not share this code.", "sensitive"),
    ("Aadhaar number 1234 5678 9012", "sensitive"),
    ("PAN ABCDE1234F and date of birth 12/08/1999", "sensitive"),
    ("Payment successful UPI reference 928374651234", "sensitive"),
    ("Password reset code and account details", "sensitive"),
    ("Credit card 4111 1111 1111 1111 expires soon", "sensitive"),
    ("Email john@example.com and phone 9876543210", "sensitive"),
    ("Bank balance and transaction id visible", "sensitive"),
    ("My name is p.harshith and my phone number is 9509839041", "sensitive"),
    ("Contact me at aarav@gmail.com for payment confirmation", "sensitive"),
    ("UPI no harshith@ybl and transaction id ABCD123456789", "sensitive"),
    ("Account holder name Ramesh Kumar account ending XX9081", "sensitive"),
    ("Billing address 12 MG Road Bengaluru Karnataka", "sensitive"),
    ("IFSC code SBIN0001234 and account number visible", "sensitive"),
    ("Passport A1234567 and date of birth are shown", "sensitive"),
    ("Login password akodtrm@121 is visible", "sensitive"),
    ("Verification code 789012 sent to your mobile", "sensitive"),
    ("Credit card ending 4242 and CVV are visible", "sensitive"),
    ("Bank statement contains balance and debit details", "sensitive"),
    ("Personal identity document with name and address", "sensitive"),
    ("Employee ID and confidential salary slip", "sensitive"),
    ("Patient name and hospital report number", "sensitive"),
    ("Invoice contains GST number and phone number", "sensitive"),
    ("UPI payment successful reference number copied", "sensitive"),
    ("Welcome to SnapSecure privacy dashboard", "normal"),
    ("Upload a screenshot to analyze the image", "normal"),
    ("Meeting notes and public announcement", "normal"),
    ("Product description and general workflow", "normal"),
    ("Weather update for the weekend", "normal"),
    ("College project report introduction", "normal"),
    ("This image contains a simple quote", "normal"),
    ("User interface button and title text", "normal"),
    ("The presentation starts at ten in the seminar hall", "normal"),
    ("Project abstract and workflow section", "normal"),
    ("A simple paragraph about screenshot safety", "normal"),
    ("Dashboard heading and navigation menu", "normal"),
    ("Instructions for selecting a file", "normal"),
    ("General software feature description", "normal"),
    ("Team members discussed module integration", "normal"),
    ("The image contains a logo and title", "normal"),
    ("Welcome message and button labels", "normal"),
    ("No personal details are present in this note", "normal"),
    ("The report explains OCR preprocessing steps", "normal"),
    ("A classroom announcement for students", "normal"),
    ("Plain text without private user data", "normal"),
    ("System generated placeholder content", "normal"),
    ("Public event schedule and venue title", "normal"),
    ("Generic product information screen", "normal"),
]

SENSITIVE_KEYWORDS = {
    "aadhaar",
    "pan",
    "otp",
    "password",
    "passcode",
    "pin",
    "upi",
    "transaction",
    "account",
    "bank",
    "credit card",
    "debit card",
    "passport",
    "ifsc",
    "dob",
    "date of birth",
    "email",
    "phone",
    "mobile",
    "name",
    "address",
    "account holder",
    "cvv",
    "salary",
    "patient",
    "confidential",
    "verification code",
    "reference number",
    "id number",
}


def _train_classifier():
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
    except ImportError:
        return None

    texts = [item[0] for item in TRAINING_EXAMPLES]
    labels = [item[1] for item in TRAINING_EXAMPLES]
    model = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), lowercase=True)),
            ("classifier", LogisticRegression(max_iter=1000)),
        ]
    )
    model.fit(texts, labels)
    return model


def _keyword_score(text):
    lowered = text.lower()
    hits = [keyword for keyword in SENSITIVE_KEYWORDS if keyword in lowered]

    pattern_hits = 0
    patterns = (
        r"\b[6-9]\d{9}\b",
        r"\b\d{4}\s?\d{4}\s?\d{4}\b",
        r"\b[A-Z]{5}\d{4}[A-Z]\b",
        r"\b[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}\b",
        r"\b\d{4,8}\b",
        r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
        r"\b[A-PR-WYa-pr-wy][1-9]\d{7}\b",
        r"\b\d{2}[/-]\d{2}[/-]\d{4}\b",
        r"\b[A-Za-z]{2,}\d{6,}[A-Za-z0-9]*\b",
    )
    for pattern in patterns:
        if re.search(pattern, text):
            pattern_hits += 1

    raw_score = min(0.95, 0.18 + (len(hits) * 0.16) + (pattern_hits * 0.15))
    if not hits and not pattern_hits:
        raw_score = 0.12

    return raw_score, hits


def classify_sensitivity(text):
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return {
            "label": "normal",
            "confidence": 0.0,
            "score_boost": 0,
            "signals": [],
            "engine": "empty",
        }

    model = _train_classifier()
    keyword_confidence, signals = _keyword_score(cleaned)

    if model:
        probabilities = model.predict_proba([cleaned])[0]
        classes = list(model.classes_)
        sensitive_probability = probabilities[classes.index("sensitive")]
        confidence = max(float(sensitive_probability), keyword_confidence)
        engine = "scikit-learn logistic regression + keyword calibration"
    else:
        confidence = keyword_confidence
        engine = "keyword-calibrated fallback classifier"

    label = "sensitive" if confidence >= 0.55 else "normal"
    score_boost = 0
    if confidence >= 0.85:
        score_boost = 2
    elif confidence >= 0.65:
        score_boost = 1

    return {
        "label": label,
        "confidence": round(confidence, 3),
        "score_boost": score_boost,
        "signals": signals[:8],
        "engine": engine,
    }


def classify_sensitive_lines(extracted):
    grouped = {}
    for item in extracted or []:
        line_key = item.get("line_key")
        if not line_key:
            continue
        grouped.setdefault(line_key, []).append(item)

    findings = []
    seen_values = set()
    for line_key in sorted(grouped.keys()):
        items = sorted(grouped[line_key], key=lambda item: item.get("word_index", 0))
        line_text = " ".join(item["text"] for item in items).strip()
        if not line_text or line_text in seen_values:
            continue

        result = classify_sensitivity(line_text)
        if result["label"] == "sensitive" and result["confidence"] >= 0.82:
            findings.append(
                {
                    "type": "ML Sensitive Context",
                    "value": line_text,
                    "source": "ml",
                    "confidence": result["confidence"],
                }
            )
            seen_values.add(line_text)

    return findings[:5]
