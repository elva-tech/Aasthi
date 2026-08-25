import { spawn } from "child_process";
import path from "path";
import * as fs from "fs";
import { fileURLToPath } from "url";

const __orchDir = path.dirname(fileURLToPath(import.meta.url));

const PYTHON = process.platform === "win32" ? "python" : "python3";

// ================================================================
// RUN PYTHON PROCESS
// ================================================================
function runProcess(command, args, cwd, label) {
  return new Promise((resolve) => {
    const proc = spawn(command, args, {
      cwd,
      shell: false,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8",
        TESSERACT_CMD:
          process.env.TESSERACT_CMD || "D:\\ocr\\tesseract.exe",
      },
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (data) => {
      const text = data.toString();
      stdout += text;
      console.log(`[${label} stdout]:`, text.trim());
    });

    proc.stderr.on("data", (data) => {
      const text = data.toString();
      stderr += text;
      console.warn(`[${label} stderr]:`, text.trim());
    });

    proc.on("error", (err) => {
      resolve({
        success: false,
        code: -1,
        stdout,
        stderr,
        error: err.message,
      });
    });

    proc.on("close", (code) => {
      resolve({
        success: code === 0,
        code,
        stdout,
        stderr,
      });
    });
  });
}

// ================================================================
// FIND LATEST RISK REPORT
// ================================================================
function latestRiskReport(outputDir) {
  if (!fs.existsSync(outputDir)) return null;

  const files = fs
    .readdirSync(outputDir)
    .filter(
      (f) =>
        f.startsWith("risk_report") &&
        f.endsWith(".json")
    )
    .sort(
      (a, b) =>
        fs.statSync(path.join(outputDir, b)).mtimeMs -
        fs.statSync(path.join(outputDir, a)).mtimeMs
    );

  return files.length
    ? path.join(outputDir, files[0])
    : null;
}

// ================================================================
// CHECK APPLICABILITY
//
// There are TWO exclusion sources:
//
// 1. Property-type exclusions
// 2. excludedChecks received from React
//
// If either excludes the check => false
// ================================================================
function isCheckApplicable(
  title,
  propertyType = "Apartment",
  excludedChecks = []
) {
  const excludedByType = {
    Apartment: [],

    Site: [
      "Occupancy Certificate",
      "Parking Certificate",
      "Association By Laws",
    ],

    "Individual House": [
      "Parking Certificate",
      "Association By Laws",
    ],

    Agricultural: [
      "Occupancy Certificate",
      "Parking Certificate",
      "Association By Laws",
      "Builder/Developer Reputation",
      "RERA / BDA / Buda / Tuda / NA Registration Check",
      "NOCs from Various Departments",
    ],
  };

  // ------------------------------------------------------------
  // PROPERTY-TYPE EXCLUSION
  // ------------------------------------------------------------
  if (
    (excludedByType[propertyType] || []).includes(title)
  ) {
    return false;
  }

  // ------------------------------------------------------------
  // FRONTEND / USER EXCLUSION
  // ------------------------------------------------------------
  if (
    Array.isArray(excludedChecks) &&
    excludedChecks.includes(title)
  ) {
    return false;
  }

  return true;
}


// ================================================================
// FIND ASSOCIATION BY-LAWS INPUT
//
// Searches ONLY:
//   wrappercode/input/bylaws
//
// If no valid document exists:
//   return null
//
// If multiple documents exist:
//   use the most recently modified document
// ================================================================

function getBylawsInput() {
  const projectRoot = path.resolve(process.cwd());

  const bylawsDir = path.join(
    projectRoot,
    "wrappercode",
    "input",
    "bylaws"
  );

  console.log(
    "[BYLAWS] Checking directory:",
    bylawsDir
  );

  if (!fs.existsSync(bylawsDir)) {
    console.log(
      "[BYLAWS] Directory does not exist."
    );
    return null;
  }

  let entries;

  try {
    entries = fs.readdirSync(
      bylawsDir,
      { withFileTypes: true }
    );
  } catch (error) {
    console.error(
      "[BYLAWS] Failed to read directory:",
      error.message
    );
    return null;
  }

  const allowedExtensions = new Set([
    ".pdf",
    ".txt",
    ".doc",
    ".docx"
  ]);

  const files = entries
    .filter(entry => entry.isFile())
    .filter(entry =>
      allowedExtensions.has(
        path.extname(entry.name).toLowerCase()
      )
    )
    .map(entry =>
      path.join(
        bylawsDir,
        entry.name
      )
    );

  if (files.length === 0) {
    console.log(
      "[BYLAWS] No valid bylaws document found."
    );
    return null;
  }

  files.sort(
    (a, b) =>
      fs.statSync(b).mtimeMs -
      fs.statSync(a).mtimeMs
  );

  console.log(
    "[BYLAWS] Selected file:",
    files[0]
  );

  return files[0];
}
// ================================================================
// REMOVE EXCLUDED CHECKS FROM FINAL REPORT
//
// Explicitly excluded checks should disappear completely.
// ================================================================

function removeExcludedChecks(
  riskReport,
  excludedChecks = []
) {

  if (
    !riskReport ||
    !Array.isArray(
      riskReport.checks
    ) ||
    !Array.isArray(
      excludedChecks
    )
  ) {
    return riskReport;
  }

  riskReport.checks =
    riskReport.checks.filter(
      check =>
        !excludedChecks.includes(
          check?.title
        )
    );

  return riskReport;
}


// ================================================================
// ADD NOT-APPLICABLE CHECKS
//
// Only applicable checks are added.
//
// IMPORTANT:
// If a check is excluded for the property type,
// it is NOT added as NOT_APPLICABLE.
// ================================================================

function addNotApplicableChecks(
  riskReport,
  params,
  resolvedPaths = {}
) {

  // ------------------------------------------------------------
  // SAFETY
  // ------------------------------------------------------------

  if (
    !riskReport ||
    typeof riskReport !== "object"
  ) {
    riskReport = {};
  }

  if (
    !Array.isArray(
      riskReport.checks
    )
  ) {
    riskReport.checks = [];
  }

  // ------------------------------------------------------------
  // EXCLUDED CHECKS
  // ------------------------------------------------------------

  const excludedChecks =
    Array.isArray(
      params?.excludedChecks
    )
      ? params.excludedChecks
      : [];

  // ------------------------------------------------------------
  // REMOVE EXCLUDED CHECKS FIRST
  // ------------------------------------------------------------

  riskReport.checks =
    riskReport.checks.filter(
      check =>
        !excludedChecks.includes(
          check?.title
        )
    );

  // ------------------------------------------------------------
  // TRACK EXISTING TITLES
  // ------------------------------------------------------------

  const existingTitles =
    new Set(
      riskReport.checks
        .filter(
          check =>
            check &&
            check.title
        )
        .map(
          check =>
            check.title
        )
    );

  // ------------------------------------------------------------
  // HELPER TO ADD NA
  // ------------------------------------------------------------

  const addNA = (
    title,
    findings
  ) => {

    const applicable =
      isCheckApplicable(
        title,
        params?.propertyType ||
          "Apartment",
        excludedChecks
      );

    // Never add excluded checks.
    if (!applicable) {
      return;
    }

    // Don't duplicate an existing check.
    if (
      existingTitles.has(
        title
      )
    ) {
      return;
    }

    riskReport.checks.push({
      title,
      status: "NOT_APPLICABLE",
      score: null,
      impact_weight: 0,
      findings
    });

    existingTitles.add(
      title
    );
  };


  // ============================================================
  // ELECTRICITY BILL
  // ============================================================

  if (!params?.bescomId) {

    addNA(
      "Electricity Bill",
      "Electricity consumer/account number was not provided."
    );
  }


  // ============================================================
  // WATER BILL
  // ============================================================

  if (!params?.waterRr) {

    addNA(
      "Water Bill",
      "Water RR number was not provided."
    );
  }


  // ============================================================
  // KHATA / PROPERTY TAX
  // ============================================================

  if (!params?.pidNumber) {

    addNA(
      "Khata/Mutation Type Verification",
      "PID number was not provided."
    );

    addNA(
      "Property Tax Paid Receipts",
      "PID number was not provided for property tax verification."
    );
  }


  // ============================================================
  // BUILDER
  // ============================================================

  if (!params?.builderName) {

    addNA(
      "Builder/Developer Reputation",
      "Builder name was not provided."
    );
  }


  // ============================================================
  // OCCUPANCY CERTIFICATE
  // ============================================================

  if (!resolvedPaths?.ocPdf) {

    addNA(
      "Occupancy Certificate",
      "OC document was not available or not downloaded."
    );
  }


  // ============================================================
  // NOC
  // ============================================================

  if (!resolvedPaths?.nocPdf) {

    addNA(
      "NOCs from Various Departments",
      "NOC document was not available or not downloaded."
    );
  }


  // ============================================================
  // PARKING
  // ============================================================

  if (
    !resolvedPaths?.parkingAgreement ||
    !resolvedPaths?.parkingSiteplan
  ) {

    addNA(
      "Parking Certificate",
      "Parking agreement or site plan was not available."
    );
  }


  // ============================================================
  // ASSOCIATION BY-LAWS
  // ============================================================

  if (!resolvedPaths?.bylawsInput) {

    addNA(
      "Association By Laws",
      "Association bylaws document was not available."
    );
  }


  // ============================================================
  // EC
  // ============================================================

  if (!resolvedPaths?.ecPdf) {

    addNA(
      "EC Document Check",
      "EC PDF was not available for deep wrapper verification."
    );
  }


  // ============================================================
  // EXISTING BANK LOANS
  // ============================================================

  if (!resolvedPaths?.bankloanPdf) {

    addNA(
      "Existing Bank Loans",
      "CERSAI/bank loan report was not uploaded or downloaded."
    );
  }


  // ============================================================
  // FINAL SAFETY FILTER
  // ============================================================

  riskReport.checks =
    riskReport.checks.filter(
      check =>
        !excludedChecks.includes(
          check?.title
        )
    );

  return riskReport;
}
// ================================================================
// MAIN PROPERTY ANALYSIS PIPELINE
// ================================================================
export async function runCompletePropertyAnalysis(
  params = {}
) {
  const projectRoot = path.resolve(
    __orchDir,
    ".."
  );

  const wrappercodeDir = path.join(
    projectRoot,
    "wrappercode"
  );

  const riskwrapperDir = path.join(
    projectRoot,
    "riskwrapper"
  );

  const reportGenerationDir = path.join(
    projectRoot,
    "reportgeneration"
  );

  const reportsDir = path.join(
    projectRoot,
    "backend",
    "reports"
  );

  fs.mkdirSync(reportsDir, {
    recursive: true,
  });

  // ==============================================================
  // NORMALIZE EXCLUDED CHECKS
  // ==============================================================

  const excludedChecks = Array.isArray(
    params.excludedChecks
  )
    ? params.excludedChecks
    : [];

  console.log(
    "=================================================="
  );

  console.log(
    "Property Type:",
    params.propertyType || "Apartment"
  );

  console.log(
    "Excluded Checks:",
    excludedChecks.length
      ? excludedChecks.join(", ")
      : "None"
  );

  console.log(
    "=================================================="
  );

  // ==============================================================
  // WRAPPERCODE
  //
  // NOTE:
  // wrappercode still receives the input values.
  // Riskwrapper modules are selectively disabled below.
  // ==============================================================

  const wrapperResult = await runProcess(
    PYTHON,
    [
      "main.py",

      "--project-name",
      params.projectName || "",

      "--owner-name",
      params.ownerName || "",

      "--pid-number",
      params.pidNumber || "",

      "--epid-number",
      params.epidNumber || "",

      "--bescom-account",
      params.bescomId || "",

      "--water-rr",
      params.waterRr || "",

      "--district",
      params.district || "",

      "--taluka",
      params.taluka || "",

      "--hobli",
      params.hobli || "",

      "--village",
      params.village || "",

      "--property-no",
      params.propertyNo || "",

      "--court-party-name",
      params.courtPartyName ||
        params.ownerName ||
        "",

      "--court-year",
      params.courtYear || "2015",
    ],
    wrappercodeDir,
    "Wrappercode"
  );

  if (!wrapperResult.success) {
    return {
      success: false,
      step: "wrappercode",
      error: "Wrappercode failed",
      wrappercodeOutput:
        wrapperResult.stdout,
      wrappercodeError:
        wrapperResult.stderr,
    };
  }

  console.log(
    "Wrappercode finished"
  );

  // ==============================================================
  // DOWNLOADS
  // ==============================================================

  const downloadsDir = path.join(
    wrappercodeDir,
    "downloads"
  );

  const downloadedFiles =
    fs.existsSync(downloadsDir)
      ? fs.readdirSync(downloadsDir)
      : [];

  const findFile = (keywords) =>
    downloadedFiles.find((f) => {
      const name =
        f.toLowerCase();

      return keywords.some(
        (k) =>
          name.includes(
            k.toLowerCase()
          )
      );
    });

  const getPath = (keywords) => {
    const file = findFile(keywords);

    return file
      ? path.join(
          downloadsDir,
          file
        )
      : null;
  };

  // ==============================================================
  // OC
  // ==============================================================

  const getOCPath = () => {
    const file =
      downloadedFiles.find((f) => {
        const name =
          f.toLowerCase();

        return (
          (
            name.includes("ocplh") ||
            name.includes("ccplh") ||
            name.startsWith("oc") ||
            name.startsWith("cc")
          ) &&
          !name.includes("noc")
        );
      });

    return file
      ? path.join(
          downloadsDir,
          file
        )
      : null;
  };

  // ==============================================================
  // BESCOM FILE
  // ==============================================================

  const bescomDir =
    params.bescomId
      ? path.join(
          wrappercodeDir,
          params.bescomId
        )
      : null;

  const bescomFile =
    bescomDir &&
    fs.existsSync(bescomDir)
      ? fs
          .readdirSync(bescomDir)
          .find((f) =>
            f
              .toLowerCase()
              .endsWith(".pdf")
          )
      : null;

  const bescomPdfPath =
    bescomFile
      ? path.join(
          bescomDir,
          bescomFile
        )
      : null;

  const tesseractPath =
    process.env.TESSERACT_CMD ||
    "D:\\ocr\\tesseract.exe";

  // ==============================================================
  // CHECK APPLICABILITY HELPER
  // ==============================================================

  const applicable = (title) =>
    isCheckApplicable(
      title,
      params.propertyType ||
        "Apartment",
      excludedChecks
    );

  // ==============================================================
  // RISKWRAPPER CONFIG
  // ==============================================================

  const config = {
  // ============================================================
  // METADATA
  // ============================================================

  _meta: {
    propertyType:
      params.propertyType || "Apartment",

    excludedChecks:
      excludedChecks,
  },

  // ============================================================
  // ELECTRICITY
  // ============================================================

  bescom:
    isCheckApplicable(
      "Electricity Bill",
      params.propertyType,
      excludedChecks
    )
      ? {
          pdf: bescomPdfPath,
          user_name:
            params.ownerName || "",
          user_address:
            params.address || "",
        }
      : null,

  // ============================================================
  // WATER
  // ============================================================

  water:
    isCheckApplicable(
      "Water Bill",
      params.propertyType,
      excludedChecks
    )
      ? {
          rr:
            params.waterRr || "",
          user_name:
            params.ownerName || "",
          user_address:
            params.address || "",
        }
      : null,

  // ============================================================
  // PROPERTY TAX
  // ============================================================

  bbmp_property_tax:
    isCheckApplicable(
      "Property Tax Paid Receipts",
      params.propertyType,
      excludedChecks
    )
      ? {
          pid_number:
            params.pidNumber || "",
          owner_name:
            params.ownerName || "",
          application_number:
            params.applicationNumber || "",
        }
      : null,

  // ============================================================
  // OCCUPANCY CERTIFICATE
  // ============================================================

  oc:
    isCheckApplicable(
      "Occupancy Certificate",
      params.propertyType,
      excludedChecks
    )
      ? {
          pdf:
            getOCPath(),
          tesseract_cmd:
            tesseractPath,
        }
      : null,

  // ============================================================
  // NOC
  // ============================================================

  noc:
    isCheckApplicable(
      "NOCs from Various Departments",
      params.propertyType,
      excludedChecks
    )
      ? {
          pdfs:
            getPath(["noc"])
              ? [
                  getPath(["noc"]),
                ]
              : [],

          tesseract_cmd:
            tesseractPath,
        }
      : null,

  // ============================================================
  // PARKING
  // ============================================================

  parking:
    isCheckApplicable(
      "Parking Certificate",
      params.propertyType,
      excludedChecks
    )
      ? {
          agreement:
            getPath(["agreement"]),

          siteplan:
            getPath([
              "site plan",
              "site",
            ]),

          tesseract_cmd:
            tesseractPath,
        }
      : null,

  // ============================================================
  // ASSOCIATION BYLAWS
  // ============================================================

  bylaws:
    isCheckApplicable(
      "Association By Laws",
      params.propertyType,
      excludedChecks
    )
      ? {
          input: getBylawsInput(),
        }
      : null,
  // ============================================================
  // EC DOCUMENT CHECK
  // ============================================================

  ec:
    isCheckApplicable(
      "EC Document Check",
      params.propertyType,
      excludedChecks
    )
      ? {
          pdf:
            getPath(["ec"]),

          tesseract_cmd:
            tesseractPath,
        }
      : null,

  // ============================================================
  // BANK LOAN
  // ============================================================

  bankloan:
    isCheckApplicable(
      "Existing Bank Loans",
      params.propertyType,
      excludedChecks
    )
      ? {
          pdf:
            getPath(["cersai"]),

          out:
            path.join(
              riskwrapperDir,
              "output",
              "bankloan_result.json"
            ),
        }
      : null,

  // ============================================================
  // BUILDER
  // ============================================================

  builder:
    isCheckApplicable(
      "Builder/Developer Reputation",
      params.propertyType,
      excludedChecks
    )
      ? {
          builder_name:
            params.builderName || "",

          db_path:
            path.join(
              wrappercodeDir,
              "db"
            ),
        }
      : null,

  // ============================================================
  // COURT
  // ============================================================

  ecourtrisk: {
    screenshots_folder:
      path.join(
        wrappercodeDir,
        "ecourtjson"
      ),
  },

  // ============================================================
  // TITLE CHECK
  // ============================================================

  kaveriecrisk:
    isCheckApplicable(
      "Title Check",
      params.propertyType,
      excludedChecks
    )
      ? {
          pdf:
            getPath(["ec"]),
        }
      : null,

  // ============================================================
  // KHATA
  // ============================================================

  ekhatarisk:
    isCheckApplicable(
      "Khata/Mutation Type Verification",
      params.propertyType,
      excludedChecks
    )
      ? {
          pdf:
            getPath(["khata"]),
        }
      : null,
  // ============================================================
  // RERA APPROVAL
  // ===========================================================
  rera_approval:
    isCheckApplicable(
      "RERA / BDA / Buda / Tuda / NA Registration Check",
      params.propertyType,
      excludedChecks
    )
      ? {
          input_json: path.join(
            wrappercodeDir,
            "input",
            "additional detail",
            "Prestige_Lakeside_Habitat_rera_details.json"
          ),
        }
      : null,
};
  // ==============================================================
  // CONFIG PATH
  // ==============================================================

  const configPath = path.join(
    reportsDir,
    `config_${Date.now()}.json`
  );

  fs.writeFileSync(
    configPath,
    JSON.stringify(
      config,
      null,
      2
    )
  );

  console.log(
    "Riskwrapper config created:",
    configPath
  );

  // ==============================================================
  // PRINT MODULE STATUS
  // ==============================================================

  console.log(
    "---------------- MODULE STATUS ----------------"
  );

  console.log(
    "Electricity Bill:",
    applicable("Electricity Bill")
      ? "ENABLED"
      : "EXCLUDED"
  );

  console.log(
    "Water Bill:",
    applicable("Water Bill")
      ? "ENABLED"
      : "EXCLUDED"
  );

  console.log(
    "Property Tax:",
    applicable(
      "Property Tax Paid Receipts"
    )
      ? "ENABLED"
      : "EXCLUDED"
  );

  console.log(
    "Title Check:",
    applicable("Title Check")
      ? "ENABLED"
      : "EXCLUDED"
  );

  console.log(
    "Existing Bank Loans:",
    applicable(
      "Existing Bank Loans"
    )
      ? "ENABLED"
      : "EXCLUDED"
  );

  console.log(
    "Khata:",
    applicable(
      "Khata/Mutation Type Verification"
    )
      ? "ENABLED"
      : "EXCLUDED"
  );

  console.log(
    "------------------------------------------------"
  );

  // ==============================================================
  // RUN RISKHWRAPPER
  // ==============================================================

  const riskResult = await runProcess(
    PYTHON,
    [
      "main.py",
      "all",
      "--config",
      configPath,
    ],
    riskwrapperDir,
    "Riskwrapper"
  );

  if (!riskResult.success) {
    return {
      success: false,
      step: "riskwrapper",
      error: "Riskwrapper failed",

      configPath,

      wrappercodeOutput:
        wrapperResult.stdout,

      wrappercodeError:
        wrapperResult.stderr,

      riskwrapperOutput:
        riskResult.stdout,

      riskwrapperError:
        riskResult.stderr,
    };
  }

  console.log(
    "Riskwrapper finished"
  );

  // ==============================================================
  // FIND RISK REPORT
  // ==============================================================

  const reportPath =
    latestRiskReport(
      path.join(
        riskwrapperDir,
        "output"
      )
    );

  if (!reportPath) {
    return {
      success: false,
      step: "risk_report",
      error:
        "Riskwrapper completed but risk_report_*.json was not found",

      downloadedFiles,
      configPath,

      wrappercodeOutput:
        wrapperResult.stdout,

      wrappercodeError:
        wrapperResult.stderr,

      riskwrapperOutput:
        riskResult.stdout,

      riskwrapperError:
        riskResult.stderr,
    };
  }

  console.log(
    "Risk report found:",
    reportPath
  );

  // ==============================================================
  // RESOLVED PATHS
  // ==============================================================

  const resolvedPaths = {
    bescomPdf:
      bescomPdfPath,

    ocPdf:
      getOCPath(),

    nocPdf:
      getPath([
        "noc",
      ]),

    parkingAgreement:
      getPath([
        "agreement",
      ]),

    parkingSiteplan:
      getPath([
        "site plan",
        "site",
      ]),

    bylawsInput:
      getBylawsInput(),

    ecPdf:
      getPath([
        "ec",
      ]),

    bankloanPdf:
      getPath([
        "cersai",
      ]),
  };

  // ==============================================================
  // READ RISK REPORT
  // ==============================================================

  const riskReport =
    JSON.parse(
      fs.readFileSync(
        reportPath,
        "utf-8"
      )
    );

  // ==============================================================
  // ADD MISSING CHECKS
  // THEN REMOVE EXPLICITLY EXCLUDED CHECKS
  // ==============================================================

  addNotApplicableChecks(
    riskReport,
    {
      ...params,
      excludedChecks,
    },
    resolvedPaths
  );

  // Final safety filter
  removeExcludedChecks(
    riskReport,
    excludedChecks
  );

  // ==============================================================
  // SAVE MERGED REPORT
  // ==============================================================

  const mergedReportPath =
    path.join(
      reportsDir,
      `merged_report_${Date.now()}.json`
    );

  fs.writeFileSync(
    mergedReportPath,
    JSON.stringify(
      riskReport,
      null,
      2
    )
  );

  // ==============================================================
  // GENERATE PDF
  // ==============================================================

  const pdfFilename =
    `final_due_diligence_${Date.now()}.pdf`;

  const pdfPath =
    path.join(
      reportsDir,
      pdfFilename
    );

  const pdfResult =
    await runProcess(
      PYTHON,
      [
        "generate_pdf_report.py",
        "--input",
        mergedReportPath,
        "--out",
        pdfPath,
        "--verbose",
      ],
      reportGenerationDir,
      "PDFGenerator"
    );

  if (!pdfResult.success) {
    return {
      success: false,
      step: "pdf_generation",
      error:
        "PDF generation failed",

      reportPath,
      mergedReportPath,
      pdfPath,

      pdfOutput:
        pdfResult.stdout,

      pdfError:
        pdfResult.stderr,
    };
  }

  console.log(
    "PDF generated:",
    pdfPath
  );

  // ==============================================================
  // RETURN RESULT
  // ==============================================================

  return {
    success: true,

    message:
      "Complete property analysis and PDF generation completed",

    reportPath,
    mergedReportPath,

    pdfPath,

    pdfUrl:
      `/reports/${pdfFilename}`,

    downloadedFiles,

    configPath,

    wrappercodeOutput:
      wrapperResult.stdout,

    wrappercodeError:
      wrapperResult.stderr,

    riskwrapperOutput:
      riskResult.stdout,

    riskwrapperError:
      riskResult.stderr,

    pdfOutput:
      pdfResult.stdout,

    pdfError:
      pdfResult.stderr,
  };
}