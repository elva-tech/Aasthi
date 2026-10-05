"""
main.py — Property Documents Wrapper

Runs 12 automations sequentially:
  1-7  : Friend's modules (RERA, BESCOM, Water, BBMP Tax, Kaveri, eKhata, eCourt)
  8-12 : Land-record fetchers (Akarband, CourtCases, Map, MR, RTC)

Config priority (highest wins):
  CLI flag  >  --config JSON  >  DEFAULT_CONFIG
"""

import sys
import os
import json
import glob
import subprocess
import argparse

# -------- Friend's wrappers --------
from rera_wrapper import KarnatakaRERAWrapper
from bescom_wrapper import BESCOMBillScraper
from water_bill_wrapper import WaterBillScraper
from property_tax_wrapper import BBMPPropertyTaxScraper
from kaveri import KaveriBot
from ekhata import DynamicEKhataBot
from ecourt import ECourtAutomation


# ==================================================================
# Subprocess helper for the 5 *_fetcher.py scripts
# ==================================================================
WRAPPER_DIR = os.path.dirname(os.path.abspath(__file__))


def run_fetcher(script_name, args_list, timeout=900):
    """Run a *_fetcher.py script; auto-answer its input() prompt."""
    script_path = os.path.join(WRAPPER_DIR, script_name)
    if not os.path.exists(script_path):
        print(f"   ❌ Not found: {script_path}")
        return False

    cmd = [sys.executable, script_path] + args_list
    print(f"   $ {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            input="\n\n\n",
            text=True,
            cwd=WRAPPER_DIR,
            timeout=timeout,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        ok = (result.returncode == 0)
        print(f"   {'✅' if ok else '⚠️'} {script_name} exited with code {result.returncode}")
        return ok
    except subprocess.TimeoutExpired:
        print(f"   ⏱️ {script_name} timed out after {timeout}s")
        return False
    except Exception as e:
        print(f"   ❌ {script_name} error: {e}")
        return False


# ==================================================================
# Main wrapper
# ==================================================================
class PropertyDocumentsWrapper:

    def __init__(
        self,
        # ---- Friend's params ----
        project_name,
        bescom_account_id,
        water_rr_number,
        pid_number,
        owner_name,
        district,
        taluka,
        hobli,
        village,
        property_no,
        epid_number,
        court_party_name,
        court_year,
        # ---- Land-record core ----
        survey_no,
        hissa_no,
        mr_hissa_no=None,
        search_text="sab kere,",
        # ---- Akarband (Kannada) ----
        akarband_district="ಬೆಂಗಳೂರು ದಕ್ಷಿಣ",
        akarband_taluk="ಕನಕಪುರ",
        akarband_hobli="ಸಾತನೂರು",
        akarband_village="ಹರಿಹರ",
        # ---- English (court_cases / map / rtc) ----
        english_district="bengaluru south",
        english_taluk="kanakpur",
        english_hobli="satanur",
        english_village="harihar",
        # ---- MR-specific casing ----
        mr_district="Bengaluru South",
        mr_taluk="Kanakpura",
        mr_hobli="SATANURU",
        mr_village="HARIHARA",
    ):
        # Friend's
        self.project_name = project_name
        self.bescom_account_id = bescom_account_id
        self.water_rr_number = water_rr_number
        self.pid_number = pid_number
        self.owner_name = owner_name
        self.district = district
        self.taluka = taluka
        self.hobli = hobli
        self.village = village
        self.property_no = property_no
        self.epid_number = epid_number
        self.court_party_name = court_party_name
        self.court_year = court_year

        # Land-record
        self.survey_no = survey_no
        self.hissa_no = hissa_no
        self.mr_hissa_no = mr_hissa_no if mr_hissa_no is not None else hissa_no
        self.search_text = search_text

        self.akarband_district = akarband_district
        self.akarband_taluk = akarband_taluk
        self.akarband_hobli = akarband_hobli
        self.akarband_village = akarband_village

        self.english_district = english_district
        self.english_taluk = english_taluk
        self.english_hobli = english_hobli
        self.english_village = english_village

        self.mr_district = mr_district
        self.mr_taluk = mr_taluk
        self.mr_hobli = mr_hobli
        self.mr_village = mr_village

    # ------------------------------------------------------------------
    # 8-12: Land-record fetchers
    # ------------------------------------------------------------------
    def run_land_records(self):

        # 8. AKARBAND
        print("📜 [8] Akarband Automation")
        try:
            run_fetcher("akarband.py", [
                "--district",  self.akarband_district,
                "--taluk",     self.akarband_taluk,
                "--hobli",     self.akarband_hobli,
                "--village",   self.akarband_village,
                "--survey-no", str(self.survey_no),
                "--hissa-no",  str(self.hissa_no),
                "--surnoc",    "*",
            ])
        except Exception as e:
            print(f"Akarband failed: {e}")

        # 9. COURT CASES (RCCMS)
        print("⚖️ [9] RCCMS Court Cases Automation")
        try:
            run_fetcher("RCCMS.py", [
                "--search-text", self.search_text,
                "--district",    self.english_district,
                "--taluk",       self.english_taluk,
                "--hobli",       self.english_hobli,
                "--village",     self.english_village,
                "--survey-no",   str(self.survey_no),
            ])
        except Exception as e:
            print(f"Court Cases failed: {e}")

        # 10. MAP
        print("🗺️ [10] Map Automation")
        try:
            run_fetcher("map.py", [
                "--search-text", self.search_text,
                "--district",    self.english_district,
                "--taluk",       self.english_taluk,
                "--hobli",       self.english_hobli,
                "--village",     self.english_village,
                "--survey-no",   str(self.survey_no),
                "--hissa-no",    str(self.hissa_no),
                "--surnoc",      "*",
            ])
        except Exception as e:
            print(f"Map failed: {e}")

        # 11. MR
        print("📋 [11] MR Automation")
        try:
            run_fetcher("mr.py", [
                "--district",  self.mr_district,
                "--taluk",     self.mr_taluk,
                "--hobli",     self.mr_hobli,
                "--village",   self.mr_village,
                "--survey-no", str(self.survey_no),
                "--hissa-no",  str(self.mr_hissa_no),
            ])
        except Exception as e:
            print(f"MR failed: {e}")

        # 12. RTC
        print("📄 [12] RTC Automation")
        try:
            run_fetcher("RTC.py", [
                "--search-text", self.search_text,
                "--district",    self.english_district,
                "--taluk",       self.english_taluk,
                "--hobli",       self.english_hobli,
                "--village",     self.english_village,
                "--survey-no",   str(self.survey_no),
                "--hissa-no",    str(self.hissa_no),
                "--surnoc",      "*",
            ])
        except Exception as e:
            print(f"RTC failed: {e}")

    # ------------------------------------------------------------------
    # Individual runners (used by --only)
    # ------------------------------------------------------------------
    def run_rera(self):
        print("🏢 [1] RERA Automation")
        try:
            rera = KarnatakaRERAWrapper(self.project_name)
            try:
                rera.open_project()
                rera.download_completion_documents()
                rera.download_uploaded_documents()
                rera.download_enquired_documents()
            finally:
                rera.close()
        except Exception as e:
            print(f"RERA failed: {e}")

    def run_bescom(self):
        print("⚡ [2] BESCOM Automation")
        try:
            BESCOMBillScraper(self.bescom_account_id).run()
        except Exception as e:
            print(f"BESCOM failed: {e}")

    def run_water(self):
        print("💧 [3] Water Bill Automation")
        try:
            print(WaterBillScraper(self.water_rr_number).run())
        except Exception as e:
            print(f"Water Bill failed: {e}")

    def run_property_tax(self):
        print("🏠 [4] BBMP Property Tax Automation")
        try:
            BBMPPropertyTaxScraper(
                pid_number=self.pid_number,
                owner_name=self.owner_name,
            ).run()
        except Exception as e:
            print(f"BBMP Property Tax failed: {e}")

    def run_kaveri(self):
        print("📑 [5] Kaveri EC Automation")
        bot = None
        try:
            bot = KaveriBot()
            bot.open_site()
            bot.login(
                username="pradhyumna.nov2004@gmail.com",
                password="OKjrjN9VZH",
                captcha_wait=40,
            )
            bot.start_application()
            bot.open_ec()
            bot.enter_property_details(
                district=self.district,
                taluka=self.taluka,
                hobli=self.hobli,
                village=self.village,
                property_type="non_agricultural",
            )
            bot.enter_property_number(property_no=self.property_no)
            bot.search(captcha_wait=40, screenshot_out="ec_result.png")
        except Exception as e:
            print(f"Kaveri EC failed: {e}")
        finally:
            if bot:
                try:
                    bot.close()
                except:
                    pass

    def run_ekhata(self):
        print("🗂️ [6] eKhata Automation")
        bot = None

        try:
            bot = DynamicEKhataBot()

            pdf_path = bot.run(
                search_type="epid",
                search_value=self.epid_number,
            )

            print("eKhata PDF:", pdf_path)

        except Exception as e:
            print(f"eKhata failed: {e}")

        finally:
            if bot:
                try:
                    bot.close()
                except:
                    pass                

    def run_ecourt(self):
        print("⚖️ [7] eCourt Automation")
        try:
            ECourtAutomation().run(
                party_name=self.court_party_name,
                year=self.court_year,
                max_courts=20,
                captcha_wait=40,
            )
            print("eCourt completed")
        except Exception as e:
            print(f"eCourt failed: {e}")

    # ------------------------------------------------------------------
    # Run all 12
    # ------------------------------------------------------------------
    def run_all(self):
        self.run_rera()
        self.run_bescom()
        self.run_water()
        self.run_property_tax()
        self.run_kaveri()
        self.run_ekhata()
        self.run_ecourt()
        self.run_land_records()

    # ------------------------------------------------------------------
    # Registry for --only
    # ------------------------------------------------------------------

    # small per-module runners for --only
    def run_land_records_akarband(self):
        print("📜 [8] Akarband Automation")
        run_fetcher("akarband.py", [
            "--district",  self.akarband_district,
            "--taluk",     self.akarband_taluk,
            "--hobli",     self.akarband_hobli,
            "--village",   self.akarband_village,
            "--survey-no", str(self.survey_no),
            "--hissa-no",  str(self.hissa_no),
            "--surnoc",    "*",
        ])

    def run_land_records_court_cases(self):
        print("⚖️ [9] RCCMS Court Cases Automation")
        run_fetcher("RCCMS.py", [
            "--search-text", self.search_text,
            "--district",    self.english_district,
            "--taluk",       self.english_taluk,
            "--hobli",       self.english_hobli,
            "--village",     self.english_village,
            "--survey-no",   str(self.survey_no),
        ])

    def run_land_records_map(self):
        print("🗺️ [10] Map Automation")
        run_fetcher("map.py", [
            "--search-text", self.search_text,
            "--district",    self.english_district,
            "--taluk",       self.english_taluk,
            "--hobli",       self.english_hobli,
            "--village",     self.english_village,
            "--survey-no",   str(self.survey_no),
            "--hissa-no",    str(self.hissa_no),
            "--surnoc",      "*",
        ])

    def run_land_records_mr(self):
        print("📋 [11] MR Automation")
        run_fetcher("mr.py", [
            "--district",  self.mr_district,
            "--taluk",     self.mr_taluk,
            "--hobli",     self.mr_hobli,
            "--village",   self.mr_village,
            "--survey-no", str(self.survey_no),
            "--hissa-no",  str(self.mr_hissa_no),
        ])

    def run_land_records_rtc(self):
        print("📄 [12] RTC Automation")
        run_fetcher("RTC.py", [
            "--search-text", self.search_text,
            "--district",    self.english_district,
            "--taluk",       self.english_taluk,
            "--hobli",       self.english_hobli,
            "--village",     self.english_village,
            "--survey-no",   str(self.survey_no),
            "--hissa-no",    str(self.hissa_no),
            "--surnoc",      "*",
        ])
    MODULE_MAP = {
            "rera":          "run_rera",
            "bescom":        "run_bescom",
            "water":         "run_water",
            "waterbill":     "run_water",
            "tax":           "run_property_tax",
            "property_tax":  "run_property_tax",
            "bbmp":          "run_property_tax",
            "kaveri":        "run_kaveri",
            "ec":            "run_kaveri",
            "ekhata":        "run_ekhata",
            "ecourt":        "run_ecourt",
            "akarband":      "run_land_records_akarband",
            "court_cases":   "run_land_records_court_cases",
            "rccms":         "run_land_records_court_cases",
            "map":           "run_land_records_map",
            "mr":            "run_land_records_mr",
            "rtc":           "run_land_records_rtc",
        }
    def run_only(self, name):
        key = name.strip().lower()
        method_name = self.MODULE_MAP.get(key)
        if not method_name:
            print(f"❌ Unknown module: '{name}'. Valid: {sorted(set(self.MODULE_MAP))}")
            return False
        getattr(self, method_name)()
        return True


# ==================================================================
# Defaults
# ==================================================================
DEFAULT_CONFIG = {
    # friend
    "project_name": "Prestige Lakeside Habitat",
    "bescom_account_id": "7220755000",
    "water_rr_number": "N-435608",
    "pid_number": "1500082907",
    "owner_name": "RAM",
    "district": "Bangalore",
    "taluka": "Bangalore",
    "hobli": "Bangalore",
    "village": "Bangalore",
    "property_no": "45",
    "epid_number": "2737828078",
    "court_party_name": "Prestige Estates",
    "court_year": "2015",
    # yours
    "survey_no": 117,
    "hissa_no": 1,
    "mr_hissa_no": 3,
    "search_text": "sab kere,",
    "akarband_district": "ಬೆಂಗಳೂರು ದಕ್ಷಿಣ",
    "akarband_taluk": "ಕನಕಪುರ",
    "akarband_hobli": "ಸಾತನೂರು",
    "akarband_village": "ಹರಿಹರ",
    "english_district": "bengaluru south",
    "english_taluk": "kanakpur",
    "english_hobli": "satanur",
    "english_village": "harihar",
    "mr_district": "Bengaluru South",
    "mr_taluk": "Kanakpura",
    "mr_hobli": "SATANURU",
    "mr_village": "HARIHARA",
}


# ==================================================================
# Argparse
# ==================================================================
def build_parser():
    p = argparse.ArgumentParser(
        description="Run property document collection wrappers (friend's 7 + land-record 5)."
    )
    p.add_argument("--config", help="Path to a single JSON property config")
    p.add_argument("--config-dir", help="Folder of *.json configs (batch mode)")
    p.add_argument("--only", help="Run only one module, e.g. --only mr / --only akarband")
    p.add_argument("--dry-run", action="store_true", help="Print resolved config and exit")

    # friend overrides
    p.add_argument("--project-name")
    p.add_argument("--bescom-account")
    p.add_argument("--water-rr")
    p.add_argument("--pid-number")
    p.add_argument("--owner-name")
    p.add_argument("--district")
    p.add_argument("--taluka")
    p.add_argument("--hobli")
    p.add_argument("--village")
    p.add_argument("--property-no")
    p.add_argument("--epid-number")
    p.add_argument("--court-party-name")
    p.add_argument("--court-year")

    # land-record overrides
    p.add_argument("--survey-no")
    p.add_argument("--hissa-no")
    p.add_argument("--mr-hissa-no")
    p.add_argument("--search-text")
    p.add_argument("--akarband-district")
    p.add_argument("--akarband-taluk")
    p.add_argument("--akarband-hobli")
    p.add_argument("--akarband-village")
    p.add_argument("--english-district")
    p.add_argument("--english-taluk")
    p.add_argument("--english-hobli")
    p.add_argument("--english-village")
    p.add_argument("--mr-district")
    p.add_argument("--mr-taluk")
    p.add_argument("--mr-hobli")
    p.add_argument("--mr-village")

    return p


# ==================================================================
# Config resolution
# ==================================================================
def resolve_config(args):
    """priority: DEFAULT < JSON file < CLI flags"""
    cfg = dict(DEFAULT_CONFIG)

    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))

    cli_map = {
        "project_name": args.project_name,
        "bescom_account_id": args.bescom_account,
        "water_rr_number": args.water_rr,
        "pid_number": args.pid_number,
        "owner_name": args.owner_name,
        "district": args.district,
        "taluka": args.taluka,
        "hobli": args.hobli,
        "village": args.village,
        "property_no": args.property_no,
        "epid_number": args.epid_number,
        "court_party_name": args.court_party_name,
        "court_year": args.court_year,
        "survey_no": args.survey_no,
        "hissa_no": args.hissa_no,
        "mr_hissa_no": args.mr_hissa_no,
        "search_text": args.search_text,
        "akarband_district": args.akarband_district,
        "akarband_taluk": args.akarband_taluk,
        "akarband_hobli": args.akarband_hobli,
        "akarband_village": args.akarband_village,
        "english_district": args.english_district,
        "english_taluk": args.english_taluk,
        "english_hobli": args.english_hobli,
        "english_village": args.english_village,
        "mr_district": args.mr_district,
        "mr_taluk": args.mr_taluk,
        "mr_hobli": args.mr_hobli,
        "mr_village": args.mr_village,
    }
    for k, v in cli_map.items():
        if v is not None:
            cfg[k] = v

    return cfg


# ==================================================================
# Entry point
# ==================================================================
if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    # -------- Batch mode --------
    if args.config_dir:
        files = sorted(glob.glob(os.path.join(args.config_dir, "*.json")))
        if not files:
            print(f"❌ No JSON files in {args.config_dir}")
            sys.exit(1)

        print(f"📦 Batch mode: {len(files)} propert(y/ies)\n")
        for path in files:
            print("\n" + "=" * 70)
            print(f"▶ {path}")
            print("=" * 70)

            args.config = path
            cfg = resolve_config(args)

            if args.dry_run:
                print(json.dumps(cfg, indent=2, ensure_ascii=False))
                continue

            try:
                wrapper = PropertyDocumentsWrapper(**cfg)
                if args.only:
                    wrapper.run_only(args.only)
                else:
                    wrapper.run_all()
            except Exception as e:
                print(f"❌ {path} failed: {e}")
                continue

        print("\n✅ Batch complete.")
        sys.exit(0)

    # -------- Single property --------
    cfg = resolve_config(args)

    if args.dry_run:
        print(json.dumps(cfg, indent=2, ensure_ascii=False))
        sys.exit(0)

    wrapper = PropertyDocumentsWrapper(**cfg)

    if args.only:
        wrapper.run_only(args.only)
    else:
        wrapper.run_all()