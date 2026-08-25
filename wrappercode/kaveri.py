# kaveri.py
# pip install selenium webdriver-manager

import argparse
from glob import glob
import os
import shutil
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.keys import Keys

from file_utils import latest_file
class KaveriBot:

    def __init__(self):

        options = webdriver.ChromeOptions()

        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

        self.wait = WebDriverWait(self.driver, 40)

    # ---------------------------------------------------
    # OPEN WEBSITE
    # ---------------------------------------------------
    def open_site(self):

        print("Opening Kaveri website...")

        self.driver.get(
            "https://kaveri.karnataka.gov.in/"
        )

        time.sleep(5)

        print("Homepage opened")

    def login(self, username, password, captcha_wait=0):

        try:

            print("Waiting homepage load...")
            time.sleep(8)

            # LOGIN BUTTON
            login_btn = self.wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//button[contains(text(),'Login')]"
                    )
                )
            )

            self.driver.execute_script(
                "arguments[0].click();",
                login_btn
            )

            print("Clicked Login")

            # WAIT FOR MODAL
            time.sleep(5)
            # USERNAME FIELD
            username_input = self.wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//input[@placeholder='Username']"
                    )
                )
            )

            # CLICK FIRST
            self.driver.execute_script(
                "arguments[0].click();",
                username_input
            )

            time.sleep(1)

            username_input.clear()

            username_input.send_keys(username)

            print("Username entered")

            # PASSWORD FIELD
            password_input = self.wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//input[@placeholder='Password']"
                    )
                )
            )

            self.driver.execute_script(
                "arguments[0].click();",
                password_input
            )

            time.sleep(1)

            password_input.clear()

            password_input.send_keys(password)

            print("Password entered")

            if captcha_wait and captcha_wait > 0:
                print(f"\nWaiting {captcha_wait}s for manual login CAPTCHA...")
                time.sleep(captcha_wait)
            else:
                print("\nEnter CAPTCHA manually")
                input("After login press ENTER...")

        except Exception as e:

            print("LOGIN ERROR:")
            print(str(e))

        
    # ---------------------------------------------------
    # START NEW APPLICATION
    # ---------------------------------------------------
    def start_application(self):

        buttons = self.driver.find_elements(By.TAG_NAME, "button")

        for btn in buttons:

            if btn.text.strip() == "START A NEW APPLICATION":

                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});",
                    btn
                )

                time.sleep(2)

                self.driver.execute_script(
                    "arguments[0].click();",
                    btn
                )

                print("START APPLICATION CLICKED")

                return

        raise Exception("START A NEW APPLICATION button not found")
    # ---------------------------------------------------
    # OPEN EC APPLICATION
    # ---------------------------------------------------
    def open_ec(self):

        try:

            print("Waiting for popup...")
            time.sleep(5)

            # Find EC text
            ec_text = self.driver.find_element(
                By.XPATH,
                "//*[contains(text(),'ENCUMBERANCE CERTIFICATE')]"
            )

            print("Found EC text")

            # Find icon ABOVE the text
            icon = ec_text.find_element(
                By.XPATH,
                "./preceding::*[name()='svg' or self::img][1]"
            )

            print("Found icon")

            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                icon
            )

            time.sleep(2)

            # Click icon using JS
            self.driver.execute_script(
                "arguments[0].click();",
                icon
            )

            print("Clicked icon")

            time.sleep(5)
            # Wait for Continue button
            continue_btn = self.wait.until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//button[contains(.,'Continue')]"
                    )
                )
            )

            self.driver.execute_script("""
            arguments[0].dispatchEvent(
                new MouseEvent('click', {
                    bubbles:true,
                    cancelable:true,
                    view:window
                })
            );
            """, continue_btn)

            print("Continue clicked")
            time.sleep(3)

            # Select After 01/01/2004
            after_radio = self.wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//label[contains(.,'After 01/01/2004')]"
                    )
                )
            )

            self.driver.execute_script(
                "arguments[0].click();",
                after_radio
            )

            print("Selected After 01/01/2004")

            time.sleep(1)

            # Click Proceed
            proceed_btn = self.wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//button[contains(.,'Proceed')]"
                    )
                )
            )

            self.driver.execute_script(
                "arguments[0].click();",
                proceed_btn
            )

            print("Clicked Proceed")

            time.sleep(5)

            print("Property Details Page Opened")            
        except Exception:
            import traceback
            traceback.print_exc()
    # ---------------------------------------------------
    # SELECT DROPDOWN OPTION
    # ---------------------------------------------------
    def select_dropdown(self, xpath, text):

        dropdown = self.wait.until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    xpath
                )
            )
        )

        dropdown.click()

        time.sleep(1)

        option = self.wait.until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    f"//option[contains(text(),'{text}')]"
                )
            )
        )

        option.click()

        time.sleep(2)

    # ---------------------------------------------------
    # ENTER PROPERTY DETAILS
    # ---------------------------------------------------
    def enter_property_details(
        self,
        district="Basavanagudi",
        taluka="Anekal",
        hobli="Anekal Town",
        village="Ward No. 1",
        property_type="non_agricultural",
    ):

        try:

            print("Entering property details...")

            # DISTRICT
            self.select_dropdown(
                "(//select)[1]",
                district
            )

            # TALUKA
            self.select_dropdown(
                "(//select)[2]",
                taluka
            )

            # HOBLI/TOWN
            self.select_dropdown(
                "(//select)[3]",
                hobli
            )

            # VILLAGE
            self.select_dropdown(
                "(//select)[4]",
                village
            )

            print("Dropdowns selected")

            if property_type == "agricultural":
                agri = self.wait.until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            "//label[contains(text(),'Agricultural')]"
                        )
                    )
                )
                agri.click()
                print("Selected Agricultural")
            else:
                non_agri = self.wait.until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            "//label[contains(text(),'Non - Agricultural')]"
                        )
                    )
                )
                non_agri.click()
                print("Selected Non Agricultural")

            time.sleep(2)

        except Exception as e:

            print("PROPERTY DETAILS ERROR:")
            print(e)


    def enter_property_number(self, property_no):

        print("Entering property number...")

        # Scroll to Property Number section
        section = self.wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(),'PROPERTY NUMBER TYPE')]")
            )
        )

        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            section
        )

        time.sleep(2)
        property_dropdown = None

        for sel in self.driver.find_elements(By.TAG_NAME, "select"):
            try:
                s = Select(sel)

                options = [o.text.strip() for o in s.options]

                if "Property No" in options:
                    property_dropdown = s
                    break

            except:
                pass

        if property_dropdown is None:
            raise Exception("Property dropdown not found")

        property_dropdown.select_by_visible_text("Property No")

        print("Property No selected")


        time.sleep(2)
        # -----------------------------
        # Property Number textbox
        # -----------------------------
        property_box = self.wait.until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//input[@formcontrolname='_currentnumber']"
                )
            )
        )

        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            property_box
        )

        property_box.click()
        property_box.clear()
        property_box.send_keys(str(property_no))

        print("Property number entered:", property_no)
        print("Textbox value:", property_box.get_attribute("value"))

    def enter_dates(self, from_date, to_date):

        date_boxes = WebDriverWait(self.driver, 20).until(
            lambda d: d.find_elements(By.XPATH, "//input[@placeholder='DD/MM/YYYY']")
        )

        # ---------- FROM DATE ----------
        self.driver.execute_script("""
            arguments[0].removeAttribute('readonly');
            arguments[0].focus();
            arguments[0].value = arguments[1];
            arguments[0].dispatchEvent(new Event('input', {bubbles:true}));
            arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
            arguments[0].dispatchEvent(new Event('blur', {bubbles:true}));
        """, date_boxes[0], from_date)
        time.sleep(2)
        # ---------- TO DATE ----------
        self.driver.execute_script("""
            arguments[0].removeAttribute('readonly');
            arguments[0].focus();
            arguments[0].value = arguments[1];
            arguments[0].dispatchEvent(new Event('input', {bubbles:true}));
            arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
            arguments[0].dispatchEvent(new Event('blur', {bubbles:true}));
        """, date_boxes[1], to_date)
        time.sleep(2)
        # Move focus out of the field
        date_boxes[1].send_keys(Keys.TAB)

        print("From Date =", date_boxes[0].get_attribute("value"))
        print("To Date   =", date_boxes[1].get_attribute("value"))    
    # ---------------------------------------------------
    # SEARCH
    # ---------------------------------------------------
    def search(self, captcha_wait=0):

        try:

            if captcha_wait and captcha_wait > 0:
                print(f"\nWaiting {captcha_wait}s for manual search CAPTCHA...")
                time.sleep(captcha_wait)
            else:
                print("\nEnter CAPTCHA manually")
                input("After CAPTCHA press ENTER...")

            search_btn = self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//button[normalize-space()='Search']")
                )
            )

            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                search_btn
            )
            time.sleep(1)

            search_btn.click()

            # Wait for success popup
            WebDriverWait(self.driver, 30).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//*[contains(text(),'Search completed successfully')]")
                )
            )

            print("Search completed popup detected")

            # Click OK
            ok_btn = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[normalize-space()='OK']")
                )
            )

            self.driver.execute_script("arguments[0].click();", ok_btn)
            print("Clicked OK")

            # Wait for popup to disappear
            WebDriverWait(self.driver, 20).until(
                EC.invisibility_of_element_located(
                    (By.XPATH, "//*[contains(text(),'Search completed successfully')]")
                )
            )

            # Wait for page to finish rendering
            time.sleep(3)

            # Scroll down gradually until the download icon appears
            download_btn = None

            for _ in range(10):

                self.driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(1)

                try:
                    # Find all clickable SVG elements
                    elements = self.driver.find_elements(
                        By.XPATH,
                        "//*[contains(@class,'mat') or self::button or self::a or self::img or self::*[local-name()='svg']]"
                    )

                    print(f"Found {len(elements)} SVG elements")

                    for i, e in enumerate(elements, 1):
                        print("=" * 60)
                        print(i)
                        print("TAG   :", e.tag_name)
                        print("ARIA  :", e.get_attribute("aria-label"))
                        print("TITLE :", e.get_attribute("title"))
                        print("CLASS :", e.get_attribute("class"))

                        aria = (e.get_attribute("aria-label") or "").lower()
                        title = (e.get_attribute("title") or "").lower()
                        cls = (e.get_attribute("class") or "").lower()

                        # Skip the calendar buttons
                        if "calendar" in aria:
                            continue

                        if "calendar" in title:
                            continue

                        download_btn = e
                        break

                    if download_btn:
                        break

                except Exception:
                    pass

            if download_btn is None:
                raise Exception("Download button not found.")

            # Bring it into view
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                download_btn
            )

            time.sleep(1)

            ActionChains(self.driver)\
                .move_to_element(download_btn)\
                .pause(0.5)\
                .click()\
                .perform()

            print("Download clicked")

            BASE_DIR = r"D:\aasthiv2\Aasthi\wrappercode"

            DOWNLOAD_DIR = os.path.join(BASE_DIR, "input", "kaveriec")

            print("Waiting for EC PDF download...")

            timeout = 60
            start = time.time()

            while time.time() - start < timeout:

                pdf = latest_file(DOWNLOAD_DIR, ("*.pdf",))

                downloading = glob(os.path.join(DOWNLOAD_DIR, "*.crdownload"))

                if pdf and not downloading:
                    print("EC PDF downloaded successfully.")
                    print("Saved to:", pdf)
                    break

                time.sleep(1)
            else:
                raise Exception("EC PDF download timed out.")

        except Exception as e:
            print("SEARCH ERROR:")
            print(e)
            raise
    # ---------------------------------------------------
    # CLOSE
    # ---------------------------------------------------
    def close(self):

        self.driver.quit()


def run_ec_search(args):
    bot = KaveriBot()
    try:
        bot.open_site()
        USERNAME = "pradhyumna.nov2004@gmail.com"
        PASSWORD = "OKjrjN9VZH"

        bot.login(
            USERNAME,
            PASSWORD,
            captcha_wait=args.captcha_wait
        )
        bot.start_application()
        bot.open_ec()
        bot.enter_property_details(
            district=args.district,
            taluka=args.taluka,
            hobli=args.hobli,
            village=args.village,
            property_type=args.property_type,
        )
        if args.property_no:
            bot.enter_property_number(args.property_no)
        bot.enter_dates(
                args.from_date,
                args.to_date
            )
        bot.search(
            captcha_wait=args.captcha_wait,
        )
    finally:
        bot.close()


def main():
    parser = argparse.ArgumentParser(description="Kaveri portal automation")
    sub = parser.add_subparsers(dest="command", required=True)

    ec = sub.add_parser("ec-search", help="Fetch EC from Kaveri")

    ec.add_argument("--district", required=True)
    ec.add_argument("--taluka", required=True)
    ec.add_argument("--hobli", required=True)
    ec.add_argument("--village", required=True)

    ec.add_argument(
        "--property-type",
        choices=["agricultural", "non_agricultural"],
        default="non_agricultural",
    )

    ec.add_argument("--property-no", required=True)

    ec.add_argument("--from-date", default="01/01/2004")
    ec.add_argument("--to-date", default="01/05/2026")

    ec.add_argument("--captcha-wait", type=int, default=40)
    # ec.add_argument("--screenshot-out", default="")

    args = parser.parse_args()

    if args.command == "ec-search":
        run_ec_search(args)


if __name__ == "__main__":
    main()