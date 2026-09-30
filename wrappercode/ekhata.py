# ekhata.py — GBA Bengaluru e-Khata Download (Dynamic, No Login) v13
# pip install selenium

import argparse
import glob
import os
import time
import base64
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


PORTAL_URL = "https://bbmpeaasthi.karnataka.gov.in/"


class DynamicEKhataBot:
    def __init__(self):
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        self.download_dir = os.path.join(BASE_DIR, "input", "ekhata")
        os.makedirs(self.download_dir, exist_ok=True)
        self.clear_old_downloads()

        options = webdriver.ChromeOptions()
        prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": False,
            "profile.default_content_settings.popups": 0,
        }
        options.add_experimental_option("prefs", prefs)
        options.add_argument("--start-maximized")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 30)

    def clear_old_downloads(self):
        for pat in ("*.pdf", "*.crdownload", "*.tmp"):
            for f in glob.glob(os.path.join(self.download_dir, pat)):
                try: os.remove(f)
                except: pass

    # ============================================================
    # MAIN FLOW
    # ============================================================
    def run(self, search_value, search_type=None):
        try:
            print(f"\n{'='*64}")
            print(f"🏙️  GBA e-KHATA DOWNLOAD (Dynamic, No Login)")
            print(f"{'='*64}")
            print(f"Search Value : {search_value}")
            print(f"Search Type  : {search_type or 'auto-detect'}")
            print(f"{'='*64}\n")

            self.driver.get(PORTAL_URL)
            print("✅ Portal opened")
            self.wait_for_page_ready(timeout=30)
            time.sleep(6)
            self.switch_to_english()
            time.sleep(3)

            print("🔍 Detecting the search card...")
            if not self.click_search_card_dynamic():
                return None
            time.sleep(5)

            if not self.wait_for_search_form(timeout=20):
                return None

            chosen_type = self.select_search_radio_dynamic(search_type)
            if not chosen_type:
                print("❌ Could not select a search type radio.")
                return None
            print(f"   ✅ Search mode: {chosen_type}")
            time.sleep(2)

            if not self.fill_search_input(search_value):
                return None
            time.sleep(1)

            if not self.click_search_submit():
                return None

            # ⭐ NEW: confirm the page actually navigated to results
            if not self.confirm_search_was_submitted(timeout=15):
                print("⚠️ Search click didn't navigate. Trying Enter key on input...")
                self.press_enter_on_input()
                time.sleep(5)
                if not self.confirm_search_was_submitted(timeout=15):
                    print("❌ Search never navigated. Debug dumped.")
                    self.dump_all_buttons()
                    self.dump_page_text("search_stuck")
                    self.save_debug_snapshot(search_value, "search_stuck")
                    return None

            if not self.wait_for_any_results_table(timeout=25):
                self.dump_page_text("results_missing")
                return None
            self.save_debug_snapshot(search_value, "results_loaded")

            blob_before = self.get_all_blob_urls()
            wins_before = set(self.driver.window_handles)
            print(f"   📸 Pre-click: {len(blob_before)} blob(s), {len(wins_before)} window(s)")

            if not self.click_download_in_row(search_value):
                print("❌ Could not click download action.")
                self.dump_row_elements(search_value)
                return None

            print("✅ Download clicked. Waiting for PDF...")
            return self.grab_pdf(search_value, blob_before, wins_before)

        except Exception as e:
            print(f"❌ Error: {e}")
            return None
        finally:
            try: self.driver.quit()
            except: pass
            print("\n🔒 Browser closed")

    # ============================================================
    # HOMEPAGE
    # ============================================================
    def click_search_card_dynamic(self):
        result = self.driver.execute_script("""
            var strongKeys = ['ward', 'ekhata', 'khata', 'property', 'search', 'complete'];
            var weakKeys   = ['know', 'download', 'view'];
            var badKeys    = ['new khata', 'bifurcation', 'amalgamation', 'mutation',
                              'grievance', 'faq', 'video', 'login', 'helpline',
                              'pendency', 'withdraw', 'inheritance', 'bylaw',
                              'correction', 'bhoomi', 'layout'];

            function isVisible(el) {
                if (!el) return false;
                var r = el.getBoundingClientRect();
                if (r.width < 10 || r.height < 10) return false;
                var st = window.getComputedStyle(el);
                return st.visibility !== 'hidden' && st.display !== 'none';
            }

            var roots = [];
            var all = document.querySelectorAll('*');
            for (var i = 0; i < all.length; i++) {
                var el = all[i];
                if (!isVisible(el)) continue;
                var cls = String(el.className || '').toLowerCase();
                if (cls.indexOf('card') !== -1 || cls.indexOf('group') !== -1 ||
                    (cls.indexOf('rounded') !== -1 && cls.indexOf('shadow') !== -1)) {
                    var t = (el.innerText || '').trim();
                    if (t.length > 5 && t.length < 300) {
                        roots.push({ el: el, text: t });
                    }
                }
            }

            if (roots.length === 0) {
                var hs = document.querySelectorAll('h1,h2,h3,h4');
                for (var i = 0; i < hs.length; i++) {
                    if (isVisible(hs[i])) {
                        roots.push({ el: hs[i], text: (hs[i].innerText || '').trim() });
                    }
                }
            }

            var best = null;
            for (var i = 0; i < roots.length; i++) {
                var t = roots[i].text.toLowerCase();
                var score = 0;
                for (var k = 0; k < strongKeys.length; k++)
                    if (t.indexOf(strongKeys[k]) !== -1) score += 10;
                for (var k = 0; k < weakKeys.length; k++)
                    if (t.indexOf(weakKeys[k]) !== -1) score += 3;
                for (var k = 0; k < badKeys.length; k++)
                    if (t.indexOf(badKeys[k]) !== -1) score -= 20;
                if (t.indexOf('click here') !== -1) score += 8;
                if (!best || score > best.score) {
                    best = { el: roots[i].el, text: roots[i].text, score: score };
                }
            }

            if (!best || best.score <= 0) return { status: 'no_match' };

            best.el.scrollIntoView({block: 'center'});
            try { best.el.click(); } catch(e) {}
            try {
                var o = {bubbles: true, cancelable: true, view: window};
                best.el.dispatchEvent(new MouseEvent('mousedown', o));
                best.el.dispatchEvent(new MouseEvent('mouseup', o));
                best.el.dispatchEvent(new MouseEvent('click', o));
            } catch(e) {}

            return {
                status: 'clicked',
                score: best.score,
                text: best.text.substring(0, 80),
                tag: best.el.tagName
            };
        """)

        print(f"   → Card detection result: {result}")
        if result and result.get("status") == "clicked":
            print(f"      Chose: '{result['text'][:50]}...' (score={result['score']})")
            return True
        return False

    # ============================================================
    # SEARCH FORM
    # ============================================================
    def wait_for_search_form(self, timeout=20):
        print("   ⏳ Waiting for search form...")
        end = time.time() + timeout
        while time.time() < end:
            try:
                ready = self.driver.execute_script("""
                    var text = (document.body.innerText || '').toLowerCase();
                    var hasSearchHeading = text.indexOf('search') !== -1 &&
                                           text.indexOf('property') !== -1;
                    var inputs = document.querySelectorAll('input[type=text], input:not([type])');
                    var hasInput = false;
                    for (var i = 0; i < inputs.length; i++) {
                        var r = inputs[i].getBoundingClientRect();
                        if (r.width > 40 && r.height > 10) { hasInput = true; break; }
                    }
                    return hasSearchHeading && hasInput;
                """)
                if ready:
                    print("   ✅ Search form detected")
                    return True
            except: pass
            time.sleep(1)
        return False

    def select_search_radio_dynamic(self, preferred=None):
        pref_map = {
            "epid":  ["epid", "e-pid", "property id"],
            "sas":   ["sas", "tax id"],
            "ward":  ["ward"],
            "owner": ["owner"],
        }
        pref_keys = pref_map.get((preferred or "epid").lower(), ["epid"])

        result = self.driver.execute_script("""
            var prefKeys = arguments[0];
            function isVisible(el) {
                if (!el) return false;
                var r = el.getBoundingClientRect();
                if (r.width < 3 || r.height < 3) return false;
                var st = window.getComputedStyle(el);
                return st.visibility !== 'hidden' && st.display !== 'none';
            }
            var radios = document.querySelectorAll('input[type=radio]');
            var items = [];
            for (var i = 0; i < radios.length; i++) {
                var r = radios[i];
                var labelText = '';
                if (r.id) {
                    var lab = document.querySelector('label[for="' + r.id + '"]');
                    if (lab) labelText = (lab.innerText || '').trim();
                }
                if (!labelText) {
                    var p = r.closest('label');
                    if (p) labelText = (p.innerText || '').trim();
                }
                if (!labelText && r.parentElement) {
                    labelText = (r.parentElement.innerText || '').trim();
                }
                if (!isVisible(r) && !labelText) continue;
                items.push({ radio: r, label: labelText, name: r.name });
            }
            if (items.length === 0) return { status: 'no_radios' };

            var best = null;
            for (var i = 0; i < items.length; i++) {
                var t = items[i].label.toLowerCase();
                var score = 0;
                for (var k = 0; k < prefKeys.length; k++) {
                    if (t.indexOf(prefKeys[k]) !== -1) score += 100 - k * 10;
                }
                score -= t.length * 0.05;
                if (!best || score > best.score) best = { item: items[i], score: score };
            }
            var chosen = (best && best.score > 1) ? best.item : items[0];
            try { chosen.radio.scrollIntoView({block: 'center'}); } catch(e) {}
            try { chosen.radio.click(); } catch(e) {}
            try {
                var o = {bubbles: true, cancelable: true, view: window};
                chosen.radio.dispatchEvent(new MouseEvent('mousedown', o));
                chosen.radio.dispatchEvent(new MouseEvent('mouseup', o));
                chosen.radio.dispatchEvent(new MouseEvent('click', o));
                chosen.radio.dispatchEvent(new Event('change', {bubbles: true}));
            } catch(e) {}
            if (chosen.label && chosen.radio.id) {
                var lab = document.querySelector('label[for="' + chosen.radio.id + '"]');
                if (lab) { try { lab.click(); } catch(e) {} }
            }
            return { status: 'clicked', label: chosen.label, name: chosen.name, score: best ? best.score : 0 };
        """, pref_keys)

        print(f"   → Radio auto-select: {result}")
        if result and result.get("status") == "clicked":
            return result.get("label", "unknown")
        return None

    def fill_search_input(self, value):
        """Find the input and fill it with real key events for Angular."""
        found = self.driver.execute_script("""
            function isVisible(el) {
                if (!el) return false;
                var r = el.getBoundingClientRect();
                if (r.width < 60 || r.height < 15) return false;
                var st = window.getComputedStyle(el);
                return st.visibility !== 'hidden' && st.display !== 'none';
            }
            var inputs = document.querySelectorAll('input');
            for (var i = 0; i < inputs.length; i++) {
                var el = inputs[i];
                if (!isVisible(el)) continue;
                var type = (el.type || 'text').toLowerCase();
                if (type !== 'text' && type !== 'search' && type !== '') continue;
                if (el.readOnly || el.disabled) continue;
                var ph = (el.placeholder || '').toLowerCase();
                if (ph.indexOf('search for services') !== -1) continue;
                if (ph.indexOf('epid') !== -1 || ph.indexOf('sas') !== -1 ||
                    ph.indexOf('ward') !== -1 || ph.indexOf('owner') !== -1 ||
                    ph.indexOf('property') !== -1 || ph.indexOf('enter') !== -1) {
                    el.setAttribute('data-ekhata-target', '1');
                    return { status: 'found', placeholder: el.placeholder || '' };
                }
            }
            return { status: 'no_input' };
        """)
        print(f"   → Input detection: {found}")
        if not found or found.get("status") != "found":
            return False

        try:
            inp = self.driver.find_element(By.CSS_SELECTOR, "input[data-ekhata-target='1']")
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
            time.sleep(0.3)
            inp.click()
            time.sleep(0.3)
            inp.clear()
            time.sleep(0.2)
            inp.send_keys(str(value))
            time.sleep(0.4)
            actual = inp.get_attribute("value") or ""
            if str(value) in actual:
                print(f"   ✅ Entered: '{actual}'")
                return True
        except Exception as e:
            print(f"   ⚠️ send_keys failed: {e}")

        try:
            result = self.driver.execute_script("""
                var el = document.querySelector('input[data-ekhata-target="1"]');
                if (!el) return { status: 'gone' };
                var value = arguments[0];
                el.focus();
                el.value = value;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true}));
                return { status: 'filled', value: el.value };
            """, value)
            print(f"   → JS fill: {result}")
            return result and result.get("status") == "filled"
        except: return False

    # ============================================================
    # ⭐ SEARCH SUBMIT — BULLETPROOF
    # ============================================================
    def click_search_submit(self):
        """
        Find the exact 'Search' button. Strategies in order:
        1. XPath: button with exact text 'Search' that comes AFTER the input
        2. XPath: any button with exact text 'Search'
        3. Position-based: button below the input whose text = 'Search'
        4. JS: score buttons, penalize 'property'/'khata' heavily
        """
        # Ensure our input is marked
        has_marker = self.driver.execute_script(
            "return !!document.querySelector('input[data-ekhata-target=\"1\"]')"
        )
        if not has_marker:
            # Mark it again
            self.driver.execute_script("""
                var inputs = document.querySelectorAll('input');
                for (var i = 0; i < inputs.length; i++) {
                    var el = inputs[i];
                    var ph = (el.placeholder || '').toLowerCase();
                    if (ph.indexOf('search for services') !== -1) continue;
                    var r = el.getBoundingClientRect();
                    if (r.width < 60 || r.height < 15) continue;
                    if (ph.indexOf('epid') !== -1 || ph.indexOf('sas') !== -1 ||
                        ph.indexOf('ward') !== -1 || ph.indexOf('owner') !== -1 ||
                        ph.indexOf('property') !== -1 || ph.indexOf('enter') !== -1) {
                        el.setAttribute('data-ekhata-target', '1');
                        return;
                    }
                }
            """)

        # Strategy 1: exact text 'Search' button that FOLLOWS the input
        try:
            btn = self.driver.find_element(
                By.XPATH,
                "//input[@data-ekhata-target='1']/following::button[normalize-space(.)='Search'][1]"
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", btn)
            print("   ✅ Search clicked (Strategy 1: exact 'Search' after input)")
            return True
        except Exception as e:
            print(f"   Strategy 1 failed: {str(e)[:80]}")

        # Strategy 2: exact text 'Search' anywhere
        try:
            btns = self.driver.find_elements(
                By.XPATH, "//button[normalize-space(.)='Search']"
            )
            for b in btns:
                if b.is_displayed():
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                    time.sleep(1)
                    self.driver.execute_script("arguments[0].click();", b)
                    print("   ✅ Search clicked (Strategy 2: exact 'Search')")
                    return True
        except Exception as e:
            print(f"   Strategy 2 failed: {str(e)[:80]}")

        # Strategy 3: position-based — button just below the input
        try:
            btn = self.driver.execute_script("""
                var input = document.querySelector('input[data-ekhata-target="1"]');
                if (!input) return null;
                var ir = input.getBoundingClientRect();
                var btns = document.querySelectorAll('button');
                var best = null;
                for (var i = 0; i < btns.length; i++) {
                    var b = btns[i];
                    if (b.offsetParent === null) continue;
                    var t = (b.innerText || '').trim().toLowerCase();
                    if (t !== 'search') continue;
                    var br = b.getBoundingClientRect();
                    // Button must be below or in the same row as the input
                    if (br.top < ir.top - 20) continue;
                    var dist = Math.abs(br.top - ir.bottom) + Math.abs(br.left - ir.left);
                    if (!best || dist < best.dist) best = { el: b, dist: dist };
                }
                if (best) {
                    best.el.scrollIntoView({block: 'center'});
                    best.el.click();
                    return 'clicked|' + best.dist;
                }
                return null;
            """)
            if btn:
                print(f"   ✅ Search clicked (Strategy 3: position-based)")
                return True
        except Exception as e:
            print(f"   Strategy 3 failed: {str(e)[:80]}")

        # Strategy 4: JS scoring with strict rules
        try:
            result = self.driver.execute_script("""
                function isVisible(el) {
                    if (!el) return false;
                    var r = el.getBoundingClientRect();
                    if (r.width < 15 || r.height < 15) return false;
                    return el.offsetParent !== null;
                }
                var btns = document.querySelectorAll('button');
                var best = null;
                for (var i = 0; i < btns.length; i++) {
                    var b = btns[i];
                    if (!isVisible(b)) continue;
                    var t = (b.innerText || '').trim().toLowerCase();
                    if (t.length === 0 || t.length > 25) continue;
                    // HARD SKIP nav-like
                    if (t.indexOf('property') !== -1) continue;
                    if (t.indexOf('khata') !== -1) continue;
                    if (t.indexOf('guidelines') !== -1) continue;
                    if (t.indexOf('home') !== -1) continue;
                    if (t.indexOf('menu') !== -1) continue;

                    var score = 0;
                    if (t === 'search') score += 200;
                    if (t === 'submit') score += 150;
                    if (t === 'go' || t === 'find') score += 100;

                    var cls = String(b.className || '').toLowerCase();
                    if (cls.indexOf('green') !== -1) score += 20;
                    if (cls.indexOf('primary') !== -1) score += 10;

                    if (!best || score > best.score) best = { el: b, score: score, text: t };
                }
                if (!best || best.score <= 0) return null;
                best.el.scrollIntoView({block: 'center'});
                try { best.el.click(); } catch(e) {}
                try {
                    var o = {bubbles: true, cancelable: true, view: window};
                    best.el.dispatchEvent(new MouseEvent('mousedown', o));
                    best.el.dispatchEvent(new MouseEvent('mouseup', o));
                    best.el.dispatchEvent(new MouseEvent('click', o));
                } catch(e) {}
                return 'clicked|' + best.text + '|score=' + best.score;
            """)
            if result:
                print(f"   ✅ Search clicked (Strategy 4: {result})")
                return True
        except Exception as e:
            print(f"   Strategy 4 failed: {str(e)[:80]}")

        print("   ❌ All search-button strategies failed")
        self.dump_all_buttons()
        return False

    def confirm_search_was_submitted(self, timeout=15):
        """Detect whether the page changed to show search results."""
        end = time.time() + timeout
        while time.time() < end:
            try:
                ok = self.driver.execute_script("""
                    // Search results page has a table with 'DOWNLOAD EKHATA'
                    // or the 'Search Property' heading is still shown with
                    // a results table
                    var headers = document.querySelectorAll('th');
                    for (var i = 0; i < headers.length; i++) {
                        var t = (headers[i].innerText || '').toLowerCase();
                        if (t.indexOf('download') !== -1 && t.indexOf('ekhata') !== -1)
                            return true;
                    }
                    return false;
                """)
                if ok:
                    print("   ✅ Search submitted (results table visible)")
                    return True
            except: pass
            time.sleep(1)
        return False

    def press_enter_on_input(self):
        try:
            inp = self.driver.find_element(By.CSS_SELECTOR, "input[data-ekhata-target='1']")
            inp.click()
            time.sleep(0.5)
            inp.send_keys(Keys.ENTER)
            print("   ⌨️ Pressed Enter on input")
        except Exception as e:
            print(f"   ⚠️ Enter press failed: {e}")

    def dump_all_buttons(self):
        print("\n🔎 ALL visible buttons on the page:")
        try:
            btns = self.driver.find_elements(By.XPATH, "//button")
            for b in btns:
                try:
                    if not b.is_displayed(): continue
                    txt = (b.text or "").strip()[:50]
                    cls = (b.get_attribute("class") or "")[:70]
                    r = b.rect
                    print(f"   <button> '{txt}' pos=({r['x']},{r['y']}) class='{cls}'")
                except: continue
        except: pass

    # ============================================================
    # RESULTS TABLE
    # ============================================================
    def wait_for_any_results_table(self, timeout=25):
        print("   ⏳ Waiting for results table...")
        end = time.time() + timeout
        while time.time() < end:
            try:
                ready = self.driver.execute_script("""
                    var tables = document.querySelectorAll('table');
                    for (var t = 0; t < tables.length; t++) {
                        var tbl = tables[t];
                        var rows = tbl.querySelectorAll('tbody tr');
                        if (rows.length === 0) continue;
                        var hasHeader = !!tbl.querySelector('thead, th');
                        if (hasHeader && rows.length >= 1) {
                            // Must have > 6 columns (results tables do)
                            var ths = tbl.querySelectorAll('th');
                            if (ths.length >= 6) return true;
                        }
                    }
                    return false;
                """)
                if ready:
                    print("   ✅ Results table detected")
                    return True
            except: pass
            time.sleep(1)
        return False

    def click_download_in_row(self, search_value):
        result = self.driver.execute_script("""
            var value = String(arguments[0]);
            function isVisible(el) {
                if (!el) return false;
                var r = el.getBoundingClientRect();
                if (r.width < 3 || r.height < 3) return false;
                return el.offsetParent !== null;
            }
            var rows = document.querySelectorAll('table tbody tr');
            for (var i = 0; i < rows.length; i++) {
                var row = rows[i];
                var rowText = row.innerText || '';
                if (rowText.indexOf(value) === -1) continue;

                var goodWords = ['ekhata', 'e-khata', 'download', 'view khata',
                                 'get khata', 'pdf', 'print'];
                var badWords = ['apply', 'correction', 'withdraw', 'edit',
                                'submit', 'update', 'delete'];

                var clickables = row.querySelectorAll(
                    'button, a, span[role=button], div[role=button], ' +
                    'span[onclick], div[onclick], [class*="cursor-pointer"]'
                );

                var best = null;
                for (var j = 0; j < clickables.length; j++) {
                    var el = clickables[j];
                    if (!isVisible(el)) continue;
                    var t = (el.innerText || el.textContent || '').trim().toLowerCase();
                    if (t.length === 0 || t.length > 40) continue;

                    var score = 0;
                    for (var k = 0; k < goodWords.length; k++)
                        if (t.indexOf(goodWords[k]) !== -1) score += 10 - k;
                    for (var k = 0; k < badWords.length; k++)
                        if (t.indexOf(badWords[k]) !== -1) score -= 30;

                    if (el.tagName === 'BUTTON' || el.tagName === 'A') score += 2;

                    if (score > 0 && (!best || score > best.score)) {
                        best = { el: el, score: score, text: t };
                    }
                }

                if (!best) {
                    for (var j = clickables.length - 1; j >= 0; j--) {
                        if (isVisible(clickables[j])) {
                            var t2 = (clickables[j].innerText || '').trim();
                            if (t2 && t2.length < 40) {
                                best = { el: clickables[j], score: 1, text: t2.toLowerCase(), fallback: true };
                                break;
                            }
                        }
                    }
                }

                if (!best) return { status: 'no_clickable' };

                best.el.scrollIntoView({block: 'center', inline: 'center'});
                try { best.el.click(); } catch(e) {}
                try {
                    var o = {bubbles: true, cancelable: true, view: window};
                    best.el.dispatchEvent(new MouseEvent('mousedown', o));
                    best.el.dispatchEvent(new MouseEvent('mouseup', o));
                    best.el.dispatchEvent(new MouseEvent('click', o));
                } catch(e) {}

                return {
                    status: 'clicked',
                    text: best.text,
                    tag: best.el.tagName,
                    score: best.score,
                    fallback: !!best.fallback
                };
            }
            return { status: 'no_row' };
        """, search_value)

        print(f"   → Row download click: {result}")
        return result and result.get("status") == "clicked"

    def dump_row_elements(self, search_value):
        try:
            rows = self.driver.find_elements(By.XPATH, "//table//tbody//tr")
            for row in rows:
                if search_value not in (row.text or ""): continue
                print(f"\n🔎 Elements in row for '{search_value}':")
                for e in row.find_elements(By.XPATH, ".//*"):
                    try:
                        txt = (e.text or "").strip()[:40]
                        cls = (e.get_attribute("class") or "")[:60]
                        role = e.get_attribute("role") or ""
                        if e.is_displayed() and (txt or role):
                            print(f"   <{e.tag_name}> '{txt}' class='{cls}' role='{role}'")
                    except: continue
                break
        except: pass

    # ============================================================
    # PDF GRABBING
    # ============================================================
    def get_all_blob_urls(self):
        try:
            return self.driver.execute_script("""
                var out = [], seen = {};
                function add(u) {
                    if (u && u.indexOf('blob:') === 0 && !seen[u]) { seen[u] = 1; out.push(u); }
                }
                document.querySelectorAll('iframe').forEach(function(f){ add(f.src); });
                document.querySelectorAll('embed,object').forEach(function(e){ add(e.src || e.data); });
                document.querySelectorAll('a[href^="blob:"]').forEach(function(a){ add(a.href); });
                return out;
            """) or []
        except: return []

    def wait_for_new_blob(self, blob_before, timeout=45, poll=2):
        print(f"   ⏳ Polling up to {timeout}s for new blob...")
        start = time.time()
        before = set(blob_before or [])
        while time.time() - start < timeout:
            try:
                current = self.get_all_blob_urls()
                new = [u for u in current if u not in before]
                if new:
                    print(f"   ✅ New blob after {round(time.time()-start,1)}s")
                    return new[-1]
            except: pass
            time.sleep(poll)
        print("   ⚠️ No new blob found.")
        return None

    def grab_pdf(self, search_value, blob_before, wins_before):
        try:
            new_wins = set(self.driver.window_handles) - wins_before
            if new_wins:
                self.driver.switch_to.window(list(new_wins)[0])
                print("   🔄 Switched to new tab")
                time.sleep(4)
        except: pass

        blob_url = self.wait_for_new_blob(blob_before, timeout=45)

        if not blob_url:
            for w in self.driver.window_handles:
                try:
                    self.driver.switch_to.window(w)
                    blob_url = self.wait_for_new_blob(blob_before, timeout=5)
                    if blob_url: break
                except: continue

        if not blob_url:
            print("   ℹ️ No blob — checking for auto-download…")
            time.sleep(5)
            pdfs = glob.glob(os.path.join(self.download_dir, "*.pdf"))
            if pdfs: return self.rename_file(max(pdfs, key=os.path.getmtime), search_value)
            self.save_debug_snapshot(search_value, "no_blob")
            return None

        print("   📥 Native blob download…")
        if self.trigger_native_download(blob_url, search_value):
            time.sleep(4)
            pdfs = glob.glob(os.path.join(self.download_dir, "*.pdf"))
            if pdfs: return self.rename_file(max(pdfs, key=os.path.getmtime), search_value)

        print("   📥 Fallback fetch…")
        return self.fetch_blob_and_save(blob_url, search_value)

    def trigger_native_download(self, blob_url, search_value):
        try:
            filename = self._make_filename(search_value)
            r = self.driver.execute_script("""
                var url = arguments[0], name = arguments[1];
                try {
                    var a = document.createElement('a');
                    a.href = url;
                    a.download = name;
                    a.style.display = 'none';
                    a.rel = 'noopener';
                    document.body.appendChild(a);
                    a.click();
                    setTimeout(function(){ try { document.body.removeChild(a); } catch(e){} }, 2000);
                    return 'ok';
                } catch (e) { return 'err:' + e.message; }
            """, blob_url, filename)
            return r == 'ok'
        except: return False

    def fetch_blob_and_save(self, blob_url, search_value):
        try:
            result = self.driver.execute_async_script("""
                var url = arguments[0], cb = arguments[arguments.length - 1];
                fetch(url).then(function(r) {
                    if (!r.ok) { cb(null); return; }
                    return r.arrayBuffer();
                }).then(function(b) {
                    if (!b) { cb(null); return; }
                    var by = new Uint8Array(b), bin = '';
                    for (var i = 0; i < by.length; i++) bin += String.fromCharCode(by[i]);
                    cb(btoa(bin));
                }).catch(function() { cb(null); });
            """, blob_url)
            if not result: return None
            data = base64.b64decode(result)
            if len(data) < 1000: return None
            fn = os.path.join(self.download_dir, self._make_filename(search_value))
            with open(fn, "wb") as f: f.write(data)
            print(f"   ✅ PDF saved: {fn}")
            return fn
        except Exception as e:
            print(f"   fetch error: {e}")
            return None

    def _make_filename(self, search_value):
        safe = re.sub(r'[^\w\-]', '_', str(search_value))[:40]
        return f"ekhata_{safe}_{int(time.time())}.pdf"

    def rename_file(self, old_path, search_value):
        new_name = os.path.join(self.download_dir, self._make_filename(search_value))
        try:
            os.rename(old_path, new_name)
            print(f"   ✅ File renamed: {new_name}")
            return new_name
        except: return old_path

    # ============================================================
    # HELPERS
    # ============================================================
    def wait_for_page_ready(self, timeout=30):
        try:
            end = time.time() + timeout
            while time.time() < end:
                if self.driver.execute_script("return document.readyState") == "complete":
                    print("   ✅ readyState: complete")
                    return True
                time.sleep(1)
        except: pass
        return False

    def switch_to_english(self):
        try:
            elems = self.driver.find_elements(
                By.XPATH,
                "//button[normalize-space()='English'] | //a[normalize-space()='English']"
            )
            for e in elems:
                if e.is_displayed():
                    self.driver.execute_script("arguments[0].click();", e)
                    print("   ✅ Switched to English")
                    return True
        except: pass
        return False

    def dump_page_text(self, label=""):
        try:
            t = self.driver.execute_script(
                "return (document.body ? document.body.innerText : '').substring(0,4000);"
            )
            print(f"\n📄 PAGE TEXT ({label}):")
            print("="*64); print(t); print("="*64)
        except: pass

    def save_debug_snapshot(self, search_value, label=""):
        try:
            ts = int(time.time())
            safe = re.sub(r'[^\w\-]', '_', str(search_value))[:40]
            png = os.path.join(self.download_dir, f"debug_{safe}_{ts}.png")
            html = os.path.join(self.download_dir, f"debug_{safe}_{ts}.html")
            self.driver.save_screenshot(png)
            with open(html, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            print(f"   🐞 Snapshot: {os.path.basename(png)}")
        except: pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GBA Bengaluru e-Khata downloader")
    parser.add_argument("--epid", help="Property ePID")
    parser.add_argument("--sas", help="SAS Property Tax ID")
    parser.add_argument("--ward", help="Ward Name or Number")
    parser.add_argument("--owner", help="Owner Name")
    parser.add_argument("--value", help="Generic search value (with --type)")
    parser.add_argument("--type", choices=["epid","sas","ward","owner"])
    args = parser.parse_args()

    if args.epid: sv, st = args.epid, "epid"
    elif args.sas: sv, st = args.sas, "sas"
    elif args.ward: sv, st = args.ward, "ward"
    elif args.owner: sv, st = args.owner, "owner"
    elif args.value and args.type: sv, st = args.value, args.type
    else: parser.error("Provide one of: --epid, --sas, --ward, --owner, or --value + --type")

    bot = DynamicEKhataBot()
    result = bot.run(sv, search_type=st)
    if result:
        print(f"\n{'='*64}")
        print(f"✅ SUCCESS! PDF saved to:\n   {result}")
        print(f"{'='*64}")
    else:
        print("\n❌ Failed to download.")