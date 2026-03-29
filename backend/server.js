import "dotenv/config";
import express from "express";
import cors from "cors";
import path from "path";
import * as fs from "fs";
import { startLogin, submitOTP, searchEC } from "./scraper.js";
import { analyzeECImage } from "./ai-service.js";
import { generatePDFReport } from "./pdf-service.js";
import { runPythonWrappers } from "./python-runner.js";
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
app.use(cors());
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ limit: '10mb', extended: true }));

// Serve static screenshots and reports
// __dirname is now correctly the backend folder
app.use('/screenshots', express.static(path.join(__dirname, 'screenshots')));
app.use('/reports', express.static(path.join(__dirname, 'reports'), {
  setHeaders: function (res, filepath, stat) {
    res.set('Content-Disposition', `attachment; filename="${path.basename(filepath)}"`);
    res.set('Content-Type', 'application/pdf');
  }
}));

app.post("/api/login", async (req, res) => {
  const { phoneNumber } = req.body;
  if (!phoneNumber) return res.status(400).json({ error: "Phone number required" });

  try {
    const result = await startLogin(phoneNumber);
    res.json(result);
  } catch (error) {
    console.error("Login Error:", error);
    res.status(500).json({ error: error.message });
  }
});

app.post("/api/verify-otp", async (req, res) => {
  const { sessionId, otp } = req.body;
  if (!sessionId || !otp) return res.status(400).json({ error: "sessionId and otp required" });

  try {
    const result = await submitOTP(sessionId, otp);
    res.json(result);
  } catch (error) {
    console.error("OTP Error:", error);
    res.status(500).json({ error: error.message });
  }
});

app.post("/api/search", async (req, res) => {
  const { sessionId, searchDetails } = req.body;

  try {
    const result = await searchEC(sessionId, searchDetails);
    res.json(result);
  } catch (error) {
    console.error("Search Error:", error);
    res.status(500).json({ error: error.message });
  }
});

app.post("/api/analyze-ec", async (req, res) => {
  const { sessionId, propertyType } = req.body;
  if (!sessionId) return res.status(400).json({ error: "sessionId required for analysis" });

  // Construct the expected screenshot path based on scraper.js logic
  // imagePath and reportsDir now use the correct __dirname (the backend folder)
  const imagePath = path.join(__dirname, 'screenshots', `landeed_result_${sessionId}.png`);

  try {
    const aiReport = await analyzeECImage(imagePath, propertyType || 'Non Agricultural');

    // Save dashboard checks to reports folder
    const reportsDir = path.join(__dirname, 'reports');
    if (!fs.existsSync(reportsDir)) {
      fs.mkdirSync(reportsDir, { recursive: true });
    }
    const dashboardChecksPath = path.join(reportsDir, `dashboard_checks_${sessionId}.json`);
    fs.writeFileSync(dashboardChecksPath, JSON.stringify(aiReport, null, 2));

    res.json({ success: true, report: aiReport });
  } catch (error) {
    console.error("=== AI Analysis Fatal Error ===");
    console.error(error.stack || error);
    res.status(500).json({ error: error.message || "Failed to analyze EC image." });
  }
});

app.post("/api/generate-pdf", async (req, res) => {
  const { sessionId, aiReport } = req.body;
  if (!sessionId || !aiReport) {
    return res.status(400).json({ error: "sessionId and aiReport required" });
  }

  try {
    const result = await generatePDFReport(aiReport, sessionId);
    res.json(result);
  } catch (error) {
    console.error("PDF Generation Error:", error);
    res.status(500).json({ error: error.message || "Failed to generate PDF." });
  }
});

app.post("/api/run-wrappers", async (req, res) => {
  try {
    const result = await runPythonWrappers(req.body);
    res.json(result);
  } catch (error) {
    console.error("Python Wrapper Error:", error);
    res.status(500).json({ error: error.message });
  }
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
