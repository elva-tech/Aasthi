import fetch from 'node-fetch';

(async () => {
    const sessionId = "1773148709231";
    const otp = "845009";
    
    try {
        console.log("2. Verifying OTP...");
        const verifyRes = await fetch('http://localhost:5000/api/verify-otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sessionId, otp })
        });
        const verifyData = await verifyRes.json();
        console.log("OTP Verification Result:", verifyData);

        if (verifyData.success) {
            console.log("3. Initiating Search...");
            const searchRes = await fetch('http://localhost:5000/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    sessionId, 
                    searchDetails: {
                        district: "Bengaluru (Urban)",
                        subRegistrarOffice: "Basavanagudi",
                        village: "Hospet",
                        surveyNo: "280",
                        duration: "5 Years"
                    }
                })
            });
            const searchData = await searchRes.json();
            console.log("Search Result:", searchData);
            
            if (searchData.success) {
                console.log("4. Running AI Analysis...");
                const analyzeRes = await fetch('http://localhost:5000/api/analyze-ec', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sessionId, propertyType: "Non Agricultural" })
                });
                const analyzeData = await analyzeRes.json();
                console.log("AI Analysis Result:", analyzeData);
            }
        }
    } catch (e) {
        console.error("Test Error:", e);
    }
})();
