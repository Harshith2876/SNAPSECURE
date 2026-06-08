SnapSecure
SnapSecure is an OCR and ML based sensitive data detection and redaction system.

OCR extracts text and word locations from screenshots.
Rule-based detection identifies Aadhaar, PAN, phone numbers, emails, UPI IDs, OTPs, passwords, transaction IDs, and similar sensitive values.
NLP analysis detects sensitive named entities such as person names, addresses, organizations, locations, and dates.
ML sensitivity scoring classifies the extracted screenshot text as sensitive or normal and adds risk context.
The Flask UI highlights findings, supports selective redaction, and exports the redacted image.
Setup
Install Python dependencies:

pip install -r requirements.txt
Install the Tesseract OCR engine and make sure it is available on your system path. On Windows, SnapSecure also checks:

C:\Program Files\Tesseract-OCR\tesseract.exe
Optional NLP model:

python -m spacy download en_core_web_sm
The app still runs without the spaCy model by using the built-in fallback NLP patterns.

Run
python app.py
Then open:

http://127.0.0.1:5000
Hybrid Detection Flow
The current pipeline is:

Image upload -> preprocessing -> OCR -> rule detector -> context analyzer -> NLP + ML hybrid analyzer -> risk score -> highlight/redact UI
The rule detector remains the main deterministic detection layer. The ML/NLP modules are added as supporting analysis.
