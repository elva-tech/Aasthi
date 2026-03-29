import { chromium } from "playwright";

async function run() {
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();

    console.log("Navigating to Landeed EC...");
    await page.goto("https://web.landeed.com/karnataka/ec-encumbrance-certificate");

    // Wait for the page to settle
    await page.waitForLoadState('networkidle');

    console.log("Checking for login buttons...");
    const html = await page.content();

    if (html.includes('Login')) {
        console.log('Login text found on page');
    } else {
        console.log('Login text NOT found');
    }

    // Dump all input fields to see what's available
    const inputs = await page.evaluate(() => {
        return Array.from(document.querySelectorAll('input')).map(i => ({
            type: i.type,
            placeholder: i.placeholder,
            id: i.id,
            name: i.name,
            class: i.className
        }));
    });

    console.log("Inputs found on page:", JSON.stringify(inputs, null, 2));

    // Dump all buttons
    const buttons = await page.evaluate(() => {
        return Array.from(document.querySelectorAll('button')).map(b => ({
            text: b.innerText,
            type: b.type,
            class: b.className
        }));
    });

    console.log("Buttons found on page:", JSON.stringify(buttons, null, 2));

    await browser.close();
}

run().catch(console.error);
