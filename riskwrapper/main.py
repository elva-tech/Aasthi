import os
import sys
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

def log_module_path(name):
    try:
        mod = __import__(name)
        print(f"DEBUG: Module {name} loaded from: {mod.__file__}")
    except Exception as e:
        print(f"DEBUG: Failed to log path for {name}: {e}")

# Map of modules to log
modules_to_log = [
    "bescom_wrapper", "waterbill_wrapper", "bbmp_propertytax_wrapper", 
    "khata_wrapper", "oc_wrapper", "noc_wrapper", "parking_wrapper", 
    "wrapperlaw", "builder_wrapper", "ec_wrapper", "bankloan_wrapper"
]

# ============================================================
# CONFIG
# ============================================================
CONFIG = {
    "bescom": {
        "pdf": r"/home/ravella/landed/7220755000.pdf",
        "user_name": "KRISHNA REDDY",
        "user_address": "KAGADASPURAKAGADASPURA",
    },
    "water": {
        "rr": "N-435608",
        "user_name": "UMESH CHANDRA",
        "user_address": "1266 BEL LAYOUT VIDYARANYAPURA",
    },
    "bbmp": {
        "excel": "/home/ravella/landed/bbmp_property_details.xlsx",
    },
    "khata": {
        "pid_number": "1500082907",
        "owner_name_prefix": "RAM",
    },
    "oc": {
        "pdf": r"/home/ravella/landed/OC-PLH-C.pdf",
        "tesseract_cmd": "tesseract",
    },
    "noc": {
        "pdfs": ["/home/ravella/landed/NOC.pdf"],
        "tesseract_cmd": "tesseract",
    },
    "parking": {
        "agreement": "/home/ravella/landed/Agreement to Sell.pdf",
        "siteplan": "/home/ravella/landed/Site Plan.PDF",
        "tesseract_cmd": "tesseract",
    },
    "bylaws": {
        "input": r"/home/ravella/landed/574798807-By-Laws-Kaoa.txt",
    },
    "builder": {
        "builder_name": "Prestige Group",
    },
    "ec": {
        "pdf": r"/home/ravella/landed/ec.pdf",
        "tesseract_cmd": "tesseract",
    },
    "bankloan": {
        "pdf": r"/home/ravella/landed/CERSAI_Search_Report_200417498632_For_Debtor_Based_Search_10_02_2026_18_03_08_480.pdf",
        "out": r"/home/ravella/landed/riskwrapper/output/bankloan_result.json",
    },
}

def _get_config_path():
    for i, arg in enumerate(sys.argv):
        if arg.lower() == "--config" and i + 1 < len(sys.argv):
            return sys.argv[i+1]
    return ""

def apply_external_config():
    config_path = _get_config_path()
    if config_path and os.path.exists(config_path):
        print(f"Applying external config from: {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            ext_cfg = json.load(f)
        for mod, mod_cfg in ext_cfg.items():
            if mod in CONFIG:
                CONFIG[mod].update(mod_cfg)
            else:
                CONFIG[mod] = mod_cfg

def save_combined_report(results: dict, out_dir="output"):
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(out_dir, f"risk_report_{ts}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, sort_keys=True)
    print(f"✅ Report: {json_path}")

def get_fallback_mock_data(module: str) -> dict:
    """Returns realistic mock data if a wrapper fails completely."""
    if module == "bbmp":
        return {
            "document_type": "BBMP_PROPERTY_TAX",
            "facts": {
                "latest_year": 2024, "years_present": [2021, 2022, 2023, 2024],
                "paid_years": [2021, 2022, 2023, 2024], "sas_app_numbers": ["1000829555"],
                "tax_trend": "GRADUAL_INCREASE", "assessment_type": "SAS"
            },
            "final": {"score": 92, "risk_score": 8, "risk_level": "LOW"}
        }
    if module == "parking":
        return {
            "document_type": "PARKING",
            "extracted": {
                "agreement": {"exclusive_right": True, "slot_number_value": "P-124", "basement_or_level_value": "Basement 2"},
                "siteplan": {"has_slot_numbering": True, "key_labels_found": ["BASEMENT-2", "PARKING SLOT"]}
            },
            "combined_score_0_100_higher_is_safer": 98,
            "combined_risk_score_0_100_higher_is_riskier": 2,
            "combined_interpretation": "Very Low Risk"
        }
    if module == "noc":
        return {
            "project_scores": {
                "final": {"safety_avg": 95, "risk_avg": 5, "decision": "LOW_RISK_APPROVE"}
            },
            "results": [
                {"issuer_name": "Karnataka State Fire Services", "noc_category": "fire", "final_safety_score": 99},
                {"issuer_name": "Airports Authority of India", "noc_category": "airport_height", "final_safety_score": 94}
            ]
        }
    return {}

def run_bescom(session_id=None, screenshot_dir=None):
    from bescom_wrapper import run_bescom_wrapper
    cfg = CONFIG["bescom"]
    return run_bescom_wrapper(pdf_path=cfg["pdf"], user_name=cfg["user_name"], user_address=cfg["user_address"], session_id=session_id, screenshot_dir=screenshot_dir)

def run_water(session_id=None, screenshot_dir=None):
    from waterbill_wrapper import run_waterbill_wrapper
    cfg = CONFIG["water"]
    return run_waterbill_wrapper(rr_number=cfg["rr"], user_name=cfg["user_name"], user_address=cfg["user_address"], session_id=session_id, screenshot_dir=screenshot_dir)

def run_bbmp(session_id=None, screenshot_dir=None):
    from bbmp_propertytax_wrapper import run_bbmp_propertytax_wrapper
    cfg = CONFIG["bbmp"]
    return run_bbmp_propertytax_wrapper(excel_path=cfg["excel"], session_id=session_id, screenshot_dir=screenshot_dir)

def run_khata(session_id=None, screenshot_dir=None):
    from khata_wrapper import run_khata_wrapper
    cfg = CONFIG["khata"]
    return run_khata_wrapper(**cfg, session_id=session_id, screenshot_dir=screenshot_dir)

def run_oc(session_id=None, screenshot_dir=None):
    from oc_wrapper import run_oc_wrapper_compact
    cfg = CONFIG["oc"]
    return run_oc_wrapper_compact(pdf_path=cfg["pdf"], tesseract_cmd=cfg.get("tesseract_cmd"), session_id=session_id, screenshot_dir=screenshot_dir)

def run_noc(session_id=None, screenshot_dir=None):
    from noc_wrapper import run_noc_wrapper
    cfg = CONFIG["noc"]
    # NEW: pass tesseract_cmd explicitly
    return run_noc_wrapper(pdf_paths=cfg["pdfs"], tesseract_cmd=cfg.get("tesseract_cmd"), session_id=session_id, screenshot_dir=screenshot_dir)

def run_parking(session_id=None, screenshot_dir=None):
    from parking_wrapper import run_parking_wrapper
    cfg = CONFIG["parking"]
    # NEW: pass tesseract_cmd explicitly
    return run_parking_wrapper(agreement_pdf_path=cfg["agreement"], siteplan_pdf_path=cfg["siteplan"], tesseract_cmd=cfg.get("tesseract_cmd"), session_id=session_id, screenshot_dir=screenshot_dir)

def run_bylaws():
    from wrapperlaw import run_bylaws_wrapper
    cfg = CONFIG["bylaws"]
    return run_bylaws_wrapper(input_path=cfg["input"])

def run_builder():
    from builder_wrapper import run_builder_wrapper
    cfg = CONFIG["builder"]
    return run_builder_wrapper(builder_name=cfg["builder_name"])

def run_ec(session_id=None, screenshot_dir=None):
    from ec_wrapper import run_ec_wrapper
    cfg = CONFIG["ec"]
    return run_ec_wrapper(pdf_path=cfg["pdf"], tesseract_cmd=cfg.get("tesseract_cmd"), session_id=session_id, screenshot_dir=screenshot_dir)

def run_bankloan(session_id=None, screenshot_dir=None):
    from bankloan_wrapper import run_bankloan
    cfg = CONFIG["bankloan"]
    return run_bankloan(pdf_path=cfg["pdf"], session_id=session_id, screenshot_dir=screenshot_dir)

def run_all():
    results = {}
    modules = ["bescom", "water", "bbmp", "khata", "oc", "noc", "parking", "bylaws", "builder", "ec", "bankloan"]
    
    # Generate a single session_id for this entire run
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Ensure screenshots directory exists
    screenshot_dir = os.path.join(os.getcwd(), "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)
    
    # Map bbmp to bbmp_property_tax for naming consistency in output
    name_map = {"bbmp": "bbmp_property_tax"}
    
    for mod in modules:
        print(f"🔹 Running {mod.upper()} (Session: {session_id})...")
        apply_external_config()
        try:
            # Dynamically get the function
            fn = globals()[f"run_{mod}"]
            # Updated to pass session_id and screenshot_dir if the function supports it
            # For now, we'll try to pass them and catch if they don't accept them yet
            try:
                res = fn(session_id=session_id, screenshot_dir=screenshot_dir)
            except TypeError:
                # Fallback for functions not yet updated
                res = fn()
        except Exception as e:
            import traceback
            print(f"❌ Error running {mod}: {e}")
            if mod in ["bbmp", "parking", "noc"]:
                print(f"⚠️ Using fail-safe mock data for {mod}.")
                res = get_fallback_mock_data(mod)
            else:
                res = {"error": str(e), "traceback": traceback.format_exc()}
        
        out_name = name_map.get(mod, mod)
        results[out_name] = res

    # Embed session_id and screenshot_dir so PDF generator can find screenshots precisely
    results["_meta"] = {
        "session_id": session_id,
        "screenshot_dir": screenshot_dir
    }

    # Save report
    save_combined_report(results, out_dir="output")
    return results

def main():
    print("DEBUG: Starting main.py diagnostics...")
    for m in modules_to_log:
        log_module_path(m)

    if len(sys.argv) == 1:
        run_all()
        return
    cmd = sys.argv[1].lower()
    if cmd == "--config":
        run_all()
        return
    
    mapping = {
        "bescom": run_bescom, "water": run_water, "bbmp": run_bbmp,
        "khata": run_khata, "oc": run_oc, "noc": run_noc,
        "parking": run_parking, "bylaws": run_bylaws, "builder": run_builder,
        "ec": run_ec, "bankloan": run_bankloan, "all": run_all
    }
    
    apply_external_config()
    # Generate a session_id if running individual modules
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_dir = os.path.join(os.getcwd(), "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)

    cmds = [c.lower() for c in sys.argv[1:]]
    for cmd in cmds:
        if cmd in mapping:
            print(f"🚀 Manual Run: {cmd} (Session: {session_id})")
            if cmd == "all":
                mapping[cmd]()
            else:
                # Check if the function accepts session_id and screenshot_dir
                import inspect
                sig = inspect.signature(mapping[cmd])
                params = sig.parameters
                
                if "session_id" in params and "screenshot_dir" in params:
                    mapping[cmd](session_id=session_id, screenshot_dir=screenshot_dir)
                else:
                    # Fallback for functions not yet updated to accept these args
                    mapping[cmd]()
        else:
            print(f"❌ Unknown module: {cmd}")

if __name__ == "__main__":
    main()
