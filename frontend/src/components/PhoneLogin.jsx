import React, { useState } from 'react';
import axios from 'axios';
import { Smartphone, ArrowRight, ShieldCheck } from 'lucide-react';

const API_URL = 'http://localhost:5000/api';

const PhoneLogin = ({ onLoginInitiated }) => {
    const [phoneNumber, setPhoneNumber] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');

        if (!phoneNumber || phoneNumber.length < 10) {
            setError('Please enter a valid 10-digit phone number');
            return;
        }

        setLoading(true);
        try {
            // Initiate Playwright session on backend
            const response = await axios.post(`${API_URL}/login`, { phoneNumber });
            if (response.data.success) {
                onLoginInitiated(phoneNumber, response.data.sessionId);
            } else {
                setError(response.data.error || 'Failed to initiate login');
            }
        } catch (err) {
            setError(err.response?.data?.error || 'Server error connecting to backend');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="glass-panel">
            <div className="step-header">
                <div className="search-icon-bg">
                    <ShieldCheck size={32} />
                </div>
                <h2>Secure Access</h2>
                <p>Enter your phone number to access Elva Asti records</p>
            </div>

            {loading ? (
                <div className="loader-container">
                    <div className="spinner"></div>
                    <p>Connecting to Elva Asti platform...</p>
                </div>
            ) : (
                <form onSubmit={handleSubmit}>
                    {error && (
                        <div className="error-msg">
                            <span className="error-icon">⚠</span>
                            {error}
                        </div>
                    )}

                    <div className="form-group">
                        <label className="form-label" htmlFor="phone">Phone Number</label>
                        <div style={{ position: 'relative' }}>
                            <div style={{ position: 'absolute', left: '1rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}>
                                <Smartphone size={20} />
                            </div>
                            <input
                                id="phone"
                                type="tel"
                                className="form-input"
                                placeholder="e.g. 9876543210"
                                value={phoneNumber}
                                onChange={(e) => setPhoneNumber(e.target.value.replace(/\D/g, '').slice(0, 10))}
                                style={{ paddingLeft: '3rem' }}
                                disabled={loading}
                            />
                        </div>
                    </div>

                    <button type="submit" className="btn btn-primary" disabled={loading || phoneNumber.length < 10}>
                        Get OTP <ArrowRight size={18} />
                    </button>
                </form>
            )}
        </div>
    );
};

export default PhoneLogin;
