import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import {
  DownloadCloud,
  RotateCcw,
  CheckCircle,
  ShieldAlert,
  Loader2,
} from "lucide-react";

const ResultCard = ({ propertyDetails, onReset }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pdfUrl, setPdfUrl] = useState("");
  const [report, setReport] = useState(null);
  const hasStarted = useRef(false);

  useEffect(() => {
    if (hasStarted.current) return;
    hasStarted.current = true;

    const runAnalysis = async () => {
      try {
        setLoading(true);
        setError("");

        const response = await axios.post(
          "http://localhost:5000/api/analyze-property",
          propertyDetails
        );

        if (!response.data.success) {
          throw new Error(response.data.error || "Analysis failed");
        }

        if (response.data.pdfUrl) {
          setPdfUrl(`http://localhost:5000${response.data.pdfUrl}`);
        }

        if (response.data.report) {
          setReport(response.data.report);
        }
      } catch (err) {
        setError(
          err?.response?.data?.error ||
            err?.message ||
            "Failed to run analysis"
        );
      } finally {
        setLoading(false);
      }
    };

    runAnalysis();
  }, [propertyDetails]);

  return (
    <div className="glass-panel glass-panel-large" style={{ maxWidth: "1200px" }}>
      <div className="step-header">
        <div
          className="search-icon-bg"
          style={{
            background:
              "linear-gradient(135deg, rgba(16,185,129,0.2), rgba(52,211,153,0.2))",
            borderColor: "rgba(16,185,129,0.5)",
            color: "#10b981",
          }}
        >
          {loading ? (
            <Loader2 size={32} className="animate-spin" />
          ) : (
            <CheckCircle size={32} />
          )}
        </div>

        <h2>
          {loading ? "Property Analysis Running" : "Property Analysis Complete"}
        </h2>
        <p>
          {loading
            ? "Collecting records, running risk checks, and preparing your report."
            : "Your verification report is ready."}
        </p>
      </div>

      <div className="result-body">
        {loading && (
          <div className="loader-container">
            <Loader2 size={48} className="animate-spin" />
            <ul className="loading-steps">
              <li>Gathering property documents…</li>
              <li>Running risk checks…</li>
              <li>Generating PDF report…</li>
            </ul>
          </div>
        )}

        {!loading && error && (
          <div className="error-panel">
            <h3>Analysis Failed</h3>
            <p>{error}</p>
            <button onClick={onReset} className="btn btn-secondary" type="button">
              <RotateCcw size={18} />
              Try Again
            </button>
          </div>
        )}

        {!loading && !error && (
          <>
            <div className="verification-list result-summary-card">
              <h3>
                <ShieldAlert size={20} />
                Property Risk Report
              </h3>

              {report?.riskScore && (
                <h2 className="risk-score">Risk Score: {report.riskScore}</h2>
              )}

              {report?.summary ? (
                <p>{report.summary}</p>
              ) : (
                <p>Report generated successfully.</p>
              )}
            </div>

            <div className="result-actions">
              {pdfUrl && (
                <a
                  href={pdfUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-primary"
                  style={{ minWidth: 220, textDecoration: "none" }}
                >
                  <DownloadCloud size={18} />
                  Download PDF Report
                </a>
              )}

              <button
                type="button"
                onClick={onReset}
                className="btn btn-secondary"
                style={{ minWidth: 220 }}
              >
                <RotateCcw size={18} />
                Analyze Another Property
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default ResultCard;
