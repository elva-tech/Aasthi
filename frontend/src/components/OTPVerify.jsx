import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { KeyRound, CheckCircle2, RefreshCw } from 'lucide-react';

const API_URL = 'http://localhost:5000/api';

const OTPVerify = ({ sessionId, phoneNumber, onOTPVerified }) => {
    const [otp, setOtp] = useState(['', '', '', '', '', '']);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const inputRefs = useRef([]);

    useEffect(() => {
        if (inputRefs.current[0]) {
            inputRefs.current[0].focus();
        }
    }, []);

    const handleChange = (index, value) => {
        if (isNaN(value)) return;

        const newOtp = [...otp];
        newOtp[index] = value;
        setOtp(newOtp);

        // Auto focus next input
        if (value !== '' && index < 5) {
            inputRefs.current[index + 1].focus();
        }
    };

    const handleKeyDown = (index, e) => {
        if (e.key === 'Backspace' && !otp[index] && index > 0) {
            inputRefs.current[index - 1].focus();
        }
    };

    const handlePaste = (e) => {
        e.preventDefault();
        const pastedData = e.clipboardData.getData('text').slice(0, 6).split('');
        if (pastedData.some(isNaN)) return;

        const newOtp = [...otp];
        pastedData.forEach((value, idx) => {
            if (idx < 6) newOtp[idx] = value;
        });
        setOtp(newOtp);

        // Focus last filled input
        const focusIndex = Math.min(pastedData.length, 5);
        inputRefs.current[focusIndex].focus();
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        const otpValue = otp.join('');

        if (otpValue.length < 6) {
            setError('Please enter the complete 6-digit OTP');
            return;
        }

        setLoading(true);
        try {
            const response = await axios.post(`${API_URL}/verify-otp`, {
                sessionId,
                otp: otpValue
            });

            if (response.data.success) {
                onOTPVerified();
            } else {
                setError(response.data.error || 'Invalid OTP');
            }
        } catch (err) {
            setError(err.response?.data?.error || 'Verification failed');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="glass-panel">
            <div className="step-header">
                <div className="search-icon-bg">
                    <KeyRound size={32} />
                </div>
                <h2>Verify OTP</h2>
                <p>Enter the 6-digit code sent to +91 {phoneNumber}</p>
            </div>

            {loading ? (
                <div className="loader-container">
                    <div className="spinner"></div>
                    <p>Verifying with Elva Asti...</p>
                </div>
            ) : (
                <form onSubmit={handleSubmit}>
                    {error && (
                        <div className="error-msg">
                            <span className="error-icon">⚠</span>
                            {error}
                        </div>
                    )}

                    <div className="form-group" style={{ textAlign: 'center' }}>
                        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center', marginBottom: '1.5rem' }}>
                            {otp.map((digit, index) => (
                                <input
                                    key={index}
                                    ref={el => inputRefs.current[index] = el}
                                    type="text"
                                    maxLength={1}
                                    value={digit}
                                    onChange={(e) => handleChange(index, e.target.value)}
                                    onKeyDown={(e) => handleKeyDown(index, e)}
                                    onPaste={handlePaste}
                                    className="form-input"
                                    style={{
                                        width: '3rem',
                                        height: '3.5rem',
                                        textAlign: 'center',
                                        fontSize: '1.25rem',
                                        padding: '0',
                                        fontWeight: '600'
                                    }}
                                    disabled={loading}
                                />
                            ))}
                        </div>
                    </div>

                    <button type="submit" className="btn btn-primary" disabled={loading || otp.join('').length < 6}>
                        Verify & Continue <CheckCircle2 size={18} />
                    </button>

                    <div style={{ textAlign: 'center', marginTop: '1.5rem' }}>
                        <button
                            type="button"
                            className="btn btn-secondary"
                            style={{ padding: '0.5rem 1rem', fontSize: '0.875rem', width: 'auto' }}
                            disabled={loading}
                        >
                            <RefreshCw size={14} /> Resend OTP
                        </button>
                    </div>
                </form>
            )}
        </div>
    );
};

export default OTPVerify;
