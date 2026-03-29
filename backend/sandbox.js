import { chromium } from 'playwright-extra';
import stealth from 'puppeteer-extra-plugin-stealth';
import path from 'path';
import fs from 'fs';

chromium.use(stealth());

(async () => {
    console.log('Starting Playwright Sandbox...');
    const browser = await chromium.launch({ headless: false });
    const context = await browser.newContext();
    const page = await context.newPage();

    await page.goto('https://web.landeed.com/karnataka/ec-encumbrance-certificate');
    console.log('Please login and enter the OTP manually in the browser window within the next 45 seconds...');

    try {
        await page.waitForSelector('input[placeholder*="Devanahalli"]', { timeout: 45000 });
        console.log('EC Form detected! Filling out...');

        await page.getByText('Non Agricultural', { exact: true }).click();

        const villageInput = page.locator('input[placeholder*="Devanahalli"]');
        await villageInput.fill('Devanahalli');
        await page.waitForTimeout(1000);
        await page.keyboard.press('ArrowDown');
        await page.keyboard.press('Enter');

        await page.getByText('Survey No', { exact: true }).click();

        const surveyInput = page.locator('input[placeholder*="Click to Enter"]');
        await surveyInput.fill('42');
        await page.keyboard.press('Enter');

        await page.getByText('5 Year', { exact: true }).click();

        const searchBtn = page.getByRole('button', { name: 'Search' });
        await searchBtn.click();

        console.log('Search clicked, waiting for results...');
        await page.waitForTimeout(10000);

        const screenshotPath = path.join(process.cwd(), 'screenshots', 'test_ec_result.png');
        if (!fs.existsSync(path.join(process.cwd(), 'screenshots'))) {
            fs.mkdirSync(path.join(process.cwd(), 'screenshots'), { recursive: true });
        }
        await page.screenshot({ path: screenshotPath, fullPage: true });
        console.log('Screenshot saved to: ' + screenshotPath);

    } catch (e) {
        console.log('Error during form fill: ', e);
    } finally {
        await browser.close();
    }
})();
