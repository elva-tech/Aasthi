# kaveri.py
# pip install selenium webdriver-manager undetected-chromedriver

import argparse
from glob import glob
import os
import subprocess
import time
import random
import undetected_chromedriver as uc
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
        
        # Kaveri EC download folder
        BASE_DIR = r"D:\aasthiv2\Aasthi\wrappercode"
        DOWNLOAD_DIR = os.path.join(
            BASE_DIR,
            "input",
            "kaveriec"
        )

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        # Chrome automatic download settings
        prefs = {
            "download.default_directory": DOWNLOAD_DIR,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": False,
            "safebrowsing.disable_download_protection": True,
            "plugins.always_open_pdf_externally": True,
            # Additional settings for better download handling
            "profile.default_content_setting_values.automatic_downloads": 1,
            "download.extensions_to_open": "",
        }

        options.add_experimental_option(
            "prefs",
            prefs
        )

        self.driver = uc.Chrome(options=options)

        # Enable download via CDP
        self.driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": DOWNLOAD_DIR
        })

        self.wait = WebDriverWait(
            self.driver,
            40
        )

    # ---------------------------------------------------
    # HUMAN-LIKE CLICK WITH NATURAL MOVEMENT
    # ---------------------------------------------------
    def human_click(self, element, offset_x=None, offset_y=None, click_type="left"):
        """
        Perform a human-like click on an element with natural mouse movement,
        random delays, and realistic timing.
        
        Args:
            element: WebElement to click
            offset_x: Random offset from center (default: random -8 to +8)
            offset_y: Random offset from center (default: random -8 to +8)
            click_type: "left" or "right"
        """
        # Get element location and size
        location = element.location
        size = element.size
        
        # Calculate center point
        center_x = location['x'] + size['width'] / 2
        center_y = location['y'] + size['height'] / 2
        
        # Add random offset if not specified
        if offset_x is None:
            offset_x = random.randint(-8, 8)
        if offset_y is None:
            offset_y = random.randint(-8, 8)
        
        target_x = center_x + offset_x
        target_y = center_y + offset_y
        
        # Random natural delay before starting (100-400ms)
        time.sleep(random.uniform(0.1, 0.4))
        
        # Human-like mouse movement with multiple steps
        steps = random.randint(8, 18)
        start_x = random.randint(0, 200)
        start_y = random.randint(0, 200)
        
        # Use ActionChains for gradual movement
        action = ActionChains(self.driver)
        
        # Move to element with bezier-like motion
        for i in range(steps):
            progress = (i + 1) / steps
            eased = progress * progress * (3 - 2 * progress)  # Smooth step
            current_x = start_x + (target_x - start_x) * eased
            current_y = start_y + (target_y - start_y) * eased
            if i == 0:
                action.move_to_element(element)
            else:
                action.move_by_offset(0, 0)
        
        # Add slight pause before click (200-400ms)
        time.sleep(random.uniform(0.2, 0.4))
        
        # Perform click with natural timing
        if click_type == "left":
            action.click()
        else:
            action.context_click()
        
        # Small pause after click (100-300ms)
        time.sleep(random.uniform(0.1, 0.3))
        
        action.perform()
        
        # Brief pause after click completes
        time.sleep(random.uniform(0.3, 0.7))
        
        return target_x, target_y

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

    # ---------------------------------------------------
    # LOGIN
    # ---------------------------------------------------
    def login(self, username, password, captcha_wait=0):

        try:
            # Try up to 3 times to handle the multi-session popup
            max_attempts = 3
            attempt = 0
            login_success = False

            while attempt < max_attempts and not login_success:
                attempt += 1
                print(f"Login attempt {attempt}/{max_attempts}")

                if attempt == 1:
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

                    print("Clicked Login - waiting for popup or login screen...")
                    time.sleep(5)

                # -----------------------------------------
                # HANDLE MULTIPLE ACTIVE SESSION POPUP
                # -----------------------------------------
                popup_handled = False
                
                # Method 1: Check for JavaScript Alert
                try:
                    alert = self.driver.switch_to.alert
                    alert_text = alert.text
                    print(f"Alert detected with text: {alert_text}")
                    
                    if "Multiple active session" in alert_text:
                        print("Multiple active session alert detected!")
                        alert.accept()
                        print("Accepted multi-session alert (clicked OK)")
                        popup_handled = True
                        time.sleep(3)
                except:
                    pass

                # Method 2: Check for HTML modal
                if not popup_handled:
                    try:
                        popup_elements = self.driver.find_elements(
                            By.XPATH,
                            "//*[contains(text(), 'Multiple active session')]"
                        )
                        if popup_elements:
                            print("Multiple active session popup detected in HTML!")
                            ok_btns = self.driver.find_elements(
                                By.XPATH,
                                "//button[contains(text(), 'OK')]"
                            )
                            for btn in ok_btns:
                                if btn.is_displayed():
                                    self.driver.execute_script("arguments[0].click();", btn)
                                    print("Clicked OK on multi-session popup")
                                    popup_handled = True
                                    time.sleep(3)
                                    break
                    except:
                        pass

                # If popup was handled, go back to home page and click Login again
                if popup_handled:
                    print("Popup handled successfully. Returning to home page...")
                    time.sleep(3)
                    
                    try:
                        login_btn = WebDriverWait(self.driver, 20).until(
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
                        print("Clicked Login again after popup")
                        time.sleep(5)
                    except:
                        print("Login button not found after popup - may be on login screen")

                # -----------------------------------------
                # CHECK IF WE'RE ON LOGIN SCREEN
                # -----------------------------------------
                try:
                    username_input = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located(
                            (
                                By.XPATH,
                                "//input[@placeholder='Username']"
                            )
                        )
                    )
                    print("Login screen detected with username field")
                    login_success = True
                    break
                except:
                    try:
                        if "dashboard" in self.driver.current_url:
                            print("Already on dashboard - already logged in!")
                            login_success = True
                            break
                    except:
                        pass
                    
                    if attempt < max_attempts:
                        print(f"Login screen not detected. Retrying... (attempt {attempt}/{max_attempts})")
                        time.sleep(3)
                        try:
                            login_btn = self.driver.find_element(
                                By.XPATH,
                                "//button[contains(text(),'Login')]"
                            )
                            self.driver.execute_script("arguments[0].click();", login_btn)
                            print("Clicked Login again")
                            time.sleep(5)
                        except:
                            pass
                        continue
                    else:
                        raise Exception("Could not access login screen after multiple attempts")

            # If we're already logged in (dashboard), skip credential entry
            if "dashboard" in self.driver.current_url:
                print("Already logged in - skipping credential entry")
                return

            # -----------------------------------------
            # ENTER CREDENTIALS
            # -----------------------------------------
            print("Entering credentials...")
            
            # USERNAME
            username_input = self.wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//input[@placeholder='Username']"
                    )
                )
            )

            self.driver.execute_script(
                "arguments[0].click();",
                username_input
            )

            time.sleep(1)

            username_input.clear()
            username_input.send_keys(username)
            print("Username entered")

            # PASSWORD
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

            # CAPTCHA handling (manual)
            print("\n" + "="*60)
            print("MANUAL STEP: Please enter CAPTCHA")
            print("="*60)
            
            if captcha_wait and captcha_wait > 0:
                print(f"Waiting {captcha_wait}s for manual CAPTCHA entry...")
                time.sleep(captcha_wait)
            else:
                input("After entering CAPTCHA, press ENTER to continue...")

            # Click Login button after CAPTCHA
            try:
                login_submit = self.wait.until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            "//button[contains(text(),'Log in') or contains(text(),'Login')]"
                        )
                    )
                )
                self.driver.execute_script("arguments[0].click();", login_submit)
                print("Login submitted - waiting for OTP screen...")
            except:
                print("Login button not found - maybe already submitted?")

            # OTP handling (manual)
            print("\n" + "="*60)
            print("MANUAL STEP: Please enter OTP")
            print("="*60)
            print("After entering OTP, the page will redirect to dashboard")
            print("Waiting for dashboard to load...")
            
            # Wait for dashboard to appear
            dashboard_timeout = 120
            start_time = time.time()
            dashboard_detected = False
            
            while time.time() - start_time < dashboard_timeout:
                try:
                    if "dashboard" in self.driver.current_url:
                        print("Dashboard detected! Login successful.")
                        dashboard_detected = True
                        break
                    
                    try:
                        elements = self.driver.find_elements(
                            By.XPATH,
                            "//*[contains(text(), 'START A NEW APPLICATION')]"
                        )
                        if elements:
                            print("START A NEW APPLICATION found! Login successful.")
                            dashboard_detected = True
                            break
                    except:
                        pass
                    
                    print("Still waiting for dashboard... (OTP may not be entered yet)")
                    time.sleep(5)
                except:
                    time.sleep(5)
            
            if not dashboard_detected:
                print("\n" + "="*60)
                print("Dashboard not detected automatically.")
                print("If you're on the dashboard, press ENTER to continue.")
                print("If not, please complete OTP entry and then press ENTER.")
                print("="*60)
                input("Press ENTER after you're on the dashboard...")
                print("Continuing with automation...")
            else:
                print("Continuing with automation...")
            
            time.sleep(3)

        except Exception as e:
            print("LOGIN ERROR:")
            print(str(e))
            raise

    # ---------------------------------------------------
    # START NEW APPLICATION
    # ---------------------------------------------------
    def start_application(self):

        print("Waiting for START A NEW APPLICATION...")

        try:
            print("Waiting for dashboard to fully load...")
            time.sleep(5)

            start_btn = None
            
            start_xpaths = [
                "//button[contains(normalize-space(), 'START A NEW APPLICATION')]",
                "//button[contains(text(), 'START A NEW APPLICATION')]",
                "//button[contains(text(), 'Start a New Application')]",
                "//button[contains(text(), 'Start New Application')]",
                "//button[contains(text(), 'START')]",
                "//a[contains(normalize-space(), 'START A NEW APPLICATION')]",
                "//a[contains(text(), 'START A NEW APPLICATION')]",
                "//div[contains(text(), 'START A NEW APPLICATION')]/parent::button",
                "//div[contains(text(), 'START A NEW APPLICATION')]/parent::a",
                "//*[@role='button' and contains(text(), 'START')]",
                "//*[@role='button' and contains(text(), 'Application')]",
                "//button[contains(@class, 'start')]",
                "//button[contains(@class, 'application')]",
                "//a[contains(@class, 'start')]",
                "//*[contains(text(), 'START A NEW APPLICATION')]",
                "//*[contains(text(), 'Start a New Application')]",
                "//div[@class='dashboard']//*[contains(text(), 'START')]",
                "//div[@class='main']//*[contains(text(), 'START')]",
                "//section//*[contains(text(), 'START')]"
            ]

            for xpath in start_xpaths:
                try:
                    elements = self.driver.find_elements(By.XPATH, xpath)
                    for elem in elements:
                        if elem.is_displayed() and elem.is_enabled():
                            start_btn = elem
                            print(f"Found START button with XPath: {xpath}")
                            print(f"Button text: '{elem.text}'")
                            print(f"Button tag: {elem.tag_name}")
                            break
                    if start_btn:
                        break
                except Exception as e:
                    continue

            if start_btn is None:
                print("Trying to find by searching all elements for 'START' text...")
                all_elements = self.driver.find_elements(By.XPATH, "//*")
                for elem in all_elements:
                    try:
                        text = elem.text.upper() if elem.text else ""
                        if "START A NEW APPLICATION" in text or "START NEW APPLICATION" in text:
                            if elem.is_displayed() and elem.is_enabled():
                                if elem.tag_name in ['button', 'a'] or elem.get_attribute('role') == 'button':
                                    start_btn = elem
                                    print(f"Found START element by text search: {elem.tag_name}")
                                    print(f"Text: '{elem.text}'")
                                    break
                    except:
                        continue

            if start_btn is None:
                print("Looking for Angular-specific selectors...")
                try:
                    start_btn = self.driver.find_element(
                        By.XPATH,
                        "//button[contains(@class, 'mat-raised-button') and contains(text(), 'START')]"
                    )
                    if start_btn:
                        print("Found START button with Angular class")
                except:
                    pass

            if start_btn is None:
                print("Checking for shadow DOM elements...")
                try:
                    start_btn = self.driver.execute_script("""
                        var elements = document.querySelectorAll('*');
                        for (var i = 0; i < elements.length; i++) {
                            var text = elements[i].textContent || '';
                            if (text.includes('START A NEW APPLICATION') || text.includes('START NEW APPLICATION')) {
                                if (elements[i].offsetParent !== null) {
                                    return elements[i];
                                }
                            }
                        }
                        return null;
                    """)
                    if start_btn:
                        print("Found START button via JavaScript search")
                except:
                    pass

            if start_btn is None:
                screenshot_path = "debug_start_button.png"
                self.driver.save_screenshot(screenshot_path)
                print(f"Screenshot saved to: {screenshot_path}")
                print(f"Current URL: {self.driver.current_url}")
                print("Page title:", self.driver.title)
                
                print("\nAll buttons on the page:")
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for i, btn in enumerate(buttons[:20]):
                    try:
                        print(f"  Button {i+1}: text='{btn.text[:50]}' class='{btn.get_attribute('class')}'")
                    except:
                        pass
                
                raise Exception("START A NEW APPLICATION button not found on dashboard")

            # Scroll to button with human-like behavior
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center', behavior: 'smooth'});",
                start_btn
            )
            time.sleep(random.uniform(0.5, 1.0))

            # Human-like click on START button
            try:
                self.human_click(start_btn)
                print("START APPLICATION CLICKED (via human_click)")
            except:
                try:
                    self.driver.execute_script("arguments[0].click();", start_btn)
                    print("START APPLICATION CLICKED (via JavaScript)")
                except:
                    start_btn.click()
                    print("START APPLICATION CLICKED (via normal click)")

            time.sleep(5)
            print("Waiting for application page to load...")

        except Exception as e:
            print("START A NEW APPLICATION button not found or could not be clicked.")
            print("Current URL:", self.driver.current_url)
            try:
                screenshot_path = "debug_start_button.png"
                self.driver.save_screenshot(screenshot_path)
                print(f"Screenshot saved to: {screenshot_path}")
            except:
                pass
            raise

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
                    EC.presence_of_element_located(
                        (
                            By.XPATH,
                            "//label[contains(text(),'Agricultural')]"
                        )
                    )
                )
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});",
                    agri
                )
                time.sleep(1)
                self.driver.execute_script("arguments[0].click();", agri)
                print("Selected Agricultural")
            else:
                non_agri = self.wait.until(
                    EC.presence_of_element_located(
                        (
                            By.XPATH,
                            "//label[contains(text(),'Non - Agricultural')]"
                        )
                    )
                )
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});",
                    non_agri
                )
                time.sleep(1)
                self.driver.execute_script("arguments[0].click();", non_agri)
                print("Selected Non Agricultural")
            time.sleep(2)

        except Exception as e:

            print("PROPERTY DETAILS ERROR:")
            print(e)

    # ---------------------------------------------------
    # ENTER PROPERTY NUMBER
    # ---------------------------------------------------
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

    # ---------------------------------------------------
    # ENTER DATES
    # ---------------------------------------------------
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
            # Define download directory at the start
            BASE_DIR = r"D:\desktop\ML project(elva)\aasthiv2\aasthiv2\Aasthi\wrappercode"
            DOWNLOAD_DIR = os.path.join(
                BASE_DIR,
                "input",
                "kaveriec"
            )

            if captcha_wait and captcha_wait > 0:
                print(f"\nWaiting {captcha_wait}s for manual search CAPTCHA...")
                time.sleep(captcha_wait)
            else:
                print("\nEnter CAPTCHA manually")
                input("After CAPTCHA press ENTER...")

            # Find and click Search button
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
            print("Search button clicked - waiting for results...")

            # Wait for results - try multiple possible popup messages
            time.sleep(5)
            
            popup_found = False
            popup_messages = [
                "Search completed successfully",
                "Search completed",
                "Record found",
                "No records found",
                "Results found"
            ]
            
            for message in popup_messages:
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.visibility_of_element_located(
                            (By.XPATH, f"//*[contains(text(),'{message}')]")
                        )
                    )
                    print(f"Popup detected: '{message}'")
                    popup_found = True
                    break
                except:
                    continue
            
            if not popup_found:
                try:
                    results = self.driver.find_elements(By.XPATH, "//table//td")
                    if results:
                        print("Results found in table format")
                        popup_found = True
                    else:
                        page_text = self.driver.find_element(By.TAG_NAME, "body").text
                        if "EC" in page_text or "Encumbrance" in page_text:
                            print("EC results detected on page")
                            popup_found = True
                except:
                    pass
            
            if not popup_found:
                print("\n" + "="*60)
                print("Could not automatically detect search completion.")
                print("If you see EC results in the browser, press ENTER.")
                print("If not, please check the search and try again.")
                print("="*60)
                input("Press ENTER to continue...")
            else:
                print("Search results found - continuing...")
            
            # Try to click OK if popup appears
            try:
                ok_btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[normalize-space()='OK']")
                    )
                )
                self.driver.execute_script("arguments[0].click();", ok_btn)
                print("Clicked OK on popup")
            except:
                print("No OK button found - continuing...")

            # Wait for page to finish rendering
            time.sleep(5)

            # -----------------------------------------
            # FIND DOWNLOAD BUTTON
            # -----------------------------------------

            print("\n" + "="*60)
            print("Auto-clicking Download button...")
            print("="*60)

            print("Locating Download button by position (top-right icon button)...")

            download_btn = self.driver.execute_script("""
                var candidates = [];
                var buttons = document.querySelectorAll('button, a');

                for (var i = 0; i < buttons.length; i++) {
                    var el = buttons[i];
                    if (el.offsetParent === null) continue;

                    var rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) continue;

                    var hasSvg = el.querySelector('svg') !== null;
                    var hasText = el.textContent.trim().length > 0;

                    if (hasSvg && !hasText) {
                        candidates.push({el: el, rect: rect});
                    }
                }

                if (candidates.length === 0) return null;

                candidates.sort(function(a, b) {
                    return b.rect.right - a.rect.right;
                });

                return candidates[0].el;
            """)

            if download_btn:
                print("Found Download button via right-edge position heuristic")
                print(f"Tag: {download_btn.tag_name}")
                print(f"Class: {download_btn.get_attribute('class')}")

            if download_btn is None:
                screenshot_path = "debug_no_download_button.png"
                self.driver.save_screenshot(screenshot_path)
                print(f"Screenshot saved to: {screenshot_path}")
                print(f"Current URL: {self.driver.current_url}")
                print("Page title:", self.driver.title)
                
                print("\nAll buttons on the page:")
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for i, btn in enumerate(buttons[:30]):
                    try:
                        text = btn.text[:50] if btn.text else "No text"
                        class_name = btn.get_attribute('class') or "No class"
                        aria_label = btn.get_attribute('aria-label') or "No aria-label"
                        title = btn.get_attribute('title') or "No title"
                        location = btn.location
                        print(f"  Button {i+1}: text='{text}' class='{class_name}' aria='{aria_label}' title='{title}' y={location['y']}")
                    except:
                        pass
                
                print("\nChecking if EC results are visible...")
                try:
                    page_text = self.driver.find_element(By.TAG_NAME, "body").text
                    if "EC" in page_text or "Encumbrance" in page_text or "Village" in page_text:
                        print("EC results appear to be visible on page!")
                        print("The download button might be at the top right corner.")
                        print("Please check the browser window.")
                    else:
                        print("No EC results found on page.")
                except:
                    pass
                
                raise Exception("EC Download button not found.")

            # -----------------------------------------
            # HUMAN-LIKE BEHAVIOR BEFORE CLICK
            # -----------------------------------------

            # Random scroll behavior
            print("Performing human-like scrolling...")
            scroll_amounts = [random.randint(-50, 50) for _ in range(random.randint(1, 3))]
            for amount in scroll_amounts:
                self.driver.execute_script(f"window.scrollBy(0, {amount});")
                time.sleep(random.uniform(0.1, 0.3))
            
            # Smooth scroll to button
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center', behavior: 'smooth'});",
                download_btn
            )
            time.sleep(random.uniform(0.3, 0.8))

            # Random mouse movement before clicking
            print("Simulating natural mouse movement...")
            rand_x = random.randint(-100, -30)
            rand_y = random.randint(-50, -20)
            
            try:
                ActionChains(self.driver)\
                    .move_to_element(download_btn)\
                    .move_by_offset(rand_x, rand_y)\
                    .pause(random.uniform(0.3, 0.7))\
                    .move_to_element(download_btn)\
                    .pause(random.uniform(0.2, 0.5))\
                    .perform()
                print("Mouse movement completed")
            except:
                print("Mouse movement skipped (fallback)")

            time.sleep(random.uniform(0.2, 0.6))

            # -----------------------------------------
            # HUMAN-LIKE CLICK SEQUENCE
            # -----------------------------------------

            print("Performing human-like click sequence...")
            
            # FIRST: Hover over the button
            try:
                ActionChains(self.driver).move_to_element(download_btn).pause(random.uniform(0.3, 0.7)).perform()
                time.sleep(random.uniform(0.2, 0.5))
                print("Hover completed")
            except Exception as e:
                print(f"Hover failed: {e}")
            
            # SECOND: Multiple click attempts with human-like patterns
            click_success = False
            
            click_methods = [
                {
                    "name": "ActionChains with natural delay",
                    "func": lambda: ActionChains(self.driver)
                        .move_to_element(download_btn)
                        .pause(random.uniform(0.2, 0.5))
                        .click()
                        .pause(random.uniform(0.1, 0.3))
                        .perform()
                },
                {
                    "name": "ActionChains with double-click simulation",
                    "func": lambda: ActionChains(self.driver)
                        .move_to_element(download_btn)
                        .pause(random.uniform(0.1, 0.3))
                        .click()
                        .pause(random.uniform(0.05, 0.15))
                        .click()
                        .pause(random.uniform(0.1, 0.3))
                        .perform()
                },
                {
                    "name": "Normal click with random delay",
                    "func": lambda: (time.sleep(random.uniform(0.1, 0.3)), download_btn.click(), time.sleep(random.uniform(0.1, 0.3)))
                },
                {
                    "name": "Human_click with random offset",
                    "func": lambda: self.human_click(download_btn)
                },
            ]
            
            # Randomize the order of methods
            random.shuffle(click_methods)
            
            for method in click_methods:
                if click_success:
                    break
                try:
                    print(f"Trying click method: {method['name']}")
                    method['func']()
                    print(f"Click method successful: {method['name']}")
                    click_success = True
                    time.sleep(random.uniform(0.2, 0.8))
                    break
                except Exception as e:
                    print(f"Click method failed: {e}")
                    time.sleep(random.uniform(0.1, 0.3))
                    continue
            
            if not click_success:
                try:
                    print("Attempting final fallback: JavaScript click")
                    self.driver.execute_script("""
                        var element = arguments[0];
                        element.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
                        setTimeout(function() {
                            element.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
                            element.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                            element.click();
                        }, 150);
                        return true;
                    """, download_btn)
                    print("JavaScript click with timeout succeeded")
                    click_success = True
                    time.sleep(random.uniform(0.5, 1.0))
                except Exception as e:
                    print(f"Final fallback failed: {e}")

            if not click_success:
                raise Exception("Could not click download button after all attempts.")

            print("Download button clicked - waiting for PDF...")
            time.sleep(random.uniform(1.0, 2.0))

            # -----------------------------------------
            # CHECK FOR NEW WINDOWS/TABS
            # -----------------------------------------

            time.sleep(3)
            original_window = self.driver.current_window_handle
            all_windows = self.driver.window_handles
            
            if len(all_windows) > 1:
                print(f"Download opened in a new window/tab! Found {len(all_windows)} windows/tabs.")
                for window_handle in all_windows:
                    if window_handle != original_window:
                        self.driver.switch_to.window(window_handle)
                        print("Switched to new tab/window")
                        time.sleep(3)
                        
                        try:
                            new_download = self.driver.find_element(By.XPATH, "//a[contains(@href, '.pdf') or contains(@download, '')]")
                            new_download.click()
                            print("Clicked download link in new tab")
                            time.sleep(5)
                        except:
                            try:
                                new_download = self.driver.find_element(By.XPATH, "//button[contains(@title, 'Download') or contains(@aria-label, 'Download')]")
                                new_download.click()
                                print("Clicked download button in new tab")
                                time.sleep(5)
                            except:
                                print("No download link found in new tab - checking if PDF is displayed directly")
                                try:
                                    pdf_object = self.driver.find_element(By.XPATH, "//embed[contains(@src, '.pdf')] | //object[contains(@data, '.pdf')] | //iframe[contains(@src, '.pdf')]")
                                    pdf_src = pdf_object.get_attribute('src') or pdf_object.get_attribute('data')
                                    if pdf_src:
                                        print(f"PDF displayed directly in new tab: {pdf_src}")
                                        self.driver.get(pdf_src)
                                        print("Navigated to PDF URL - should download")
                                        time.sleep(5)
                                except:
                                    pass
                        
                        self.driver.close()
                        self.driver.switch_to.window(original_window)
                        print("Closed new tab/window")
                        break

            # -----------------------------------------
            # WAIT FOR EC PDF DOWNLOAD
            # -----------------------------------------

            print(f"\nDownload directory: {DOWNLOAD_DIR}")
            print("Waiting for EC PDF download...")

            timeout = 180
            start = time.time()
            pdf_downloaded = False
            retry_click_count = 0
            progress_messages = [
                "Download is initializing...",
                "Preparing file for download...",
                "Transferring data...",
                "Download in progress...",
            ]
            msg_index = 0
            
            time.sleep(random.uniform(0.5, 1.5))

            while time.time() - start < timeout:
                pdf = latest_file(
                    DOWNLOAD_DIR,
                    ("*.pdf",)
                )

                downloading = glob(
                    os.path.join(
                        DOWNLOAD_DIR,
                        "*.crdownload"
                    )
                )

                if pdf and not downloading:
                    print("\n" + "="*60)
                    print("EC PDF DOWNLOADED SUCCESSFULLY!")
                    print("="*60)
                    print(f"File: {os.path.basename(pdf)}")
                    print(f"Location: {os.path.dirname(pdf)}")
                    print(f"Full path: {pdf}")
                    print("="*60)
                    pdf_downloaded = True
                    break
                elif downloading:
                    if msg_index < len(progress_messages):
                        print(f"{progress_messages[msg_index]} ({len(downloading)} .crdownload files)")
                        msg_index += 1
                    else:
                        print(f"Download in progress... ({len(downloading)} .crdownload files)")
                else:
                    elapsed = time.time() - start
                    retry_threshold = random.randint(55, 75)
                    if elapsed > retry_threshold and retry_click_count < 2 and not downloading:
                        print(f"No download detected after {int(elapsed)}s - retrying click with human-like interaction...")
                        try:
                            ActionChains(self.driver)\
                                .move_to_element(download_btn)\
                                .pause(random.uniform(0.3, 0.6))\
                                .click()\
                                .pause(random.uniform(0.2, 0.4))\
                                .perform()
                            print(f"Retry click {retry_click_count + 1} done")
                            retry_click_count += 1
                            
                            time.sleep(random.uniform(1, 3))
                            
                            all_windows = self.driver.window_handles
                            if len(all_windows) > 1:
                                print("Retry opened a new window/tab!")
                                for window_handle in all_windows:
                                    if window_handle != original_window:
                                        self.driver.switch_to.window(window_handle)
                                        try:
                                            new_download = self.driver.find_element(By.XPATH, "//a[contains(@href, '.pdf') or contains(@download, '')]")
                                            new_download.click()
                                            print("Clicked download link in new tab from retry")
                                            time.sleep(random.uniform(3, 5))
                                        except:
                                            pass
                                        self.driver.close()
                                        self.driver.switch_to.window(original_window)
                                        print("Closed new tab/window")
                                        break
                        except Exception as e:
                            print(f"Retry click failed: {e}")
                    else:
                        if elapsed < 30:
                            print("Waiting for download to start...")
                        elif elapsed < 60:
                            print("Download should start soon...")
                        else:
                            if elapsed % 10 < 2:
                                print(f"Still waiting... ({int(elapsed)}s elapsed)")

                time.sleep(random.uniform(1.5, 3.5))

            if not pdf_downloaded:
                pdf = latest_file(DOWNLOAD_DIR, ("*.pdf",))
                if pdf:
                    print(f"EC PDF found: {pdf}")
                    pdf_downloaded = True
                else:
                    print("\n" + "="*60)
                    print("Checking if download opened in new tab/window...")
                    print("="*60)
                    
                    time.sleep(5)
                    
                    original_window = self.driver.current_window_handle
                    all_windows = self.driver.window_handles
                    
                    if len(all_windows) > 1:
                        print(f"Found {len(all_windows)} windows/tabs. Looking for PDF in new tab...")
                        for window_handle in all_windows:
                            if window_handle != original_window:
                                self.driver.switch_to.window(window_handle)
                                time.sleep(3)
                                
                                try:
                                    new_download_btn = self.driver.find_element(By.XPATH, "//a[contains(@href, '.pdf') or contains(@download, '')]")
                                    new_download_btn.click()
                                    print("Clicked download link in new tab")
                                    time.sleep(5)
                                except:
                                    pass
                                
                                self.driver.close()
                                self.driver.switch_to.window(original_window)
                                print("Closed new tab/window")
                                
                                pdf = latest_file(DOWNLOAD_DIR, ("*.pdf",))
                                if pdf:
                                    print(f"PDF found: {pdf}")
                                    pdf_downloaded = True
                                    break
                    
                    if not pdf_downloaded:
                        print("\n" + "="*60)
                        print("MANUAL STEP: Download didn't start automatically.")
                        print("Please manually click the Download button in the browser.")
                        print("="*60)
                        input("Press ENTER after you've clicked Download...")
                        
                        print("Waiting for download to complete...")
                        time.sleep(30)
                        
                        pdf = latest_file(DOWNLOAD_DIR, ("*.pdf",))
                        if pdf:
                            print(f"PDF found after manual download: {pdf}")
                            pdf_downloaded = True
                        else:
                            raise Exception("EC PDF download not detected even after manual click.")

            # Open the download folder
            try:
                subprocess.Popen(f'explorer "{DOWNLOAD_DIR}"')
                print(f"\nOpening download folder: {DOWNLOAD_DIR}")
            except:
                pass

            print("\n" + "="*60)
            print("AUTOMATION COMPLETED SUCCESSFULLY!")
            print("="*60)

        except Exception as e:
            print("SEARCH ERROR:")
            print(e)
            raise

    # ---------------------------------------------------
    # CLOSE
    # ---------------------------------------------------
    def close(self):

        try:
            self.driver.quit()
        except OSError:
            pass


def run_ec_search(args):
    bot = KaveriBot()
    try:
        bot.open_site()
        
        time.sleep(3)
        
        USERNAME = "pradhyumna.nov2004@gmail.com"  # Replace with your Kaveri username
        PASSWORD = "OKjrjN9VZH"  # Replace with your Kaveri password

        bot.login(
            USERNAME,
            PASSWORD,
            captcha_wait=args.captcha_wait
        )
        
        print("Waiting for dashboard to load...")
        time.sleep(5)
        
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

    ec.add_argument("--captcha-wait", type=int, default=180)

    args = parser.parse_args()

    if args.command == "ec-search":
        run_ec_search(args)


if __name__ == "__main__":
    main()