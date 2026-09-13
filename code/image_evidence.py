from pathlib import Path
import re
import pandas as pd

try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None


ROOT = Path(__file__).parent.parent
IMAGE_FOLDER = ROOT / "dataset" / "media" / "images"


def extract_amount(text):
    """
    Extract money-like numbers from OCR text.
    """
    if not text:
        return None

    patterns = [
        r"(?:net pay|net amount|amount payable|balance due|"
        r"grand total|total paid|total|current charge|"
        r"item bill|amount due)[^\d]{0,30}"
        r"([\d,]+(?:\.\d{1,2})?)"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            value = match.group(1).replace(",", "")

            try:
                return float(value)
            except ValueError:
                pass

    return None


def fill_missing_amounts(events, images):
    """
    Recover missing event amounts from the image linked to the event.
    """

    if pytesseract is None or Image is None:
        return events

    events = events.copy()

    image_map = {}

    for _, row in images.iterrows():
        event_id = str(row.get("related_event_id", "")).strip()
        image_id = str(row.get("image_id", "")).strip()

        if event_id and image_id:
            image_map[event_id] = image_id

    for index, row in events.iterrows():

        amount = row.get("amount")

        if not (
            pd_is_missing(amount)
        ):
            continue

        event_id = str(row.get("event_id", "")).strip()

        image_id = image_map.get(event_id)

        if not image_id:
            continue

        image_file = IMAGE_FOLDER / f"{image_id}.png"

        if not image_file.exists():
            continue

        try:
            image = Image.open(image_file)
            text = pytesseract.image_to_string(image)

            value = extract_amount(text)

            if value is not None:
                events.at[index, "amount"] = value

        except Exception:
            continue

    return events


def pd_is_missing(value):
    if value is None:
        return True

    try:
        return bool(__import__("pandas").isna(value))
    except Exception:
        return False