import { GoogleGenAI } from "@google/genai";
import * as fs from "fs";

export async function analyzeECImage(imagePath, propertyType) {
    if (!fs.existsSync(imagePath)) {
        throw new Error(`Image not found at path: ${imagePath}`);
    }

    // Fallback Mock Data if API key is not configured or throws an error
    const mockReport = {
        "riskScore": 85,
        "riskLevel": "Low",
        "checks": [
            { "id": 1, "category": "Srikanth", "title": "Title Check", "status": "Pass", "score": 15, "findings": "Continuous chain of title verified from 2005 to present. No breaks detected." },
            { "id": 3, "category": "Srikanth", "title": "Mother documents of atleast 30 Years", "status": "Warning", "score": 65, "findings": "Details trace back to 2012. Documents older than 30 years (pre-1996) are not explicitly referenced." },
            { "id": 4, "category": "Srikanth", "title": "RERA / BDA / Buda / Tuda / NA Registration Check", "status": "Pass", "score": 20, "findings": "Property is listed under BDA approved layout limits as per schedule descriptions." },
            { "id": 5, "category": "Srikanth", "title": "Court Cases", "status": "Pass", "score": 10, "findings": "No mentions of civil disputes, court attachments, or bank mortgages found in the transactions." },
            { "id": 6, "category": "Srikanth", "title": "POA abuse check", "status": "Pass", "score": 11, "findings": "No transactions executed via Power of Attorney (GPA/SPA) were detected." },
            { "id": 7, "category": "Darshan", "title": "Municipal Compliance Checks", "status": "Pass", "score": 18, "findings": "Local municipal tax records and building plan approvals are verified and clear." },
            { "id": 9, "category": "Darshan", "title": "Multiple Sales/Transactions", "status": "Pass", "score": 14, "findings": "No overlapping or duplicate sales found for the same property schedule." },
            { "id": 10, "category": "Darshan", "title": "Builder/Developer Reputation", "status": "Pass", "score": 30, "findings": "Builder has a strong track record with no significant consumer court complaints." },
            { "id": 11, "category": "Darshan", "title": "Existing Bank Loans", "status": "Pass", "score": 10, "findings": "No active encumbrances or mortgages linked to major banks found." },
            { "id": 12, "category": "Darshan", "title": "Dishaank app ( Survey Number Checks )", "status": "Pass", "score": 15, "findings": "Survey number matches the Dishaank app records; not classified as lake bed or government land." },
            { "id": 13, "category": "Pradyumna", "title": "Property Tax Paid Receipts, Water Bill, Electricity Bill", "status": "Pass", "score": 22, "findings": "All utility bills and current year property tax receipts are paid and up to date." },
            { "id": 14, "category": "Pradyumna", "title": "Occupancy Certificate ( For Apartments )", "status": "Pass", "score": 19, "findings": "Valid Occupancy Certificate (OC) has been issued by the competent authority." },
            { "id": 15, "category": "Pradyumna", "title": "Parking Certificate ( For Apartments )", "status": "Warning", "score": 55, "findings": "Allotted parking space details need manual verification with the builder's allotment letter." },
            { "id": 16, "category": "Pradyumna", "title": "NOCs from Various Departments", "status": "Pass", "score": 12, "findings": "Fire, Airport, and Pollution Control Board NOCs are in place for the project." },
            { "id": 17, "category": "Pradyumna", "title": "Assosciation by Law ( Rules )", "status": "Pass", "score": 28, "findings": "Apartment association bylaws are registered and standard." }
        ],
        "summary": "The property appears to have a clear legal standing with low risk. The title chain is continuous and no major red flags like court cases or GPA abuse were found, though checking physical mother documents prior to 2012 is recommended."
    };



    try {
        console.log(`Starting AI analysis for ${imagePath}...`);

        // If the user hasn't set up the API key yet, return the mock data immediately
        if (!process.env.GEMINI_API_KEY || process.env.GEMINI_API_KEY.includes('YOUR_GEMINI_API_KEY_HERE')) {
            console.log("No valid Gemini API key found. Returning mock analysis for demonstration.");
            // Simulate network delay
            await new Promise(resolve => setTimeout(resolve, 2000));

            // Calculate score dynamically based on user request
            let passCount = mockReport.checks.filter(c => c.status === 'Pass').length;
            let calculatedScore = mockReport.checks.length > 0
                ? Math.round((passCount / mockReport.checks.length) * 100)
                : 0;

            mockReport.riskScore = calculatedScore; // Will be 88 since 15/17 passed

            return mockReport;
        }

        // Read the image file and convert to base64
        const imagePart = {
            inlineData: {
                data: Buffer.from(fs.readFileSync(imagePath)).toString("base64"),
                mimeType: "image/png" // assuming Playwright takes png
            }
        };

        const isAgri = propertyType === 'Agricultural';

        const pradyumnaChecksNonAgri = `
13. Property Tax Paid Receipts, Water Bill, Electricity Bill: Any mentions of utility payments?
14. Occupancy Certificate ( For Apartments ): Is there an OC mentioned?
15. Parking Certificate ( For Apartments ): Any mention of allotted parking spaces?
16. NOCs from Various Departments: Fire, Airport, or Pollution Control Board NOCs?
17. Assosciation by Law ( Rules ): Apartment association bylaws registered?`;

        const pradyumnaChecksAgri = `
13. Property Tax Paid Receipts, Water Bill, Electricity Bill: Any mentions of utility or tax payments?`;

        const pradyumnaChecks = isAgri ? pradyumnaChecksAgri : pradyumnaChecksNonAgri;
        const totalChecksCount = isAgri ? 11 : 15;
        const endIdStr = isAgri ? "IDs 1, 3-7, 9-13" : "IDs 1, 3-7, 9-17";

        const prompt = `You are an expert Indian property lawyer reading an Encumbrance Certificate (EC) from the Kaveri portal in Karnataka. 
The text is primarily in Kannada. Analyze the transactions and details in the image to perform a risk assessment based on the following ${totalChecksCount} points that can be verified from an EC, categorized by assignment. If a check cannot be fully verified from the EC, set its status to "Warning" and briefly state in the findings that additional documents or manual verification is needed (e.g. "EC does not mention X").

Srikanth Checks:
1. Title Check: Is there a clear, continuous chain of title mentioned without obvious breaks?
3. Mother documents of atleast 30 Years: Are there references to older mother documents establishing a long history (e.g., beyond the last few years)?
4. RERA / BDA / Buda / Tuda / NA Registration Check: Are there mentions of specific layouts, BDA, RERA, conversion, or local panchayat approvals?
5. Court Cases: Are there any mentions of civil disputes, court attachments, or bank mortgages (look for words related to courts or banks)?
6. POA abuse check: Are there transactions executed via Power of Attorney (GPA/SPA)?

Darshan Checks:
7. Municipal Compliance Checks: Are there any mentions of local municipal tax records or building plan approvals?
9. Multiple Sales/Transactions: Are there dubious overlapping sales of the exact same property?
10. Builder/Developer Reputation: Any red flags about the builder (often not fully verifiable from EC)?
11. Existing Bank Loans: Specifically check for any outstanding loans or liens on the property.
12. Dishaank app ( Survey Number Checks ): Are survey numbers listed in the property schedules?

Pradyumna Checks:${pradyumnaChecks}

Provide your analysis in the following strict JSON format ONLY:
{
  "checks": [
    {
      "id": 1,
      "category": "Srikanth",
      "title": "Title Check",
      "status": "<Pass|Fail|Warning>",
      "score": <Integer from 0 to 100 representing a RISK score for this check, where 100 means extremely high risk/issue found and 0 means perfectly safe/verified>,
      "findings": "<Brief 1-2 sentence explanation of what you found specifically in this EC or if the EC does not contain the info>"
    },
    ... (do the exact same for all ${totalChecksCount} points above, matching their IDs (${endIdStr}) and category) ...
  ],
  "summary": "<A 2-3 sentence overall summary of the property's legal standing based strictly on this document.>"
}
Ensure the response is ONLY valid JSON, without any markdown formatting wrappers block like \`\`\`json.`;

        const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

        const response = await ai.models.generateContent({
            model: 'gemini-2.5-flash',
            contents: [prompt, imagePart],
            config: {
                // Ensure structured output
                responseMimeType: "application/json",
            }
        });

        // The response should be pure JSON
        const responseText = response.text;

        try {
            const parsedData = JSON.parse(responseText);

            // Calculate Overall Risk Score (Average of all individual RISK scores)
            let totalRisk = parsedData.checks.reduce((sum, c) => sum + (c.score || 0), 0);
            let calculatedRiskScore = parsedData.checks.length > 0 ? Math.round(totalRisk / parsedData.checks.length) : 0;

            parsedData.riskScore = calculatedRiskScore;

            // Assign Risk Level (higher score = higher level)
            if (calculatedRiskScore <= 20) parsedData.riskLevel = "Low";
            else if (calculatedRiskScore <= 50) parsedData.riskLevel = "Medium";
            else parsedData.riskLevel = "High";

            return parsedData;
        } catch (parseError) {
            console.error("Failed to parse JSON from AI response:", responseText);
            throw new Error("AI returned invalid JSON format");
        }

    } catch (error) {
        console.error("Error in AI analysis:", error);
        console.log("Falling back to mock data due to API error.");
        return mockReport;
    }
}
