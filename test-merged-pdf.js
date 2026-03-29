import { generatePDFReport } from './backend/pdf-service.js';
import * as fs from 'fs';
import path from 'path';

async function testMergedPdf() {
    const sessionId = 'test_merged_session_' + Date.now();
    
    // Mock merged report (matching NEW standardized Risk Score logic: 100 = critical risk)
    const mockMergedReport = {
        "riskScore": 65, // Average risk: Medium
        "riskLevel": "Medium",
        "summary": "This is a merged test report with standardized RISK scores (Higher = More Risk).",
        "checks": [
            // AI Checks (Srikanth)
            { "id": 1, "category": "Srikanth", "title": "Official Title Check", "status": "Pass", "score": 10, "findings": "Title documents verified | Clear flow of ownership found." },
            { "id": 2, "category": "Srikanth", "title": "Official EC Check", "status": "Warning", "score": 45, "findings": "Minor mismatch in date | Manual verification recommended." },
            
            // Python Checks (Darshan/Pradyumna)
            { "id": 101, "category": "Pradyumna", "title": "BESCOM Verification", "status": "Fail", "score": 90, "findings": "Consumer name mismatch | 3 months unpaid arrears detected." },
            { "id": 102, "category": "Pradyumna", "title": "Water Board (BWSSB)", "status": "Pass", "score": 5, "findings": "RR Number matched successfully." },
            { "id": 103, "category": "Darshan", "title": "Khata (PID) Check", "status": "Fail", "score": 85, "findings": "PID found in legacy database only | Requires physical khata copy verification." }
        ]
    };

    console.log("Generating merged PDF for session:", sessionId);
    try {
        const result = await generatePDFReport(mockMergedReport, sessionId);
        console.log("PDF generated successfully:", result.pdfPath);
    } catch (err) {
        console.error("Failed to generate PDF:", err);
    }
}

testMergedPdf();
