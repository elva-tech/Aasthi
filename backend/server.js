import "dotenv/config";
import express from "express";
import cors from "cors";
import path from "path";
import { fileURLToPath } from "url";
import { runCompletePropertyAnalysis } from "./wrapper-orchestrator.js";


const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();

app.use(cors());

app.use(
  express.json({
    limit: "10mb",
  })
);

app.use(
  express.urlencoded({
    limit: "10mb",
    extended: true,
  })
);

app.use(
  "/reports",
  express.static(path.join(__dirname, "reports"), {
    setHeaders(res, filepath) {
      res.set(
        "Content-Disposition",
        `attachment; filename="${path.basename(filepath)}"`
      );

      res.set("Content-Type", "application/pdf");
    },
  })
);



app.post("/api/analyze-property", async (req, res) => {
  try {
    console.log(
      "Starting complete property analysis pipeline..."
    );

    const result = await runCompletePropertyAnalysis(
      req.body
    );

    if (!result.success) {
      return res.status(400).json({
        success: false,
        error: result.error,
        step: result.step,
        details: {
          wrappercodeError:
            result.wrappercodeError,

          riskwrapperError:
            result.riskwrapperError,

          pdfError:
            result.pdfError,
        },
      });
    }

    return res.json({
      success: true,

      message:
        result.message ||
        "Property analysis completed successfully",

      pdfUrl: result.pdfUrl,
      pdfPath: result.pdfPath,

      reportPath: result.reportPath,
      mergedReportPath:
        result.mergedReportPath,

      downloadedFiles:
        result.downloadedFiles || [],

      configPath:
        result.configPath,
    });
  } catch (error) {
    console.error(
      "Property Analysis Error:",
      error
    );

    return res.status(500).json({
      success: false,
      error:
        error.message ||
        "Failed to run property analysis",
    });
  }
});

const PORT = process.env.PORT || 5000;

app.listen(PORT, () => {
  console.log(
    `Server running on port ${PORT}`
  );
});