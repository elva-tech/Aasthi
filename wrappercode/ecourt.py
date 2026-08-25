import argparse
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


class ECourtAutomation:

    def __init__(self):

        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")

        self.driver = webdriver.Chrome(
            service=Service(
                ChromeDriverManager().install()
            ),
            options=options
        )

        self.wait = WebDriverWait(
            self.driver,
            60
        )

        # ==========================================================
        # MAIN JSON OUTPUT FOLDER
        # ==========================================================
        self.json_dir = "ecourtjson"

        os.makedirs(
            self.json_dir,
            exist_ok=True
        )

        # Current case JSON file
        self.current_case_file = None

        # Current case data
        self.current_case_data = None

    # ==============================================================
    # CREATE JSON FILE FOR ONE CASE / COURT
    # ==============================================================

    def create_case_json(self, case_index, court_name, party_name, year):
        self.current_case_file = os.path.join(
            self.json_dir,
            f"case_{case_index}.json"
        )

        self.current_case_data = {
            "case_index": case_index,
            "court": court_name,
            "party_name": party_name,
            "registration_year": year,
            "search_url": "",
            "views": []
        }

        print("\n======================================")
        print(f"📄 CASE JSON: {self.current_case_file}")
        print("======================================\n")

        return self.current_case_file

    # ==============================================================
    # SAVE CURRENT CASE JSON
    # ==============================================================

    def save_case_json(self):
        if not self.current_case_file or self.current_case_data is None:
            raise Exception("Case JSON has not been created")

        with open(
            self.current_case_file,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                self.current_case_data,
                f,
                indent=4,
                ensure_ascii=False
            )

        print(f"💾 JSON saved: {self.current_case_file}")
        return self.current_case_file

    # ---------------- OPEN SITE ---------------- #

    def open_site(self):

        self.driver.get(
            "https://services.ecourts.gov.in/ecourtindia_v6/"
        )

        print("✅ Site opened")

    # ---------------- CLICK CASE STATUS ---------------- #

    def click_case_status(self):

        btn = self.wait.until(
            EC.element_to_be_clickable(
                (
                    By.ID,
                    "leftPaneMenuCS"
                )
            )
        )

        self.driver.execute_script(
            "arguments[0].click();",
            btn
        )

        print("✅ Case Status opened")

    # ---------------- SELECT STATE ---------------- #

    def select_state(self, state_name):

        dropdown = self.wait.until(
            EC.presence_of_element_located(
                (
                    By.ID,
                    "sess_state_code"
                )
            )
        )

        Select(dropdown).select_by_visible_text(
            state_name
        )

        print("✅ State selected")

    # ---------------- SELECT DISTRICT ---------------- #

    def select_district(self, district_name):

        dropdown = self.wait.until(
            EC.presence_of_element_located(
                (
                    By.ID,
                    "sess_dist_code"
                )
            )
        )

        self.wait.until(
            lambda d: len(
                Select(dropdown).options
            ) > 1
        )

        time.sleep(2)

        Select(dropdown).select_by_visible_text(
            district_name
        )

        print("✅ District selected")

    # ---------------- GET ALL COURTS ---------------- #

    def get_all_courts(self):

        dropdown = self.wait.until(
            EC.presence_of_element_located(
                (
                    By.ID,
                    "court_complex_code"
                )
            )
        )

        self.wait.until(
            lambda d: len(
                Select(dropdown).options
            ) > 1
        )

        select = Select(dropdown)

        courts = []

        print("\n==============================")
        print("AVAILABLE COURTS")
        print("==============================\n")

        for i in range(1, len(select.options)):

            text = select.options[i].text.strip()

            print(i, "->", text)

            courts.append(text)

        return courts

    # ---------------- SELECT COURT ---------------- #

    def select_court(self, court_name):

        dropdown = self.wait.until(
            EC.presence_of_element_located(
                (
                    By.ID,
                    "court_complex_code"
                )
            )
        )

        select = Select(dropdown)

        for option in select.options:

            text = option.text.strip()

            if court_name.lower() in text.lower():

                select.select_by_visible_text(
                    text
                )

                print(
                    f"\n✅ Court selected: {text}"
                )

                return

        raise Exception("Court not found")

    # ---------------- SELECT ESTABLISHMENT ---------------- #

    def select_establishment(self):

        dropdown = self.wait.until(
            EC.presence_of_element_located(
                (
                    By.ID,
                    "court_est_code"
                )
            )
        )

        self.wait.until(
            lambda d: len(
                Select(dropdown).options
            ) > 1
        )

        select = Select(dropdown)

        print("\nAVAILABLE ESTABLISHMENTS:\n")

        for i in range(1, len(select.options)):

            text = select.options[i].text.strip()

            print(i, "->", text)

        # select first valid establishment
        select.select_by_index(1)

        selected = select.options[1].text.strip()

        print(
            f"\n✅ Establishment selected: {selected}"
        )

    # ---------------- ENTER DETAILS ---------------- #

    def enter_details(self, party_name, year):

        # Party name
        party_input = self.wait.until(
            EC.presence_of_element_located(
                (By.ID, "petres_name")
            )
        )

        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            party_input
        )

        try:
            party_input.click()
            party_input.clear()
            party_input.send_keys(str(party_name))
        except Exception:
            self.driver.execute_script(
                """
                arguments[0].value = arguments[1];
                arguments[0].dispatchEvent(
                    new Event('input', {bubbles:true})
                );
                arguments[0].dispatchEvent(
                    new Event('change', {bubbles:true})
                );
                """,
                party_input,
                str(party_name)
            )

        # Registration year
        year_elements = self.driver.find_elements(
            By.ID,
            "rgyearP"
        )

        if not year_elements:
            raise Exception(
                "Registration year field #rgyearP was not found"
            )

        year_input = None

        for element in year_elements:
            try:
                if element.is_displayed() and element.is_enabled():
                    year_input = element
                    break
            except Exception:
                pass

        if year_input is None:
            year_input = year_elements[0]

        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            year_input
        )

        time.sleep(0.5)

        try:
            year_input.click()
            year_input.clear()
            year_input.send_keys(str(year))
        except Exception:
            self.driver.execute_script(
                """
                arguments[0].value = arguments[1];

                arguments[0].dispatchEvent(
                    new Event('input', {bubbles:true})
                );

                arguments[0].dispatchEvent(
                    new Event('change', {bubbles:true})
                );

                arguments[0].dispatchEvent(
                    new Event('blur', {bubbles:true})
                );
                """,
                year_input,
                str(year)
            )

        actual_year = self.driver.execute_script(
            "return arguments[0].value;",
            year_input
        )

        print("✅ Party details entered")
        print(f"✅ Registration year entered: {actual_year}")

    # ---------------- SELECT BOTH ---------------- #

    def select_both(self):

        both = self.wait.until(
            EC.element_to_be_clickable(
                (
                    By.ID,
                    "radB"
                )
            )
        )

        self.driver.execute_script(
            "arguments[0].click();",
            both
        )

        print("✅ Both selected")

    # ---------------- CAPTCHA ---------------- #

    def wait_for_captcha(self, captcha_wait=0):

        print("\n================================")
        print("ENTER CAPTCHA")
        print("CLICK GO")
        print("================================\n")

        if captcha_wait and captcha_wait > 0:

            print(
                f"Waiting {captcha_wait}s "
                f"for manual CAPTCHA + GO..."
            )

            time.sleep(captcha_wait)

        else:

            input(
                "Press ENTER after clicking GO..."
            )

        print("✅ Search submitted")

    # ==============================================================
    # EXTRACT STRUCTURED CASE DATA FROM eCOURTS DOM
    # ==============================================================

    def extract_case_details(self):
        """
        Extract structured data directly from the eCourts DOM.

        Supports variable rows, variable columns, links and
        additional fields. No screenshots/OCR are used.
        """

        import re

        def clean(value):
            if value is None:
                return ""
            return " ".join(
                str(value).replace("\xa0", " ").split()
            ).strip()

        def cell_links(cell):
            links = []

            for link in cell.find_elements(
                By.CSS_SELECTOR, "a"
            ):
                text = clean(link.text)
                href = link.get_attribute("href") or ""

                if text or href:
                    links.append({
                        "text": text,
                        "url": href
                    })

            return links

        def dynamic_table(selector):
            tables = self.driver.find_elements(
                By.CSS_SELECTOR,
                selector
            )

            if not tables:
                return []

            table = tables[0]
            headers = []

            # First try THEAD.
            for row in table.find_elements(
                By.CSS_SELECTOR,
                "thead tr"
            ):
                ths = row.find_elements(
                    By.CSS_SELECTOR,
                    "th"
                )
                values = [clean(x.text) for x in ths]

                if any(values):
                    headers = values
                    break

            # Then look for a TH row anywhere in the table.
            if not headers:
                for row in table.find_elements(
                    By.CSS_SELECTOR,
                    "tr"
                ):
                    ths = row.find_elements(
                        By.CSS_SELECTOR,
                        "th"
                    )
                    values = [clean(x.text) for x in ths]

                    if any(values):
                        headers = values
                        break

            rows = table.find_elements(
                By.CSS_SELECTOR,
                "tbody tr"
            )

            if not rows:
                rows = table.find_elements(
                    By.CSS_SELECTOR,
                    "tr"
                )

            result = []

            for row in rows:

                cells = row.find_elements(
                    By.CSS_SELECTOR,
                    "td, th"
                )

                if not cells:
                    continue

                if all(
                    c.tag_name.lower() == "th"
                    for c in cells
                ):
                    continue

                values = [
                    clean(c.text)
                    for c in cells
                ]

                if not any(values):
                    continue

                item = {}

                for i, value in enumerate(values):

                    if i < len(headers) and headers[i]:
                        key = headers[i]
                    else:
                        key = f"column_{i + 1}"

                    original_key = key
                    n = 2

                    while key in item:
                        key = f"{original_key}_{n}"
                        n += 1

                    item[key] = value

                links = []

                for cell in cells:
                    links.extend(cell_links(cell))

                if links:
                    item["_links"] = links

                result.append(item)

            return result

        def label_value_table(selector):
            result = {}

            tables = self.driver.find_elements(
                By.CSS_SELECTOR,
                selector
            )

            if not tables:
                return result

            table = tables[0]

            for row in table.find_elements(
                By.CSS_SELECTOR,
                "tr"
            ):

                cells = row.find_elements(
                    By.CSS_SELECTOR,
                    "th, td"
                )

                i = 0

                while i < len(cells):

                    if cells[i].tag_name.lower() != "th":
                        i += 1
                        continue

                    label = clean(cells[i].text)

                    if not label:
                        i += 1
                        continue

                    value = ""

                    if i + 1 < len(cells):
                        next_cell = cells[i + 1]

                        if next_cell.tag_name.lower() == "td":
                            value = clean(next_cell.text)
                            i += 2
                        else:
                            i += 1
                    else:
                        i += 1

                    result[label] = value

            return result

        def case_status_table():

            result = {}

            tables = self.driver.find_elements(
                By.CSS_SELECTOR,
                "#CSpartyName table.case_status_table"
            )

            if not tables:
                tables = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "table.case_status_table"
                )

            if not tables:
                return result

            known = {
                "First Hearing Date": "first_hearing_date",
                "Decision Date": "decision_date",
                "Case Status": "case_status",
                "Nature of Disposal": "nature_of_disposal",
                "Court Number and Judge":
                    "court_number_and_judge"
            }

            for row in tables[0].find_elements(
                By.CSS_SELECTOR,
                "tr"
            ):

                cells = row.find_elements(
                    By.CSS_SELECTOR,
                    "th, td"
                )

                values = [
                    clean(c.text)
                    for c in cells
                ]

                while values and not values[0]:
                    values.pop(0)

                while values and not values[-1]:
                    values.pop()

                if len(values) < 2:
                    continue

                i = 0

                while i < len(values) - 1:

                    label = values[i]
                    value = values[i + 1]

                    if not label:
                        i += 1
                        continue

                    result[
                        known.get(label, label)
                    ] = value

                    if (
                        label == "Case Status"
                        and i + 2 < len(values)
                        and values[i + 2]
                    ):
                        result["sub_stage"] = values[i + 2]
                        i += 3
                    else:
                        i += 2

            return result

        def parties(selector):

            result = []

            for li in self.driver.find_elements(
                By.CSS_SELECTOR,
                selector
            ):

                lines = [
                    clean(x)
                    for x in li.text.splitlines()
                    if clean(x)
                ]

                if not lines:
                    continue

                names = []
                advocates = []

                for line in lines:

                    if line.lower().startswith("advocate"):
                        advocate = re.sub(
                            r"^\s*advocate\s*[-:]?\s*",
                            "",
                            line,
                            flags=re.IGNORECASE
                        )
                        if advocate:
                            advocates.append(clean(advocate))
                    else:
                        names.append(line)

                name = clean(" ".join(names))
                name = re.sub(
                    r"^\s*\d+\)\s*",
                    "",
                    name
                )

                advocate = clean(" ".join(advocates))

                if name or advocate:
                    result.append({
                        "name": name,
                        "advocate": advocate
                    })

            return result

        case_details = label_value_table(
            "#CSpartyName table.case_details_table"
        )

        if not case_details:
            case_details = label_value_table(
                "table.case_details_table"
            )

        case_status = case_status_table()

        petitioners = parties(
            "ul.Petitioner_Advocate_table li"
        )

        respondents = parties(
            "ul.Respondent_Advocate_table li"
        )

        acts = dynamic_table(
            "table#act_table"
        )

        case_history = dynamic_table(
            "table.history_table"
        )

        orders = dynamic_table(
            "table.order_table"
        )

        try:
            court_name = clean(
                self.driver.find_element(
                    By.CSS_SELECTOR,
                    "#CSpartyName #CSpheading"
                ).text
            )
        except Exception:
            try:
                court_name = clean(
                    self.driver.find_element(
                        By.ID,
                        "CSpheading"
                    ).text
                )
            except Exception:
                court_name = ""

        try:
            page_title = clean(
                self.driver.title
            )
        except Exception:
            page_title = ""

        return {
            "court_name": court_name,
            "page_title": page_title,
            "url": self.driver.current_url,
            "case_details": case_details,
            "case_status": case_status,
            "petitioner_and_advocate": petitioners,
            "respondent_and_advocate": respondents,
            "acts": acts,
            "case_history": case_history,
            "final_orders_judgments": orders
        }

    # ==============================================================
    # CLICK ALL VIEWS + EXTRACT ALL DETAILS INTO JSON
    # ==============================================================

    def click_all_views_and_save_json(self):

        time.sleep(5)

        view_buttons = self.driver.find_elements(
            By.XPATH,
            "//a[contains(normalize-space(.), 'View')]"
        )

        print(
            f"\n✅ Total Views Found: {len(view_buttons)}"
        )

        for i in range(len(view_buttons)):

            try:

                view_buttons = self.driver.find_elements(
                    By.XPATH,
                    "//a[contains(normalize-space(.), 'View')]"
                )

                if i >= len(view_buttons):
                    break

                print(
                    f"\n=============================="
                )
                print(
                    f"Opening View {i + 1}"
                )
                print(
                    f"=============================="
                )

                before = set(
                    self.driver.window_handles
                )

                self.driver.execute_script(
                    "arguments[0].click();",
                    view_buttons[i]
                )

                time.sleep(5)

                after = set(
                    self.driver.window_handles
                )

                new_handles = after - before

                if new_handles:
                    self.driver.switch_to.window(
                        list(new_handles)[0]
                    )
                elif len(self.driver.window_handles) > 1:
                    self.driver.switch_to.window(
                        self.driver.window_handles[-1]
                    )

                try:
                    self.wait.until(
                        lambda d:
                            d.find_elements(
                                By.CSS_SELECTOR,
                                "table.case_details_table"
                            )
                            or
                            d.find_elements(
                                By.ID,
                                "CSpheading"
                            )
                    )
                except Exception:
                    time.sleep(2)

                case_data = self.extract_case_details()

                self.current_case_data[
                    "views"
                ].append({
                    "view_number": i + 1,
                    **case_data
                })

                self.save_case_json()

                print(
                    f"✅ View {i + 1} extracted and saved"
                )

                if len(self.driver.window_handles) > 1:

                    current = self.driver.current_window_handle

                    self.driver.close()

                    remaining = [
                        h for h in self.driver.window_handles
                        if h != current
                    ]

                    if remaining:
                        self.driver.switch_to.window(
                            remaining[0]
                        )

                else:

                    self.driver.back()
                    time.sleep(5)

            except Exception as e:

                print(
                    f"❌ Failed View {i + 1}: {e}"
                )

                self.current_case_data[
                    "views"
                ].append({
                    "view_number": i + 1,
                    "status": "FAILED",
                    "error": str(e)
                })

                self.save_case_json()

                try:
                    if len(self.driver.window_handles) > 1:
                        self.driver.close()
                        self.driver.switch_to.window(
                            self.driver.window_handles[0]
                        )
                    else:
                        self.driver.back()
                        time.sleep(4)
                except Exception:
                    pass

        self.save_case_json()

    # ==============================================================
    # SEARCH CASE
    # ==============================================================

    def search_case(
        self,
        case_index,
        court_name,
        party_name,
        year,
        captcha_wait=0,
    ):

        # ==========================================================
        # CREATE ONE JSON FILE FOR THIS COURT / CASE
        # ==========================================================

        self.create_case_json(
            case_index=case_index,
            court_name=court_name,
            party_name=party_name,
            year=year
        )

        # Select court
        self.select_court(
            court_name
        )

        time.sleep(3)

        # Select establishment
        self.select_establishment()

        time.sleep(2)

        # Enter details
        self.enter_details(
            party_name,
            year
        )

        # Select both
        self.select_both()

        # CAPTCHA
        self.wait_for_captcha(
            captcha_wait=captcha_wait
        )

        self.current_case_data["search_url"] = (
            self.driver.current_url
        )
        self.save_case_json()

        # ==========================================================
        # EXTRACT ALL VIEWS AND SAVE THEM INTO JSON
        # ==========================================================

        self.click_all_views_and_save_json()

    # ==============================================================
    # RESET SEARCH PAGE
    # ==============================================================

    def reset_search(self):

        self.driver.get(
            "https://services.ecourts.gov.in/ecourtindia_v6/"
        )

        time.sleep(3)

        self.click_case_status()

        time.sleep(2)

        self.select_state(
            "Karnataka"
        )

        time.sleep(3)

        self.select_district(
            "BENGALURU"
        )

        time.sleep(3)

    # ==============================================================
    # RUN
    # ==============================================================

    def run(
        self,
        party_name="Ramesh",
        year="2015",
        max_courts=6,
        captcha_wait=60,
    ):

        try:

            self.open_site()

            time.sleep(2)

            self.click_case_status()

            time.sleep(2)

            self.select_state(
                "Karnataka"
            )

            time.sleep(3)

            self.select_district(
                "BENGALURU"
            )

            time.sleep(3)

            courts = self.get_all_courts()

            total_courts_to_check = min(
                max_courts,
                len(courts)
            )

            # ======================================================
            # ONE JSON FILE PER COURT
            # ======================================================

            for idx in range(
                total_courts_to_check
            ):

                case_index = idx + 1

                print(
                    "\n===================================="
                )

                print(
                    f"SEARCHING CASE {case_index}"
                )

                print(
                    f"COURT: {courts[idx]}"
                )

                print(
                    "====================================\n"
                )

                self.search_case(
                    case_index=case_index,
                    court_name=courts[idx],
                    party_name=party_name,
                    year=year,
                    captcha_wait=captcha_wait,
                )

                print(
                    f"\n✅ CASE {case_index} DONE"
                )

                print(
                    f"📄 JSON saved in:"
                )

                print(
                    f"   {self.current_case_file}"
                )

                # ==================================================
                # RESET BEFORE NEXT COURT
                # ==================================================

                if idx != total_courts_to_check - 1:

                    self.reset_search()

                    courts = self.get_all_courts()

            print(
                "\n✅ ALL CASES COMPLETED"
            )

            print(
                f"\n📁 Main JSON directory:"
            )

            print(
                f"   {os.path.abspath(self.json_dir)}"
            )

            time.sleep(10)

        finally:

            self.driver.quit()

            print(
                "\n✅ Browser closed"
            )


# ==============================================================
# MAIN
# ==============================================================

def main():

    parser = argparse.ArgumentParser(
        description="eCourts portal automation"
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True
    )

    search = sub.add_parser(
        "search",
        help="Search case status by party name"
    )

    search.add_argument(
        "--party-name",
        required=True
    )

    search.add_argument(
        "--year",
        default="2015"
    )

    search.add_argument(
        "--max-courts",
        type=int,
        default=6
    )

    search.add_argument(
        "--captcha-wait",
        type=int,
        default=60
    )

    args = parser.parse_args()

    if args.command == "search":

        bot = ECourtAutomation()

        bot.run(
            party_name=args.party_name,
            year=args.year,
            max_courts=args.max_courts,
            captcha_wait=args.captcha_wait,
        )


if __name__ == "__main__":
    main()