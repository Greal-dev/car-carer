"""Document extraction using Gemini 2.5 Flash via OpenRouter."""

import io
import json
import logging
import time
import base64
from pathlib import Path

import httpx
import fitz  # PyMuPDF
from PIL import Image, ImageEnhance, ImageFilter, ExifTags

from app.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-2.5-flash"

# Configurable timeout (seconds) and retry settings
EXTRACTION_TIMEOUT = 60
EXTRACTION_MAX_RETRIES = 2
EXTRACTION_RETRY_DELAY = 2  # seconds between retries

INVOICE_PROMPT = """Analyse cette facture ou ce devis d'entretien automobile.
Extrais les informations suivantes au format JSON strict :

{
  "doc_type": "invoice" ou "quote",
  "date": "YYYY-MM-DD",
  "date_confidence": "high" ou "low",
  "mileage": nombre ou null,
  "garage_name": "string ou null",
  "total_cost": nombre ou null,
  "vehicle_info": {
    "brand": "marque du vehicule ou null",
    "model": "modele du vehicule ou null",
    "year": nombre ou null,
    "plate_number": "plaque d'immatriculation ou null",
    "vin": "numero de serie/VIN ou null",
    "fuel_type": "Essence/Diesel/Electrique/Hybride/GPL ou null"
  },
  "items": [
    {
      "description": "description du travail",
      "category": "une parmi la liste ci-dessous",
      "part_name": "nom de la piece ou null",
      "quantity": nombre ou null,
      "unit_price": nombre ou null,
      "labor_cost": nombre ou null,
      "total_price": nombre ou null
    }
  ],
  "notes": "remarques generales ou null"
}

CATEGORIES DISPONIBLES (choisis la plus precise) :
- moteur : bloc moteur, culasse, joint de culasse, bougies, injecteurs, turbo, durite, support moteur, courroie accessoire, pompe a eau
- freinage : plaquettes, disques, tambours, etriers, liquide de frein, flexible de frein, maitre cylindre
- direction : cremaillere, biellette de direction, rotule, pompe direction assistee, volant, colonne
- suspension : amortisseurs, ressorts, silent-blocs, triangles, biellettes de barre stabilisatrice, roulement de roue, soufflets
- transmission : embrayage, boite de vitesses, cardan, soufflet de cardan, differentiel, volant moteur
- echappement : pot, catalyseur, sonde lambda, silencieux, collecteur, tube, FAP/DPF
- electricite : batterie, alternateur, demarreur, faisceau, fusible, capteur, sonde, calculateur
- eclairage : phares, ampoules, feux AR, antibrouillard, clignotants, optiques, xénon, LED
- carrosserie : pare-chocs, ailes, capot, portes, retros, joints, verins capot/coffre, vitrage
- climatisation : compresseur clim, gaz refrigerant, recharge clim, condenseur, evaporateur
- pneus : pneumatiques, equilibrage, geometrie, parallelisme, jantes, valve
- vidange : huile moteur, filtre a huile, vidange boite
- filtres : filtre a air, filtre habitacle, filtre a carburant, filtre a particules
- distribution : courroie/chaine de distribution, kit distribution, galet tendeur
- refroidissement : radiateur, thermostat, calorstat, liquide refroidissement, durite refroidissement, pompe a eau
- essuyage : balais essuie-glace, lave-glace, pompe lave-glace, gicleurs
- antipollution : vanne EGR, AdBlue, catalyseur, FAP, sonde NOx, code defaut OBD
- revision : forfait revision, controle multi-points, diagnostic electronique
- autre : uniquement si AUCUNE categorie ci-dessus ne convient

IMPORTANT :
- Les montants sont en euros (ou dans la devise visible)
- "date" = la date d'emission de la facture/devis imprimee sur le document
- NE PAS confondre la date d'impression/scan avec la date de facture
- Si la date est illisible, floue, ou absente, mets date_confidence a "low"
- Si la date est clairement lisible, mets date_confidence a "high"
- Si une information n'est pas visible, mets null
- Retourne UNIQUEMENT le JSON, sans markdown ni commentaire"""

CT_PROMPT = """Analyse ce proces-verbal de controle technique automobile.
Extrais les informations suivantes au format JSON strict :

{
  "date": "YYYY-MM-DD",
  "date_confidence": "high" ou "low",
  "mileage": nombre ou null,
  "center_name": "nom du centre ou null",
  "result": "favorable" ou "defavorable" ou "contre_visite",
  "next_due_date": "YYYY-MM-DD ou null",
  "vehicle_info": {
    "brand": "marque du vehicule ou null",
    "model": "modele du vehicule ou null",
    "year": "annee de premiere mise en circulation ou null",
    "plate_number": "plaque d'immatriculation ou null",
    "vin": "numero de serie/VIN ou null",
    "fuel_type": "Essence/Diesel/Electrique/Hybride/GPL ou null",
    "owner_count": "nombre de proprietaires successifs ou null"
  },
  "defects": [
    {
      "code": "code du defaut (ex: 1.1.1.a.1) ou null",
      "description": "description du defaut",
      "severity": "mineur" ou "majeur" ou "critique" ou "a_surveiller",
      "category": "categorie generale (direction, freinage, visibilite, eclairage, liaison_sol, structure, equipements, pollution, identification)"
    }
  ],
  "notes": "remarques generales ou null"
}

IMPORTANT :
- "date" = la date du controle technique imprimee sur le PV (champ "date du controle")
- NE PAS confondre avec la date d'impression, la date de validite, ou la date du scan
- Si la date est illisible ou absente, mets date_confidence a "low"
- Si la date est clairement lisible, mets date_confidence a "high"
- "a_surveiller" correspond aux points a controler lors du prochain CT
- Si pas de defauts, retourne une liste vide
- Retourne UNIQUEMENT le JSON, sans markdown ni commentaire"""


def _pdf_to_images(file_path: str) -> list[bytes]:
    """Convert PDF pages to PNG images."""
    doc = fitz.open(file_path)
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        images.append(pix.tobytes("png"))
    doc.close()
    return images


def _read_image(file_path: str) -> bytes:
    return Path(file_path).read_bytes()


def _detect_mime(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")


def _preprocess_image(img_bytes: bytes) -> bytes:
    """Optimize a photo for OCR: fix orientation, enhance contrast/sharpness, upscale if small."""
    img = Image.open(io.BytesIO(img_bytes))

    # 1. Fix EXIF orientation (phone photos taken sideways/upside down)
    try:
        exif = img._getexif()
        if exif:
            orientation_key = next(
                (k for k, v in ExifTags.TAGS.items() if v == "Orientation"), None
            )
            if orientation_key and orientation_key in exif:
                orientation = exif[orientation_key]
                rotations = {3: 180, 6: 270, 8: 90}
                if orientation in rotations:
                    img = img.rotate(rotations[orientation], expand=True)
    except (AttributeError, StopIteration):
        pass

    # 2. Convert to RGB if needed (RGBA/palette modes)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # 3. Upscale small images (< 1500px on shortest side)
    min_dim = min(img.size)
    if min_dim < 1500:
        scale = 1500 / min_dim
        new_size = (int(img.width * scale), int(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)

    # 4. Auto-contrast enhancement (helps with poor lighting)
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.3)

    # 5. Slight brightness boost (underexposed photos)
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(1.1)

    # 6. Sharpen (helps with slightly blurry photos)
    img = img.filter(ImageFilter.SHARPEN)

    # Export as PNG
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _build_image_content(file_path: str) -> list[dict]:
    """Build OpenAI-compatible image_url content parts with preprocessing."""
    mime = _detect_mime(file_path)
    is_pdf = mime == "application/pdf"

    parts = []
    if is_pdf:
        images = _pdf_to_images(file_path)
        for img_bytes in images:
            # PDF renders are already clean, no preprocessing needed
            b64 = base64.b64encode(img_bytes).decode()
            parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
    else:
        img_bytes = _read_image(file_path)
        img_bytes = _preprocess_image(img_bytes)
        b64 = base64.b64encode(img_bytes).decode()
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })
    return parts


def _call_openrouter(image_parts: list[dict], prompt: str) -> str:
    """Call OpenRouter with image + text prompt, return text response.

    Retries up to EXTRACTION_MAX_RETRIES times with EXTRACTION_RETRY_DELAY between attempts.
    """
    content = image_parts + [{"type": "text", "text": prompt}]

    last_error = None
    for attempt in range(1, EXTRACTION_MAX_RETRIES + 1):
        try:
            logger.info("OpenRouter API call attempt %d/%d (timeout=%ds)",
                        attempt, EXTRACTION_MAX_RETRIES, EXTRACTION_TIMEOUT)
            resp = httpx.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": content}],
                    "max_tokens": 4096,
                },
                timeout=EXTRACTION_TIMEOUT,
            )
            resp.raise_for_status()
            logger.info("OpenRouter API call succeeded on attempt %d", attempt)
            return resp.json()["choices"][0]["message"]["content"]
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            last_error = e
            logger.warning("OpenRouter API call failed (attempt %d/%d): %s",
                           attempt, EXTRACTION_MAX_RETRIES, e)
            if attempt < EXTRACTION_MAX_RETRIES:
                logger.info("Retrying in %d seconds...", EXTRACTION_RETRY_DELAY)
                time.sleep(EXTRACTION_RETRY_DELAY)

    raise last_error  # type: ignore[misc]


def _parse_json_response(raw_text: str) -> dict | None:
    """Clean markdown wrapping and parse JSON. Returns None on failure."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("JSON parse failed: %s — raw text (first 500 chars): %s", e, raw_text[:500])
        return None


async def extract_document(file_path: str, doc_type_hint: str = "auto") -> dict:
    """Extract structured data from a document using Gemini via OpenRouter.

    Args:
        file_path: Path to the uploaded file (PDF or image)
        doc_type_hint: "invoice", "ct_report", "quote", or "auto"

    Returns:
        Extracted structured data as dict
    """
    logger.info("Starting extraction — file=%s, hint=%s", file_path, doc_type_hint)
    image_parts = _build_image_content(file_path)

    # Choose prompt based on hint or try auto-detection
    if doc_type_hint == "ct_report":
        prompts_to_try = [CT_PROMPT]
    elif doc_type_hint in ("invoice", "quote"):
        prompts_to_try = [INVOICE_PROMPT]
    else:
        detected = _call_openrouter(
            image_parts,
            "Ce document est-il un controle technique (CT) ou une facture/devis d'entretien ? Reponds UNIQUEMENT par 'ct' ou 'facture'.",
        ).strip().lower()
        logger.info("Auto-detection result: %s", detected)
        if "ct" in detected:
            prompts_to_try = [CT_PROMPT, INVOICE_PROMPT]
        else:
            prompts_to_try = [INVOICE_PROMPT, CT_PROMPT]

    last_raw = ""
    for prompt in prompts_to_try:
        raw_text = _call_openrouter(image_parts, prompt)
        last_raw = raw_text
        data = _parse_json_response(raw_text)
        if data is not None:
            logger.info("Extraction succeeded — doc_type=%s", data.get("doc_type", data.get("result", "unknown")))
            return data
        logger.warning("JSON parse failed for prompt type, trying next prompt if available")

    logger.error("Extraction failed — all prompts exhausted, returning error with raw text")
    return {"error": "Failed to parse extraction result", "raw": last_raw.strip()}
