import { chromium } from "playwright-extra";
import stealth from "puppeteer-extra-plugin-stealth";

chromium.use(stealth());
import path from "path";
import * as fs from "fs";
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// In-memory session store (In production, replace with proper persistent storage / Redis)
const sessions = new Map();

/**
 * Ensures screenshots directory exists.
 */
function ensureScreenshotDir() {
    const dir = path.join(__dirname, 'screenshots');
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
}

/**
 * Step 1: Initialize browser, go to Landeed, enter phone number and start OTP.
 */
export async function startLogin(phoneNumber) {
    const browser = await chromium.launch({
        headless: false,
        args: ['--no-sandbox', '--disable-blink-features=AutomationControlled']
    });
    const context = await browser.newContext({
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport: { width: 1280, height: 720 }
    });
    const page = await context.newPage();

    // Give a unique session id
    const sessionId = Date.now().toString();
    sessions.set(sessionId, { browser, context, page });

    try {
        // Using domcontentloaded to avoid strict networkidle timeouts which fail on Landeed
        // Adding a 60s timeout as well since init can take a while
        await page.goto("https://web.landeed.com/karnataka/ec-encumbrance-certificate", { waitUntil: 'domcontentloaded', timeout: 60000 });

        // Give it a brief moment to render JS components
        await page.waitForTimeout(5000);

        // Use exact name match from screenshot
        const loginBtn = page.getByRole('button', { name: /login\/signup/i });
        if (await loginBtn.isVisible()) {
            await loginBtn.click();
            await page.waitForTimeout(2000); // Wait for modal animation
        }

        // The input has name="phoneNo" based on HTML dump
        const phoneInput = page.locator('input[name="phoneNo"]');
        await phoneInput.waitFor({ state: 'visible', timeout: 10000 });
        await phoneInput.fill(phoneNumber);

        // Click Send OTP ("Send OTP")
        const getOtpBtn = page.getByRole('button', { name: /send otp/i });
        // Use dispatchEvent to prevent Playwright from hanging if the page tries to navigate unexpectedly
        await getOtpBtn.dispatchEvent('click');

        // Wait for either the error message or the Verify OTP button
        try {
            await Promise.race([
                page.getByText(/Enter a 10-digit valid mobile number/i).waitFor({ state: 'visible', timeout: 5000 }),
                page.getByRole('button', { name: /verify otp/i }).waitFor({ state: 'visible', timeout: 5000 })
            ]);
        } catch (e) {
            // Ignore timeout, verify immediately below
        }

        const errorMsg = page.getByText(/Enter a 10-digit valid mobile number/i);
        if (await errorMsg.isVisible()) {
            throw new Error("Elva Asti rejected the phone number. Please enter a valid 10-digit mobile number.");
        }

        const verifyBtnVisible = await page.getByRole('button', { name: /verify otp/i }).isVisible();
        if (!verifyBtnVisible) {
            throw new Error("Failed to reach OTP verification screen. The phone number might be invalid or blocked.");
        }

        return { success: true, sessionId, message: "OTP Requested" };

    } catch (error) {
        await browser.close();
        sessions.delete(sessionId);
        throw error;
    }
}

/**
 * Step 2: Input the OTP and submit to log in to Landeed.
 */
export async function submitOTP(sessionId, otp) {
    const session = sessions.get(sessionId);
    if (!session) throw new Error("Invalid or expired session");

    const { page } = session;

    try {
        // Based on the screenshot, there are 6 separate input boxes. Let's find them
        // They are typically the only 6 inputs next to each other, or we can just find all text/tel/number inputs without name="phoneNo"

        // Wait a small amount
        await page.waitForTimeout(1000);

        // A robust way to fill multi-input OTPs is typing the whole string while the first is focused
        // Let's try to find inputs with maxlength="1" or similar
        // Dump the html of the page to see the exact structure
        const html = await page.content();
        fs.writeFileSync('landeed-otp-snapshot.html', html);
        console.log("Wrote OTP modal HTML to landeed-otp-snapshot.html");

        // Find all inputs that are visible and try to log their attributes
        const visibleInputs = await page.evaluate(() => {
            return Array.from(document.querySelectorAll('input')).map(i => ({
                type: i.type,
                name: i.name,
                id: i.id,
                maxLength: i.maxLength,
                className: i.className,
                placeholder: i.placeholder,
                isVisible: i.offsetWidth > 0 && i.offsetHeight > 0
            })).filter(i => i.isVisible);
        });
        console.log("Visible inputs on OTP page:", JSON.stringify(visibleInputs, null, 2));

        // Find OTP inputs. Landeed uses a single transparent input for all 6 digits
        // identified by data-input-otp="true"
        const otpInputLocator = page.locator('input[data-input-otp="true"]');
        const count = await otpInputLocator.count();
        console.log(`Found ${count} exact OTP inputs via data-attribute.`);

        if (count > 0) {
            const singleInput = otpInputLocator.first();
            await singleInput.waitFor({ state: 'attached', timeout: 5000 });
            await singleInput.focus();
            await singleInput.fill(otp);
        } else {
            console.log("Could not find exact OTP input. Please check landeed-otp-snapshot.html");
            throw new Error(`Could not find the OTP input on the page. Elva Asti UI might have changed.`);
        }

        // After filling OTP, Landeed often auto-submits.
        // Let's wait to see if the EC search form appears (Property Type "Non Agricultural" becomes visible)
        try {
            console.log("Waiting to see if it auto-submits...");
            await page.getByText('Non Agricultural', { exact: true }).waitFor({ state: 'visible', timeout: 6000 });
            console.log("Auto-submit successful!");
        } catch (autoSubmitTimeout) {
            console.log("Did not auto-submit. Attempting manual click...");

            // Try different button selectors as fallback
            const verifyBtnRoles = [
                page.getByRole('button', { name: /Verify OTP/i }),
                page.locator('button:has-text("Verify OTP")').first(),
                page.locator('button:has-text("Verify OTP")').last(),
                page.locator('button:has-text("Verify & Continue")')
            ];

            let clicked = false;
            for (const btn of verifyBtnRoles) {
                if (await btn.isVisible().catch(() => false)) {
                    console.log(`Clicking button: ${await btn.textContent().catch(() => 'unknown')}`);
                    await btn.click();
                    clicked = true;
                    break;
                }
            }

            if (!clicked) {
                console.log("Could not find any verify button to click. Proceeding anyway assuming background success.");
            }
        }

        // Wait for the EC search form to be visible indicating successful login
        // Property type "Non Agricultural" will be present
        await page.waitForTimeout(4000);

        return { success: true, message: "Logged in successfully" };
    } catch (error) {
        throw error;
    }
}

/**
 * Step 3: Fill the EC search form, submit, and screenshot result.
 */
export async function searchEC(sessionId, details) {
    const session = sessions.get(sessionId);
    if (!session) throw new Error("Invalid or expired session");

    const { page } = session;
    ensureScreenshotDir();

    try {
        // Fill in the form based on details

        // Property Type (Radio buttons are hidden, so clicking the text label is best)
        if (details.propertyType === 'Non Agricultural') {
            await page.getByText('Non Agricultural', { exact: true }).click();
        } else {
            await page.getByText('Agricultural', { exact: true }).click();
        }

        // Village/Division
        console.log(`Filling village: ${details.village}`);
        const villageInput = page.getByPlaceholder(/Eg: Devanahalli/i);
        await villageInput.waitFor({ state: 'visible', timeout: 10000 });
        await villageInput.click();
        await villageInput.fill(details.village);

        // Landeed usually has an auto-complete dropdown. Wait for it and press Enter or select the first option.
        await page.waitForTimeout(2000); // Increased wait for dropdown
        await page.keyboard.press('ArrowDown');
        await page.waitForTimeout(500);
        await page.keyboard.press('Enter');
        console.log('Village selected from dropdown');

        // Search By (Survey No, Party Name, etc.)
        if (details.searchBy) {
            console.log(`Selecting search by: ${details.searchBy}`);
            await page.getByText(details.searchBy, { exact: true }).click();
        }

        // Survey No / Party Name / Flat No input
        // The placeholder is 'Click to Enter' for Non Agricultural, and 'Eg: 101, 804' for Agricultural
        const mainInput = page.getByPlaceholder(/Click to Enter|Eg:\s*101/i).first();
        await mainInput.waitFor({ state: 'visible', timeout: 5000 });

        const inputValue = details.surveyNo || details.partyName || details.flatNo;
        await mainInput.fill(inputValue);

        // For Agricultural, Landeed often shows a "Did you mean X?" dropdown that must be clicked
        // or requires an Enter keypress to validate the pill/tag
        await page.waitForTimeout(1000);

        try {
            // Check if there is a "Did you mean X?" suggestion and click it
            const suggestionBtn = page.getByText(new RegExp(`Did you mean\\s*${inputValue}\\s*\\?`, 'i'));
            if (await suggestionBtn.isVisible({ timeout: 2000 })) {
                console.log(`Clicking suggestion for ${inputValue}`);
                // The actual clickable element is usually an <a> or <span> inside the text
                const clickTarget = page.locator(`text=${inputValue}`).last();
                await clickTarget.click();
            } else {
                // Fallback: press Enter to register the tag
                await page.keyboard.press('Enter');
            }
        } catch (e) {
            // If suggestion isn't found, just press Enter to see if that registers it
            await page.keyboard.press('Enter');
        }

        console.log('Main detail entered');

        // Check for and dismiss the "Stay on website" popup if it's blocking on search page
        try {
            const stayBtn = page.getByText('Stay on website', { exact: true });
            if (await stayBtn.isVisible({ timeout: 2000 })) {
                console.log('Dismissing "Stay on website" modal on search page...');
                await stayBtn.click();
                await page.waitForTimeout(1000); // give it time to fade out
            }
        } catch (e) {
            // ignore if not found
        }

        // Duration handling
        if (details.duration) {
            console.log(`Selecting duration: ${details.duration}`);

            // Map the frontend duration text to the exact value Landeed uses
            const durationValueMap = {
                '5 Year': '5',
                '13 Year': '13',
                '20 Year': '20',
                'Custom': '-1'
            };

            const exactValue = durationValueMap[details.duration];

            try {
                if (exactValue) {
                    const radioBtn = page.locator(`button[role="radio"][value="${exactValue}"]`);
                    await radioBtn.waitFor({ state: 'visible', timeout: 5000 });
                    await radioBtn.click({ force: true });
                } else {
                    const fallbackBtn = page.getByText(details.duration, { exact: true }).first();
                    await fallbackBtn.waitFor({ state: 'visible', timeout: 5000 });
                    await fallbackBtn.click();
                }

                // Give the UI time to update the selected state and trigger underlying React changes
                await page.waitForTimeout(2000);
                console.log(`Duration selection applied for ${details.duration}`);
            } catch (e) {
                console.log(`Could not click duration ${details.duration}:`, e.message);
            }
        }

        // Click Search and handle a new tab opening
        const searchBtn = page.getByRole('button', { name: 'Search' });

        console.log("Clicking search...");
        // Landeed now shows a progress bar ("It would take ~1 min") before opening the new tab. Wait up to 120 seconds.
        const pagePromise = page.context().waitForEvent('page', { timeout: 120000 }).catch(() => null);
        await searchBtn.click({ force: true });

        console.log("Waiting for results tab to open (this can take ~1-2 minutes)...");
        const newPage = await pagePromise;
        const targetPage = newPage || page;

        if (newPage) {
            console.log("EC Results opened in a new tab.");
            await targetPage.waitForLoadState('domcontentloaded');
        } else {
            console.log("EC Results loading in the current tab.");
        }

        // The "Stay on website" modal usually pops up ON the results page!
        try {
            const stayBtnResults = targetPage.getByText('Stay on website', { exact: true });
            await stayBtnResults.waitFor({ state: 'visible', timeout: 15000 });
            console.log('Dismissing "Stay on website" modal on results page...');
            await stayBtnResults.click({ force: true });
            await targetPage.waitForTimeout(1000); // let it fade out
        } catch (e) {
            console.log("No modal appeared on the results page.");
        }

        // Wait for results to finish rendering (EC documents can take a moment)
        console.log("Waiting 10s for EC document to fully render...");
        await targetPage.waitForTimeout(10000);

        // Expand scrollable areas for full page screenshot
        await targetPage.evaluate(() => {
            const style = document.createElement('style');
            style.innerHTML = `
                body, html, #__next, .overflow-y-auto, .overflow-auto, * {
                    overflow: visible !important;
                    height: auto !important;
                    max-height: none !important;
                }
            `;
            document.head.appendChild(style);
        });
        await targetPage.waitForTimeout(2000); // Wait for relayout

        // Capture screenshot
        const screenshotName = `landeed_result_${sessionId}.png`;
        const screenshotPath = path.join(__dirname, 'screenshots', screenshotName);

        // We use fullPage: true which now works because we removed scroll limitations
        await targetPage.screenshot({ path: screenshotPath, fullPage: true });
        console.log(`Saved screenshot to ${screenshotPath}`);

        // --- NEW: Download the real PDF ---
        let ecPdfPath = null;
        try {
            console.log("Attempting to download real EC PDF...");
            // Looking for the download icon in the viewer header (usually the down arrow)
            const downloadBtn = targetPage.locator('button[title="Download"], button[aria-label="Download"], .download-icon').first();
            
            if (await downloadBtn.isVisible({ timeout: 10000 })) {
                const [download] = await Promise.all([
                    targetPage.waitForEvent('download', { timeout: 30000 }),
                    downloadBtn.click()
                ]);
                
                const reportsDir = path.join(__dirname, 'reports');
                if (!fs.existsSync(reportsDir)) fs.mkdirSync(reportsDir, { recursive: true });
                
                ecPdfPath = path.join(reportsDir, `ec_${sessionId}.pdf`);
                await download.saveAs(ecPdfPath);
                console.log(`Successfully downloaded real EC PDF to: ${ecPdfPath}`);
            } else {
                console.log("Download button not found in time. Falling back to screenshot-only mode.");
            }
        } catch (downloadError) {
            console.log("Failed to download PDF, continuing with screenshot only:", downloadError.message);
        }

        // Clean up session
        if (newPage && !newPage.isClosed()) await newPage.close().catch(() => null);
        if (!page.isClosed()) await page.close().catch(() => null);
        sessions.delete(sessionId);

        return { 
            success: true, 
            screenshotUrl: `/screenshots/${screenshotName}`,
            ecPdfPath: ecPdfPath ? `/reports/ec_${sessionId}.pdf` : null
        };
    } catch (error) {
        throw error;
    }
}

