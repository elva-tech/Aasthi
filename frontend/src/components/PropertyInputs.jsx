import React, { useState } from "react";
import {
  Building2,
  ArrowRight,
  ArrowLeft,
  MapPin,
  FileText,
  Languages,
  Info,
} from "lucide-react";

/* ============================================================
 * Property types & check rules
 * ============================================================ */
const PROPERTY_TYPES = [
  "Apartment",
  "Site",
  "Individual House",
  "Farm Land",
];

export const CHECK_RULES = {
  Apartment: { exclude: [] },

  Site: {
    exclude: [
      "Occupancy Certificate",
      "Parking Certificate",
      "Association By Laws",
    ],
  },

  "Individual House": {
    exclude: [
      "Parking Certificate",
      "Association By Laws",
      "Title Check",
      "Builder/Developer Reputation",
      "RERA / BDA / Buda / Tuda / NA Registration Check",
      "NOCs from Various Departments",
      "Occupancy Certificate",
      "AKARBAND",
      "MAP",
      "MR",
      "RCCMS",
      "RTC",
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
      "Title Check",
      "Electricity Bill",
      "Water Bill",
      "Property Tax Paid Receipts",
      "Existing Bank Loans",
      "Khata/Mutation Type Verification",
      "Court Case",
    ],
  },
};

/* ============================================================
 * Land-record modules metadata
 * ============================================================ */
const LAND_MODULES = [
  {
    key: "akarband",
    label: "Akarband",
    sublabel: "ಆಕಾರಬಂದ್",
    needsHissa: true,
    needsSurnoc: true,
    needsSearch: false,
    needsKannada: true,
  },
  {
    key: "courtCases",
    label: "Court Cases",
    sublabel: "RCCMS",
    needsHissa: false,
    needsSurnoc: false,
    needsSearch: true,
    needsKannada: false,
  },
  {
    key: "map",
    label: "Map",
    sublabel: "Form 16A",
    needsHissa: true,
    needsSurnoc: true,
    needsSearch: true,
    needsKannada: false,
  },
  {
    key: "mr",
    label: "MR",
    sublabel: "Mutation Register",
    needsHissa: true,
    needsSurnoc: false,
    needsSearch: false,
    needsKannada: false,
    mrHissaOverride: true,
  },
  {
    key: "rtc",
    label: "RTC",
    sublabel: "Pahani",
    needsHissa: true,
    needsSurnoc: true,
    needsSearch: true,
    needsKannada: false,
  },
];

const DEFAULT_LAND_MODULES = {
  akarband: true,
  courtCases: true,
  map: true,
  mr: true,
  rtc: true,
};

/* ============================================================
 * Section header
 * ============================================================ */
function SectionHeader({ icon: Icon, title, subtitle }) {
  return (
    <div style={{ marginTop: "1.75rem", marginBottom: "0.75rem" }}>
      <h3
        style={{
          fontSize: "0.95rem",
          fontWeight: 600,
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          color: "#1f2937",
          margin: 0,
        }}
      >
        <Icon size={16} />
        {title}
      </h3>

      {subtitle && (
        <p
          style={{
            fontSize: "0.82rem",
            color: "#6b7280",
            marginTop: "0.25rem",
            marginBottom: 0,
          }}
        >
          {subtitle}
        </p>
      )}
    </div>
  );
}

/* ============================================================
 * Main Component
 *
 * INPUT STRUCTURE
 *
 * Apartment:
 *   - Project Name
 *   - Builder Name
 *   - Legal Name
 *   - Start Year of Project
 *
 * Site:
 *   - Owner Name
 *   - PID Number
 *   - Property Address
 *   - District
 *   - Taluka
 *   - Hobli
 *   - Village
 *   - Property Number
 *   - Legal Name
 *   - Start Year of Project
 *
 * Individual House:
 *   - Owner Name
 *   - PID Number
 *   - BESCOM Account ID
 *   - Water RR Number
 *   - Property Address
 *   - District
 *   - Taluka
 *   - Hobli
 *   - Village
 *   - Property Number
 *   - Legal Name
 *   - Start Year of Project
 *
 * Farm Land:
 *   - Property Number
 *   - Legal Name
 *   - Start Year of Project
 *   - Land Records
 * ============================================================ */
function PropertyInputs({ onSubmit, onBack }) {
  const [formData, setFormData] = useState({
    /* ---------- Existing/backend-compatible fields ---------- */
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

    /* ---------- Land-record fields ---------- */
    surveyNo: "",
    hissaNo: "1",
    mrHissaNo: "",
    surnoc: "*",
    searchText: "",

    /* ---------- Kannada labels for Akarband ---------- */
    akarbandDistrict: "",
    akarbandTaluk: "",
    akarbandHobli: "",
    akarbandVillage: "",

    /* ---------- Selected land-record modules ---------- */
    landModules: { ...DEFAULT_LAND_MODULES },
  });

  const [showKannada, setShowKannada] = useState(false);

  const handleChange = (e) => {
    const { name, value } = e.target;

    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleModuleToggle = (key) => {
    setFormData((prev) => ({
      ...prev,
      landModules: {
        ...prev.landModules,
        [key]: !prev.landModules[key],
      },
    }));
  };

  const handleSelectAllModules = (checked) => {
    const next = {};

    LAND_MODULES.forEach((module) => {
      next[module.key] = checked;
    });

    setFormData((prev) => ({
      ...prev,
      landModules: next,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    const selectedLandModules = LAND_MODULES.filter(
      (module) => formData.landModules[module.key]
    ).map((module) => module.key);

    onSubmit({
      ...formData,

      /* Derived location values used by land-record fetchers */
      englishDistrict: (formData.district || "").toLowerCase(),
      englishTaluk: (formData.taluka || "").toLowerCase(),
      englishHobli: (formData.hobli || "").toLowerCase(),
      englishVillage: (formData.village || "").toLowerCase(),

      mrDistrict: formData.district || "",
      mrTaluk: formData.taluka || "",
      mrHobli: (formData.hobli || "").toUpperCase(),
      mrVillage: (formData.village || "").toUpperCase(),

      selectedLandModules,

      excludedChecks:
        CHECK_RULES[formData.propertyType]?.exclude || [],
    });
  };

  /* ---------- Property-type flags ---------- */
  const isApartment = formData.propertyType === "Apartment";
  const isSite = formData.propertyType === "Site";
  const isHouse = formData.propertyType === "Individual House";
  const isAgricultural = formData.propertyType === "Farm Land";

  /* ---------- Land Records ONLY for Farm Land ---------- */
  const showLandRecords = isAgricultural;

  const showKannadaSection =
    showLandRecords && formData.landModules.akarband;

  const selectedModuleKeys = LAND_MODULES.filter(
    (module) => formData.landModules[module.key]
  ).map((module) => module.key);

  const anyNeedsHissa = LAND_MODULES.some(
    (module) =>
      formData.landModules[module.key] && module.needsHissa
  );

  const anyNeedsSurnoc = LAND_MODULES.some(
    (module) =>
      formData.landModules[module.key] && module.needsSurnoc
  );

  const anyNeedsSearch = LAND_MODULES.some(
    (module) =>
      formData.landModules[module.key] && module.needsSearch
  );

  const anyNeedsMrHissa = LAND_MODULES.some(
    (module) =>
      formData.landModules[module.key] &&
      module.mrHissaOverride
  );

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
          Enter available property details. You can leave unknown
          fields blank and continue.
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        {/* ============================================================
         * PROPERTY TYPE
         * ============================================================ */}
        <div className="form-group">
          <label className="form-label">Property Type</label>

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
                  checked={formData.propertyType === type}
                  onChange={handleChange}
                />

                <div className="radio-content">
                  {type}
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* ============================================================
         * APARTMENT
         *
         * ONLY:
         * - Project Name
         * - Builder Name
         * - Legal Name
         * - Start Year of Project
         * ============================================================ */}
        {isApartment && (
          <>
            <SectionHeader
              icon={Building2}
              title="Apartment Details"
            />

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

              {/* LEGAL NAME */}
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

              {/* START YEAR OF PROJECT */}
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

        {/* ============================================================
         * SITE
         *
         * - Owner Name
         * - PID Number
         * - Property Address
         * - District
         * - Taluka
         * - Hobli
         * - Village
         * - Property Number
         * - Legal Name
         * - Start Year of Project
         * ============================================================ */}
        {isSite && (
          <>
            <SectionHeader
              icon={MapPin}
              title="Site Details"
            />

            <div className="form-grid">
              {/* OWNER NAME */}
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

              {/* PID NUMBER */}
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

            {/* PROPERTY ADDRESS */}
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

            {/* LOCATION + PROPERTY DETAILS */}
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
                  placeholder="e.g. Bengaluru South"
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
                  placeholder="e.g. Kanakpura"
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
                  placeholder="e.g. Satanuru"
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
                  placeholder="e.g. Harihara"
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

        {/* ============================================================
         * INDIVIDUAL HOUSE
         *
         * - Owner Name
         * - PID Number
         * - BESCOM Account ID
         * - Water RR Number
         * - Property Address
         * - District
         * - Taluka
         * - Hobli
         * - Village
         * - Property Number
         * - Legal Name
         * - Start Year of Project
         * - epidNumber
         * ============================================================ */}
        {isHouse && (
          <>
            <SectionHeader
              icon={Building2}
              title="Individual House Details"
            />

            <div className="form-grid">
              {/* OWNER NAME */}
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

              {/* PID NUMBER */}
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

              {/* BESCOM ACCOUNT ID */}
              <div className="form-group">
                <label className="form-label">
                  BESCOM Account ID
                </label>

                <input
                  type="text"
                  name="bescomId"
                  className="form-input"
                  placeholder="e.g. 7220755000"
                  value={formData.bescomId}
                  onChange={handleChange}
                />
              </div>

              {/* WATER RR NUMBER */}
              <div className="form-group">
                <label className="form-label">
                  Water RR Number
                </label>

                <input
                  type="text"
                  name="waterRr"
                  className="form-input"
                  placeholder="e.g. N-435608"
                  value={formData.waterRr}
                  onChange={handleChange}
                />
              </div>
            </div>

            {/* PROPERTY ADDRESS */}
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

            {/* LOCATION + PROPERTY DETAILS */}
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
                  placeholder="e.g. Bengaluru South"
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
                  placeholder="e.g. Kanakpura"
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
                  placeholder="e.g. Satanuru"
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
                  placeholder="e.g. Harihara"
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
              {/* EPID NUMBER */}
            <div className="form-group">
              <label className="form-label">
                EPID Number
              </label>

              <input
                type="text"
                name="epidNumber"
                className="form-input"
                placeholder="e.g. 2737828078"
                value={formData.epidNumber}
                onChange={handleChange}
              />
            </div>
            </div>
          </>
        )}

        {/* ============================================================
         * FARM LAND
         *
         * - Property Number
         * - Legal Name
         * - Start Year of Project
         * - Land Records
         * ============================================================ */}

        {/* ============================================================
         * LOCATION DETAILS
         *
         * Required for Site, Individual House and Farm Land.
         * Apartment intentionally does not show these fields because
         * Apartment's input set is limited to its four fields above.
         * ============================================================ */}
        {!isApartment && !isSite && !isHouse &&(
          <>
            <SectionHeader
              icon={MapPin}
              title="Location Details"
              subtitle="Used by Kaveri EC, Bhoomi Maps and land-record fetchers"
            />

            <div className="form-grid">
              {/* DISTRICT */}
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
                  placeholder="e.g. Bengaluru South"
                />
              </div>

              {/* TALUKA */}
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
                  placeholder="e.g. Kanakpura"
                />
              </div>

              {/* HOBLI */}
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
                  placeholder="e.g. Satanuru"
                />
              </div>

              {/* VILLAGE */}
              <div className="form-group">
                <label className="form-label">
                  Village
                </label>

                <input
                  type="text"
                  name="village"
                  className="form-input"
                  placeholder="e.g. Harihara"
                  value={formData.village}
                  onChange={handleChange}
                />
              </div>
            </div>
          </>
        )}

        {/* ============================================================
         * LAND RECORDS
         *
         * ONLY shown for Farm Land.
         * ============================================================ */}
        {showLandRecords && (
          <>
            <SectionHeader
              icon={FileText}
              title="Land Records"
              subtitle="Fetched from Bhoomi / Bhoomi Mojini / RCCMS portals"
            />

            {/* MODULE SELECTOR */}
            <div className="form-group">
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "0.5rem",
                }}
              >
                <label
                  className="form-label"
                  style={{ marginBottom: 0 }}
                >
                  Documents to Fetch
                </label>

                <div
                  style={{
                    display: "flex",
                    gap: "0.75rem",
                  }}
                >
                  <button
                    type="button"
                    onClick={() =>
                      handleSelectAllModules(true)
                    }
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "#2563eb",
                      cursor: "pointer",
                      fontSize: "0.8rem",
                      padding: 0,
                    }}
                  >
                    Select all
                  </button>

                  <button
                    type="button"
                    onClick={() =>
                      handleSelectAllModules(false)
                    }
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "#2563eb",
                      cursor: "pointer",
                      fontSize: "0.8rem",
                      padding: 0,
                    }}
                  >
                    Clear all
                  </button>
                </div>
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "repeat(auto-fit, minmax(180px, 1fr))",
                  gap: "0.5rem",
                }}
              >
                {LAND_MODULES.map((module) => (
                  <label
                    key={module.key}
                    className="radio-card"
                    style={{
                      cursor: "pointer",
                      padding: "0.65rem 0.8rem",
                      border: formData.landModules[module.key]
                        ? "2px solid #2563eb"
                        : "1px solid #e5e7eb",
                      transition: "border-color 0.15s",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={
                        formData.landModules[module.key]
                      }
                      onChange={() =>
                        handleModuleToggle(module.key)
                      }
                    />

                    <div
                      className="radio-content"
                      style={{ fontSize: "0.88rem" }}
                    >
                      <div style={{ fontWeight: 600 }}>
                        {module.label}
                      </div>

                      <div
                        style={{
                          fontSize: "0.75rem",
                          color: "#6b7280",
                        }}
                      >
                        {module.sublabel}
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            {/* CORE LAND INPUTS */}
            <div className="form-grid">
              {/* SURVEY NUMBER */}
              <div className="form-group">
                <label className="form-label">
                  Survey Number{" "}
                  <span style={{ color: "#dc2626" }}>
                    *
                  </span>
                </label>

                <input
                  type="text"
                  name="surveyNo"
                  className="form-input"
                  placeholder="e.g. 117"
                  value={formData.surveyNo}
                  onChange={handleChange}
                  required={
                    showLandRecords &&
                    selectedModuleKeys.length > 0
                  }
                />
              </div>

              {/* HISSA */}
              {anyNeedsHissa && (
                <div className="form-group">
                  <label className="form-label">
                    Hissa Number
                  </label>

                  <input
                    type="text"
                    name="hissaNo"
                    className="form-input"
                    placeholder="e.g. 1"
                    value={formData.hissaNo}
                    onChange={handleChange}
                  />
                </div>
              )}

              {/* MR HISSA */}
              {anyNeedsMrHissa && (
                <div className="form-group">
                  <label className="form-label">
                    MR Hissa
                    <span
                      style={{
                        fontSize: "0.75rem",
                        color: "#6b7280",
                        marginLeft: "0.4rem",
                        fontWeight: 400,
                      }}
                    >
                      (optional — overrides Hissa for MR only)
                    </span>
                  </label>

                  <input
                    type="text"
                    name="mrHissaNo"
                    className="form-input"
                    placeholder="e.g. 3"
                    value={formData.mrHissaNo}
                    onChange={handleChange}
                  />
                </div>
              )}

              {/* SURNOC */}
              {anyNeedsSurnoc && (
                <div className="form-group">
                  <label className="form-label">
                    Surnoc
                  </label>

                  <input
                    type="text"
                    name="surnoc"
                    className="form-input"
                    placeholder="default: *"
                    value={formData.surnoc}
                    onChange={handleChange}
                  />
                </div>
              )}

              {/* VILLAGE SEARCH TEXT */}
              {anyNeedsSearch && (
                <div className="form-group">
                  <label className="form-label">
                    Village Search Text
                    <span
                      style={{
                        fontSize: "0.75rem",
                        color: "#6b7280",
                        marginLeft: "0.4rem",
                        fontWeight: 400,
                      }}
                    >
                      (for Bhoomi Maps)
                    </span>
                  </label>

                  <input
                    type="text"
                    name="searchText"
                    className="form-input"
                    placeholder="e.g. sab kere,"
                    value={formData.searchText}
                    onChange={handleChange}
                  />
                </div>
              )}
            </div>

            {/* KANNADA LABELS FOR AKARBAND */}
            {showKannadaSection && (
              <>
                <div style={{ marginTop: "1rem" }}>
                  <button
                    type="button"
                    onClick={() =>
                      setShowKannada((state) => !state)
                    }
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "#2563eb",
                      cursor: "pointer",
                      fontSize: "0.85rem",
                      padding: 0,
                      display: "flex",
                      alignItems: "center",
                      gap: "0.4rem",
                    }}
                  >
                    <Languages size={14} />

                    {showKannada
                      ? "Hide"
                      : "Add"}{" "}
                    Kannada labels for Akarband
                  </button>

                  <p
                    style={{
                      fontSize: "0.75rem",
                      color: "#6b7280",
                      margin: "0.35rem 0 0 1.4rem",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.3rem",
                    }}
                  >
                    <Info size={12} />

                    Bhoomi Mojini requires Kannada labels.
                    Leave blank to auto-translate from English
                    on the backend.
                  </p>
                </div>

                {showKannada && (
                  <div
                    className="form-grid"
                    style={{ marginTop: "0.75rem" }}
                  >
                    {/* KANNADA DISTRICT */}
                    <div className="form-group">
                      <label className="form-label">
                        ಜಿಲ್ಲೆ / District (Kannada)
                      </label>

                      <input
                        type="text"
                        name="akarbandDistrict"
                        className="form-input"
                        placeholder="e.g. ಬೆಂಗಳೂರು ದಕ್ಷಿಣ"
                        value={formData.akarbandDistrict}
                        onChange={handleChange}
                      />
                    </div>

                    {/* KANNADA TALUK */}
                    <div className="form-group">
                      <label className="form-label">
                        ತಾಲ್ಲೂಕು / Taluk (Kannada)
                      </label>

                      <input
                        type="text"
                        name="akarbandTaluk"
                        className="form-input"
                        placeholder="e.g. ಕನಕಪುರ"
                        value={formData.akarbandTaluk}
                        onChange={handleChange}
                      />
                    </div>

                    {/* KANNADA HOBLI */}
                    <div className="form-group">
                      <label className="form-label">
                        ಹೋಬಳಿ / Hobli (Kannada)
                      </label>

                      <input
                        type="text"
                        name="akarbandHobli"
                        className="form-input"
                        placeholder="e.g. ಸಾತನೂರು"
                        value={formData.akarbandHobli}
                        onChange={handleChange}
                      />
                    </div>

                    {/* KANNADA VILLAGE */}
                    <div className="form-group">
                      <label className="form-label">
                        ಗ್ರಾಮ / Village (Kannada)
                      </label>

                      <input
                        type="text"
                        name="akarbandVillage"
                        className="form-input"
                        placeholder="e.g. ಹರಿಹರ"
                        value={formData.akarbandVillage}
                        onChange={handleChange}
                      />
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        )}

        {/* ============================================================
         * SUBMIT
         * ============================================================ */}
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
            Continue <ArrowRight size={18} />
          </button>
        </div>
      </form>
    </div>
  );
}

export default PropertyInputs;
