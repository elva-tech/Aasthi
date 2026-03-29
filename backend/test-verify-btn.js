import { chromium } from 'playwright-extra';
import stealth from 'puppeteer-extra-plugin-stealth';
import fs from 'fs';
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

        await page.waitForTimeout(6000);
        console.log("Waited 6 seconds for OTP UI. Taking screenshot...");
        await page.screenshot({ path: 'otp-screen-dump.png', fullPage: true });

        const html = await page.content();
        fs.writeFileSync('page-otp-dump.html', html);
        console.log("Wrote DOM to page-otp-dump.html");

    } catch (e) {
        console.log("Error: " + e);
    } finally {
        await browser.close();
    }
})();
