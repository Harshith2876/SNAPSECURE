def calculate_risk(findings, context=None):
    
    # Risk weights for each type of sensitive data
    weights = {
    'Aadhaar Number': 3,
    'PAN Number': 3,
    'Credit Card': 4,
    'Phone Number': 2,
    'Email': 1,
    'UPI ID': 3,
    'IP Address': 2,
    'GST Number': 3,
    'Passport Number': 4,
    'Date of Birth': 2,
    'IFSC Code': 3,
    'Transaction ID': 2,
    'Masked Account Number': 2,
    'OTP': 4,
    'Password': 4,
    'NLP Person Name': 1,
    'NLP Address': 2,
    'NLP Organization': 1,
    'NLP Location': 1,
    'NLP Date': 1,
    'ML Sensitive Context': 2,
    'Transaction Amount': 2,
    'Available Balance': 3
    }
    
    # Calculate total score
    score = 0
    for finding in findings:
        data_type = finding['type']
        if data_type in weights:
            score += weights[data_type]

    context = context or {}
    score += int(context.get('score_boost', 0) or 0)
    
    # Classify risk level
    if score == 0:
        risk_level = 'No Risk'
        color = 'green'
    elif score <= 3:
        risk_level = 'Low Risk'
        color = 'green'
    elif score <= 6:
        risk_level = 'Medium Risk'
        color = 'orange'
    else:
        risk_level = 'High Risk'
        color = 'red'
    
    return {
        'score': score,
        'risk_level': risk_level,
        'color': color,
        'context_boost': int(context.get('score_boost', 0) or 0),
    }
