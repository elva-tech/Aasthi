import React, { useState } from "react";
import { Building2, ArrowRight, ArrowLeft, MapPin, FileText, Languages, Info } from "lucide-react";

/* ============================================================
 * EXISTING (friend) — Property types & check rules
 * ============================================================ */
const PROPERTY_TYPES = ["Apartment", "Site", "Individual House", "Agricultural"];

export const CHECK_RULES = {
  Apartment: { exclude: [] },
  Site: {
    exclude: ["Occupancy Certificate", "Parking Certificate", "Association By Laws"],
  },
  "Individual House": {
    exclude: ["Parking Certificate", "Association By Laws"],
  },
  Agricultural: {
    exclude: [
      "Occupancy Certificate",
      "Parking Certificate",
      "Association By Laws",
      "Builder/Developer Reputation",
      "RERA / BDA / Buda / Tuda / NA Registration Check",
      "NOCs from Various Departments",
    ],
  },
};

/* ============================================================
 * ⭐ ADDED (yours) — Land-record modules metadata
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
 * Small helper — ⭐ ADDED (yours)
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
        <p style={{ fontSize: "0.82rem", color: "#6b7280", marginTop: "0.25rem", marginBottom: 0 }}>
          {subtitle}
        </p>
      )}
    </div>
  );
}

/* ============================================================
 * Main Component — friend's structure + ⭐ YOUR additions
 * ============================================================ */
function PropertyInputs({ onSubmit, onBack }) {
  const [formData, setFormData] = useState({
    /* ---------- EXISTING (friend) ---------- */
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
    propertyNo: "45",
    courtPartyName: "",
    courtYear: "2015",

    /* ---------- ⭐ ADDED (yours) ---------- */
    // Land-record core
    surveyNo: "",
    hissaNo: "1",
    mrHissaNo: "",
    surnoc: "*",
    searchText: "",

    // Kannada labels (Akarband only)
    akarbandDistrict: "",
    akarbandTaluk: "",
    akarbandHobli: "",
    akarbandVillage: "",

    // Which fetchers to run
    landModules: { ...DEFAULT_LAND_MODULES },
  });

  /* ---------- ⭐ ADDED (yours) ---------- */
  const [showKannada, setShowKannada] = useState(false);

  /* ---------- EXISTING (friend) ---------- */
  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  /* ---------- ⭐ ADDED (yours) ---------- */
  const handleModuleToggle = (key) => {
    setFormData((prev) => ({
      ...prev,
      landModules: { ...prev.landModules, [key]: !prev.landModules[key] },
    }));
  };

  const handleSelectAllModules = (checked) => {
    const next = {};
    LAND_MODULES.forEach((m) => {
      next[m.key] = checked;
    });
    setFormData((prev) => ({ ...prev, landModules: next }));
  };

  /* ---------- EXISTING (friend) — extended on submit ---------- */
  const handleSubmit = (e) => {
    e.preventDefault();

    /* ⭐ ADDED: build derived values + selectedLandModules */
    const selectedLandModules = LAND_MODULES.filter(
      (m) => formData.landModules[m.key]
    ).map((m) => m.key);

    onSubmit({
      ...formData,

      // derived (yours)
      englishDistrict: (formData.district || "").toLowerCase(),
      englishTaluk: (formData.taluka || "").toLowerCase(),
      englishHobli: (formData.hobli || "").toLowerCase(),
      englishVillage: (formData.village || "").toLowerCase(),

      mrDistrict: formData.district || "",
      mrTaluk: formData.taluka || "",
      mrHobli: (formData.hobli || "").toUpperCase(),
      mrVillage: (formData.village || "").toUpperCase(),

      selectedLandModules,

      // existing
      excludedChecks: CHECK_RULES[formData.propertyType]?.exclude || [],
    });
  };

  /* ---------- EXISTING (friend) ---------- */
  const isApartment = formData.propertyType === "Apartment";
  const isSite = formData.propertyType === "Site";
  const isHouse = formData.propertyType === "Individual House";
  const isAgricultural = formData.propertyType === "Agricultural";

  /* ---------- ⭐ ADDED (yours) — derived flags ---------- */
  const showLandRecords = isSite || isHouse || isAgricultural;
  const showKannadaSection = showLandRecords && formData.landModules.akarband;

  const selectedModuleKeys = LAND_MODULES.filter(
    (m) => formData.landModules[m.key]
  ).map((m) => m.key);

  const anyNeedsHissa = LAND_MODULES.some(
    (m) => formData.landModules[m.key] && m.needsHissa
  );
  const anyNeedsSurnoc = LAND_MODULES.some(
    (m) => formData.landModules[m.key] && m.needsSurnoc
  );
  const anyNeedsSearch = LAND_MODULES.some(
    (m) => formData.landModules[m.key] && m.needsSearch
  );
  const anyNeedsMrHissa = LAND_MODULES.some(
    (m) => formData.landModules[m.key] && m.mrHissaOverride
  );

  /* ============================================================
   * Render
   * ============================================================ */
  return (
    <div className="glass-panel glass-panel-large" style={{ maxWidth: "900px" }}>
      {onBack && (
        <button type="button" className="btn-back" onClick={onBack}>
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
          Enter available property details. You can leave unknown fields blank
          and continue.
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        {/* ============================================================
         * EXISTING (friend) — Property Type
         * ============================================================ */}
        <div className="form-group">
          <label className="form-label">Property Type</label>

          <div className="radio-group" style={{ flexWrap: "wrap" }}>
            {PROPERTY_TYPES.map((type) => (
              <label className="radio-card" key={type}>
                <input
                  type="radio"
                  name="propertyType"
                  value={type}
                  checked={formData.propertyType === type}
                  onChange={handleChange}
                />
                <div className="radio-content">{type}</div>
              </label>
            ))}
          </div>
        </div>

        {/* ============================================================
         * EXISTING (friend) — Basic details
         * ============================================================ */}
        <div className="form-grid">
          {isApartment && (
            <div className="form-group">
              <label className="form-label">Project Name</label>
              <input
                type="text"
                name="projectName"
                className="form-input"
                placeholder="e.g. Prestige Lakeside Habitat"
                value={formData.projectName}
                onChange={handleChange}
              />
            </div>
          )}
          {isApartment && (
            <div className="form-group">
              <label className="form-label">Builder Name</label>
              <input
                type="text"
                name="builderName"
                className="form-input"
                placeholder="e.g. Prestige Group"
                value={formData.builderName}
                onChange={handleChange}
              />
            </div>
          )}
          {(isApartment || isHouse) && (
            <div className="form-group">
              <label className="form-label">BESCOM Account ID</label>
              <input
                type="text"
                name="bescomId"
                className="form-input"
                placeholder="e.g. 7220755000"
                value={formData.bescomId}
                onChange={handleChange}
              />
            </div>
          )}
          {(isApartment || isHouse) && (
            <div className="form-group">
              <label className="form-label">Water RR Number</label>
              <input
                type="text"
                name="waterRr"
                className="form-input"
                placeholder="e.g. N-435608"
                value={formData.waterRr}
                onChange={handleChange}
              />
            </div>
          )}
          {!isAgricultural && (
            <div className="form-group">
              <label className="form-label">PID Number</label>
              <input
                type="text"
                name="pidNumber"
                className="form-input"
                placeholder="e.g. 1500082907"
                value={formData.pidNumber}
                onChange={handleChange}
              />
            </div>
          )}
          {!isAgricultural && (
            <div className="form-group">
              <label className="form-label">Owner Name</label>
              <input
                type="text"
                name="ownerName"
                className="form-input"
                placeholder="e.g. RAM"
                value={formData.ownerName}
                onChange={handleChange}
              />
            </div>
          )}
        </div>

        {!isAgricultural && (
          <div className="form-group">
            <label className="form-label">Property Address</label>
            <textarea
              name="address"
              className="form-input"
              placeholder="Enter property address if available"
              value={formData.address}
              onChange={handleChange}
              rows={3}
              style={{ resize: "vertical" }}
            />
          </div>
        )}

        {/* ============================================================
         * EXISTING (friend) — Location (only for non-Agricultural)
         * ------------------------------------------------------------
         * ⭐ CHANGED (yours): now shown for ALL types
         *   (yours fetchers need location for Agricultural too)
         * ============================================================ */}
        <SectionHeader
          icon={MapPin}
          title="Location Details"
          subtitle="Used by Kaveri EC, Bhoomi Maps and land-record fetchers"
        />

        <div className="form-grid">
          <div className="form-group">
            <label className="form-label">District</label>
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
            <label className="form-label">Taluka</label>
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
            <label className="form-label">Hobli</label>
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
            <label className="form-label">Village</label>
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

        {/* ============================================================
         * ⭐ ADDED (yours) — LAND RECORDS SECTION
         * ============================================================ */}
        {showLandRecords && (
          <>
            <SectionHeader
              icon={FileText}
              title="Land Records"
              subtitle="Fetched from Bhoomi / Bhoomi Mojini / RCCMS portals"
            />

            {/* ---- Module selector ---- */}
            <div className="form-group">
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "0.5rem",
                }}
              >
                <label className="form-label" style={{ marginBottom: 0 }}>
                  Documents to Fetch
                </label>
                <div style={{ display: "flex", gap: "0.75rem" }}>
                  <button
                    type="button"
                    onClick={() => handleSelectAllModules(true)}
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
                    onClick={() => handleSelectAllModules(false)}
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
                  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                  gap: "0.5rem",
                }}
              >
                {LAND_MODULES.map((m) => (
                  <label
                    key={m.key}
                    className="radio-card"
                    style={{
                      cursor: "pointer",
                      padding: "0.65rem 0.8rem",
                      border:
                        formData.landModules[m.key]
                          ? "2px solid #2563eb"
                          : "1px solid #e5e7eb",
                      transition: "border-color 0.15s",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={formData.landModules[m.key]}
                      onChange={() => handleModuleToggle(m.key)}
                    />
                    <div className="radio-content" style={{ fontSize: "0.88rem" }}>
                      <div style={{ fontWeight: 600 }}>{m.label}</div>
                      <div style={{ fontSize: "0.75rem", color: "#6b7280" }}>
                        {m.sublabel}
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            {/* ---- Core land inputs ---- */}
            <div className="form-grid">
              <div className="form-group">
                <label className="form-label">
                  Survey Number <span style={{ color: "#dc2626" }}>*</span>
                </label>
                <input
                  type="text"
                  name="surveyNo"
                  className="form-input"
                  placeholder="e.g. 117"
                  value={formData.surveyNo}
                  onChange={handleChange}
                  required={showLandRecords && selectedModuleKeys.length > 0}
                />
              </div>

              {anyNeedsHissa && (
                <div className="form-group">
                  <label className="form-label">Hissa Number</label>
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

              {anyNeedsSurnoc && (
                <div className="form-group">
                  <label className="form-label">Surnoc</label>
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

            {/* ---- Kannada labels for Akarband ---- */}
            {showKannadaSection && (
              <>
                <div style={{ marginTop: "1rem" }}>
                  <button
                    type="button"
                    onClick={() => setShowKannada((s) => !s)}
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
                    {showKannada ? "Hide" : "Add"} Kannada labels for Akarband
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
                    Bhoomi Mojini requires Kannada labels. Leave blank to
                    auto-translate from English on the backend.
                  </p>
                </div>

                {showKannada && (
                  <div className="form-grid" style={{ marginTop: "0.75rem" }}>
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
         * EXISTING (friend) — Additional / court fields
         * ============================================================ */}
        <SectionHeader icon={FileText} title="Additional Details" />

        <div className="form-grid">
          <div className="form-group">
            <label className="form-label">Property Number</label>
            <input
              type="text"
              name="propertyNo"
              className="form-input"
              placeholder="e.g. 45"
              value={formData.propertyNo}
              onChange={handleChange}
            />
          </div>

          {!isAgricultural && (
            <div className="form-group">
              <label className="form-label">ePID Number</label>
              <input
                type="text"
                name="epidNumber"
                className="form-input"
                placeholder="Optional"
                value={formData.epidNumber}
                onChange={handleChange}
              />
            </div>
          )}

          <div className="form-group">
            <label className="form-label">Court Party Name</label>
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
            <label className="form-label">Court Year</label>
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

        <div
          style={{
            marginTop: "2rem",
            display: "flex",
            justifyContent: "flex-end",
          }}
        >
          <button type="submit" className="btn btn-primary">
            Continue <ArrowRight size={18} />
          </button>
        </div>
      </form>
    </div>
  );
}

export default PropertyInputs;