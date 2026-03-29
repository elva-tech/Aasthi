import { chromium } from 'playwright-extra';
import stealth from 'puppeteer-extra-plugin-stealth';
import fetch from 'node-fetch'; // Requires node-fetch or Node v18+

chromium.use(stealth());

(async () => {
    let sessionId;
    try {
        console.log("1. Starting Login...");
        const loginRes = await fetch('http://localhost:5000/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phoneNumber: '9110833256' })
        });
        const loginData = await loginRes.json();
        if (!loginData.success) throw new Error("Login failed: " + JSON.stringify(loginData));
        sessionId = loginData.sessionId;
        console.log("Session ID:", sessionId);

        console.log("WAITING FOR USER OTP... (Simulating 10s wait, but we can't fully automate OTP here easily without user interaction. If possible, we'll just test the AI endpoint directly with a dummy image)");
        
    } catch (e) {
        console.error("Test Error:", e);
    }
})();
