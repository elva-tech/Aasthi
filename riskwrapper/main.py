import os
import sys
import json
from datetime import datetime
from glob import glob
from typing import List, Dict, Any, Optional

# Fix Windows Unicode console issue
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def log_module_path(name):
    try:
        mod = __import__(name)
        print(f"DEBUG: Module {name} loaded from: {mod.__file__}")
    except Exception as e:
        print(f"DEBUG: Failed to log path for {name}: {e}")


modules_to_log = [
   # "bescom_wrapper", "waterbill_wrapper", "bbmp_propertytax_wrapper","karveriecrisk","ekhatarisk","bankloan_wrapper",
    "oc_wrapper", "noc_wrapper", "parking_wrapper",
    "wrapperlaw", "builder_wrapper", "ec_wrapper", "ecourtrisk" ,"rera_approval_risk"
]


# ============================================================
# CONFIG
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)


def p(file):
    return os.path.join(PROJECT_ROOT, file)


BASE_DIR = r"D:\aasthiv2\Aasthi\wrappercode"

CONFIG = {

    "bescom": {
        "input_dir": os.path.join(BASE_DIR, "input", "bescom"),
        "user_name": "",
        "user_address": "",
    },

    "water": {
        "rr": "",
        "user_name": "",
        "user_address": "",
    },

    "bbmp": {
        "screenshot_dir": os.path.join(BASE_DIR, "tax_screenshots"),
    },

    "oc": {
        "input_dir": os.path.join(BASE_DIR, "input", "oc"),
        "tesseract_cmd": "tesseract",
    },

    "noc": {
        "input_dir": os.path.join(BASE_DIR, "input", "noc"),
        "tesseract_cmd": "tesseract",
    },

    "parking": {
        "input_dir": os.path.join(BASE_DIR, "input", "parking"),
        "tesseract_cmd": "tesseract",
    },

    "bylaws": {
        "input_dir": os.path.join(BASE_DIR, "input", "bylaws"),
    },

    "builder": {
    "builder_name": "",
    },

    "ec": {
        "input_dir": os.path.join(BASE_DIR, "input", "ec"),
        "tesseract_cmd": "tesseract",
    },

    "bankloan": {
        "input_dir": os.path.join(BASE_DIR, "input", "bankloan"),
        "out": os.path.join(BASE_DIR, "output", "bankloan_result.json"),
    },

    "ecourtrisk": {
        "screenshots_folder": os.path.join(BASE_DIR, "ecourtjson"),
    },

    "kaveriecrisk": {
        "input_dir": os.path.join(BASE_DIR, "input", "kaveriec"),
    },

    "ekhatarisk": {
        "input_dir": os.path.join(BASE_DIR,"input", "ekhata"),
    },
    "rera_approval": {
        "input_json": r"D:\\aasthiv2\\Aasthi\\wrappercode\\input\\additional detail\\Prestige_Lakeside_Habitat_rera_details.json",
        "output_json": ""
}
}



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
            if mod in CONFIG and isinstance(CONFIG[mod], dict) and isinstance(mod_cfg, dict):
                CONFIG[mod].update(mod_cfg)
            else:
                CONFIG[mod] = mod_cfg


def save_combined_report(results: dict, out_dir="output"):
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(out_dir, f"risk_report_{ts}.json")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, sort_keys=True)

    print(f"Report saved: {json_path}")




def run_bescom(session_id=None, screenshot_dir=None):
    from bescom_wrapper import run_bescom_wrapper

    cfg = CONFIG["bescom"]

    pdfs = glob(os.path.join(cfg["input_dir"], "*.pdf"))

    if not pdfs:
        raise FileNotFoundError(
            f"No BESCOM PDF found in {cfg['input_dir']}"
        )

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
    ]

    image_paths.sort()

    if not image_paths:
        raise FileNotFoundError(f"No screenshots found in {screenshot_dir}")

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
        raise FileNotFoundError(f"No OC PDF found in {cfg['input_dir']}")

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
        raise FileNotFoundError(f"No NOC PDFs found in {cfg['input_dir']}")

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
        raise FileNotFoundError("Parking PDFs not found")

    agreement_pdf = None
    siteplan_pdf = None

    for pdf in pdfs:
        name = os.path.basename(pdf).lower()

        if "agreement" in name or "sale" in name:
            agreement_pdf = pdf

        elif "site plan" in name or "siteplan" in name:
            siteplan_pdf = pdf

    if not agreement_pdf:
        raise FileNotFoundError(
            "Agreement to Sell PDF not found"
        )

    if not siteplan_pdf:
        raise FileNotFoundError(
            "Site Plan PDF not found"
        )

    print(f"[PARKING] Agreement PDF: {agreement_pdf}")
    print(f"[PARKING] Site Plan PDF: {siteplan_pdf}")

    return run_parking_wrapper(
        agreement_pdf_path=agreement_pdf,
        siteplan_pdf_path=siteplan_pdf,
        tesseract_cmd=cfg["tesseract_cmd"],
        session_id=session_id,
        screenshot_dir=screenshot_dir,
    )


def run_bylaws( session_id=None,
    screenshot_dir=None):
    from wrapperlaw import run_bylaws_wrapper

    cfg = CONFIG["bylaws"]

    files = glob(os.path.join(cfg["input_dir"], "*"))

    if not files:
        raise FileNotFoundError(
            f"No input file found in {cfg['input_dir']}"
        )

    input_path = max(files, key=os.path.getmtime)

    print("Bylaws Input:", input_path)

    return run_bylaws_wrapper(
    input_path=input_path,
    session_id=session_id,
    screenshot_dir=screenshot_dir
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
        raise FileNotFoundError(
            f"No EC PDF found in {cfg['input_dir']}"
        )

    pdf_path = max(pdfs, key=os.path.getmtime)

    if not screenshot_dir:
        screenshot_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "screenshots"
        )

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
        raise FileNotFoundError(
            f"No Bank Loan PDF found in {cfg['input_dir']}"
        )

    pdf_path = max(pdfs, key=os.path.getmtime)

    print("Bank Loan PDF:", pdf_path)
    print("Exists:", os.path.isfile(pdf_path))

    return run_bankloan(
        pdf_path=pdf_path,
        session_id=session_id,
        screenshot_dir=screenshot_dir,
    )

def run_ecourtrisk(session_id=None, screenshot_dir=None):

    from ecourtrisk import analyze_ecourt_json

    cfg = CONFIG["ecourtrisk"]

    folder = cfg.get(
        "screenshots_folder",
        os.path.join(BASE_DIR, "ecourtjson")
    )

    print(f"[ECOURT] JSON folder: {folder}")
    print(f"[ECOURT] Folder exists: {os.path.isdir(folder)}")

    if not os.path.isdir(folder):
        raise FileNotFoundError(
            f"eCourt JSON folder not found: {folder}"
        )

    return analyze_ecourt_json(
        folder=folder
    )

def run_kaveriecrisk(
    session_id=None,
    screenshot_dir=None
):
    from karveriecrisk import create_ec_evidence_screenshot
    from karveriecrisk import (
        extract_pdf_text,
        extract_ec_transactions,
        title_risk,
        poa_risk,
        ec_risk,
        final_score,
        llm_legal_risk_assessment,
        blend_scores,
    )

    cfg = CONFIG["kaveriecrisk"]

    pdfs = glob(os.path.join(cfg["input_dir"], "*.pdf"))

    if not pdfs:
        raise FileNotFoundError(
            f"No EC PDF found in {cfg['input_dir']}"
        )

    pdf_path = max(pdfs, key=os.path.getmtime)
    if session_id and screenshot_dir:

        os.makedirs(
            screenshot_dir,
            exist_ok=True
        )

        screenshot_path = os.path.join(
            screenshot_dir,
            f"kaveri_result_{session_id}.png"
        )

        create_ec_evidence_screenshot(
            pdf_path,
            screenshot_path
        )
    print("EC PDF:", pdf_path)
    print("Exists:", os.path.isfile(pdf_path))

    text = extract_pdf_text(pdf_path)

    data = extract_ec_transactions(text)
    transactions = data["transactions"]

    # -----------------------------
    # Rule-based checks
    # -----------------------------
    title = title_risk(transactions)
    poa = poa_risk(transactions)
    ec = ec_risk(transactions)

    rule_based = final_score(
        title["risk_score"],
        poa["risk_score"],
        ec["risk_score"]
    )

    # -----------------------------
    # LLM assessment
    # -----------------------------
    llm = llm_legal_risk_assessment(transactions)

    # -----------------------------
    # Final blended score
    # -----------------------------
    final = blend_scores(
        rule_based["risk_score"],
        llm["risk_score"]
    )

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


def run_ekhatarisk(
    session_id=None,
    screenshot_dir=None
):

    from ekhatarisk import generate_report

    cfg = CONFIG["ekhatarisk"]

    pdfs = glob(os.path.join(cfg["input_dir"], "*.pdf"))

    if not pdfs:
        raise FileNotFoundError(
            f"No Khata PDF found in {cfg['input_dir']}"
        )

    pdf_path = max(pdfs, key=os.path.getmtime)

    print("Khata PDF:", pdf_path)
    print("Exists:", os.path.isfile(pdf_path))

    result = generate_report(
    pdf_path=pdf_path,
    session_id=session_id,
    screenshot_dir=screenshot_dir
)

    return result

def run_rera_approval():
    """Run RERA + BDA/BUDA/TUDA approval verification using Claude + Python rules."""
    from rera_approval_risk import run as run_rera_approval_risk
    cfg = CONFIG["rera_approval"]
    input_json = cfg["input_json"]
    if not input_json or not os.path.exists(input_json):
        raise FileNotFoundError(
            f"RERA approval input JSON not found: {input_json}"
        )
    output_json = cfg.get("output_json") or None
    return run_rera_approval_risk(
        input_json=input_json,
        output_json=output_json
    )

def run_all():
    results = {}

    modules = [
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
]

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_dir = os.path.join(os.getcwd(), "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)

    name_map = {
        "bbmp": "bbmp_property_tax"
    }

    apply_external_config()
    # Only run modules enabled by wrapper_orchesator.
    # A module with null config is skipped.
    CONFIG_MODULE_MAP = {
    "bbmp": "bbmp_property_tax",
}

    modules = [
        mod
        for mod in modules
        if CONFIG.get(
            CONFIG_MODULE_MAP.get(mod, mod)
        ) is not None
    ]
    failed_modules = []

    for mod in modules:
        print(f"Running {mod.upper()} (Session: {session_id})...")

        try:
            fn = globals()[f"run_{mod}"]

            try:
                res = fn(session_id=session_id, screenshot_dir=screenshot_dir)
            except TypeError:
                res = fn()

            print(f"Completed {mod.upper()}")

        except Exception as e:
            import traceback

            print(f"Error running {mod}: {e}")

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

    if failed_modules:
        print(f"Completed with failed modules: {', '.join(failed_modules)}")
    else:
        print("Completed all modules successfully")

    return results


def main():
    print("DEBUG: Starting main.py diagnostics...")

    for m in modules_to_log:
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
        "all": run_all,
    }

    args = [a for a in sys.argv[1:] if a.lower() != "--config"]

    config_path = _get_config_path()
    if config_path:
        args = [a for a in args if a != config_path]

    if not args:
        run_all()
        return

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_dir = os.path.join(os.getcwd(), "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)

    for cmd in args:
        cmd = cmd.lower()

        if cmd not in mapping:
            print(f"Unknown module: {cmd}")
            continue

        print(f"Manual Run: {cmd} (Session: {session_id})")

        if cmd == "all":
            mapping[cmd]()
        else:
            import inspect

            sig = inspect.signature(mapping[cmd])
            params = sig.parameters

            if "session_id" in params and "screenshot_dir" in params:
                mapping[cmd](session_id=session_id, screenshot_dir=screenshot_dir)
            else:
                mapping[cmd]()


if __name__ == "__main__":
    main()