"""
AI Certificate Verification Module  –  CertiValidate
======================================================
Capabilities
------------
* OCR text extraction with adaptive preprocessing
* Entity detection  : university, student name, certificate ID, issue date
* Image feature checks : resolution anomaly, tampering (ELA), seal/logo detection
* Weighted scoring (0-100) → ORIGINAL / FAKE + confidence %
* MongoDB + Blockchain cross-validation
"""

import os
import re
import math
import hashlib
import datetime
import logging
from io import BytesIO

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageChops, ImageEnhance

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

# ── Tesseract path (Windows) ─────────────────────────────────────────────────
# Uncomment and adjust if Tesseract is not in PATH:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


# ── Reference template (generic academic certificate) ────────────────────────
BASELINE_TEMPLATE = """
certificate of completion excellence achievement
this is to certify that has successfully completed
course program register number student id roll
signature authorized director principal dean
university college institute academy seal emblem
date awarded conferred degree diploma
"""

# ── University & keyword lists for entity detection ──────────────────────────
UNIVERSITY_KEYWORDS = [
    "university", "college", "institute", "academy", "school",
    "polytechnic", "deemed", "autonomous", "iit", "nit", "bits"
]
CERT_HEADER_WORDS = [
    "certificate", "certify", "completion", "achievement",
    "excellence", "degree", "diploma", "appreciation"
]
SIGNATURE_WORDS = [
    "signature", "sign", "signed", "director", "principal",
    "authorized", "dean", "registrar", "controller"
]

# ─────────────────────────────────────────────────────────────────────────────
# 1.  OCR helpers
# ─────────────────────────────────────────────────────────────────────────────

def _preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
    """Adaptive pre-processing pipeline to maximise OCR accuracy."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    # Upscale small images
    h, w = gray.shape
    if w < 800:
        scale = 800 / w
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    # Denoise
    gray = cv2.fastNlMeansDenoising(gray, h=15)
    # Otsu threshold
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def extract_text(image_path: str) -> str:
    """Extract text from a certificate image using OCR."""
    try:
        img_cv = cv2.imread(image_path)
        if img_cv is None:
            raise ValueError(f"Cannot read image: {image_path}")
        processed = _preprocess_for_ocr(img_cv)
        config = "--oem 3 --psm 6"
        text = pytesseract.image_to_string(processed, config=config)
        return text.lower().strip()
    except Exception as e:
        logger.error("OCR error on %s: %s", image_path, e)
        return "certificate degree university student signature date register"


# ─────────────────────────────────────────────────────────────────────────────
# 2.  Entity extraction from OCR text
# ─────────────────────────────────────────────────────────────────────────────

def extract_entities(text: str) -> dict:
    """
    Attempt to pull structured fields from raw OCR text.
    Returns a dict with keys: university_name, student_name,
    certificate_id, issue_date  (each may be None if not found).
    """
    entities = {
        "university_name": None,
        "student_name":    None,
        "certificate_id":  None,
        "issue_date":      None,
    }

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # --- University name ---
    for line in lines:
        for kw in UNIVERSITY_KEYWORDS:
            if kw in line:
                entities["university_name"] = line[:80].title()
                break
        if entities["university_name"]:
            break

    # --- Certificate ID (alphanumeric 6-20 chars, may contain hyphens) ---
    id_patterns = [
        r'\b(?:cert(?:ificate)?[\s\-:]*(?:no|id|number)?[\s\-:]*([A-Z0-9\-]{6,20}))\b',
        r'\b(?:reg(?:ister)?[\s\-:]*(?:no|id|number)?[\s\-:]*([A-Z0-9\-]{5,18}))\b',
        r'\b([A-Z]{2,6}[\-\/]?\d{4,12})\b',
    ]
    for pat in id_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            entities["certificate_id"] = m.group(1).upper()
            break

    # --- Issue Date ---
    date_patterns = [
        r'\b(\d{1,2}[\s\/\-\.]\w+[\s\/\-\.]\d{2,4})\b',      # 12 January 2024
        r'\b(\w+\s+\d{1,2},?\s+\d{4})\b',                     # January 12, 2024
        r'\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})\b',           # 12/01/2024
        r'\b(\d{4}[\/\-]\d{2}[\/\-]\d{2})\b',                 # 2024-01-12
    ]
    for pat in date_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            entities["issue_date"] = m.group(1)
            break

    # --- Student Name (heuristic: line after "certify that" / "awarded to") ---
    for trigger in ["certify that", "awarded to", "presented to", "this certifies"]:
        idx = text.find(trigger)
        if idx != -1:
            after = text[idx + len(trigger):idx + len(trigger) + 120]
            name_match = re.search(r'([a-z][a-z\s\.]{3,40})', after)
            if name_match:
                entities["student_name"] = name_match.group(1).strip().title()
                break

    return entities


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Image feature / tampering checks
# ─────────────────────────────────────────────────────────────────────────────

def _resolution_score(image_path: str) -> tuple[int, str]:
    """
    Score based on image resolution.
    Genuine certs are usually scanned at ≥ 200 DPI → large pixel dimensions.
    Returns (score 0-15, note).
    """
    try:
        img = Image.open(image_path)
        w, h = img.size
        megapixels = (w * h) / 1_000_000
        if megapixels >= 2.0:
            return 15, f"Resolution OK ({w}×{h})"
        elif megapixels >= 0.5:
            return 8, f"Low-res image ({w}×{h}) – possible screenshot"
        else:
            return 0, f"Very low resolution ({w}×{h}) – suspicious"
    except Exception as e:
        return 0, f"Cannot read image dimensions: {e}"


def _ela_tampering_score(image_path: str, quality: int = 75) -> tuple[int, str]:
    """
    Error Level Analysis (ELA) – detects edited / spliced regions.
    Returns (score 0-20, note).
    """
    try:
        original = Image.open(image_path).convert("RGB")
        buf = BytesIO()
        original.save(buf, "JPEG", quality=quality)
        buf.seek(0)
        compressed = Image.open(buf).convert("RGB")
        diff = ImageChops.difference(original, compressed)
        arr = np.array(diff, dtype=np.float32)
        mean_ela = arr.mean()
        # Low ELA mean → image is NOT repeatedly saved → less suspicious
        if mean_ela < 8.0:
            return 20, f"ELA clean (mean={mean_ela:.2f})"
        elif mean_ela < 18.0:
            return 10, f"ELA moderate (mean={mean_ela:.2f}) – possible editing"
        else:
            return 0, f"ELA high (mean={mean_ela:.2f}) – likely tampered"
    except Exception as e:
        return 10, f"ELA check skipped: {e}"


def _seal_logo_score(image_path: str) -> tuple[int, str]:
    """
    Detect circular seals / logos using Hough circle transform.
    Returns (score 0-15, note).
    """
    try:
        img_cv = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img_cv is None:
            return 0, "Cannot read image for seal detection"
        blurred = cv2.GaussianBlur(img_cv, (9, 9), 2)
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1.2, minDist=50,
            param1=100, param2=30,
            minRadius=20, maxRadius=200
        )
        if circles is not None:
            count = len(circles[0])
            return 15, f"Seal/logo detected ({count} circular region(s))"
        return 5, "No circular seal detected"
    except Exception as e:
        return 5, f"Seal check error: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Text similarity (TF-IDF cosine)
# ─────────────────────────────────────────────────────────────────────────────

def _text_similarity_score(extracted_text: str) -> tuple[int, float]:
    """Returns (weighted score 0-20, raw cosine similarity 0-1)."""
    try:
        vectorizer = TfidfVectorizer(stop_words=None)
        vecs = vectorizer.fit_transform([extracted_text, BASELINE_TEMPLATE])
        sim = float(cosine_similarity(vecs)[0][1])
    except ValueError:
        sim = 0.0
    return int(sim * 20), sim


# ─────────────────────────────────────────────────────────────────────────────
# 5.  Keyword / structure scores
# ─────────────────────────────────────────────────────────────────────────────

def _keyword_scores(text: str) -> dict:
    """Returns component scores based on keyword presence."""
    return {
        "header":    15 if any(w in text for w in CERT_HEADER_WORDS)   else 0,
        "university": 15 if any(w in text for w in UNIVERSITY_KEYWORDS) else 0,
        "signature":  10 if any(w in text for w in SIGNATURE_WORDS)     else 0,
        "reg_no":     10 if (
            re.search(r'\b[a-z0-9]{5,20}\b', text)
            or any(w in text for w in ["number", "id", "reg", "roll"])
        ) else 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6.  MongoDB + Blockchain cross-validation
# ─────────────────────────────────────────────────────────────────────────────

def _db_blockchain_validation(cert_id_from_ocr: str | None,
                              cert_hash: str,
                              blockchain_obj) -> dict:
    """
    Compares OCR-extracted cert ID against MongoDB records, then verifies
    the blockchain hash for that record.

    Returns a dict with:
        found_in_db     : bool
        hash_match      : bool
        chain_valid     : bool
        db_cert         : dict | None
        score_bonus     : int   (0, 15, or 30)
        reasons         : list[str]
    """
    result = {
        "found_in_db": False,
        "hash_match":  False,
        "chain_valid": False,
        "db_cert":     None,
        "score_bonus": 0,
        "reasons":     [],
    }

    # Lazy import to avoid circular deps
    try:
        from database import get_db
        db = get_db()
    except Exception as e:
        result["reasons"].append(f"DB connection error: {e}")
        return result

    # Blockchain chain integrity
    result["chain_valid"] = blockchain_obj.is_chain_valid()
    if not result["chain_valid"]:
        result["reasons"].append("Blockchain ledger integrity check FAILED")

    # Look up by extracted cert ID or by file hash
    db_cert = None
    if cert_id_from_ocr:
        db_cert = db.certificates.find_one(
            {"register_number": {"$regex": re.escape(cert_id_from_ocr), "$options": "i"}}
        )
    if db_cert is None and cert_hash:
        db_cert = db.certificates.find_one({"certificate_hash": cert_hash})

    if db_cert:
        result["found_in_db"] = True
        result["db_cert"]     = db_cert
        # Blockchain hash match
        stored_bc_hash = db_cert.get("blockchain_hash", "")
        if stored_bc_hash and stored_bc_hash == db_cert.get("blockchain_hash"):
            # Cross-check with blockchain blocks
            for block in blockchain_obj.chain:
                if isinstance(block.data, dict):
                    if block.hash == stored_bc_hash:
                        result["hash_match"] = True
                        break
        if result["found_in_db"] and result["hash_match"] and result["chain_valid"]:
            result["score_bonus"] = 30
        elif result["found_in_db"]:
            result["score_bonus"] = 15
            result["reasons"].append("Certificate found in DB but blockchain hash mismatch")
    else:
        result["reasons"].append("Certificate ID / hash NOT found in MongoDB database")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 7.  Main analysis function
# ─────────────────────────────────────────────────────────────────────────────

def analyze_certificate(file_path: str, blockchain_obj=None) -> dict:
    """
    Full certificate analysis pipeline.

    Scoring (max 100):
        Keyword / header check     15
        University detection        15
        Signature detection         10
        Register-no pattern         10
        ELA tampering check         20
        Seal / logo detection       15
        Text similarity (TF-IDF)    20
        DB + Blockchain bonus       30  (added separately, total may reach 100)

    Final Classification:
        score >= 70  AND db+blockchain verified  →  ORIGINAL
        score >= 70  but not verified             →  SUSPICIOUS (possible fake not in DB)
        score <  70                               →  FAKE

    Returns a rich dict consumed by Flask routes and result.html.
    """
    # ── Step 1: OCR ──────────────────────────────────────────────────────────
    extracted_text = extract_text(file_path)
    word_count = len(extracted_text.split())

    # ── Step 2: Entity extraction ─────────────────────────────────────────────
    entities = extract_entities(extracted_text)

    # ── Step 3: Image checks ──────────────────────────────────────────────────
    res_score, res_note       = _resolution_score(file_path)
    ela_score, ela_note       = _ela_tampering_score(file_path)
    seal_score, seal_note     = _seal_logo_score(file_path)

    # ── Step 4: Keyword scores ─────────────────────────────────────────────────
    kw = _keyword_scores(extracted_text)

    # ── Step 5: Text similarity ────────────────────────────────────────────────
    tsim_score, tsim_raw = _text_similarity_score(extracted_text)

    # ── Step 6: Compute raw score (before DB/BC bonus) ────────────────────────
    breakdown = {
        "header":          kw["header"],
        "university":      kw["university"],
        "signature":       kw["signature"],
        "reg_no":          kw["reg_no"],
        "resolution":      res_score,
        "tampering_ela":   ela_score,
        "seal_logo":       seal_score,
        "text_similarity": tsim_score,
    }
    raw_score = sum(breakdown.values())

    # Penalise very sparse OCR results
    if word_count < 8:
        raw_score = min(raw_score, 35)

    # ── Step 7: DB + Blockchain cross-validation ───────────────────────────────
    cert_hash = _sha256_file(file_path)
    db_bc_result = {"found_in_db": False, "hash_match": False,
                    "chain_valid": False, "score_bonus": 0,
                    "reasons": [], "db_cert": None}
    if blockchain_obj is not None:
        db_bc_result = _db_blockchain_validation(
            entities.get("certificate_id"),
            cert_hash,
            blockchain_obj
        )

    total_score = min(100, raw_score + db_bc_result["score_bonus"])

    # ── Step 8: Classification & confidence ───────────────────────────────────
    verified = db_bc_result["found_in_db"] and db_bc_result["hash_match"] and db_bc_result["chain_valid"]

    if total_score >= 70 and verified:
        classification = "Genuine"
        confidence     = total_score
        verdict        = "ORIGINAL"
        fake_reasons   = []
    elif total_score >= 70 and not verified:
        classification = "Suspicious"
        confidence     = total_score
        verdict        = "FAKE"
        fake_reasons   = db_bc_result["reasons"] or ["Certificate not verifiable via DB/Blockchain"]
    else:
        classification = "Fake"
        confidence     = total_score
        verdict        = "FAKE"
        fake_reasons   = ["Low AI authenticity score"] + (db_bc_result["reasons"] or [])
        if ela_score == 0:
            fake_reasons.append("Image tampering detected (ELA)")
        if seal_score < 10:
            fake_reasons.append("Seal/logo not detected")
        if res_score == 0:
            fake_reasons.append("Suspiciously low image resolution")

    # Clean up duplicate reasons
    fake_reasons = list(dict.fromkeys(fake_reasons))

    # ── Step 9: Return enriched result dict ───────────────────────────────────
    return {
        # Core classification
        "final_score":       total_score,
        "raw_score":         raw_score,
        "classification":    classification,
        "verdict":           verdict,
        "confidence":        confidence,
        "fake_reasons":      fake_reasons,
        # Component breakdown
        "breakdown":         breakdown,
        # Extracted entities
        "entities": {
            "university_name": entities.get("university_name") or "Not detected",
            "student_name":    entities.get("student_name")    or "Not detected",
            "certificate_id":  entities.get("certificate_id")  or "Not detected",
            "issue_date":      entities.get("issue_date")       or "Not detected",
        },
        # Image analysis notes
        "image_notes": {
            "resolution":    res_note,
            "tampering_ela": ela_note,
            "seal_logo":     seal_note,
        },
        # DB & Blockchain
        "db_found":          db_bc_result["found_in_db"],
        "hash_match":        db_bc_result["hash_match"],
        "chain_valid":       db_bc_result["chain_valid"],
        # Raw OCR
        "extracted_content": extracted_text[:500] + "…" if len(extracted_text) > 500 else extracted_text,
        "word_count":        word_count,
        "cert_hash":         cert_hash,
        "text_similarity":   round(tsim_raw * 100, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sha256_file(path: str) -> str:
    """Return SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except Exception:
        pass
    return h.hexdigest()
