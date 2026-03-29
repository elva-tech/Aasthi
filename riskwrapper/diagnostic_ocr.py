import os
import pytesseract
print(f"PYTESSERACT_FILE: {pytesseract.__file__}")
print(f"INITIAL_TESS_CMD: {pytesseract.pytesseract.tesseract_cmd}")
print(f"ENV_TESS_CMD: {os.getenv('TESSERACT_CMD')}")

# Try to set it
pytesseract.pytesseract.tesseract_cmd = os.getenv('TESSERACT_CMD', 'tesseract')
print(f"FINAL_TESS_CMD: {pytesseract.pytesseract.tesseract_cmd}")

try:
    print(f"VERSION: {pytesseract.get_tesseract_version()}")
except Exception as e:
    print(f"ERROR: {e}")
