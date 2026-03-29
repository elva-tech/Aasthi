import { chromium } from 'playwright-extra';
import stealth from 'puppeteer-extra-plugin-stealth';
chromium.use(stealth());

(async () => {
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();

    page.on('console', msg => {
        if (msg.type() === 'error') {
            console.log(`[Browser Error]: ${msg.text()}`);
        }
    });

    page.on('pageerror', error => {
        console.log(`[Uncaught Exception]: ${error.message}`);
        console.log(`[Stack]: ${error.stack}`);
    });

    try {
        console.log('Navigating to frontend Result page via mock state...');
        
        // Let's inject a script to force the App component to go straight to step 4
        await page.addInitScript(() => {
            window.__MOCK_SESSION_ID = "1773141780601";
            window.__MOCK_IMAGE_URL = "http://localhost:5000/screenshots/ec_result_1773141780601.png";
        });

        await page.goto('http://localhost:5173');
        await page.waitForTimeout(1000);

        // This is tricky if we don't modify App.jsx to read debug variables.
        // Let's just monitor the network requests to see if the frontend sends the right things.
        console.log('We need to trigger the ResultCard to see the error.');
        
    } catch (e) {
        console.error('Test error:', e);
    } finally {
        await browser.close();
    }
})();
