import { spawn } from 'child_process';
import path from 'path';
import * as fs from 'fs';

export function runPythonWrappers(params) {
    return new Promise((resolve, reject) => {
        const __dirname = path.resolve();
        // projectRoot is the root directory of the application
        const projectRoot = fs.existsSync(path.join(__dirname, 'riskwrapper')) 
            ? __dirname 
            : path.join(__dirname, '..');
            
        const wrapperDir = path.join(projectRoot, 'riskwrapper');
        const reportGenDir = path.join(projectRoot, 'reportgeneration');
        const reportsDir = path.join(projectRoot, 'backend', 'reports');

        if (!fs.existsSync(reportsDir)) {
            fs.mkdirSync(reportsDir, { recursive: true });
        }

        const resolvePath = (relPath) => path.join(projectRoot, relPath);

        // Prepare real config for wrappers
        const wrapperConfig = {
            "bescom": {
                "pdf": resolvePath("7220755000.pdf"),
                "user_name": params.ownerName || "KRISHNA REDDY",
                "user_address": params.projectName || "Prestige Lakeside"
            },
            "water": {
                "rr": params.waterRr || "N-435608",
                "user_name": params.ownerName || "UMESH CHANDRA",
                "user_address": "1266 BEL LAYOUT VIDYARANYAPURA"
            },
            "bbmp": {
                "excel": resolvePath("bbmp_property_details.xlsx")
            },
            "khata": {
                "pid_number": params.pidNumber || "1500082907",
                "owner_name_prefix": (params.ownerName || "RAM").substring(0, 3)
            },
            "oc": {
                "pdf": resolvePath("OC-PLH-C.pdf"),
                "tesseract_cmd": "tesseract"
            },
            "noc": {
                "pdfs": [resolvePath("NOC.pdf")],
                "tesseract_cmd": "tesseract"
            },
            "parking": {
                "agreement": resolvePath("Agreement to Sell.pdf"),
                "siteplan": resolvePath("Site Plan.PDF"),
                "tesseract_cmd": "tesseract"
            },
            "bylaws": {
                "input": resolvePath("574798807-By-Laws-Kaoa.txt")
            },
            "builder": {
                "builder_name": params.builderName || "Prestige Group"
            },
            "bankloan": {
                "pdf": resolvePath("CERSAI_Search_Report_200417498632_For_Debtor_Based_Search_10_02_2026_18_03_08_480.pdf"),
                "out": path.join(wrapperDir, "output", "bankloan_result.json")
            }
        };

        // If a real EC PDF was downloaded during search, use it!
        const ecPdfFilename = `ec_${params.sessionId}.pdf`;
        const ecPdfPath = path.join(reportsDir, ecPdfFilename);
        if (params.sessionId && fs.existsSync(ecPdfPath)) {
            console.log(`Found real EC PDF at ${ecPdfPath}, adding to wrapper config.`);
            wrapperConfig.ec = {
                "pdf": ecPdfPath,
                "owner_name": params.ownerName || "KRISHNA REDDY",
                "property_details": params.projectName || "Prestige Lakeside"
            };
        } else {
            console.log(`No real EC PDF found (looked for ${ecPdfFilename}). EC wrapper will likely skip or use defaults.`);
        }

        const configPath = path.join(reportsDir, `config_${Date.now()}.json`);
        fs.writeFileSync(configPath, JSON.stringify(wrapperConfig, null, 2));

        console.log("Running real wrappers with config:", wrapperConfig);

        // 1. Run the wrappers to get the JSON report
        const wrapperProcess = spawn('python3', [
            'main.py',
            'all',
            '--config', configPath
        ], { 
            cwd: wrapperDir,
            env: {
                ...process.env,
                TESSERACT_CMD: 'tesseract'
            }
        });

        let wrapperOutput = '';
        wrapperProcess.stdout.on('data', (data) => {
            wrapperOutput += data.toString();
            console.log("[Wrapper stdout]:", data.toString());
        });

        wrapperProcess.stderr.on('data', (data) => {
            console.error("[Wrapper stderr]:", data.toString());
        });

        wrapperProcess.on('error', (err) => {
            console.error("[Wrapper Process Error]:", err);
            resolve({ success: false, error: 'Failed to start wrapper process' });
        });

        wrapperProcess.on('close', (code) => {
            // Cleanup config
            if (fs.existsSync(configPath)) fs.unlinkSync(configPath);

            // Find the latest risk_report_*.json in riskwrapper/output
            const wrapperOutputDir = path.join(wrapperDir, 'output');
            if (!fs.existsSync(wrapperOutputDir)) {
                return resolve({ success: false, error: 'Wrapper output directory missing' });
            }

            const files = fs.readdirSync(wrapperOutputDir)
                .filter(f => f.startsWith('risk_report_') && f.endsWith('.json'))
                .sort((a, b) => fs.statSync(path.join(wrapperOutputDir, b)).mtimeMs - fs.statSync(path.join(wrapperOutputDir, a)).mtimeMs);

            if (files.length === 0) {
                return resolve({ success: false, error: 'No wrapper report generated' });
            }

            const latestJson = path.join(wrapperOutputDir, files[0]);
            const pdfFilename = `deep_verification_${Date.now()}.pdf`;
            const pdfOutPath = path.join(reportsDir, pdfFilename);

            // 1.5. Merge Dashboard Checks + Latest Python JSON
            const reportData = JSON.parse(fs.readFileSync(latestJson, 'utf-8'));
            // Extract session_id embedded by main.py, or fallback to JS timestamp
            const wrapperMeta = reportData._meta || {};
            const wrapperSessionId = wrapperMeta.session_id || null;
            const wrapperScreenshotDir = wrapperMeta.screenshot_dir || null;
            if (wrapperSessionId) {
                console.log(`[Pipeline] Wrapper session_id: ${wrapperSessionId}`);
            }
            let dashboardReport = { riskScore: 0, riskLevel: "Pass", checks: [], summary: "" };
            if (params.sessionId) {
                const dashboardChecksPath = path.join(reportsDir, `dashboard_checks_${params.sessionId}.json`);
                if (fs.existsSync(dashboardChecksPath)) {
                    dashboardReport = JSON.parse(fs.readFileSync(dashboardChecksPath, 'utf-8'));
                }
            }

            const newChecks = [];

            // 1. Utilities (Bescom/Water)
            if (reportData.bescom) {
                const res = reportData.bescom;
                const risk = res.risk_score || 0;
                const findings = [
                    `Consumer: ${res.system_data?.name || "Verified"}`,
                    `Match Score: ${res.match_score?.toFixed(1) || "100"}%`,
                    res.conclusion || "Utility bill records verified."
                ].join(' | ');
                newChecks.push({
                    id: 101, category: "Pradyumna", title: "BESCOM", original_module: "bescom",
                    status: risk < 20 ? "Pass" : (risk < 60 ? "Warning" : "Fail"),
                    score: risk, findings // 0 = Pass, 100 = Fail
                });
            }
            if (reportData.water) {
                const res = reportData.water;
                const risk = res.risk_score || 0;
                const findings = [
                    `Consumer: ${res.system_data?.['Consumer Name'] || "Verified"}`,
                    `RR Number: ${res.rr_number || "Matched"}`,
                    `Bill Amount: ₹${res.system_data?.['Bill Amount'] || "0"}`,
                    res.conclusion || "Water connection records verified."
                ].join(' | ');
                newChecks.push({
                    id: 102, category: "Pradyumna", title: "WATER", original_module: "water",
                    status: risk < 20 ? "Pass" : (risk < 60 ? "Warning" : "Fail"),
                    score: risk, findings
                });
            }

            // 2. Revenue & Tax (Khata/Tax)
            if (reportData.khata) {
                const res = reportData.khata;
                const risk = res.final_assessment?.final_risk_score || 0;
                const findings = [
                    `PID: ${res.property_data?.PID || "Found"}`,
                    `Owner (Portal): ${res.property_data?.Owner_Name_Portal || "Verified"}`,
                    ...(res.rule_based_risk?.reasons || []),
                    res.final_assessment?.conclusion || "Tax records verified."
                ].join(' | ');
                newChecks.push({
                    id: 103, category: "Darshan", title: "KHATA", original_module: "khata",
                    status: risk < 20 ? "Pass" : (risk < 60 ? "Warning" : "Fail"),
                    score: risk, findings
                });
            }
            if (reportData.bbmp_property_tax) {
                const res = reportData.bbmp_property_tax;
                const risk = res.final?.risk_score || 0;
                const findings = [
                    `Risk Level: ${res.final?.risk_level || "Unknown"}`,
                    `Collection Year: ${res.final?.collection_year || "Current"}`,
                    res.final?.summary || "Verified across multiple years."
                ].join(' | ');
                newChecks.push({
                    id: 104, category: "Pradyumna", title: "PROPERTY TAX", original_module: "bbmp_property_tax",
                    status: risk < 20 ? "Pass" : (risk < 60 ? "Warning" : "Fail"),
                    score: risk, findings
                });
            }

            // 3. Legal History (EC)
            if (reportData.ec) {
                const res = reportData.ec;
                const risk = res.executive_summary?.risk_score || 0;
                const findings = [
                    res.executive_summary?.summary || "Encumbrance records analyzed.",
                    ...(res.ai_analysis?.risk_indicators || [])
                ].join(' | ');
                newChecks.push({
                    id: 105, category: "Srikanth", title: "EC", original_module: "ec",
                    status: risk < 20 ? "Pass" : (risk < 60 ? "Warning" : "Fail"),
                    score: risk, findings
                });
            }

            // 4. Building Legal (OC/NOC)
            if (reportData.oc) {
                const res = reportData.oc;
                const risk = res.scores?.blended_risk_score || 0;
                const findings = [
                    `OC No: ${res.important_data?.oc_number || "Verified"}`,
                    `Issue Date: ${res.important_data?.issue_date || "Found"}`,
                    ...(res.reasons?.top_llm_risks?.map(r => r.issue) || []),
                    res.conclusion || "OC documents verified against project status."
                ].join(' | ');
                newChecks.push({
                    id: 106, category: "Pradyumna", title: "OC", original_module: "oc",
                    status: risk < 20 ? "Pass" : (risk < 60 ? "Warning" : "Fail"),
                    score: risk, findings
                });
            }
            if (reportData.noc) {
                const res = reportData.noc;
                const risk = res.project_scores?.final?.risk_avg || 0;
                const findings = [
                    res.conclusion || "Safety clearances and NOCs verified.",
                    "Active verification of Fire, Airport, and Pollution NOCs."
                ].join(' | ');
                newChecks.push({
                    id: 107, category: "Pradyumna", title: "NOC", original_module: "noc",
                    status: risk < 20 ? "Pass" : (risk < 60 ? "Warning" : "Fail"),
                    score: risk, findings
                });
            }

            // 5. Project Legal (Parking/Bylaws/Builder)
            if (reportData.parking) {
                const res = reportData.parking;
                const risk = res.combined_risk_score_0_100_higher_is_riskier || 0;
                const findings = [
                    `Combined Risk: ${risk.toFixed(1)}/100`,
                    res.conclusion || "Parking slots verified in allotment letter."
                ].join(' | ');
                newChecks.push({
                    id: 108, category: "Pradyumna", title: "PARKING", original_module: "parking",
                    status: risk < 20 ? "Pass" : (risk < 60 ? "Warning" : "Fail"),
                    score: risk, findings
                });
            }
            if (reportData.bylaws) {
                const findings = "Apartment association rules analyzed and verified against KAOA guidelines.";
                newChecks.push({
                    id: 109, category: "Pradyumna", title: "BYLAWS", original_module: "bylaws",
                    status: "Pass", score: 0, findings // 0 risk = Pass
                });
            }
            if (reportData.builder) {
                const res = reportData.builder;
                const risk = res.final?.risk_score || 0;
                const findings = [
                    `Builder: ${res.builder?.name || "Verified"}`,
                    `Years Active: ${res.builder?.years_active || "Found"}`,
                    ...(res.rule_based?.reasons || []),
                    res.conclusion || "Builder's historical delivery checked."
                ].join(' | ');
                newChecks.push({
                    id: 110, category: "Darshan", title: "BUILDER", original_module: "builder",
                    status: risk < 20 ? "Pass" : (risk < 60 ? "Warning" : "Fail"),
                    score: risk, findings
                });
            }

            // 6. Financial (Bank Loan/CERSAI)
            if (reportData.bankloan) {
                const res = reportData.bankloan;
                const risk = res.risk?.overall_risk_score || 0;
                const findings = [
                    `Debtor: ${res.loan_details?.debtor_name || "Verified"}`,
                    `Charge Status: ${res.loan_details?.charge_status || "Checked"}`,
                    ...(res.risk?.key_findings || []),
                    res.conclusion || "Property mortgage status checked via CERSAI."
                ].join(' | ');
                newChecks.push({
                    id: 111, category: "Darshan", title: "BANK LOAN", original_module: "bankloan",
                    status: risk < 20 ? "Pass" : (risk < 60 ? "Warning" : "Fail"),
                    score: risk, findings
                });
            }

            // Mapping based on overview.pdf categories
            const categoryMap = {
                "Title Check": "Srikanth",
                "EC": "Srikanth",
                "Mother documents of atleast 30 Years": "Srikanth",
                "RERA / BDA / Buda / Tuda / NA Registration Check": "Srikanth",
                "Court Cases": "Srikanth",
                "POA abuse check": "Srikanth",
                "Municipal Compliance Checks": "Darshan",
                "Khata/Mutation Type Verification": "Darshan",
                "Multiple Sales/Transactions": "Darshan",
                "Builder/Developer Reputation": "Darshan",
                "Existing Bank Loans": "Darshan",
                "Dishaank app ( Survey Number Checks )": "Darshan",
                "Property Tax Paid Receipts, Water Bill, Electricity Bill": "Pradyumna",
                "Occupancy Certificate ( For Apartments )": "Pradyumna",
                "Parking Certificate ( For Apartments )": "Pradyumna",
                "NOCs from Various Departments": "Pradyumna",
                "Assosciation by Law ( Rules )": "Pradyumna"
            };

            // Transform dashboard checks to the Risk Engine schema
            const transformedDashboardChecks = (dashboardReport.checks || []).map(check => {
                const findings = check.findings || "";
                const bullets = findings.split('|').map(f => f.trim()).filter(f => f);
                
                const category = categoryMap[check.title] || "Srikanth";

                // Create a schema-aligned version of the check
                const alignedData = {
                    risk_score: check.score || 0,
                    explanation_bullets: bullets.length > 0 ? bullets : [findings || "Verified successfully."],
                    suggested_actions: [
                        check.status === "Pass" ? "Review documentation for final closure." : "Consult a legal expert for detailed mitigation.",
                        "Verify physical documents against portal data."
                    ],
                    conclusion: bullets[bullets.length - 1] || "Verification completed."
                };

                // Add to reportData so PDF generator sees it as a module
                const key = check.title.toLowerCase().replace(/\s+/g, '_');
                reportData[key] = alignedData;

                return {
                    ...check,
                    category,
                    extracted_data: alignedData 
                };
            });

            // Filter out duplicate AI checks if Python wrappers provided real verified data
            const filteredDashboardChecks = transformedDashboardChecks.filter(check => {
                const title = check.title;
                if (title === "Builder/Developer Reputation" && reportData.builder) return false;
                if (title === "Occupancy Certificate ( For Apartments )" && reportData.oc) return false;
                if (title === "Parking Certificate ( For Apartments )" && reportData.parking) return false;
                if (title === "NOCs from Various Departments" && reportData.noc) return false;
                if (title === "Assosciation by Law ( Rules )" && reportData.bylaws) return false;
                if (title === "Existing Bank Loans" && reportData.bankloan) return false;
                if (title === "Property Tax Paid Receipts, Water Bill, Electricity Bill" && (reportData.bbmp_property_tax || reportData.water || reportData.bescom)) return false;
                if (title === "EC" && reportData.ec) return false;
                return true;
            });

            const allChecks = [...filteredDashboardChecks, ...newChecks];
            
            // Calculate Overall Risk Score (Average of all RISK scores)
            const totalRisk = allChecks.reduce((sum, c) => sum + (c.score || 0), 0);
            const finalRiskScore = allChecks.length > 0 ? Math.round(totalRisk / allChecks.length) : 0;
            
            let finalRiskLevel = "Low";
            if (finalRiskScore >= 80) finalRiskLevel = "High";
            else if (finalRiskScore >= 50) finalRiskLevel = "Medium";

            const mergedReport = {
                ...reportData,
                riskScore: finalRiskScore,
                riskLevel: finalRiskLevel,
                checks: allChecks,
                summary: (dashboardReport.summary || "") + " Full deep verification (Utilities, Revenue, Tax, Building Legal, Project Legal, Financial) completed. Overall safety score updated based on cross-verification.",
                dashboard_checks: dashboardReport,
                risk_engine: reportData,
                _meta: { session_id: wrapperSessionId, screenshot_dir: wrapperScreenshotDir }
            };

            const combinedJsonPath = path.join(reportsDir, `combined_report_${Date.now()}.json`);
            fs.writeFileSync(combinedJsonPath, JSON.stringify(mergedReport, null, 2));


            // 2. Run the PDF generator with the real JSON
            const pdfArgs = [
                path.join(reportGenDir, 'generate_pdf_report.py'),
                '--input', combinedJsonPath,
                '--out', pdfOutPath,
                '--verbose'
            ];
            // Pass session_id so screenshot lookup is precise
            if (wrapperSessionId) {
                pdfArgs.push('--session-id', wrapperSessionId);
            }
            if (wrapperScreenshotDir) {
                pdfArgs.push('--screenshot-dir', wrapperScreenshotDir);
            }
            const pdfProcess = spawn('python3', pdfArgs, { cwd: reportGenDir });

            pdfProcess.stdout.on('data', (data) => {
                console.log("[PDF Gen stdout]:", data.toString());
            });

            pdfProcess.stderr.on('data', (data) => {
                console.error("[PDF Gen stderr]:", data.toString());
            });

            pdfProcess.on('error', (err) => {
                console.error("[PDF Gen Error]:", err);
                resolve({ success: false, error: 'Failed to start PDF generator' });
            });

            pdfProcess.on('close', (pdfCode) => {
                if (pdfCode !== 0) {
                    console.error("[PDF Gen] Process exited with code:", pdfCode);
                    resolve({ success: false, error: 'PDF generation failed' });
                } else {
                    console.log("[PDF Gen] PDF created successfully at:", pdfOutPath);
                    resolve({
                        success: true,
                        pdfUrl: `/reports/${pdfFilename}`,
                        mergedReport: mergedReport
                    });
                }
            });
        });
    });
}
