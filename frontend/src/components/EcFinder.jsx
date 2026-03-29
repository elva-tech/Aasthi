import React, { useState } from 'react';
import axios from 'axios';
import { FileSearch, Search } from 'lucide-react';

const API_URL = 'http://localhost:5000/api';

const EcFinder = ({ sessionId, onEcFetched }) => {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const [formData, setFormData] = useState({
        propertyType: 'Non Agricultural',
        village: '',
        searchBy: 'Survey No',
        surveyNo: '',
        duration: '5 Year'
    });

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
    };

    const handleRadioChange = (name, value) => {
        setFormData(prev => ({ ...prev, [name]: value }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');

        // Basic validation
        if (!formData.village || !formData.surveyNo) {
            setError('Please fill out all mandatory fields (Village and Survey No)');
            return;
        }

        setLoading(true);
        try {
            const response = await axios.post(`${API_URL}/search`, {
                sessionId,
                searchDetails: formData
            });

            if (response.data.success) {
                onEcFetched(API_URL.replace('/api', '') + response.data.screenshotUrl, formData.propertyType);
            } else {
                setError(response.data.error || 'Failed to fetch EC');
            }
        } catch (err) {
            const respError = err.response?.data?.error;
            setError(`Search failed: ${respError || err.message}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="glass-panel glass-panel-large">
            <div className="step-header">
                <div className="search-icon-bg">
                    <FileSearch size={32} />
                </div>
                <h2>Search Encumbrance Certificate</h2>
                <p>Fill in property details to fetch the official EC document</p>
            </div>

            {loading ? (
                <div className="loader-container">
                    <div className="spinner"></div>
                    <h3 style={{ marginTop: '1rem', color: 'var(--text-primary)' }}>Fetching Official Records...</h3>
                    <p style={{ textAlign: 'center', maxWidth: '300px' }}>
                        We're navigating the Elva Asti portal and requesting your EC. This may take up to 30 seconds.
                    </p>
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
                        <label className="form-label">Property Type *</label>
                        <div className="radio-group" style={{ marginBottom: 0 }}>
                            <label className="radio-card">
                                <input
                                    type="radio"
                                    name="propertyType"
                                    value="Non Agricultural"
                                    checked={formData.propertyType === 'Non Agricultural'}
                                    onChange={() => handleRadioChange('propertyType', 'Non Agricultural')}
                                />
                                <div className="radio-content">Non Agricultural</div>
                            </label>
                            <label className="radio-card">
                                <input
                                    type="radio"
                                    name="propertyType"
                                    value="Agricultural"
                                    checked={formData.propertyType === 'Agricultural'}
                                    onChange={() => handleRadioChange('propertyType', 'Agricultural')}
                                />
                                <div className="radio-content">Agricultural</div>
                            </label>
                        </div>
                    </div>

                    <div className="form-grid">
                        <div className="form-group">
                            <label className="form-label">Village / Division *</label>
                            <input
                                type="text"
                                name="village"
                                className="form-input"
                                placeholder="e.g. Devanahalli"
                                value={formData.village}
                                onChange={handleChange}
                                required
                            />
                        </div>

                        <div className="form-group">
                            <label className="form-label">Search By *</label>
                            <select
                                name="searchBy"
                                className="form-select"
                                value={formData.searchBy}
                                onChange={handleChange}
                            >
                                <option value="Survey No">Survey No</option>
                                <option value="Party Name">Party Name</option>
                                <option value="Flat No">Flat No</option>
                            </select>
                        </div>
                    </div>

                    <div className="form-group">
                        <label className="form-label">{formData.searchBy} *</label>
                        <input
                            type="text"
                            name="surveyNo"
                            className="form-input"
                            placeholder={`Enter ${formData.searchBy}`}
                            value={formData.surveyNo}
                            onChange={handleChange}
                            required
                        />
                    </div>

                    <div className="form-group">
                        <label className="form-label">Duration *</label>
                        <div className="radio-group" style={{ flexWrap: 'wrap', gap: '0.5rem' }}>
                            {['5 Year', '13 Year', '20 Year', 'Custom'].map(dur => (
                                <label className="radio-card" style={{ minWidth: 'calc(25% - 0.5rem)' }} key={dur}>
                                    <input
                                        type="radio"
                                        name="duration"
                                        value={dur}
                                        checked={formData.duration === dur}
                                        onChange={() => handleRadioChange('duration', dur)}
                                    />
                                    <div className="radio-content" style={{ padding: '0.75rem' }}>{dur}</div>
                                </label>
                            ))}
                        </div>
                    </div>

                    <div style={{ marginTop: '2rem' }}>
                        <button type="submit" className="btn btn-primary">
                            <Search size={18} /> Search EC Document
                        </button>
                    </div>
                </form>
            )}
        </div>
    );
};

export default EcFinder;
