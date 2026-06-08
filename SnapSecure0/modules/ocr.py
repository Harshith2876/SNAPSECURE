import os
import shutil

import cv2
import pytesseract
from pytesseract import Output


def _configure_tesseract():
    configured_path = os.environ.get("TESSERACT_CMD")
    if configured_path and os.path.exists(configured_path):
        pytesseract.pytesseract.tesseract_cmd = configured_path
        return configured_path

    detected_path = shutil.which("tesseract")
    common_paths = [
        detected_path,
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
    ]

    for path in common_paths:
        if path and os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            return path

    return None


def _parse_confidence(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def _line_bbox(parts):
    left = min(part["left"] for part in parts)
    top = min(part["top"] for part in parts)
    right = max(part["left"] + part["width"] for part in parts)
    bottom = max(part["top"] + part["height"] for part in parts)
    return [
        [left, top],
        [right, top],
        [right, bottom],
        [left, bottom],
    ]


def _scale_bbox(bbox, scale):
    if not scale or scale == 1:
        return bbox

    scaled = []
    for x, y in bbox:
        scaled.append([x / scale, y / scale])
    return scaled


def _extract_words(image_path, config, scale=1):
    image = cv2.imread(image_path)
    if image is None:
        return []

    data = pytesseract.image_to_data(image, output_type=Output.DICT, config=config)
    extracted = []

    for index, raw_text in enumerate(data["text"]):
        text = " ".join(raw_text.split())
        confidence = _parse_confidence(data["conf"][index])
        if not text or confidence < 30:
            continue

        part = {
            "text": text,
            "confidence": confidence,
            "left": data["left"][index],
            "top": data["top"][index],
            "width": data["width"][index],
            "height": data["height"][index],
        }
        extracted.append(
            {
                "text": text,
                "bbox": _scale_bbox(_line_bbox([part]), scale),
                "confidence": confidence / 100,
                "line_key": (
                    data["block_num"][index],
                    data["par_num"][index],
                    data["line_num"][index],
                ),
                "word_index": data["word_num"][index],
            }
        )

    return extracted


def extract_text(image_paths):
    if isinstance(image_paths, str):
        image_paths = [image_paths]

    if not _configure_tesseract():
        raise RuntimeError(
            "Tesseract OCR is not installed. Install Tesseract and optionally set "
            "the TESSERACT_CMD environment variable to the executable path."
        )

    extracted = []
    seen = set()
    configs = ("--oem 3 --psm 6", "--oem 3 --psm 11")

    for image_info in image_paths:
        if isinstance(image_info, dict):
            image_path = image_info.get("path")
            scale = image_info.get("scale", 1)
        else:
            image_path = image_info
            scale = 1

        for config in configs:
            for item in _extract_words(image_path, config, scale):
                bbox = item["bbox"]
                dedupe_key = (
                    item["text"].strip().lower(),
                    round(bbox[0][0] / 10),
                    round(bbox[0][1] / 10),
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                extracted.append(item)

    extracted.sort(
        key=lambda item: (
            item.get("line_key", (0, 0, 0))[0],
            item.get("line_key", (0, 0, 0))[1],
            item.get("line_key", (0, 0, 0))[2],
            item.get("word_index", 0),
            item["bbox"][0][1],
            item["bbox"][0][0],
        )
    )
    return extracted
