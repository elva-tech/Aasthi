import { chromium } from 'playwright-extra';
import stealth from 'puppeteer-extra-plugin-stealth';
chromium.use(stealth());

(async () => {
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();

    await page.goto('https://web.landeed.com/karnataka/ec-encumbrance-certificate');

    try {
        const loginBtn = page.getByRole('button', { name: /login/i }).first();
        if (await loginBtn.isVisible()) {
            await loginBtn.click();
        }

        const phoneInput = page.locator('input[name="phoneNo"]');
        await phoneInput.waitFor({ state: 'visible', timeout: 5000 });
        await phoneInput.fill('9999999999');

        const getOtpBtn = page.getByRole('button', { name: /send otp/i });
        await getOtpBtn.click();

        await page.waitForTimeout(4000);
        console.log("Waited 4 seconds for OTP UI. Dumping inputs...");

        const inputs = await page.locator('input').all();
        console.log(`Found ${inputs.length} inputs on page.`);
        for (let i = 0; i < inputs.length; i++) {
            const outerHTML = await inputs[i].evaluate(node => node.outerHTML);
            console.log(`Input ${i}: ${outerHTML}`);
        }
    } catch (e) {
        console.log("Error: " + e);
    } finally {
        await browser.close();
    }
})();
