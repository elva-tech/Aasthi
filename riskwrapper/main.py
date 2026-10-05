"""
main.py – Risk Wrapper Orchestrator
====================================
Runs all modules (friend's 14 + your 5 land risk modules) in one command.

Usage:
  python main.py                          → runs ALL modules
  python main.py rtc map                  → runs only specified modules
  python main.py --survey-no 45 --hissa-no 2   → override property for land modules
  python main.py --config custom.json    → apply external config

Best practices applied:
  - Uses mtime (not ctime) for "latest file" detection
  - Inspects function signatures instead of blind TypeError retry
  - Modular: each module reads from its own dedicated input folder
  - Graceful failure: one module failing doesn't stop the others
  - Combined report saved to output/risk_report_<timestamp>.json
"""

import os
import sys
import json
import inspect
from datetime import datetime
from glob import glob

# Fix Windows Unicode console issues
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


# ============================================================
# DEBUG HELPER
# ============================================================

def log_module_path(name):
    try:
        mod = __import__(name)
        print(f"DEBUG: Module {name} loaded from: {mod.__file__}")
    except Exception as e:
        print(f"DEBUG: Failed to log path for {name}: {e}")


MODULES_TO_LOG = [
    "oc_wrapper", "noc_wrapper", "parking_wrapper",
    "wrapperlaw", "builder_wrapper", "ec_wrapper", "ecourtrisk",
    "rera_approval_risk",
    # 5 new land risk modules
    "rtc", "map", "akarband", "mr", "RCCMS",
]


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

AASHTI_ROOT = os.path.dirname(BASE_DIR)              # .../Aasthi
WRAPPERCODE_DIR = os.path.join(AASHTI_ROOT, "wrappercode")
INPUT_DIR = os.path.join(WRAPPERCODE_DIR, "input")

print(f"DEBUG: BASE_DIR        = {BASE_DIR}")
print(f"DEBUG: WRAPPERCODE_DIR = {WRAPPERCODE_DIR}")
print(f"DEBUG: INPUT_DIR       = {INPUT_DIR}")


# ============================================================
# CONFIG
# ============================================================

CONFIG = {
    # ---------------- Friend's modules ----------------
    "bescom": {
        "input_dir": os.path.join(INPUT_DIR, "bescom"),
        "user_name": "G KRISHNA REDDY",
        "user_address": "KAGADASPURAKAGADASPU RA, KARNATAKA, 583231",
    },
    "water": {
        "rr": "",
        "user_name": "",
        "user_address": "",
    },
    "bbmp": {
        "screenshot_dir": os.path.join(WRAPPERCODE_DIR, "tax_screenshots"),
    },
    "oc": {
        "input_dir": os.path.join(INPUT_DIR, "oc"),
        "tesseract_cmd": "tesseract",
    },
    "noc": {
        "input_dir": os.path.join(INPUT_DIR, "noc"),
        "tesseract_cmd": "tesseract",
    },
    "parking": {
        "input_dir": os.path.join(INPUT_DIR, "parking"),
        "tesseract_cmd": "tesseract",
    },
    "bylaws": {
        "input_dir": os.path.join(INPUT_DIR, "bylaws"),
    },
    "builder": {
        "builder_name": "",
    },
    "ec": {
        "input_dir": os.path.join(INPUT_DIR, "kaveriec"),
        "tesseract_cmd": "tesseract",
    },
    "bankloan": {
        "input_dir": os.path.join(INPUT_DIR, "bankloan"),
        "out": os.path.join(WRAPPERCODE_DIR, "output", "bankloan_result.json"),
    },
    "ecourtrisk": {
        "screenshots_folder": os.path.join(WRAPPERCODE_DIR, "ecourtjson"),
    },
    "ekhatarisk": {
        "input_dir": os.path.join(INPUT_DIR, "ekhata"),
    },
    "rera_approval": {
        "input_json": os.path.join(
            INPUT_DIR, "additional detail",
            "Prestige_Lakeside_Habitat_rera_details.json"
        ),
        "output_json": "",
    },

    # ---------------- Your 5 land risk modules ----------------
    "rtc": {
        "input_dir": os.path.join(INPUT_DIR, "RTC"),
        "survey_no": "117",
        "hissa_no": "1",
    },
    "map": {
        "input_dir": os.path.join(INPUT_DIR, "Map"),
        "survey_no": "117",
        "hissa_no": "1",
    },
    "akarband": {
        "input_dir": os.path.join(INPUT_DIR, "Akarband"),
        "survey_no": "117",
        "hissa_no": "1",
    },
    "mr": {
        "input_dir": os.path.join(INPUT_DIR, "MR"),
        "survey_no": "117",
        "hissa_no": "3",   # MR for our current test is 117/3
    },
    "rccms": {
        "input_dir": os.path.join(INPUT_DIR, "CourtCases"),
        "survey_no": "117",
        "hissa_no": "1",
    },
}


# ============================================================
# EXTERNAL CONFIG
# ============================================================

def _get_config_path():
    for i, arg in enumerate(sys.argv):
        if arg.lower() == "--config" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return ""


def apply_external_config():
    config_path = _get_config_path()
    if config_path and os.path.exists(config_path):
        print(f"Applying external config from: {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            ext_cfg = json.load(f)
        for mod, mod_cfg in ext_cfg.items():
            if (mod in CONFIG and isinstance(CONFIG[mod], dict)
                    and isinstance(mod_cfg, dict)):
                CONFIG[mod].update(mod_cfg)
            else:
                CONFIG[mod] = mod_cfg


# ============================================================
# COMBINED REPORT
# ============================================================

def save_combined_report(results: dict, out_dir: str = "output"):
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(out_dir, f"risk_report_{ts}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, sort_keys=True, ensure_ascii=False)
    print(f"\n📄 Combined report saved: {json_path}")


# ============================================================
# SHARED HELPERS
# ============================================================

def _get_cli_overrides():
    """Read --survey-no and --hissa-no values from CLI."""
    survey = None
    hissa = None
    for i, arg in enumerate(sys.argv):
        if arg == "--survey-no" and i + 1 < len(sys.argv):
            survey = sys.argv[i + 1]
        elif arg == "--hissa-no" and i + 1 < len(sys.argv):
            hissa = sys.argv[i + 1]
    return survey, hissa


def _pick_latest_file(folder: str, exts):
    """Return the newest file (by mtime) in folder matching any extension."""
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"Folder not found: {folder}")
    files = []
    for ext in exts:
        files += glob(os.path.join(folder, ext))
    if not files:
        raise FileNotFoundError(f"No {'/'.join(exts)} file in {folder}")
    # mtime is more reliable than ctime on Windows
    return max(files, key=os.path.getmtime)


# ============================================================
# FRIEND'S MODULE RUNNERS
# ============================================================

def run_bescom(session_id=None, screenshot_dir=None):
    from bescom_wrapper import run_bescom_wrapper
    cfg = CONFIG["bescom"]
    pdfs = glob(os.path.join(cfg["input_dir"], "*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No BESCOM PDF in {cfg['input_dir']}")
    pdf_path = max(pdfs, key=os.path.getmtime)
    return run_bescom_wrapper(
        pdf_path=pdf_path,
        user_name=cfg["user_name"],
        user_address=cfg["user_address"],
        session_id=session_id,
        screenshot_dir=screenshot_dir,
    )


def run_water(session_id=None, screenshot_dir=None):
    from waterbill_wrapper import run_waterbill_wrapper
    cfg = CONFIG["water"]
    return run_waterbill_wrapper(
        rr_number=cfg["rr"],
        user_name=cfg["user_name"],
        user_address=cfg["user_address"],
        session_id=session_id,
        screenshot_dir=screenshot_dir,
    )


def run_bbmp(session_id=None, screenshot_dir=None):
    from bbmp_propertytax_wrapper import run_bbmp_propertytax_wrapper
    screenshot_dir = CONFIG["bbmp"]["screenshot_dir"]
    image_paths = [
        os.path.join(screenshot_dir, f)
        for f in os.listdir(screenshot_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    ] if os.path.isdir(screenshot_dir) else []
    image_paths.sort()
    if not image_paths:
        raise FileNotFoundError(f"No screenshots in {screenshot_dir}")
    return run_bbmp_propertytax_wrapper(
        image_paths=image_paths,
        session_id=session_id,
        screenshot_dir=screenshot_dir,
    )


def run_oc(session_id=None, screenshot_dir=None):
    from oc_wrapper import run_oc_wrapper_compact
    cfg = CONFIG["oc"]
    pdfs = glob(os.path.join(cfg["input_dir"], "*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No OC PDF in {cfg['input_dir']}")
    pdf_path = max(pdfs, key=os.path.getmtime)
    return run_oc_wrapper_compact(
        pdf_path=pdf_path,
        tesseract_cmd=cfg["tesseract_cmd"],
        session_id=session_id,
        screenshot_dir=screenshot_dir,
    )


def run_noc(session_id=None, screenshot_dir=None):
    from noc_wrapper import run_noc_wrapper
    cfg = CONFIG["noc"]
    pdf_paths = glob(os.path.join(cfg["input_dir"], "*.pdf"))
    if not pdf_paths:
        raise FileNotFoundError(f"No NOC PDFs in {cfg['input_dir']}")
    return run_noc_wrapper(
        pdf_paths=pdf_paths,
        tesseract_cmd=cfg["tesseract_cmd"],
        session_id=session_id,
        screenshot_dir=screenshot_dir,
    )


def run_parking(session_id=None, screenshot_dir=None):
    from parking_wrapper import run_parking_wrapper
    cfg = CONFIG["parking"]
    pdfs = glob(os.path.join(cfg["input_dir"], "*.pdf"))
    if len(pdfs) < 2:
        raise FileNotFoundError("Parking PDFs not found (need agreement + siteplan)")
    agreement_pdf = None
    siteplan_pdf = None
    for pdf in pdfs:
        name = os.path.basename(pdf).lower()
        if "agreement" in name or "sale" in name:
            agreement_pdf = pdf
        elif "site plan" in name or "siteplan" in name:
            siteplan_pdf = pdf
    if not agreement_pdf:
        raise FileNotFoundError("Agreement to Sell PDF not found")
    if not siteplan_pdf:
        raise FileNotFoundError("Site Plan PDF not found")
    return run_parking_wrapper(
        agreement_pdf_path=agreement_pdf,
        siteplan_pdf_path=siteplan_pdf,
        tesseract_cmd=cfg["tesseract_cmd"],
        session_id=session_id,
        screenshot_dir=screenshot_dir,
    )


def run_bylaws(session_id=None, screenshot_dir=None):
    from wrapperlaw import run_bylaws_wrapper
    cfg = CONFIG["bylaws"]
    files = glob(os.path.join(cfg["input_dir"], "*"))
    if not files:
        raise FileNotFoundError(f"No input file in {cfg['input_dir']}")
    input_path = max(files, key=os.path.getmtime)
    return run_bylaws_wrapper(
        input_path=input_path,
        session_id=session_id,
        screenshot_dir=screenshot_dir,
    )


def run_builder():
    from builder_wrapper import run_builder_wrapper
    cfg = CONFIG["builder"]
    return run_builder_wrapper(builder_name=cfg["builder_name"])


def run_ec(session_id=None, screenshot_dir=None):
    from ec_wrapper import run_ec_wrapper
    cfg = CONFIG["ec"]
    pdfs = glob(os.path.join(cfg["input_dir"], "*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No EC PDF in {cfg['input_dir']}")
    pdf_path = max(pdfs, key=os.path.getmtime)
    if not screenshot_dir:
        screenshot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)
    return run_ec_wrapper(
        pdf_path=pdf_path,
        tesseract_cmd=cfg["tesseract_cmd"],
        session_id=session_id,
        screenshot_dir=screenshot_dir,
    )


def run_bankloan(session_id=None, screenshot_dir=None):
    from bankloan_wrapper import run_bankloan
    cfg = CONFIG["bankloan"]
    pdfs = glob(os.path.join(cfg["input_dir"], "*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No Bank Loan PDF in {cfg['input_dir']}")
    pdf_path = max(pdfs, key=os.path.getmtime)
    return run_bankloan(
        pdf_path=pdf_path,
        session_id=session_id,
        screenshot_dir=screenshot_dir,
    )


def run_ecourtrisk(session_id=None, screenshot_dir=None):
    from ecourtrisk import analyze_ecourt_json
    cfg = CONFIG["ecourtrisk"]
    folder = cfg.get("screenshots_folder",
                     os.path.join(WRAPPERCODE_DIR, "ecourtjson"))
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"eCourt JSON folder not found: {folder}")
    return analyze_ecourt_json(folder=folder)


def run_kaveriecrisk(session_id=None, screenshot_dir=None):
    from karveriecrisk import create_ec_evidence_screenshot
    from karveriecrisk import (
        extract_pdf_text, extract_ec_transactions,
        title_risk, poa_risk, ec_risk, final_score,
        llm_legal_risk_assessment, blend_scores,
    )
    cfg = CONFIG["kaveriecrisk"]
    pdfs = glob(os.path.join(cfg["input_dir"], "*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No EC PDF in {cfg['input_dir']}")
    pdf_path = max(pdfs, key=os.path.getmtime)
    if session_id and screenshot_dir:
        os.makedirs(screenshot_dir, exist_ok=True)
        screenshot_path = os.path.join(screenshot_dir,
                                       f"kaveri_result_{session_id}.png")
        create_ec_evidence_screenshot(pdf_path, screenshot_path)
    text = extract_pdf_text(pdf_path)
    data = extract_ec_transactions(text)
    transactions = data["transactions"]
    title = title_risk(transactions)
    poa = poa_risk(transactions)
    ec = ec_risk(transactions)
    rule_based = final_score(title["risk_score"], poa["risk_score"], ec["risk_score"])
    llm = llm_legal_risk_assessment(transactions)
    final = blend_scores(rule_based["risk_score"], llm["risk_score"])
    return {
        "transactions": transactions,
        "title_check": title,
        "poa_check": poa,
        "ec_check": ec,
        "rule_based_risk": rule_based,
        "llm_risk": llm,
        "final_assessment": final,
        "risk_score": final["risk_score"],
        "risk_level": final["risk_level"],
    }


def run_ekhatarisk(session_id=None, screenshot_dir=None):
    from ekhatarisk import generate_report
    cfg = CONFIG["ekhatarisk"]
    pdfs = glob(os.path.join(cfg["input_dir"], "*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No Khata PDF in {cfg['input_dir']}")
    pdf_path = max(pdfs, key=os.path.getmtime)
    return generate_report(
        pdf_path=pdf_path,
        session_id=session_id,
        screenshot_dir=screenshot_dir,
    )


def run_rera_approval():
    from rera_approval_risk import run as run_rera_approval_risk
    cfg = CONFIG["rera_approval"]
    input_json = cfg["input_json"]
    if not input_json or not os.path.exists(input_json):
        raise FileNotFoundError(f"RERA approval input JSON not found: {input_json}")
    output_json = cfg.get("output_json") or None
    return run_rera_approval_risk(input_json=input_json, output_json=output_json)


# ============================================================
# YOUR 5 LAND RISK MODULE RUNNERS
# ============================================================

def run_rtc(session_id=None, screenshot_dir=None):
    from rtc import analyze_rtc
    cfg = CONFIG["rtc"]
    survey, hissa = _get_cli_overrides()
    survey = survey or cfg["survey_no"]
    hissa = hissa or cfg["hissa_no"]
    path = _pick_latest_file(cfg["input_dir"], ["*.pdf", "*.png"])
    print(f"[RTC] File: {path}")
    print(f"[RTC] Target: Survey {survey}, Hissa {hissa}")
    return analyze_rtc(
    path,
    survey,
    hissa,
    session_id=session_id,
    screenshot_dir=screenshot_dir,
    )


def run_map(session_id=None, screenshot_dir=None):
    from map import analyze_map
    cfg = CONFIG["map"]
    survey, hissa = _get_cli_overrides()
    survey = survey or cfg["survey_no"]
    hissa = hissa or cfg["hissa_no"]
    path = _pick_latest_file(cfg["input_dir"], ["*.pdf", "*.png"])
    print(f"[MAP] File: {path}")
    print(f"[MAP] Target: Survey {survey}, Hissa {hissa}")
    return analyze_map(
    path,
    survey,
    hissa,
    session_id=session_id,
    screenshot_dir=screenshot_dir,
    )


def run_akarband(session_id=None, screenshot_dir=None):
    from akarband import analyze_akarband
    cfg = CONFIG["akarband"]
    survey, hissa = _get_cli_overrides()
    survey = survey or cfg["survey_no"]
    hissa = hissa or cfg["hissa_no"]
    path = _pick_latest_file(cfg["input_dir"], ["*.pdf", "*.png"])
    print(f"[AKARBAND] File: {path}")
    print(f"[AKARBAND] Target: Survey {survey}, Hissa {hissa}")
    return analyze_akarband(
    path,
    survey,
    hissa,
    session_id=session_id,
    screenshot_dir=screenshot_dir,
    )


def run_mr(session_id=None, screenshot_dir=None):
    from mr import analyze_mr
    cfg = CONFIG["mr"]
    survey, hissa = _get_cli_overrides()
    survey = survey or cfg["survey_no"]
    hissa = hissa or cfg["hissa_no"]
    path = _pick_latest_file(cfg["input_dir"], ["*.png", "*.pdf"])
    print(f"[MR] File: {path}")
    print(f"[MR] Target: Survey {survey}, Hissa {hissa}")
    return analyze_mr(
    path,
    survey,
    hissa,
    session_id=session_id,
    screenshot_dir=screenshot_dir,
    )


def run_rccms(session_id=None, screenshot_dir=None):
    from RCCMS import analyze_court
    cfg = CONFIG["rccms"]
    survey, hissa = _get_cli_overrides()
    survey = survey or cfg["survey_no"]
    hissa = hissa or cfg["hissa_no"]
    path = _pick_latest_file(cfg["input_dir"], ["*.png", "*.pdf"])
    print(f"[RCCMS] File: {path}")
    print(f"[RCCMS] Target: Survey {survey}, Hissa {hissa}")
    return analyze_court(
    path,
    survey,
    hissa,
    session_id=session_id,
    screenshot_dir=screenshot_dir,
    )


# ============================================================
# ALL MODULES
# ============================================================

ALL_MODULES = [
    # Friend's modules
    "bescom",
    "water",
    "bbmp",
    "oc",
    "noc",
    "parking",
    "bylaws",
    "builder",
    "ec",
    "bankloan",
    "ecourtrisk",
    "kaveriecrisk",
    "ekhatarisk",
    "rera_approval",
    # Your 5 land modules
    "rtc",
    "map",
    "akarband",
    "mr",
    "rccms",
]


def _call_module(fn, session_id, screenshot_dir):
    """Call a module function, passing kwargs only if the function accepts them."""
    sig = inspect.signature(fn)
    accepts_sid = "session_id" in sig.parameters
    accepts_sdir = "screenshot_dir" in sig.parameters
    if accepts_sid and accepts_sdir:
        return fn(session_id=session_id, screenshot_dir=screenshot_dir)
    elif accepts_sid:
        return fn(session_id=session_id)
    else:
        return fn()


def run_all():
    results = {}
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_dir = os.path.join(os.getcwd(), "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)

    name_map = {"bbmp": "bbmp_property_tax"}

    apply_external_config()

    failed_modules = []

    for mod in ALL_MODULES:
        if CONFIG.get(mod) is None:
            print(f"⏭️  Skipping {mod.upper()} (config is None)")
            continue

        print(f"\n{'='*60}")
        print(f"▶️  Running {mod.upper()} (Session: {session_id})")
        print(f"{'='*60}")

        try:
            fn = globals()[f"run_{mod}"]
            res = _call_module(fn, session_id, screenshot_dir)
            print(f"✅ Completed {mod.upper()}")
        except Exception as e:
            import traceback
            print(f"❌ Error running {mod}: {e}")
            res = {
                "status": "FAILED",
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
            failed_modules.append(mod)

        out_name = name_map.get(mod, mod)
        results[out_name] = res

    results["_meta"] = {
        "session_id": session_id,
        "screenshot_dir": screenshot_dir,
        "failed_modules": failed_modules,
        "success": len(failed_modules) == 0,
    }

    save_combined_report(results, out_dir="output")

    print(f"\n{'#'*60}")
    print(f"# FINAL SUMMARY")
    print(f"{'#'*60}")
    for mod in ALL_MODULES:
        name = name_map.get(mod, mod)
        if name not in results:
            continue
        r = results[name]
        if isinstance(r, dict) and r.get("status") == "FAILED":
            print(f"  ❌  {mod:20s}  FAILED: {r.get('error', '')[:60]}")
        else:
            print(f"  ✅  {mod:20s}  OK")
    print(f"{'#'*60}")
    if failed_modules:
        print(f"⚠️  Failed modules: {', '.join(failed_modules)}")
    else:
        print("🎉 All modules completed successfully")
    print(f"{'#'*60}\n")

    return results


# ============================================================
# MAIN
# ============================================================

def main():
    print("DEBUG: Starting main.py diagnostics...")
    for m in MODULES_TO_LOG:
        log_module_path(m)

    apply_external_config()

    mapping = {
        "bescom": run_bescom,
        "water": run_water,
        "bbmp": run_bbmp,
        "oc": run_oc,
        "noc": run_noc,
        "parking": run_parking,
        "bylaws": run_bylaws,
        "builder": run_builder,
        "ec": run_ec,
        "bankloan": run_bankloan,
        "ecourtrisk": run_ecourtrisk,
        "kaveriecrisk": run_kaveriecrisk,
        "ekhatarisk": run_ekhatarisk,
        "rera_approval": run_rera_approval,
        "rtc": run_rtc,
        "map": run_map,
        "akarband": run_akarband,
        "mr": run_mr,
        "rccms": run_rccms,
        "all": run_all,
    }

    # Parse CLI args (ignore --config and its value)
    args = [a for a in sys.argv[1:] if a.lower() != "--config"]
    config_path = _get_config_path()
    if config_path:
        args = [a for a in args if a != config_path]

    # Strip --survey-no / --hissa-no flags and their values
    clean_args = []
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a in ("--survey-no", "--hissa-no"):
            skip_next = True
            continue
        if a.startswith("--"):
            continue
        clean_args.append(a)
    args = clean_args

    # No args → run everything
    if not args:
        run_all()
        return

    # Run specific modules
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_dir = os.path.join(os.getcwd(), "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)

    for cmd in args:
        cmd = cmd.lower()
        if cmd not in mapping:
            print(f"⚠️  Unknown module: {cmd}")
            continue

        print(f"\n{'='*60}")
        print(f"▶️  Manual Run: {cmd} (Session: {session_id})")
        print(f"{'='*60}")

        if cmd == "all":
            mapping[cmd]()
        else:
            _call_module(mapping[cmd], session_id, screenshot_dir)


if __name__ == "__main__":
    main()