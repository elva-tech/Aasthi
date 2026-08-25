import os
import re
import time
import requests
import json
from urllib.parse import urlparse, unquote
from glob import glob
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException


class KarnatakaRERAWrapper:

    def __init__(self, project_name, timeout=40):
        self.project_name = project_name
        self.timeout = timeout
        BASE_DIR = r"D:\aasthiv2\Aasthi\wrappercode"

        # Project-level RERA details are stored here as JSON.
        self.additional_detail_dir = os.path.join(
            BASE_DIR, "input", "additional detail"
        )
        os.makedirs(self.additional_detail_dir, exist_ok=True)

        self.download_dirs = {
            "oc": os.path.join(BASE_DIR, "input", "oc"),
            "noc": os.path.join(BASE_DIR, "input", "noc"),
            "ec": os.path.join(BASE_DIR, "input", "ec"),
            "parking": os.path.join(BASE_DIR, "input", "parking")
}

        for folder in self.download_dirs.values():
            os.makedirs(folder, exist_ok=True)
        options = webdriver.ChromeOptions()

        # 🔥 Anti-block + stability
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        prefs = {
            "download.default_directory": os.path.abspath(list(self.download_dirs.values())[0]),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,
        }
        options.add_experimental_option("prefs", prefs)

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        self.wait = WebDriverWait(self.driver, self.timeout)

    def clear_old_downloads(self):
        for folder in self.download_dirs.values():
            for file in glob(os.path.join(folder, "*.pdf")):
                try:
                    os.remove(file)
                    print(f"Deleted old PDF: {os.path.basename(file)}")
                except Exception as e:
                    print(f"Could not delete {file}: {e}")
    # -------------------------------------------------
    # OPEN PROJECT (FIXED)
    # -------------------------------------------------
    def open_project(self):
        self.clear_old_downloads()
        self.driver.get("https://rera.karnataka.gov.in/viewAllProjects")

        project_input = self.wait.until(
            EC.presence_of_element_located((By.ID, "projectName"))
        )
        project_input.clear()
        project_input.send_keys(self.project_name)
        time.sleep(1)
        project_input.send_keys(Keys.ENTER)

        # Wait for table
        self.wait.until(
            EC.presence_of_element_located((By.XPATH, "//table/tbody/tr"))
        )

        rows = self.driver.find_elements(By.XPATH, "//table/tbody/tr")

        if not rows:
            raise Exception("No RERA results found")

        # 🔥 FIX: search inside row more flexibly
        first_row = rows[0]

        links = first_row.find_elements(By.TAG_NAME, "a")

        if not links:
            raise Exception("No clickable link found in first row")

        view_btn = links[0]  # take first link safely

        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", view_btn)
        time.sleep(0.5)
        self.driver.execute_script("arguments[0].click();", view_btn)

        time.sleep(3)


    # -------------------------------------------------
    # PROJECT DETAILS EXTRACTION
    # -------------------------------------------------
    def extract_project_details(self):
        """
        Extract ALL data from the Karnataka RERA Project Details tab.

        The RERA page has a search form at the top containing fields such as
        "Project Name" and "District". Therefore this method NEVER takes the
        first occurrence of those labels blindly.

        It:
          1. Opens the Project Details tab.
          2. Scrolls through the entire tab incrementally so lazy content loads.
          3. Reads the complete page text after scrolling.
          4. Extracts each section using its section boundaries.
          5. Saves the result to input/additional detail/*.json.
        """

        def clean(value):
            return re.sub(r"\s+", " ", str(value or "")).strip()

        def norm(value):
            """Normalize labels for comparison."""
            value = clean(value).lower()
            value = value.replace("&", "and")
            return re.sub(r"[^a-z0-9]+", "", value)

        def body_text():
            try:
                return self.driver.find_element(By.TAG_NAME, "body").text or ""
            except Exception:
                return ""

        def scroll_entire_page():
            """
            RERA uses a long page. Scroll in small increments instead of
            jumping directly to the bottom. This gives lazy-loaded/Angular
            content time to render.
            """
            print("Scrolling through complete RERA Project Details page...")

            try:
                self.driver.execute_script("window.scrollTo(0, 0);")
            except Exception:
                pass

            time.sleep(1)

            last_height = 0
            stable_rounds = 0

            for step in range(120):
                try:
                    current_height = self.driver.execute_script(
                        "return Math.max("
                        "document.body.scrollHeight,"
                        "document.documentElement.scrollHeight"
                        ");"
                    )

                    viewport = self.driver.execute_script(
                        "return window.innerHeight || 800;"
                    )

                    current_y = self.driver.execute_script(
                        "return window.pageYOffset || "
                        "document.documentElement.scrollTop || 0;"
                    )

                    next_y = min(
                        current_y + max(int(viewport * 0.75), 500),
                        current_height
                    )

                    self.driver.execute_script(
                        "window.scrollTo({top: arguments[0], behavior: 'instant'});",
                        next_y
                    )

                    time.sleep(0.25)

                    new_height = self.driver.execute_script(
                        "return Math.max("
                        "document.body.scrollHeight,"
                        "document.documentElement.scrollHeight"
                        ");"
                    )

                    if new_height == last_height and next_y >= new_height - 10:
                        stable_rounds += 1
                    else:
                        stable_rounds = 0

                    last_height = new_height

                    if (
                        next_y >= new_height - 10
                        and stable_rounds >= 4
                    ):
                        break

                except Exception as e:
                    print(f"Scroll warning at step {step}: {e}")
                    break

            # Final bottom position.
            try:
                self.driver.execute_script(
                    "window.scrollTo(0, Math.max("
                    "document.body.scrollHeight,"
                    "document.documentElement.scrollHeight"
                    "));"
                )
                time.sleep(2)
            except Exception:
                pass

            print("Finished scrolling RERA Project Details page.")

        def click_project_details_tab():
            """
            Click the actual Project Details tab, not the search-page text.
            """
            selectors = [
                "//a[normalize-space()='Project Details']",
                "//button[normalize-space()='Project Details']",
                "//*[self::a or self::button][contains("
                "normalize-space(.), 'Project Details')]",
            ]

            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)

                    for element in elements:
                        try:
                            if not element.is_displayed():
                                continue

                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});",
                                element
                            )
                            time.sleep(0.4)

                            try:
                                element.click()
                            except Exception:
                                self.driver.execute_script(
                                    "arguments[0].click();",
                                    element
                                )

                            time.sleep(2)

                            txt = body_text()

                            if (
                                "Project Description" in txt
                                or "Approving Authority" in txt
                                or "Development Details" in txt
                            ):
                                print("Project Details tab opened.")
                                return True

                        except Exception as e:
                            print(
                                f"Project Details click attempt failed: {e}"
                            )

                except Exception:
                    continue

            print(
                "WARNING: Project Details tab could not be explicitly "
                "identified. Continuing with current project page."
            )
            return False

        def get_lines():
            return [
                clean(x)
                for x in body_text().splitlines()
                if clean(x)
            ]

        def find_section(lines, start_titles, end_titles):
            """
            Return the text lines between a section heading and the next
            section heading.

            start_titles/end_titles can contain spelling variations used by
            different Karnataka RERA page versions.
            """
            start_norms = {norm(x) for x in start_titles}
            end_norms = {norm(x) for x in end_titles}

            start_index = None

            # Prefer a start occurrence that is followed by actual fields.
            for i, line in enumerate(lines):
                if norm(line) in start_norms:
                    start_index = i

                    # Avoid a navigation-only occurrence when another one
                    # exists later with real data.
                    lookahead = lines[i + 1:i + 8]
                    if any("project description" in x.lower()
                           for x in lookahead):
                        break

            if start_index is None:
                return []

            end_index = len(lines)

            for i in range(start_index + 1, len(lines)):
                if norm(lines[i]) in end_norms:
                    end_index = i
                    break

            return lines[start_index + 1:end_index]

        def make_label_map():
            """
            All field labels used by the RERA project-detail page.
            Keys are normalized labels; values are our JSON keys.
            """
            return {
                # Project details
                "projectname": "project_name",
                "projectdescription": "project_description",
                "projecttype": "project_type",
                "projectstatus": "project_status",
                "projectstartdate": "project_start_date",
                "proposedprojectcompletiondate":
                    "proposed_project_completion_date",
                "totalareaoflandsqmtr": "total_area_of_land_sq_m",
                "totalcoverdareasqmtr": "total_covered_area_sq_m",
                "totalcoveredareasqmtr": "total_covered_area_sq_m",
                "totalopenareasqmtr": "total_open_area_sq_m",
                "estimatedcostofconstructioninr":
                    "estimated_cost_of_construction_inr",
                "costoflandinr": "cost_of_land_inr",
                "totalprojectcostinr": "total_project_cost_inr",
                "projectaddress": "project_address",
                "district": "district",
                "taluk": "taluk",
                "approvingauthority": "approving_authority",
                "noofgarageforsale": "no_of_garage_for_sale",
                "areaofgarageforsalesqmtr":
                    "area_of_garage_for_sale_sq_m",
                "noofparkingforsale": "no_of_parking_for_sale",
                "areaofparkingforsalesqmtr":
                    "area_of_parking_for_sale_sq_m",

                # Development
                "typeofinventory": "type_of_inventory",
                "noofinventory": "no_of_inventory",
                "carpetareasqmtr": "carpet_area_sq_m",
                "areaofexclusivebalconyverandahsqmtr":
                    "exclusive_balcony_verandah_sq_m",
                "areaofexclusiveopenterraceifanysqmtr":
                    "exclusive_open_terrace_sq_m",

                # External development
                "roadsystem": "road_system",
                "watersupply": "water_supply",
                "sewegeanddrainagesystem":
                    "sewage_and_drainage_system",
                "sewageanddrainagesystem":
                    "sewage_and_drainage_system",
                "electricitysupplytransformerandsubstation":
                    "electricity_supply_transformer_and_sub_station",
                "solidwastemanagementanddisposal":
                    "solid_waste_management_and_disposal",
                "firefightingfacility": "fire_fighting_facility",
                "drinkingwaterfacility": "drinking_water_facility",
                "emergencyevacuationservices":
                    "emergency_evacuation_services",
                "useofrenewableenergy": "use_of_renewable_energy",

                # Bank
                "bankname": "bank_name",
                "branch": "branch",
                "ifsccode": "ifsc_code",
                "accountno70account": "account_no_70_account",
                "state": "state",
                "district": "district",

                # People
                "name": "name",
                "type": "type",
                "address": "address",
                "pincode": "pin_code",
                "yearofestablishment": "year_of_establishment",
                "numberofprojectcompleted":
                    "number_of_project_completed",
                "numberofprojectcompleted": 
                    "number_of_project_completed",
                "numberofprojectcompleted": 
                    "number_of_project_completed",
                "regofcoano": "reg_of_coa_no",
                "localauthoritylicencenumber":
                    "local_authority_licence_number",
            }

        LABELS = make_label_map()

        def parse_key_value_lines(section_lines, allowed_keys=None):
            """
            Parse the RERA format:

                Label:
                Value

            and also:

                Label : Value

            The function tolerates spaces before ':' and portal spelling
            variations.
            """
            result = {}
            i = 0

            while i < len(section_lines):
                line = clean(section_lines[i])

                # Match "Label : Value" OR "Label: Value".
                if ":" in line:
                    left, right = line.split(":", 1)
                    key_norm = norm(left)

                    if key_norm in LABELS:
                        key = LABELS[key_norm]

                        if allowed_keys is None or key in allowed_keys:
                            value = clean(right)

                            if not value and i + 1 < len(section_lines):
                                nxt = clean(section_lines[i + 1])

                                # Only consume next line when it looks like
                                # a value rather than another label.
                                if norm(nxt) not in LABELS:
                                    value = nxt
                                    i += 1

                            result[key] = value
                            i += 1
                            continue

                # Match separate:
                # Label:
                # Value
                key_norm = norm(line.rstrip(":"))

                if key_norm in LABELS:
                    key = LABELS[key_norm]

                    if allowed_keys is None or key in allowed_keys:
                        value = ""

                        if i + 1 < len(section_lines):
                            nxt = clean(section_lines[i + 1])

                            if (
                                nxt
                                and norm(nxt) not in LABELS
                                and not nxt.endswith(":")
                            ):
                                value = nxt
                                i += 1

                        result[key] = value

                i += 1

            return result

        def extract_registration_header(lines):
            """
            Search ONLY for the explicit header labels containing ':'.
            This prevents the search form's "Project Name" from being used.
            """
            result = {
                "project_name": "",
                "acknowledgement_number": "",
                "registration_number": "",
            }

            wanted = {
                "projectname": "project_name",
                "acknowledgementnumber": "acknowledgement_number",
                "registrationnumber": "registration_number",
            }

            for line in lines:
                if ":" not in line:
                    continue

                left, right = line.split(":", 1)
                key = norm(left)

                if key in wanted and clean(right):
                    # Project Name in the search form has no value after ':',
                    # whereas the project header does.
                    result[wanted[key]] = clean(right)

            return result

        def extract_people(title, end_titles):
            lines = get_lines()

            section = find_section(
                lines,
                [title],
                end_titles
            )

            if not section:
                return []

            # The first Name begins one person record. A subsequent Name
            # starts another record.
            records = []
            current = {}

            i = 0

            while i < len(section):
                line = clean(section[i])

                # Ignore empty/no-data text.
                if not line:
                    i += 1
                    continue

                matched_key = None
                matched_value = None

                if ":" in line:
                    left, right = line.split(":", 1)
                    left_norm = norm(left)

                    if left_norm in {
                        "name",
                        "type",
                        "state",
                        "district",
                        "address",
                        "pincode",
                        "yearofestablishment",
                        "numberofprojectcompleted",
                        "regofcoano",
                        "localauthoritylicencenumber",
                    }:
                        matched_key = LABELS[left_norm]
                        matched_value = clean(right)

                else:
                    left_norm = norm(line)

                    if left_norm in {
                        "name",
                        "type",
                        "state",
                        "district",
                        "address",
                        "pincode",
                        "yearofestablishment",
                        "numberofprojectcompleted",
                        "regofcoano",
                        "localauthoritylicencenumber",
                    }:
                        matched_key = LABELS[left_norm]

                if matched_key:
                    if not matched_value and i + 1 < len(section):
                        nxt = clean(section[i + 1])

                        if (
                            norm(nxt) not in LABELS
                            and not nxt.endswith(":")
                        ):
                            matched_value = nxt
                            i += 1

                    # New Name = new person.
                    if matched_key == "name" and current:
                        if any(clean(v) for v in current.values()):
                            records.append(current)
                        current = {}

                    current[matched_key] = matched_value

                i += 1

            if current and any(clean(v) for v in current.values()):
                records.append(current)

            return records

        print("Opening RERA Project Details tab...")
        click_project_details_tab()

        # Allow tab content to render.
        time.sleep(2)

        # IMPORTANT: actually scroll down through the whole page.
        scroll_entire_page()

        # Wait once more for bottom content such as architects/contractors.
        time.sleep(1)

        lines = get_lines()

        # Save the final page text AFTER scrolling.
        full_text = body_text()

        print(f"RERA page contains {len(lines)} text lines after scrolling.")

        # -------------------------------------------------
        # REGISTRATION HEADER
        # -------------------------------------------------
        registration = extract_registration_header(lines)

        # -------------------------------------------------
        # REGISTRATION / EXTENSIONS TABLE
        # -------------------------------------------------
        registration_extensions = {
            "registration_extensions": "",
            "start_date": "",
            "proposed_completion_date": "",
        }

        for i, line in enumerate(lines):
            if norm(line) == "registrationextensions":
                # Expected:
                # At the time of Registration
                # 10-05-2015
                # 31-01-2020
                if i + 1 < len(lines):
                    registration_extensions["registration_extensions"] = (
                        clean(lines[i + 1])
                    )
                if i + 2 < len(lines):
                    registration_extensions["start_date"] = (
                        clean(lines[i + 2])
                    )
                if i + 3 < len(lines):
                    registration_extensions[
                        "proposed_completion_date"
                    ] = clean(lines[i + 3])
                break

        # -------------------------------------------------
        # PROJECT DETAILS
        # -------------------------------------------------
        project_section = find_section(
            lines,
            ["Project Details"],
            ["Development Details"]
        )

        project = parse_key_value_lines(
            project_section,
            allowed_keys={
                "project_name",
                "project_description",
                "project_type",
                "project_status",
                "project_start_date",
                "proposed_project_completion_date",
                "total_area_of_land_sq_m",
                "total_covered_area_sq_m",
                "total_open_area_sq_m",
                "estimated_cost_of_construction_inr",
                "cost_of_land_inr",
                "total_project_cost_inr",
                "project_address",
                "district",
                "taluk",
                "approving_authority",
                "no_of_garage_for_sale",
                "area_of_garage_for_sale_sq_m",
                "no_of_parking_for_sale",
                "area_of_parking_for_sale_sq_m",
            }
        )

        # -------------------------------------------------
        # DEVELOPMENT DETAILS
        # -------------------------------------------------
        development_section = find_section(
            lines,
            ["Development Details"],
            ["External Development Work"]
        )

        development = parse_key_value_lines(
            development_section,
            allowed_keys={
                "type_of_inventory",
                "no_of_inventory",
                "carpet_area_sq_m",
                "exclusive_balcony_verandah_sq_m",
                "exclusive_open_terrace_sq_m",
            }
        )

        # -------------------------------------------------
        # EXTERNAL DEVELOPMENT WORK
        # -------------------------------------------------
        external_section = find_section(
            lines,
            ["External Development Work"],
            ["Other External Development Work",
             "Project Bank ( Escrow Account ) Details",
             "Project Bank (Escrow Account) Details"]
        )

        external = parse_key_value_lines(
            external_section,
            allowed_keys={
                "road_system",
                "water_supply",
                "sewage_and_drainage_system",
                "electricity_supply_transformer_and_sub_station",
                "solid_waste_management_and_disposal",
                "fire_fighting_facility",
                "drinking_water_facility",
                "emergency_evacuation_services",
                "use_of_renewable_energy",
            }
        )

        # -------------------------------------------------
        # PROJECT BANK / ESCROW
        # -------------------------------------------------
        bank_section = find_section(
            lines,
            [
                "Project Bank ( Escrow Account ) Details",
                "Project Bank (Escrow Account) Details",
                "Project Bank ( Escrow Account ) Details",
            ],
            ["Project Agents", "Project Architects"]
        )

        bank = parse_key_value_lines(
            bank_section,
            allowed_keys={
                "bank_name",
                "branch",
                "ifsc_code",
                "account_no_70_account",
                "state",
                "district",
            }
        )

        # -------------------------------------------------
        # ARCHITECTS / STRUCTURAL ENGINEERS / CONTRACTORS
        # -------------------------------------------------
        architects = extract_people(
            "Project Architects",
            ["Structural Engineers"]
        )

        structural_engineers = extract_people(
            "Structural Engineers",
            ["Project Contractors"]
        )

        contractors = extract_people(
            "Project Contractors",
            []
        )

        # -------------------------------------------------
        # FINAL JSON
        # -------------------------------------------------
        details = {
            "registration": registration,

            "registration_extensions": registration_extensions,

            "project_details": {
                "project_name": project.get("project_name", ""),
                "project_description":
                    project.get("project_description", ""),
                "project_type": project.get("project_type", ""),
                "project_status": project.get("project_status", ""),
                "project_start_date":
                    project.get("project_start_date", ""),
                "proposed_project_completion_date":
                    project.get(
                        "proposed_project_completion_date", ""
                    ),
                "total_area_of_land_sq_m":
                    project.get("total_area_of_land_sq_m", ""),
                "total_covered_area_sq_m":
                    project.get("total_covered_area_sq_m", ""),
                "total_open_area_sq_m":
                    project.get("total_open_area_sq_m", ""),
                "estimated_cost_of_construction_inr":
                    project.get(
                        "estimated_cost_of_construction_inr", ""
                    ),
                "cost_of_land_inr":
                    project.get("cost_of_land_inr", ""),
                "total_project_cost_inr":
                    project.get("total_project_cost_inr", ""),
                "project_address":
                    project.get("project_address", ""),
                "district": project.get("district", ""),
                "taluk": project.get("taluk", ""),
                "approving_authority":
                    project.get("approving_authority", ""),
                "no_of_garage_for_sale":
                    project.get("no_of_garage_for_sale", ""),
                "area_of_garage_for_sale_sq_m":
                    project.get(
                        "area_of_garage_for_sale_sq_m", ""
                    ),
                "no_of_parking_for_sale":
                    project.get("no_of_parking_for_sale", ""),
                "area_of_parking_for_sale_sq_m":
                    project.get(
                        "area_of_parking_for_sale_sq_m", ""
                    ),
            },

            "development_details": {
                "type_of_inventory":
                    development.get("type_of_inventory", ""),
                "no_of_inventory":
                    development.get("no_of_inventory", ""),
                "carpet_area_sq_m":
                    development.get("carpet_area_sq_m", ""),
                "exclusive_balcony_verandah_sq_m":
                    development.get(
                        "exclusive_balcony_verandah_sq_m", ""
                    ),
                "exclusive_open_terrace_sq_m":
                    development.get(
                        "exclusive_open_terrace_sq_m", ""
                    ),
            },

            "external_development_work": {
                "road_system":
                    external.get("road_system", ""),
                "water_supply":
                    external.get("water_supply", ""),
                "sewage_and_drainage_system":
                    external.get(
                        "sewage_and_drainage_system", ""
                    ),
                "electricity_supply_transformer_and_sub_station":
                    external.get(
                        "electricity_supply_transformer_and_sub_station",
                        ""
                    ),
                "solid_waste_management_and_disposal":
                    external.get(
                        "solid_waste_management_and_disposal",
                        ""
                    ),
                "fire_fighting_facility":
                    external.get(
                        "fire_fighting_facility", ""
                    ),
                "drinking_water_facility":
                    external.get(
                        "drinking_water_facility", ""
                    ),
                "emergency_evacuation_services":
                    external.get(
                        "emergency_evacuation_services", ""
                    ),
                "use_of_renewable_energy":
                    external.get(
                        "use_of_renewable_energy", ""
                    ),
            },

            "project_bank_escrow": {
                "bank_name": bank.get("bank_name", ""),
                "branch": bank.get("branch", ""),
                "ifsc_code": bank.get("ifsc_code", ""),
                "account_no_70_account":
                    bank.get("account_no_70_account", ""),
                "state": bank.get("state", ""),
                "district": bank.get("district", ""),
            },

            "project_architects": architects,
            "structural_engineers": structural_engineers,
            "project_contractors": contractors,

            "_meta": {
                "source": "Karnataka RERA",
                "searched_project_name": self.project_name,
                "page_url": self.driver.current_url,
                "extracted_at": time.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "project_details_tab_opened": True,
                "full_page_scrolled": True,
                "raw_page_text": full_text,
            },
        }

        # Use actual project name from project details first.
        project_name = (
            details["project_details"]["project_name"]
            or registration["project_name"]
            or self.project_name
        )

        filename = re.sub(
            r'[<>:"/\\|?*\n\r\t]',
            "_",
            project_name
        )
        filename = re.sub(
            r"\s+",
            "_",
            filename
        ).strip("_")

        output_path = os.path.join(
            self.additional_detail_dir,
            f"{filename}_rera_details.json"
        )

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                details,
                f,
                indent=2,
                ensure_ascii=False
            )

        print(f"RERA project details saved: {output_path}")

        print("\n========== RERA EXTRACTION SUMMARY ==========")
        print(
            "Project:",
            details["project_details"]["project_name"]
        )
        print(
            "Approving Authority:",
            details["project_details"]["approving_authority"]
        )
        print(
            "Development Inventory:",
            details["development_details"]["no_of_inventory"]
        )
        print(
            "Bank:",
            details["project_bank_escrow"]["bank_name"]
        )
        print(
            "Architects:",
            len(details["project_architects"])
        )
        print(
            "Structural Engineers:",
            len(details["structural_engineers"])
        )
        print(
            "Contractors:",
            len(details["project_contractors"])
        )
        print("============================================\n")

        return details


    # COMPLETION DETAILS (OC / CC)
    # -------------------------------------------------
    def download_completion_documents(self):
        print("Opening Completion Details tab...")
        completion_tab = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(.,'Completion Details')]"))
        )
        self.driver.execute_script("arguments[0].click();", completion_tab)
        time.sleep(2)

        def find_doc_links_for(name_text: str):
            nodes = self.driver.find_elements(
                By.XPATH,
                f"//*[contains(normalize-space(), 'Name') and contains(normalize-space(), '{name_text}')]"
            )
            out = []
            for n in nodes:
                candidates = n.find_elements(By.XPATH, "following::a[contains(@href,'download')][1]")
                if candidates:
                    a = candidates[0]
                    t = (a.text or "").strip().lower()
                    if "not" in t and "app" in t:
                        continue
                    out.append(a)
            return out

        oc_links = find_doc_links_for("Occupancy Certificate")
        #cc_links = find_doc_links_for("Completion certificate") or find_doc_links_for("Completion Certificate")

        picked = oc_links #+ cc_links

        seen = set()
        unique = []
        for a in picked:
            href = a.get_attribute("href")
            if href and href not in seen:
                seen.add(href)
                unique.append(a)

        print(f"Found {len(unique)} matching document(s) (OC/CC)")
        for a in unique:
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", a
            )
            time.sleep(0.3)

            self._download_pdf(
                a,
                self.download_dirs["oc"]
            )

        self.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.6)

    # -------------------------------------------------
    # TAB CLICK (RELIABLE)
    # -------------------------------------------------
    def _click_tab_reliably(self, tab_name: str, attempts: int = 4):
        tab_xpath = f"//a[normalize-space()='{tab_name}']"
        last_err = None

        for _ in range(attempts):
            try:
                self.driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.4)

                tab = self.wait.until(EC.presence_of_element_located((By.XPATH, tab_xpath)))
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab)
                time.sleep(0.2)

                try:
                    tab.click()
                except Exception:
                    pass
                self.driver.execute_script("arguments[0].click();", tab)
                time.sleep(0.8)

                # if this selector doesn't exist on some pages, it won't block downloads
                try:
                    self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".tab-pane.active")))
                except Exception:
                    pass

                return
            except Exception as e:
                last_err = e
                time.sleep(0.8)

        raise TimeoutException(f"Could not activate tab: {tab_name}. Last error: {last_err}")

    # -------------------------------------------------
    # DOWNLOAD BY LABEL ANYWHERE ON PAGE (ROW-SAFE)
    # -------------------------------------------------
    def _download_by_label_page(
        self,
        label_text: str,
        folder: str,
        max_scroll_steps=80):
        label_upper = re.sub(r"\s+", " ", label_text.strip()).upper()

        def is_visible(el):
            try:
                return el.is_displayed()
            except Exception:
                return False

        def get_visible_roots():
            """
            Karnataka RERA tabs are inconsistent. Try common containers and pick the one visible.
            """
            roots = []
            selectors = [
                ".tab-content",
                ".tab-pane.active",
                ".tab-pane.show.active",
                "div[role='tabpanel']",
                "#tabs-1", "#tabs-2", "#tabs-3", "#tabs-4", "#tabs-5",  # sometimes ids
                "body",
            ]
            for sel in selectors:
                try:
                    els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for e in els:
                        if is_visible(e):
                            roots.append(e)
                except Exception:
                    pass

            # fallback: body always exists
            if not roots:
                roots = [self.driver.find_element(By.TAG_NAME, "body")]
            return roots

        # case-insensitive contains match
        label_xpath = (
            ".//*[contains(translate(normalize-space(.),"
            "'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),"
            f"'{label_upper}')]"
        )

        for _ in range(max_scroll_steps):
            roots = get_visible_roots()

            # search label in any visible root
            label_el = None
            for root in roots:
                try:
                    candidates = [e for e in root.find_elements(By.XPATH, label_xpath) if is_visible(e)]
                    if candidates:
                        # pick smallest (most specific)
                        label_el = min(
                            candidates,
                            key=lambda e: self.driver.execute_script(
                                "return arguments[0].getBoundingClientRect().height || 999999;", e
                            )
                        )
                        break
                except Exception:
                    continue

            if label_el:
                # ✅ nearest link AFTER label in the DOM
                # ... after label_el is found
                # 1) Try normal href links first
                links = label_el.find_elements(
                    By.XPATH,
                    "following::a[contains(@href,'download') or contains(translate(@href,'PDF','pdf'),'.pdf')]"
                )

                good = []
                for a in links:
                    if not is_visible(a):
                        continue
                    href = a.get_attribute("href") or ""
                    if not href:
                        continue
                    t = (a.text or "").strip().lower()
                    if "not" in t and "app" in t:
                        continue
                    good.append(a)

                if good:
                    # (same logic as before)
                    a = good[0]
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", a)
                    time.sleep(0.2)
                    self._download_pdf(a,folder, fallback_prefix=label_text)
                    return

                # 2) ✅ Fallback: look for clickable download controls near the label (onclick / button)
                row = label_el
                for _ in range(8):  # climb a few parents to get the row container
                    try:
                        # candidates that might trigger download
                        candidates = row.find_elements(By.XPATH, ".//a[@onclick] | .//button[@onclick] | .//a[contains(@class,'download')] | .//button[contains(@class,'download')]")
                        candidates = [c for c in candidates if is_visible(c)]
                        if candidates:
                            # click each candidate; wait; detect new link or new file in download_dir
                            for c in candidates:
                                try:
                                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", c)
                                    time.sleep(0.2)
                                    self.driver.execute_script("arguments[0].click();", c)
                                    time.sleep(1.5)

                                    # After click, sometimes an <a href="...download..."> appears
                                    new_links = row.find_elements(By.XPATH, ".//a[contains(@href,'download')]")
                                    new_links = [a for a in new_links if is_visible(a) and (a.get_attribute("href") or "")]
                                    if new_links:
                                        self._download_pdf(new_links[0], folder, fallback_prefix=label_text)
                                        return

                                    # Or the browser directly downloaded (if portal triggers file download)
                                    # In that case, you can just return and rely on Chrome download prefs.
                                    # But since you use requests download, we need a URL.
                                    # If no URL appears, continue trying other candidates.
                                except Exception:
                                    continue

                        row = row.find_element(By.XPATH, "..")
                    except Exception:
                        break

                raise Exception(f" '{label_text}' found but no downloadable link/control near it.")


    # -------------------------------------------------
    # UPLOADED DOCUMENTS: download multiple label-based docs
    # -------------------------------------------------
    def download_uploaded_documents(self):
        print("Opening Uploaded Documents tab...")
        self._click_tab_reliably("Uploaded Documents")
        time.sleep(2)
        docs = {
            "Approved Layout Plan": self.download_dirs["parking"],
            "Proforma of Agreement for Sale": self.download_dirs["parking"]
        }

        for label, folder in docs.items():
            self._download_by_label_page(
                label,
                folder
            )
            print(f"Downloading by label: {label}")
            

    def download_enquired_documents(self):
        print("Opening Uploaded Documents tab...")
        self._click_tab_reliably("Uploaded Documents")
        time.sleep(2)
        docs = {
            "All NOCs from Authority": self.download_dirs["noc"],
            "Encumbrance Certificate": self.download_dirs["ec"]
        }
        for label, folder in docs.items():
            print(f"Downloading by label: {label}")
            self._download_by_label_page(label, folder)


    # -------------------------------------------------
    # REQUESTS SESSION WITH SELENIUM COOKIES
    # -------------------------------------------------
    def _requests_session_from_selenium(self):
        s = requests.Session()
        try:
            ua = self.driver.execute_script("return navigator.userAgent;")
            s.headers.update({"User-Agent": ua})
        except Exception:
            pass

        for c in self.driver.get_cookies():
            s.cookies.set(c["name"], c["value"])
        return s

    # -------------------------------------------------
    # SAFE FILENAME
    # -------------------------------------------------
    @staticmethod
    def _safe_filename(name: str) -> str:
        name = (name or "").strip()
        name = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", name).strip()
        if not name:
            name = "document"
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        return name

    # -------------------------------------------------
    # PDF DOWNLOADER (USE REAL FILENAME)
    # -------------------------------------------------
    def _download_pdf(self, link_element,folder, fallback_prefix: str = "document"):
        pdf_url = link_element.get_attribute("href")
        if not pdf_url:
            return

        s = self._requests_session_from_selenium()
        resp = s.get(pdf_url, timeout=60)
        resp.raise_for_status()

        # ✅ Real filename usually comes from Content-Disposition
        cd = resp.headers.get("Content-Disposition", "") or resp.headers.get("content-disposition", "")
        filename = None
        if "filename=" in cd.lower():
            # handle filename="abc.pdf" and filename=abc.pdf
            m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";\r\n]+)"?', cd, flags=re.IGNORECASE)
            if m:
                filename = m.group(1).strip()

        if not filename:
            # fallback: anchor text OR URL basename OR fallback_prefix
            anchor_text = (link_element.text or "").strip()
            if anchor_text:
                filename = anchor_text
            else:
                path = urlparse(pdf_url).path
                filename = os.path.basename(path) or fallback_prefix

        filename = unquote(filename)
        filename = self._safe_filename(filename)

        # Avoid overwriting (NOC.pdf etc.)
        base, ext = os.path.splitext(filename)
        if not ext:
            ext = ".pdf"
        out_path = os.path.join(folder, base + ext)
        i = 2
        while os.path.exists(out_path):
            out_path = os.path.join(folder, f"{base}_{i}{ext}")
            i += 1

        print(f"Downloading: {os.path.basename(out_path)}")
        with open(out_path, "wb") as f:
            f.write(resp.content)
        print(f" Saved: {out_path}")

    # -------------------------------------------------
    # CLEANUP
    # -------------------------------------------------
    def close(self):
        time.sleep(1)
        self.driver.quit()


if __name__ == "__main__":
    bot = KarnatakaRERAWrapper("Prestige Lakeside Habitat", timeout=50)
    try:
        print(" RERA Automation")
        bot.open_project()
        bot.extract_project_details()
        bot.download_completion_documents()
        bot.download_uploaded_documents()
        bot.download_enquired_documents()
    finally:
        bot.close()