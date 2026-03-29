import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { DownloadCloud, RotateCcw, Image, CheckCircle, ShieldAlert, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';

const ResultCard = ({ sessionId, imageUrl, propertyType, onReset }) => {
    const [aiReport, setAiReport] = useState(null);
    const [loadingAi, setLoadingAi] = useState(true);
    const [aiError, setAiError] = useState(null);

    const [showDeepScrape, setShowDeepScrape] = useState(false);
    const [scrapeLoading, setScrapeLoading] = useState(false);
    const [scrapeData, setScrapeData] = useState({
        projectName: 'Prestige Lakeside Habitat',
        bescomId: '7220755000',
        waterRr: 'N-435608',
        pidNumber: '1500082907',
        ownerName: 'RAM'
    });

    useEffect(() => {
        const fetchAiAnalysis = async () => {
            if (!sessionId) {
                setLoadingAi(false);
                setAiError("Session ID missing. Cannot perform AI analysis.");
                return;
            }

            try {
                // Endpoint handles the analysis using the screenshot saved with sessionId and the property type
                const response = await axios.post('http://localhost:5000/api/analyze-ec', { sessionId, propertyType });
                if (response.data.success) {
                    setAiReport(response.data.report);
                } else {
                    setAiError(response.data.error || "Failed to analyze document.");
                }
            } catch (err) {
                console.error("AI Analysis Error:", err);
                setAiError(err.response?.data?.error || "Error connecting to AI service.");
            } finally {
                setLoadingAi(false);
            }
        };

        fetchAiAnalysis();
    }, [sessionId]);

    const renderStatusIcon = (status) => {
        if (!status) return null;
        const normalized = status.toLowerCase();
        if (normalized.includes('pass') || normalized.includes('low')) {
            return <CheckCircle2 size={20} color="var(--success)" />;
        }
        if (normalized.includes('fail') || normalized.includes('high')) {
            return <XCircle size={20} color="var(--error)" />;
        }
        return <AlertTriangle size={20} color="orange" />;
    };

    const handleDeepScrape = async () => {
        setScrapeLoading(true);
        try {
            const response = await axios.post('http://localhost:5000/api/run-wrappers', { ...scrapeData, sessionId });
            if (response.data.success) {
                if (response.data.pdfUrl) {
                    const link = document.createElement('a');
                    link.href = `http://localhost:5000${response.data.pdfUrl}`;
                    link.download = `Deep_Verification_Report.pdf`;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                }

                // The backend now provides a fully merged `mergedReport` in the exact same format
                if (response.data.mergedReport) {
                    setAiReport(response.data.mergedReport);
                }
                setShowDeepScrape(false);
            }
        } catch (err) {
            alert('Failed to run deep scrape: ' + err.message);
        } finally {
            setScrapeLoading(false);
        }
    };

    return (
        <div className="glass-panel glass-panel-large" style={{ maxWidth: '1200px' }}>
            <div className="step-header">
                <div className="search-icon-bg" style={{ background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(52, 211, 153, 0.2))', borderColor: 'rgba(16, 185, 129, 0.5)', color: '#10b981' }}>
                    <CheckCircle size={32} />
                </div>
                <h2>EC Fetched Successfully</h2>
                <p>Your official Encumbrance Certificate snapshot is ready for review.</p>
            </div>

            <div className="result-container">
                <div className="result-image-section">
                    <div className="result-image-container" style={{ marginTop: 0 }}>
                        {imageUrl ? (
                            <img
                                src={imageUrl}
                                alt="Encumbrance Certificate Result"
                                className="result-image"
                                style={{ width: '100%', minHeight: '300px', objectFit: 'contain', backgroundColor: '#fff' }}
                                onError={(e) => {
                                    e.target.onerror = null;
                                    e.target.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="300" background="#f3f4f6"><text x="50%" y="50%" font-family="sans-serif" font-size="20px" fill="#ef4444" text-anchor="middle">Failed to load result image</text></svg>';
                                }}
                            />
                        ) : (
                            <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                                <Image size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                                <p>No image URL provided</p>
                            </div>
                        )}
                    </div>

                    <div style={{ display: 'flex', gap: '1rem', marginTop: '1.5rem', flexWrap: 'wrap' }}>
                        <a
                            href={imageUrl || '#'}
                            download="ec-certificate.png"
                            className="btn btn-primary"
                            style={{ flex: 1, textDecoration: 'none', minWidth: '200px' }}
                        >
                            <DownloadCloud size={18} /> Download Image
                        </a>

                        {aiReport && (
                            <button
                                onClick={async () => {
                                    try {
                                        const res = await axios.post('http://localhost:5000/api/generate-pdf', { sessionId, aiReport });
                                        if (res.data.success) {
                                            // The backend now securely sets Content-Disposition: attachment,
                                            // so we can rely purely on the browser's native flawless download manager
                                            // without manually parsing blobs.
                                            const link = document.createElement('a');
                                            link.href = `http://localhost:5000${res.data.pdfUrl}`;
                                            link.download = `Verification_Report_${sessionId}.pdf`;
                                            document.body.appendChild(link);
                                            link.click();
                                            document.body.removeChild(link);
                                        }
                                    } catch (err) {
                                        alert('Failed to generate PDF Report');
                                        console.error(err);
                                    }
                                }}
                                className="btn btn-primary"
                                style={{ flex: 1, backgroundColor: '#4F46E5', borderColor: '#4F46E5', minWidth: '200px' }}
                            >
                                <DownloadCloud size={18} /> Download PDF Report
                            </button>
                        )}

                        <button
                            onClick={() => setShowDeepScrape(true)}
                            className="btn btn-secondary"
                            style={{ flex: 1, backgroundColor: '#10b981', color: '#fff', borderColor: '#10b981', minWidth: '200px' }}
                        >
                            <ShieldAlert size={18} /> Deep Background Check
                        </button>

                        <button
                            onClick={onReset}
                            className="btn btn-secondary"
                            style={{ flex: 1, minWidth: '200px' }}
                        >
                            <RotateCcw size={18} /> Search Another
                        </button>
                    </div>
                </div>

                <div className="verification-list">
                    <h3><ShieldAlert size={20} /> AI Risk Assessment</h3>

                    {loadingAi ? (
                        <div className="loader-container" style={{ padding: '4rem 0' }}>
                            <div className="spinner" style={{ width: '32px', height: '32px', borderWidth: '3px' }}></div>
                            <p style={{ fontSize: '0.9rem', marginTop: '1rem' }}>Gemini AI is analyzing the Kannada document...</p>
                        </div>
                    ) : aiError ? (
                        <div className="error-msg" style={{ margin: '1rem 0' }}>
                            <span className="error-icon">⚠</span>
                            {aiError}
                        </div>
                    ) : aiReport ? (
                        <>
                            <div className="risk-score-card" style={{
                                padding: '1.5rem',
                                borderRadius: '12px',
                                background: 'rgba(0,0,0,0.2)',
                                border: '1px solid var(--border-color)',
                                marginBottom: '1.5rem',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between'
                            }}>
                                <div>
                                    <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1px' }}>Overall Risk Score</span>
                                    <div style={{ fontSize: '2.5rem', fontWeight: 'bold', color: aiReport.riskScore > 50 ? 'var(--error)' : 'var(--success)' }}>
                                        {aiReport.riskScore} <span style={{ fontSize: '1rem', color: 'var(--text-muted)', fontWeight: 'normal' }}>/ 100</span>
                                    </div>
                                </div>
                                <div style={{
                                    padding: '0.5rem 1.5rem',
                                    borderRadius: '50px',
                                    fontWeight: '600',
                                    background: aiReport.riskLevel === 'Low' ? 'rgba(16, 185, 129, 0.1)' : aiReport.riskLevel === 'High' ? 'rgba(239, 68, 68, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                                    color: aiReport.riskLevel === 'Low' ? 'var(--success)' : aiReport.riskLevel === 'High' ? 'var(--error)' : 'orange',
                                    border: `1px solid ${aiReport.riskLevel === 'Low' ? 'rgba(16, 185, 129, 0.3)' : aiReport.riskLevel === 'High' ? 'rgba(239, 68, 68, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`
                                }}>
                                    {aiReport.riskLevel} Risk
                                </div>
                            </div>

                            <p style={{ marginBottom: '1.5rem', fontSize: '0.95rem', lineHeight: '1.5' }}>
                                <strong>AI Summary:</strong> {aiReport.summary}
                            </p>

                            <div className="checks-container">
                                <h4 style={{
                                    marginBottom: '1rem',
                                    paddingBottom: '0.5rem',
                                    borderBottom: '1px solid var(--border-color)',
                                    color: 'var(--primary-color)',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '0.5rem'
                                }}>
                                    <ShieldAlert size={16} /> Verification Details
                                </h4>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                    {aiReport.checks && aiReport.checks.map((check) => (
                                                <div key={check.id} className="check-item" style={{ alignItems: 'flex-start', background: 'rgba(255,255,255,0.02)', padding: '1rem', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
                                                    <div style={{ marginTop: '2px' }}>
                                                        {renderStatusIcon(check.status)}
                                                    </div>
                                                    <div className="check-text" style={{ flex: 1, marginLeft: '0.75rem' }}>
                                                        <strong style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                                                            {check.title}
                                                            <span style={{
                                                                fontSize: '0.7rem',
                                                                padding: '2px 8px',
                                                                borderRadius: '12px',
                                                                background: check.status.toLowerCase() === 'pass' ? 'rgba(16, 185, 129, 0.1)' : check.status.toLowerCase() === 'fail' ? 'rgba(239, 68, 68, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                                                                color: check.status.toLowerCase() === 'pass' ? 'var(--success)' : check.status.toLowerCase() === 'fail' ? 'var(--error)' : 'orange',
                                                                border: `1px solid ${check.status.toLowerCase() === 'pass' ? 'rgba(16, 185, 129, 0.3)' : check.status.toLowerCase() === 'fail' ? 'rgba(239, 68, 68, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`
                                                            }}>{check.status}</span>
                                                        </strong>
                                                        <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'block', marginTop: '6px', lineHeight: '1.4' }}>
                                                            {check.findings}
                                                        </span>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                        </>
                    ) : null}
                </div>
            </div>

            {showDeepScrape && (
                <div style={{
                    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
                    backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex',
                    alignItems: 'center', justifyContent: 'center', zIndex: 9999
                }}>
                    <div className="glass-panel" style={{ width: '500px', backgroundColor: '#1f2937', border: '1px solid #374151' }}>
                        <h3 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <ShieldAlert size={20} color="#10b981" /> Government Portal Verification
                        </h3>
                        <p style={{ fontSize: '0.9rem', color: '#9ca3af', marginBottom: '1.5rem' }}>
                            Enter the property identification numbers to automatically scrape and verify bills and taxes.
                        </p>

                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1.5rem' }}>
                            <input type="text" className="form-input" placeholder="Project Name (e.g. Prestige Lakeside)"
                                value={scrapeData.projectName} onChange={e => setScrapeData({ ...scrapeData, projectName: e.target.value })} />

                            <input type="text" className="form-input" placeholder="BESCOM Account ID"
                                value={scrapeData.bescomId} onChange={e => setScrapeData({ ...scrapeData, bescomId: e.target.value })} />

                            <input type="text" className="form-input" placeholder="Water RR Number"
                                value={scrapeData.waterRr} onChange={e => setScrapeData({ ...scrapeData, waterRr: e.target.value })} />

                            <input type="text" className="form-input" placeholder="PID Number"
                                value={scrapeData.pidNumber} onChange={e => setScrapeData({ ...scrapeData, pidNumber: e.target.value })} />

                            <input type="text" className="form-input" placeholder="Owner Name"
                                value={scrapeData.ownerName} onChange={e => setScrapeData({ ...scrapeData, ownerName: e.target.value })} />
                        </div>

                        <div style={{ display: 'flex', gap: '1rem' }}>
                            <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setShowDeepScrape(false)} disabled={scrapeLoading}>
                                Cancel
                            </button>
                            <button className="btn btn-primary" style={{ flex: 1, backgroundColor: '#10b981', borderColor: '#10b981' }}
                                onClick={handleDeepScrape} disabled={scrapeLoading}>
                                {scrapeLoading ? 'Running Scrapers...' : 'Run Scrapers'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default ResultCard;
