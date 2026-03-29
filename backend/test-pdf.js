import { generatePDFReport } from './pdf-service.js';

const mockReport = {
    "riskScore": 41.6,
    "riskLevel": "Medium",
    "checks": [
        { "id": 1, "category": "Bank", "title": "BANKLOAN", "status": "Fail", "score": 100.0, "findings": "This check reviews if there are any active bank loans or debts linked to the property you are interested in. | Your property's risk score is 100 out of 100, which indicates the highest possible risk. Remember, a score of 0 is best, meaning no risk, while a higher score means high risk. | Our findings clearly show an active loan or charge on the property that is currently marked as 'Not Satisfied' in official records. | This means the property is 'encumbered' or tied to an existing debt, making it impossible to transfer a clear title to you right now. | There is a high risk of fraud if the seller asks for payment before this debt is officially cleared and the records are updated." },
        { "id": 2, "category": "Legal", "title": "EC", "status": "Fail", "score": 77.0, "findings": "Your risk score for this check is 77 out of 100. Remember, 0 is the best score, and higher scores mean higher risk. | We found two 'Agreement to Sell' transactions related to this property from the same date in 2016. | In both agreements, the declared value was only $1.00, which is highly unusual for property transactions. | These agreements involved the same complex seller and two brothers as buyers, all occurring on the same day. | This pattern strongly suggests potential issues like trying to hide the true value of the property or avoid taxes." },
        { "id": 3, "category": "Builder", "title": "BUILDER", "status": "Warning", "score": 56.0, "findings": "We review builder history and reputation using various sources. | Score is elevated due to pending consumer court cases. | Ensure you review the RERA website for history and potential liabilities." },
        { "id": 4, "category": "Legal", "title": "NOC", "status": "Warning", "score": 49.5, "findings": "We check whether requisite NOCs are in place. | Currently awaiting water NOC clearance. | Ensure clearance is obtained before making final payments." },
        { "id": 5, "category": "Legal", "title": "KHATA", "status": "Warning", "score": 40.0, "findings": "Khata transfer is currently in progress. | No critical alerts, but ensure mutation is completed before final registration." },
        { "id": 6, "category": "Amenity", "title": "PARKING", "status": "Pass", "score": 35.0, "findings": "Parking allocation verified against builder documents. | No major issues detected." },
        { "id": 7, "category": "Legal", "title": "OC", "status": "Pass", "score": 29.0, "findings": "Occupancy certificate verified. | Structure appears built according to approved plan." },
        { "id": 8, "category": "Tax", "title": "BBMP PROPERTY TAX", "status": "Pass", "score": 26.0, "findings": "Property taxes are paid up to date for the current financial year. | Receipt verified." },
        { "id": 9, "category": "Utility", "title": "WATER", "status": "Pass", "score": 16.1, "findings": "Water connection verified and active. | Bills are paid up to date." },
        { "id": 10, "category": "Legal", "title": "BYLAWS", "status": "Pass", "score": 16.0, "findings": "Association bylaws reviewed. | Rules are standard and comply with local regulations." }
    ],
    "summary": "This report helps you spot issues that can delay registration, impact home loans, or create problems during resale. 0 is best. Higher score = higher risk."
};

async function testGeneration() {
    try {
        console.log("Generating test PDF...");
        const result = await generatePDFReport(mockReport, 'test_session_123');
        console.log(`Success! PDF saved to ${result.pdfPath}`);
    } catch (e) {
        console.error("Failed to generate PDF:", e);
    }
}

testGeneration();
