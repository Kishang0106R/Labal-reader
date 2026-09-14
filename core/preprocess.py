"""
Image preprocessing for label scans.

Cleans up a raw product-label photo before OCR so that text extraction
is more accurate: converts to grayscale, boosts contrast, reduces
noise, and applies adaptive thresholding.
"""

import cv2
import numpy as np
from PIL import Image


def pil_to_cv2(pil_image: Image.Image) -> np.ndarray:
    """Convert a PIL image (RGB) to an OpenCV image (BGR)."""
    rgb = pil_image.convert("RGB")
    arr = np.array(rgb)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def cv2_to_pil(cv_image: np.ndarray) -> Image.Image:
    """Convert an OpenCV image (BGR or grayscale) back to PIL for display."""
    if len(cv_image.shape) == 2:
        return Image.fromarray(cv_image)
    rgb = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def preprocess_for_ocr(pil_image: Image.Image, max_dim: int = 2400) -> Image.Image:
    """
    Run a standard cleanup pipeline on a label image before OCR.

        Steps:
            1. Resize (cap the largest dimension so OCR runs fast & consistently)
            2. Grayscale
            3. Denoise
            4. Contrast enhancement (CLAHE)

        The enhanced grayscale image is returned instead of a single thresholded
        image. Tesseract performs better when the OCR layer can compare grayscale
        and thresholded variants, especially for colored or low-contrast labels.

    Returns a PIL image ready to hand to the OCR engine.
    """
    cv_img = pil_to_cv2(pil_image)

    # 1. Resize if oversized, preserving aspect ratio
    h, w = cv_img.shape[:2]
    largest_dimension = max(h, w)
    if largest_dimension == 0:
        raise ValueError("The uploaded image has no usable pixels.")

    scale = max_dim / largest_dimension
    if scale < 1:
        cv_img = cv2.resize(
            cv_img,
            (int(w * scale), int(h * scale)),
            interpolation=cv2.INTER_AREA,
        )
    elif largest_dimension < 2200:
        scale = 2200 / largest_dimension
        cv_img = cv2.resize(
            cv_img,
            (int(w * scale), int(h * scale)),
            interpolation=cv2.INTER_CUBIC,
        )

    # 2. Grayscale
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

    # 3. Denoise
    denoised = cv2.fastNlMeansDenoising(gray, h=10)

    # 4. Contrast boost (CLAHE handles uneven label lighting better than global equalization)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)

    return cv2_to_pil(enhanced)


def estimate_text_heights_mm(pil_image: Image.Image, dpi: int = 300) -> list[float]:
    """
    Rough readability/font-size check.

    Finds text-like contours in the (preprocessed) image and estimates
    each one's height in millimetres, assuming the image was captured
    at the given DPI. This is a simplified stand-in for a full font-size
    compliance check — good enough for a prototype demo, not a legal
    measurement tool.
    """
    cv_img = pil_to_cv2(pil_image)
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    heights_px = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        # Filter out noise / very large blobs (likely not single characters)
        if 5 < h < 80 and 2 < w < 80:
            heights_px.append(h)

    if not heights_px:
        return []

    mm_per_px = 25.4 / dpi
    return sorted(h * mm_per_px for h in heights_px)
