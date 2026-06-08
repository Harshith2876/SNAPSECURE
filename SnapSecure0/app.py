import os
import shutil
from flask import Flask, render_template, request, send_file
from werkzeug.utils import secure_filename

from modules.contextAnalyzer import analyze_context
from modules.preprocessor import preprocess_image
from modules.ocr import extract_text
from modules.detector import detect_sensitive_data
from modules.hybrid_analyzer import enrich_with_hybrid_analysis
from modules.riskScore import calculate_risk
from modules.masker import highlight_sensitive, redact_sensitive

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
DOWNLOAD_FOLDER = os.path.join(BASE_DIR, 'downloads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER


def normalize_ocr_text(text):
    replacements = [
        ('_com', '.com'),
        ('_in', '.in'),
        ('_org', '.org'),
        ('_net', '.net'),
        (' com', '.com'),
        (' in', '.in'),
        (' org', '.org'),
        (' net', '.net'),
        (' @', '@'),
        ('@ ', '@'),
        (' .', '.'),
        ('. ', '.'),
    ]

    normalized = text
    for source, target in replacements:
        normalized = normalized.replace(source, target)
    return normalized


def analyze_image(filepath):
    processed_paths = preprocess_image(filepath)
    extracted = extract_text(processed_paths)
    full_text = normalize_ocr_text(' '.join([item['text'] for item in extracted]))
    findings = detect_sensitive_data(full_text, extracted)
    context = analyze_context(full_text, extracted, findings)
    if context['derived_findings']:
        findings = findings + context['derived_findings']
    findings, context = enrich_with_hybrid_analysis(full_text, extracted, findings, context)
    risk = calculate_risk(findings, context)
    return extracted, findings, risk, context


def parse_selected_indices(values):
    selected = []
    for value in values:
        try:
            index = int(value)
        except (TypeError, ValueError):
            continue
        if index not in selected:
            selected.append(index)
    return selected

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['screenshot']
    if file:
        filename = secure_filename(file.filename) or 'upload.png'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        try:
            extracted, findings, risk, context = analyze_image(filepath)
        except (RuntimeError, ValueError) as exc:
            return (
                f"<h3>OCR setup issue</h3><p>{exc}</p>"
                "<p>Install the Tesseract OCR engine and the Python dependencies, "
                "then try again.</p>"
            )
        highlighted_path = highlight_sensitive(filepath, extracted, findings)
        return render_template(
            'result.html',
            risk=risk,
            findings=findings,
            context=context,
            image_name=os.path.basename(highlighted_path),
            download_image_name=os.path.basename(highlighted_path),
            original_name=os.path.basename(filepath),
            selected_indices=[],
        )
    return "No file uploaded!"


@app.route('/redact', methods=['POST'])
def redact():
    filename = secure_filename(request.form.get('original_name', ''))
    selected_index = request.form.get('finding_index')
    action = request.form.get('action', 'single')
    selected_indices = parse_selected_indices(request.form.getlist('selected_indices'))

    if not filename:
        return "Missing redaction details."

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(filepath):
        return "Original file not found."

    try:
        extracted, findings, risk, context = analyze_image(filepath)
        if action == 'all':
            selected_indices = list(range(len(findings)))
        elif action == 'clear':
            selected_indices = []
        elif selected_index is not None:
            try:
                selected_index_int = int(selected_index)
            except (TypeError, ValueError):
                selected_index_int = None

            if selected_index_int is not None:
                if selected_index_int in selected_indices:
                    selected_indices = [
                        index for index in selected_indices if index != selected_index_int
                    ]
                else:
                    selected_indices = parse_selected_indices(
                        selected_indices + [selected_index_int]
                    )

        preview_path, export_path = redact_sensitive(filepath, extracted, findings, selected_indices)
    except (RuntimeError, ValueError) as exc:
        return (
            f"<h3>Redaction issue</h3><p>{exc}</p>"
            "<p>Please verify the OCR setup and try again.</p>"
        )

    return render_template(
        'result.html',
        risk=risk,
        findings=findings,
        context=context,
        image_name=os.path.basename(preview_path),
        download_image_name=os.path.basename(export_path),
        original_name=os.path.basename(filepath),
        selected_indices=selected_indices,
    )


@app.route('/download', methods=['POST'])
def download():
    image_name = secure_filename(request.form.get('image_name', ''))
    if not image_name:
        return "Missing image to download."

    source_path = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
    if not os.path.exists(source_path):
        return "Generated image not found."

    download_path = os.path.join(app.config['DOWNLOAD_FOLDER'], image_name)
    shutil.copy2(source_path, download_path)
    return send_file(download_path, as_attachment=True, download_name=image_name)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_file(os.path.join(UPLOAD_FOLDER, filename))

if __name__ == '__main__':
    app.run(debug=True)
