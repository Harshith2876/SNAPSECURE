import os
import re

import cv2


def _normalize_value(text, finding_type):
    text = text.lower().strip()

    if finding_type in {
        "Aadhaar Number",
        "Phone Number",
        "Credit Card",
        "IP Address",
        "Date of Birth",
        "OTP",
        "Transaction Amount",
        "Available Balance",
    }:
        return re.sub(r"[^0-9]", "", text)

    if finding_type in {
        "PAN Number",
        "GST Number",
        "Passport Number",
        "IFSC Code",
        "UPI ID",
        "Transaction ID",
        "Masked Account Number",
    }:
        return re.sub(r"[^a-z0-9@]", "", text)

    if finding_type == "Email":
        return re.sub(r"[^a-z0-9@._+-]", "", text)

    return re.sub(r"\s+", " ", text)


def _bbox_coords(bbox):
    x1 = int(round(min(point[0] for point in bbox)))
    y1 = int(round(min(point[1] for point in bbox)))
    x2 = int(round(max(point[0] for point in bbox)))
    y2 = int(round(max(point[1] for point in bbox)))
    return x1, y1, x2, y2


def _match_score(item_text, finding):
    normalized_item = _normalize_value(item_text, finding["type"])
    normalized_value = _normalize_value(finding["value"], finding["type"])

    if not normalized_item or not normalized_value:
        return 0

    if normalized_value in normalized_item:
        return len(normalized_value)

    return 0


def _combine_bbox(items):
    boxes = [item["bbox"] for item in items]
    x1 = int(round(min(min(point[0] for point in bbox) for bbox in boxes)))
    y1 = int(round(min(min(point[1] for point in bbox) for bbox in boxes)))
    x2 = int(round(max(max(point[0] for point in bbox) for bbox in boxes)))
    y2 = int(round(max(max(point[1] for point in bbox) for bbox in boxes)))
    return x1, y1, x2, y2


def _group_by_line(extracted):
    grouped = {}
    for item in extracted:
        line_key = item.get("line_key", ("single", id(item)))
        grouped.setdefault(line_key, []).append(item)

    for items in grouped.values():
        items.sort(key=lambda item: item.get("word_index", 0))

    return grouped


def _best_region_for_finding(extracted, finding):
    normalized_value = _normalize_value(finding["value"], finding["type"])
    if not normalized_value:
        return None

    best_region = None
    best_score = None

    for line_items in _group_by_line(extracted).values():
        for start in range(len(line_items)):
            for end in range(start, len(line_items)):
                span_items = line_items[start : end + 1]
                span_text = " ".join(item["text"] for item in span_items)
                normalized_span = _normalize_value(span_text, finding["type"])
                if normalized_value not in normalized_span:
                    continue

                span_length = len(normalized_span)
                extra_chars = max(0, span_length - len(normalized_value))
                word_count = len(span_items)
                score = (extra_chars, word_count)

                if best_score is None or score < best_score:
                    best_score = score
                    best_region = {
                        "type": finding["type"],
                        "value": finding["value"],
                        "bbox": _combine_bbox(span_items),
                    }

    if best_region:
        return best_region

    best_item = None
    best_item_score = 0
    for item in extracted:
        score = _match_score(item["text"], finding)
        if score > best_item_score:
            best_item_score = score
            best_item = item

    if not best_item:
        return None

    return {
        "type": finding["type"],
        "value": finding["value"],
        "bbox": _bbox_coords(best_item["bbox"]),
    }


def match_findings_to_regions(extracted, findings):
    matched_regions = []

    for index, finding in enumerate(findings):
        best_region = _best_region_for_finding(extracted, finding)
        if not best_region:
            continue

        matched_regions.append(
            {
                "index": index,
                "type": best_region["type"],
                "value": best_region["value"],
                "bbox": best_region["bbox"],
            }
        )

    return matched_regions


def _highlight_style():
    colors = {
        "Aadhaar Number": (0, 0, 255),
        "PAN Number": (0, 0, 255),
        "Credit Card": (0, 0, 255),
        "Passport Number": (0, 0, 255),
        "GST Number": (0, 0, 255),
        "IFSC Code": (0, 0, 255),
        "Masked Account Number": (255, 140, 0),
        "Phone Number": (0, 165, 255),
        "UPI ID": (0, 165, 255),
        "Date of Birth": (0, 165, 255),
        "IP Address": (0, 255, 255),
        "Email": (0, 255, 255),
        "Transaction ID": (255, 140, 0),
        "Transaction Amount": (255, 140, 0),
        "Available Balance": (255, 140, 0),
        "OTP": (255, 0, 255),
        "Password": (255, 0, 255),
        "NLP Person Name": (116, 180, 255),
        "NLP Address": (116, 180, 255),
        "NLP Organization": (116, 180, 255),
        "NLP Location": (116, 180, 255),
        "NLP Date": (116, 180, 255),
        "ML Sensitive Context": (105, 240, 199),
    }

    severity = {
        "Aadhaar Number": 3,
        "PAN Number": 3,
        "Credit Card": 3,
        "Passport Number": 3,
        "GST Number": 3,
        "IFSC Code": 3,
        "Masked Account Number": 2,
        "Phone Number": 2,
        "UPI ID": 2,
        "Date of Birth": 2,
        "IP Address": 1,
        "Email": 1,
        "Transaction ID": 2,
        "Transaction Amount": 2,
        "Available Balance": 3,
        "OTP": 4,
        "Password": 4,
        "NLP Person Name": 1,
        "NLP Address": 2,
        "NLP Organization": 1,
        "NLP Location": 1,
        "NLP Date": 1,
        "ML Sensitive Context": 2,
    }

    return colors, severity


def _draw_highlights(image, extracted, findings, excluded_indices=None):
    colors, severity = _highlight_style()
    excluded_indices = set(excluded_indices or [])

    matched_boxes = {}
    for region in match_findings_to_regions(extracted, findings):
        if region["index"] in excluded_indices:
            continue
        coords = region["bbox"]
        if coords not in matched_boxes:
            matched_boxes[coords] = []
        matched_boxes[coords].append(region["type"])

    for (x1, y1, x2, y2), types in matched_boxes.items():
        unique_types = []
        for finding_type in types:
            if finding_type not in unique_types:
                unique_types.append(finding_type)

        primary_type = max(unique_types, key=lambda value: severity.get(value, 0))
        color = colors.get(primary_type, (0, 255, 255))
        label = ", ".join(unique_types[:2])
        if len(unique_types) > 2:
            label += ", +more"

        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            image,
            label,
            (x1, max(20, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
        )


def highlight_sensitive(image_path, extracted, findings):
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("Unable to read the original image for highlighting.")

    _draw_highlights(image, extracted, findings)

    highlighted_path = os.path.join("uploads", "highlighted_" + os.path.basename(image_path))
    cv2.imwrite(highlighted_path, image)
    return highlighted_path


def redact_sensitive(image_path, extracted, findings, selected_indices):
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("Unable to read the original image for redaction.")

    regions = match_findings_to_regions(extracted, findings)
    selected_set = set(selected_indices)
    preview_image = image.copy()
    export_image = image.copy()

    for region in regions:
        if region["index"] not in selected_set:
            continue
        x1, y1, x2, y2 = region["bbox"]
        cv2.rectangle(preview_image, (x1, y1), (x2, y2), (0, 0, 0), thickness=-1)
        cv2.rectangle(export_image, (x1, y1), (x2, y2), (0, 0, 0), thickness=-1)

    _draw_highlights(preview_image, extracted, findings, excluded_indices=selected_set)

    if selected_indices:
        suffix = "_".join(str(index) for index in sorted(selected_set))
    else:
        suffix = "none"

    preview_name = f"redacted_preview_{suffix}_{os.path.basename(image_path)}"
    preview_path = os.path.join("uploads", preview_name)
    export_name = f"redacted_export_{suffix}_{os.path.basename(image_path)}"
    export_path = os.path.join("uploads", export_name)
    cv2.imwrite(preview_path, preview_image)
    cv2.imwrite(export_path, export_image)
    return preview_path, export_path
