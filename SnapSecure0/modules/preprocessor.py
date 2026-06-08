import os

import cv2
import numpy as np


def _save_variant(base_dir, original_name, suffix, image):
    filename = f"{suffix}_{original_name}"
    path = os.path.join(base_dir, filename)
    cv2.imwrite(path, image)
    return path


def preprocess_image(filepath):
    image = cv2.imread(filepath)
    if image is None:
        raise ValueError("Unable to read the uploaded image.")

    upload_dir = os.path.dirname(filepath)
    original_name = os.path.basename(filepath)

    height, width = image.shape[:2]
    scale = max(1.0, 1600 / max(width, 1))
    if scale > 1.0:
        image = cv2.resize(
            image,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=12)
    contrast = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(denoised)
    _, otsu = cv2.threshold(contrast, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(
        contrast,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        11,
    )

    variants = [
        {
            "path": _save_variant(upload_dir, original_name, "processed_contrast", contrast),
            "scale": scale,
        },
        {
            "path": _save_variant(upload_dir, original_name, "processed_otsu", otsu),
            "scale": scale,
        },
        {
            "path": _save_variant(upload_dir, original_name, "processed_adaptive", adaptive),
            "scale": scale,
        },
    ]

    if np.mean(gray) < 120:
        inverted = cv2.bitwise_not(adaptive)
        variants.append(
            {
                "path": _save_variant(upload_dir, original_name, "processed_inverted", inverted),
                "scale": scale,
            }
        )

    return variants
