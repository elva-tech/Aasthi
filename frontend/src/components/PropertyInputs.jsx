import React, { useState } from "react";
import { Building2, ArrowRight, ArrowLeft } from "lucide-react";

const PROPERTY_TYPES = [
  "Apartment",
  "Site",
  "Individual House",
  "Farm Land",
];

export const CHECK_RULES = {
  Apartment: {
    exclude: [
      "Electricity Bill",
      "Water Bill",
      "Property Tax Paid Receipts",
      "Title Check",
      "Existing Bank Loans",
      "Khata/Mutation Type Verification",
    ],
  },

  Site: {
    exclude: [
      "Occupancy Certificate",
      "Parking Certificate",
      "Association By Laws",

      "Electricity Bill",
      "Water Bill",
      "Property Tax Paid Receipts",
      "Title Check",
      "Existing Bank Loans",
      "Khata/Mutation Type Verification",
    ],
  },

  "Individual House": {
    exclude: [
      "Parking Certificate",
      "Association By Laws",

      "Electricity Bill",
      "Water Bill",
      "Property Tax Paid Receipts",
      "Title Check",
      "Existing Bank Loans",
      "Khata/Mutation Type Verification",
    ],
  },

  "Farm Land": {
    exclude: [
      "Occupancy Certificate",
      "Parking Certificate",
      "Association By Laws",
      "Builder/Developer Reputation",
      "RERA / BDA / Buda / Tuda / NA Registration Check",
      "NOCs from Various Departments",

      "Electricity Bill",
      "Water Bill",
      "Property Tax Paid Receipts",
      "Title Check",
      "Existing Bank Loans",
      "Khata/Mutation Type Verification",
    ],
  },
};

function PropertyInputs({ onSubmit, onBack }) {
  const [formData, setFormData] = useState({
    propertyType: "Apartment",

    projectName: "",
    builderName: "",
    ownerName: "",
    address: "",

    pidNumber: "",
    epidNumber: "",

    bescomId: "",
    waterRr: "",

    applicationNumber: "",

    district: "",
    taluka: "",
    hobli: "",
    village: "",

    propertyNo: "",

    courtPartyName: "",
    courtYear: "",
  });

  const handleChange = (e) => {
    const { name, value } = e.target;

    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    onSubmit({
      ...formData,

      excludedChecks:
        CHECK_RULES[formData.propertyType]?.exclude || [],
    });
  };

  const isApartment =
    formData.propertyType === "Apartment";

  const isSite =
    formData.propertyType === "Site";

  const isHouse =
    formData.propertyType === "Individual House";

  const isAgricultural =
    formData.propertyType === "Farm Land";

  return (
    <div
      className="glass-panel glass-panel-large"
      style={{ maxWidth: "900px" }}
    >
      {onBack && (
        <button
          type="button"
          className="btn-back"
          onClick={onBack}
        >
          <ArrowLeft size={18} />
          Back
        </button>
      )}

      <div className="step-header">
        <div className="search-icon-bg">
          <Building2 size={32} />
        </div>

        <h2>Property Details</h2>

        <p>
          Enter available property details. You can leave
          unknown fields blank and continue.
        </p>
      </div>

      <form onSubmit={handleSubmit}>

        {/* =====================================================
            PROPERTY TYPE
        ====================================================== */}

        <div className="form-group">
          <label className="form-label">
            Property Type
          </label>

          <div
            className="radio-group"
            style={{ flexWrap: "wrap" }}
          >
            {PROPERTY_TYPES.map((type) => (
              <label
                className="radio-card"
                key={type}
              >
                <input
                  type="radio"
                  name="propertyType"
                  value={type}
                  checked={
                    formData.propertyType === type
                  }
                  onChange={handleChange}
                />

                <div className="radio-content">
                  {type}
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* =====================================================
            APARTMENT
            ONLY:
            - Project Name
            - Builder Name
            - Court Party Name
            - Court Year
        ====================================================== */}

        {isApartment && (
          <>
            <div className="form-grid">

              {/* PROJECT NAME */}
              <div className="form-group">
                <label className="form-label">
                  Project Name
                </label>

                <input
                  type="text"
                  name="projectName"
                  className="form-input"
                  placeholder="e.g. Prestige Lakeside Habitat"
                  value={formData.projectName}
                  onChange={handleChange}
                />
              </div>

              {/* BUILDER NAME */}
              <div className="form-group">
                <label className="form-label">
                  Builder Name
                </label>

                <input
                  type="text"
                  name="builderName"
                  className="form-input"
                  placeholder="e.g. Prestige Group"
                  value={formData.builderName}
                  onChange={handleChange}
                />
              </div>

              {/* COURT PARTY NAME */}
              <div className="form-group">
                <label className="form-label">
                  Legal Name
                </label>

                <input
                  type="text"
                  name="courtPartyName"
                  className="form-input"
                  placeholder="Optional"
                  value={formData.courtPartyName}
                  onChange={handleChange}
                />
              </div>

              {/* COURT YEAR */}
              <div className="form-group">
                <label className="form-label">
                  Start Year of Project
                </label>

                <input
                  type="text"
                  name="courtYear"
                  className="form-input"
                  placeholder="e.g. 2015"
                  value={formData.courtYear}
                  onChange={handleChange}
                />
              </div>

            </div>
          </>
        )}

        {/* =====================================================
            SITE
            Keep the other fields for Site
        ====================================================== */}

        {isSite && (
          <>
            <div className="form-grid">

              <div className="form-group">
                <label className="form-label">
                  Owner Name
                </label>

                <input
                  type="text"
                  name="ownerName"
                  className="form-input"
                  placeholder="e.g. RAM"
                  value={formData.ownerName}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  PID Number
                </label>

                <input
                  type="text"
                  name="pidNumber"
                  className="form-input"
                  placeholder="e.g. 1500082907"
                  value={formData.pidNumber}
                  onChange={handleChange}
                />
              </div>

            </div>

            <div className="form-group">
              <label className="form-label">
                Property Address
              </label>

              <textarea
                name="address"
                className="form-input"
                placeholder="Enter property address"
                value={formData.address}
                onChange={handleChange}
                rows={3}
                style={{ resize: "vertical" }}
              />
            </div>

            <div className="form-grid">

              <div className="form-group">
                <label className="form-label">
                  District
                </label>

                <input
                  type="text"
                  name="district"
                  className="form-input"
                  value={formData.district}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Taluka
                </label>

                <input
                  type="text"
                  name="taluka"
                  className="form-input"
                  value={formData.taluka}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Hobli
                </label>

                <input
                  type="text"
                  name="hobli"
                  className="form-input"
                  value={formData.hobli}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Village
                </label>

                <input
                  type="text"
                  name="village"
                  className="form-input"
                  value={formData.village}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Property Number
                </label>

                <input
                  type="text"
                  name="propertyNo"
                  className="form-input"
                  placeholder="e.g. 45"
                  value={formData.propertyNo}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Legal Name
                </label>

                <input
                  type="text"
                  name="courtPartyName"
                  className="form-input"
                  placeholder="Optional"
                  value={formData.courtPartyName}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Start Year of Project
                </label>

                <input
                  type="text"
                  name="courtYear"
                  className="form-input"
                  placeholder="e.g. 2015"
                  value={formData.courtYear}
                  onChange={handleChange}
                />
              </div>

            </div>
          </>
        )}

        {/* =====================================================
            INDIVIDUAL HOUSE
        ====================================================== */}

        {isHouse && (
          <>
            <div className="form-grid">

              <div className="form-group">
                <label className="form-label">
                  Owner Name
                </label>

                <input
                  type="text"
                  name="ownerName"
                  className="form-input"
                  placeholder="e.g. RAM"
                  value={formData.ownerName}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  PID Number
                </label>

                <input
                  type="text"
                  name="pidNumber"
                  className="form-input"
                  placeholder="e.g. 1500082907"
                  value={formData.pidNumber}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  BESCOM Account ID
                </label>

                <input
                  type="text"
                  name="bescomId"
                  className="form-input"
                  value={formData.bescomId}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Water RR Number
                </label>

                <input
                  type="text"
                  name="waterRr"
                  className="form-input"
                  value={formData.waterRr}
                  onChange={handleChange}
                />
              </div>

            </div>

            <div className="form-group">
              <label className="form-label">
                Property Address
              </label>

              <textarea
                name="address"
                className="form-input"
                placeholder="Enter property address"
                value={formData.address}
                onChange={handleChange}
                rows={3}
                style={{ resize: "vertical" }}
              />
            </div>

            <div className="form-grid">

              <div className="form-group">
                <label className="form-label">
                  District
                </label>

                <input
                  type="text"
                  name="district"
                  className="form-input"
                  value={formData.district}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Taluka
                </label>

                <input
                  type="text"
                  name="taluka"
                  className="form-input"
                  value={formData.taluka}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Hobli
                </label>

                <input
                  type="text"
                  name="hobli"
                  className="form-input"
                  value={formData.hobli}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Village
                </label>

                <input
                  type="text"
                  name="village"
                  className="form-input"
                  value={formData.village}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Property Number
                </label>

                <input
                  type="text"
                  name="propertyNo"
                  className="form-input"
                  value={formData.propertyNo}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Legal Name
                </label>

                <input
                  type="text"
                  name="courtPartyName"
                  className="form-input"
                  value={formData.courtPartyName}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Start Year of Project
                </label>

                <input
                  type="text"
                  name="courtYear"
                  className="form-input"
                  value={formData.courtYear}
                  onChange={handleChange}
                />
              </div>

            </div>
          </>
        )}

        {/* =====================================================
            AGRICULTURAL
        ====================================================== */}

        {isAgricultural && (
          <>
            <div className="form-group">
              <label className="form-label">
                Property Number
              </label>

              <input
                type="text"
                name="propertyNo"
                className="form-input"
                placeholder="e.g. 45"
                value={formData.propertyNo}
                onChange={handleChange}
              />
            </div>

            <div className="form-grid">

              <div className="form-group">
                <label className="form-label">
                  Legal Name
                </label>

                <input
                  type="text"
                  name="courtPartyName"
                  className="form-input"
                  placeholder="Optional"
                  value={formData.courtPartyName}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Start Year of Project
                </label>

                <input
                  type="text"
                  name="courtYear"
                  className="form-input"
                  placeholder="e.g. 2015"
                  value={formData.courtYear}
                  onChange={handleChange}
                />
              </div>

            </div>
          </>
        )}

        {/* =====================================================
            CONTINUE
        ====================================================== */}

        <div
          style={{
            marginTop: "2rem",
            display: "flex",
            justifyContent: "flex-end",
          }}
        >
          <button
            type="submit"
            className="btn btn-primary"
          >
            Continue
            <ArrowRight size={18} />
          </button>
        </div>

      </form>
    </div>
  );
}

export default PropertyInputs;