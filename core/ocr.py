"""
OCR extraction layer.

Wraps whichever OCR engine you choose behind one function,
`extract_text()`, so the rest of the app never needs to know which
engine is running underneath. Default engine is Tesseract (free,
offline, no API key) — swap in Google Cloud Vision by implementing
`_extract_with_cloud_vision()` and changing ENGINE below.
"""

import os
import shutil
from functools import lru_cache
from pathlib import Path

import pytesseract
import cv2
import numpy as np
from PIL import Image

ENGINE = "tesseract"  # change to "cloud_vision" once you wire up an API key


class OCRConfigurationError(RuntimeError):
    """Raised when the selected OCR engine is not available on this machine."""


@lru_cache(maxsize=1)
def get_tesseract_path() -> str:
    """Return the configured Tesseract executable or raise a useful setup error."""
    configured_path = os.getenv("TESSERACT_CMD", "").strip().strip('"')
    candidates = [
        configured_path,
        shutil.which("tesseract"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]

    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate))

    raise OCRConfigurationError(
        "Tesseract OCR is not installed or is not available on PATH. "
        "Install it from https://github.com/UB-Mannheim/tesseract/wiki, "
        "restart the app, or set TESSERACT_CMD to the full path of "
        "tesseract.exe."
    )


def extract_text(pil_image: Image.Image) -> str:
    """Extract raw text from a (preferably preprocessed) label image."""
    if ENGINE == "tesseract":
        return _extract_with_tesseract(pil_image)
    elif ENGINE == "cloud_vision":
        return _extract_with_cloud_vision(pil_image)
    else:
        raise ValueError(f"Unknown OCR engine: {ENGINE}")


def _extract_with_tesseract(pil_image: Image.Image) -> str:
    pytesseract.pytesseract.tesseract_cmd = get_tesseract_path()
    image = pil_image.convert("L")
    image_array = np.array(image)
    variants = [
        image_array,
        cv2.adaptiveThreshold(
            image_array,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        ),
        cv2.threshold(image_array, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
    ]

    best_text = ""
    best_score = -1.0
    try:
        for variant in variants:
            for page_mode in (6, 11, 12):
                config = f"--oem 3 --psm {page_mode}"
                data = pytesseract.image_to_data(
                    variant,
                    config=config,
                    output_type=pytesseract.Output.DICT,
                )
                text_parts = []
                confidences = []
                for text, confidence in zip(data["text"], data["conf"]):
                    if text.strip():
                        text_parts.append(text)
                        try:
                            confidence_value = float(confidence)
                        except (TypeError, ValueError):
                            confidence_value = 0.0
                        if confidence_value >= 0:
                            confidences.append(confidence_value)

                candidate_text = " ".join(text_parts).strip()
                if not candidate_text:
                    continue
                confidence_score = sum(confidences) / len(confidences)
                length_bonus = min(len(candidate_text), 120) / 120
                score = confidence_score + length_bonus
                if score > best_score:
                    best_score = score
                    best_text = candidate_text
    except pytesseract.TesseractNotFoundError as error:
        get_tesseract_path.cache_clear()
        raise OCRConfigurationError(
            "Tesseract was found but could not be started. Check the "
            "TESSERACT_CMD path or reinstall Tesseract OCR."
        ) from error
    return best_text


def _extract_with_cloud_vision(pil_image: Image.Image) -> str:
    """
    Placeholder for Google Cloud Vision integration.

    To enable:
      1. pip install google-cloud-vision
      2. Set GOOGLE_APPLICATION_CREDENTIALS env var to your service-account JSON
      3. Uncomment the implementation below
    """
    raise NotImplementedError(
        "Cloud Vision not configured. Set ENGINE='tesseract' or implement this function."
    )
    # from google.cloud import vision
    # import io
    # client = vision.ImageAnnotatorClient()
    # buf = io.BytesIO()
    # pil_image.save(buf, format="PNG")
    # image = vision.Image(content=buf.getvalue())
    # response = client.text_detection(image=image)
    # return response.full_text_annotation.text
