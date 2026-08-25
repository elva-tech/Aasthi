# kaveri.py
# pip install selenium webdriver-manager

import argparse
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
                "//*[contains(text(),'CERTIFIED COPY')]"
            )

            print("Found CC text")

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
        document_type="Document Registration",
        district="Bangalore Rural",
        sro="Anekal",
        book_type="Book-1",
        document_no="04686",
        year="2017-18",
    ):
        print("Selecting Standard Search...")

        standard_search = self.wait.until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//label[contains(.,'Standard Search')]"
                )
            )
        )

        self.driver.execute_script(
            "arguments[0].click();",
            standard_search
        )

        time.sleep(2)

        print("Selecting Document Type...")
        Select(
            self.driver.find_element(
                By.XPATH,
                "(//select)[1]"
            )
        ).select_by_visible_text(document_type)

        print("Selecting District...")
        Select(
            self.driver.find_element(
                By.XPATH,
                "(//select)[2]"
            )
        ).select_by_visible_text(district)

        time.sleep(2)

        print("Selecting SRO...")
        Select(
            self.driver.find_element(
                By.XPATH,
                "(//select)[3]"
            )
        ).select_by_visible_text(sro)

        Select(
            self.driver.find_element(
                By.XPATH,
                "(//select)[4]"
            )
        ).select_by_visible_text(book_type)

        print(f"Book Type: {book_type}")

        print("Entering Document Number...")
        doc_box = self.driver.find_element(
            By.XPATH,
            "//input[@placeholder='Example: 04686']"
        )
        doc_box.clear()
        doc_box.send_keys(document_no)

        print("Selecting Year...")
        Select(
            self.driver.find_element(
                By.XPATH,
                "(//select)[5]"
            )
        ).select_by_visible_text(year)

        print("Standard Search details entered")

    
    # ---------------------------------------------------
    # SEARCH
    # ---------------------------------------------------
    def search(self, screenshot_out=""):

        try:

            search_btn = self.wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//*[contains(text(),'Search')]"
                    )
                )
            )

            self.driver.execute_script(
                "arguments[0].click();",
                search_btn
            )

            print("Search clicked")

            time.sleep(20)

            result_path = screenshot_out or "step9_results.png"
            self.driver.save_screenshot(result_path)

            print(f"Saved EC screenshot: {result_path}")

        except Exception as e:

            print("SEARCH ERROR:")
            print(e)

            err_path = screenshot_out or "search_error.png"
            self.driver.save_screenshot(err_path)

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
            document_type=args.document_type,
            district=args.district,
            sro=args.sro,
            book_type=args.book_type,
            document_no=args.document_no,
            year=args.year,
        )
        bot.search(
            screenshot_out=args.screenshot_out or "step9_results.png"
        )
    finally:
        bot.close()


def main():
    parser = argparse.ArgumentParser(description="Kaveri portal automation")
    sub = parser.add_subparsers(dest="command", required=True)

    ec = sub.add_parser("ec-search", help="Fetch EC from Kaveri")

    ec.add_argument("--document-type", required=True)
    ec.add_argument("--district", required=True)
    ec.add_argument("--sro", required=True)
    ec.add_argument("--book-type", required=True)
    ec.add_argument("--document-no", required=True)
    ec.add_argument("--year", required=True)
    ec.add_argument("--screenshot-out", default="")

    args = parser.parse_args()

    if args.command == "ec-search":
        run_ec_search(args)


if __name__ == "__main__":
    main()