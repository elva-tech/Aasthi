import React, { useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Baby,
  CheckCircle2,
  Home,
  MapPin,
  PawPrint,
  Search,
  Sparkles,
  Users,
  Wallet,
  XCircle,
} from "lucide-react";

const AREAS = [
  "Whitefield",
  "Electronic City",
  "Indiranagar",
  "Koramangala",
  "Hebbal",
  "Sarjapur Road",
  "Yelahanka",
  "JP Nagar",
  "HSR Layout",
  "Marathahalli",
];

const BUDGET_OPTIONS = [
  { label: "Under ₹50 Lakh", value: 50 },
  { label: "₹50 Lakh – ₹80 Lakh", value: 80 },
  { label: "₹80 Lakh – ₹1.2 Cr", value: 120 },
  { label: "₹1.2 Cr – ₹2 Cr", value: 200 },
  { label: "Above ₹2 Cr", value: 350 },
];

const APARTMENTS = [
  {
    id: "wf-1",
    name: "Prestige Lakeside Habitat",
    area: "Whitefield",
    builder: "Prestige Group",
    priceLakhs: 95,
    bhk: 2,
    sqft: 1180,
    maxPeople: 4,
    petsAllowed: true,
    childFriendly: true,
    expectedRoi: "8.2%",
    highlights: ["Lake view", "Clubhouse", "Metro nearby"],
    imageTone: "#1e3a5f",
  },
  {
    id: "wf-2",
    name: "Sobha Dream Acres",
    area: "Whitefield",
    builder: "Sobha Limited",
    priceLakhs: 72,
    bhk: 2,
    sqft: 1050,
    maxPeople: 4,
    petsAllowed: true,
    childFriendly: true,
    expectedRoi: "7.6%",
    highlights: ["Large park", "School bus stop", "Gated security"],
    imageTone: "#1a3d2e",
  },
  {
    id: "wf-3",
    name: "Brigade Cornerstone Utopia",
    area: "Whitefield",
    builder: "Brigade Group",
    priceLakhs: 145,
    bhk: 3,
    sqft: 1680,
    maxPeople: 6,
    petsAllowed: false,
    childFriendly: true,
    expectedRoi: "9.1%",
    highlights: ["Premium finishes", "Indoor games", "Pool"],
    imageTone: "#3d2a1a",
  },
  {
    id: "ec-1",
    name: "Ajmera Infinity",
    area: "Electronic City",
    builder: "Ajmera Realty",
    priceLakhs: 58,
    bhk: 2,
    sqft: 980,
    maxPeople: 4,
    petsAllowed: true,
    childFriendly: true,
    expectedRoi: "8.8%",
    highlights: ["IT corridor", "Affordable entry", "Play area"],
    imageTone: "#1a2e3d",
  },
  {
    id: "ec-2",
    name: "Assetz Soul & Soil",
    area: "Electronic City",
    builder: "Assetz Property",
    priceLakhs: 110,
    bhk: 3,
    sqft: 1520,
    maxPeople: 6,
    petsAllowed: true,
    childFriendly: true,
    expectedRoi: "9.4%",
    highlights: ["Pet park", "Organic farm", "Wide roads"],
    imageTone: "#2e3d1a",
  },
  {
    id: "ec-3",
    name: "SJR Luxuria",
    area: "Electronic City",
    builder: "SJR Group",
    priceLakhs: 48,
    bhk: 1,
    sqft: 720,
    maxPeople: 2,
    petsAllowed: false,
    childFriendly: false,
    expectedRoi: "7.1%",
    highlights: ["Compact living", "Low maintenance", "Near tech parks"],
    imageTone: "#3d1a2e",
  },
  {
    id: "ind-1",
    name: "Embassy Grove",
    area: "Indiranagar",
    builder: "Embassy Group",
    priceLakhs: 220,
    bhk: 3,
    sqft: 1850,
    maxPeople: 5,
    petsAllowed: true,
    childFriendly: true,
    expectedRoi: "6.8%",
    highlights: ["Prime location", "Walkable cafes", "Low density"],
    imageTone: "#1a1a3d",
  },
  {
    id: "ind-2",
    name: "Purva Venezia",
    area: "Indiranagar",
    builder: "Puravankara",
    priceLakhs: 175,
    bhk: 2,
    sqft: 1320,
    maxPeople: 4,
    petsAllowed: false,
    childFriendly: true,
    expectedRoi: "6.5%",
    highlights: ["Central Bangalore", "Schools nearby", "Retail hub"],
    imageTone: "#3d1a1a",
  },
  {
    id: "kor-1",
    name: "Mantri Elegant",
    area: "Koramangala",
    builder: "Mantri Developers",
    priceLakhs: 165,
    bhk: 2,
    sqft: 1280,
    maxPeople: 4,
    petsAllowed: true,
    childFriendly: true,
    expectedRoi: "7.0%",
    highlights: ["Startup hub", "Parks nearby", "Pet-friendly society"],
    imageTone: "#1a3d3d",
  },
  {
    id: "kor-2",
    name: "Salarpuria Sattva Cadenza",
    area: "Koramangala",
    builder: "Salarpuria Sattva",
    priceLakhs: 280,
    bhk: 4,
    sqft: 2400,
    maxPeople: 7,
    petsAllowed: false,
    childFriendly: true,
    expectedRoi: "6.2%",
    highlights: ["Luxury tower", "Concierge", "Kids zone"],
    imageTone: "#2a1a3d",
  },
  {
    id: "heb-1",
    name: "Godrej Aqua",
    area: "Hebbal",
    builder: "Godrej Properties",
    priceLakhs: 125,
    bhk: 3,
    sqft: 1600,
    maxPeople: 6,
    petsAllowed: true,
    childFriendly: true,
    expectedRoi: "8.5%",
    highlights: ["Lake facing", "Airport access", "Family amenities"],
    imageTone: "#1a2a3d",
  },
  {
    id: "heb-2",
    name: "Bren Imperia",
    area: "Hebbal",
    builder: "Bren Corporation",
    priceLakhs: 88,
    bhk: 2,
    sqft: 1120,
    maxPeople: 4,
    petsAllowed: true,
    childFriendly: false,
    expectedRoi: "7.9%",
    highlights: ["Ring road access", "Gym", "Power backup"],
    imageTone: "#3d2e1a",
  },
  {
    id: "sar-1",
    name: "Total Environment Pursuit of a Radical Rhapsody",
    area: "Sarjapur Road",
    builder: "Total Environment",
    priceLakhs: 195,
    bhk: 3,
    sqft: 2100,
    maxPeople: 6,
    petsAllowed: true,
    childFriendly: true,
    expectedRoi: "9.0%",
    highlights: ["Design-led homes", "Forest walks", "Pet & kids zones"],
    imageTone: "#1a3d28",
  },
  {
    id: "sar-2",
    name: "Sobha Silicon Oasis",
    area: "Sarjapur Road",
    builder: "Sobha Limited",
    priceLakhs: 78,
    bhk: 2,
    sqft: 1080,
    maxPeople: 4,
    petsAllowed: false,
    childFriendly: true,
    expectedRoi: "8.3%",
    highlights: ["IT corridor growth", "School proximity", "Clubhouse"],
    imageTone: "#2e1a3d",
  },
  {
    id: "yel-1",
    name: "Brigade Atmosphere",
    area: "Yelahanka",
    builder: "Brigade Group",
    priceLakhs: 92,
    bhk: 2,
    sqft: 1200,
    maxPeople: 4,
    petsAllowed: true,
    childFriendly: true,
    expectedRoi: "8.0%",
    highlights: ["Airport corridor", "Open spaces", "Family parks"],
    imageTone: "#1a283d",
  },
  {
    id: "yel-2",
    name: "Vaswani Exquisite",
    area: "Yelahanka",
    builder: "Vaswani Group",
    priceLakhs: 55,
    bhk: 2,
    sqft: 950,
    maxPeople: 3,
    petsAllowed: true,
    childFriendly: false,
    expectedRoi: "7.4%",
    highlights: ["Value buy", "Quiet locality", "Pet welcome"],
    imageTone: "#3d1a28",
  },
  {
    id: "jp-1",
    name: "Salarpuria Sattva Celesta",
    area: "JP Nagar",
    builder: "Salarpuria Sattva",
    priceLakhs: 135,
    bhk: 3,
    sqft: 1550,
    maxPeople: 5,
    petsAllowed: false,
    childFriendly: true,
    expectedRoi: "7.2%",
    highlights: ["South Bangalore", "Schools & hospitals", "Metro upcoming"],
    imageTone: "#283d1a",
  },
  {
    id: "jp-2",
    name: "Provident Park Square",
    area: "JP Nagar",
    builder: "Provident Housing",
    priceLakhs: 68,
    bhk: 2,
    sqft: 1020,
    maxPeople: 4,
    petsAllowed: true,
    childFriendly: true,
    expectedRoi: "7.8%",
    highlights: ["Budget friendly", "Kids play zone", "Pet park"],
    imageTone: "#1a3d3a",
  },
  {
    id: "hsr-1",
    name: "Nitesh Forest Hills",
    area: "HSR Layout",
    builder: "Nitesh Estates",
    priceLakhs: 155,
    bhk: 3,
    sqft: 1480,
    maxPeople: 5,
    petsAllowed: true,
    childFriendly: true,
    expectedRoi: "7.5%",
    highlights: ["Planned layout", "Cafes & parks", "Family living"],
    imageTone: "#3d281a",
  },
  {
    id: "hsr-2",
    name: "Concorde Midway City",
    area: "HSR Layout",
    builder: "Concorde Group",
    priceLakhs: 85,
    bhk: 2,
    sqft: 1100,
    maxPeople: 4,
    petsAllowed: false,
    childFriendly: true,
    expectedRoi: "7.3%",
    highlights: ["Sector 2 access", "School belt", "Good connectivity"],
    imageTone: "#1a1f3d",
  },
  {
    id: "mar-1",
    name: "Purva Skywood",
    area: "Marathahalli",
    builder: "Puravankara",
    priceLakhs: 98,
    bhk: 3,
    sqft: 1420,
    maxPeople: 5,
    petsAllowed: true,
    childFriendly: true,
    expectedRoi: "8.1%",
    highlights: ["ORR access", "Tech parks", "Family amenities"],
    imageTone: "#1a3d32",
  },
  {
    id: "mar-2",
    name: "Rohan Upavan",
    area: "Marathahalli",
    builder: "Rohan Builders",
    priceLakhs: 62,
    bhk: 2,
    sqft: 990,
    maxPeople: 3,
    petsAllowed: true,
    childFriendly: false,
    expectedRoi: "7.7%",
    highlights: ["Compact 2BHK", "Pet allowed", "Near bus depot"],
    imageTone: "#321a3d",
  },
];

function formatPrice(lakhs) {
  if (lakhs >= 100) {
    const crores = lakhs / 100;
    return `₹${crores % 1 === 0 ? crores.toFixed(0) : crores.toFixed(1)} Cr`;
  }
  return `₹${lakhs} Lakh`;
}

function scoreApartment(apt, prefs) {
  let score = 0;
  const reasons = [];

  if (apt.area === prefs.area) {
    score += 40;
    reasons.push(`Located in ${prefs.area}`);
  }

  if (apt.priceLakhs <= prefs.budget) {
    score += 25;
    reasons.push(`Within your ${formatPrice(prefs.budget)} budget`);
  } else if (apt.priceLakhs <= prefs.budget * 1.1) {
    score += 10;
    reasons.push("Slightly above budget but strong fit");
  }

  if (apt.maxPeople >= prefs.people) {
    score += 15;
    reasons.push(`Fits ${prefs.people} people (${apt.bhk} BHK)`);
  }

  if (prefs.hasPets) {
    if (apt.petsAllowed) {
      score += 12;
      reasons.push("Pet-friendly society");
    }
  } else {
    score += 5;
  }

  if (prefs.hasChildren) {
    if (apt.childFriendly) {
      score += 12;
      reasons.push("Child-friendly amenities nearby");
    }
  } else {
    score += 5;
  }

  if (apt.expectedRoi) {
    score += 3;
  }

  return { score, reasons };
}

function InvestmentInputs({ onBack }) {
  const [form, setForm] = useState({
    area: "Whitefield",
    people: 3,
    hasPets: false,
    hasChildren: false,
    budget: 120,
  });
  const [submitted, setSubmitted] = useState(false);
  const [selectedId, setSelectedId] = useState(null);

  const recommendations = useMemo(() => {
    if (!submitted) return [];

    return APARTMENTS.map((apt) => {
      const { score, reasons } = scoreApartment(apt, form);
      return { ...apt, matchScore: score, reasons };
    })
      .filter((apt) => {
        const areaMatch = apt.area === form.area;
        const budgetOk = apt.priceLakhs <= form.budget * 1.15;
        const peopleOk = apt.maxPeople >= form.people;
        const petsOk = !form.hasPets || apt.petsAllowed;
        const kidsOk = !form.hasChildren || apt.childFriendly;
        return areaMatch && budgetOk && peopleOk && petsOk && kidsOk;
      })
      .sort((a, b) => b.matchScore - a.matchScore)
      .slice(0, 6);
  }, [submitted, form]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]:
        type === "checkbox"
          ? checked
          : name === "people" || name === "budget"
            ? Number(value)
            : value,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setSubmitted(true);
    setSelectedId(null);
  };

  const handleReset = () => {
    setSubmitted(false);
    setSelectedId(null);
  };

  return (
    <div className="glass-panel glass-panel-xl invest-panel">
      <div className="invest-header">
        <button type="button" className="btn-back" onClick={onBack}>
          <ArrowLeft size={18} />
          Back
        </button>

        <div className="step-header" style={{ marginBottom: 0 }}>
          <div
            className="search-icon-bg"
            style={{
              background:
                "linear-gradient(135deg, rgba(16,185,129,0.2), rgba(52,211,153,0.2))",
              borderColor: "rgba(16,185,129,0.5)",
              color: "#34d399",
            }}
          >
            <Sparkles size={28} />
          </div>
          <h2>Find Your Ideal Apartment</h2>
          <p>
            Tell us your lifestyle needs — area, household size, pets, children,
            and budget — and we&apos;ll recommend matching homes.
          </p>
        </div>
      </div>

      {!submitted ? (
        <form onSubmit={handleSubmit} className="invest-form">
          <div className="form-grid">
            <div className="form-group">
              <label className="form-label">
                <MapPin size={14} className="label-icon" /> Preferred Area
              </label>
              <select
                name="area"
                className="form-input form-select"
                value={form.area}
                onChange={handleChange}
              >
                {AREAS.map((area) => (
                  <option key={area} value={area}>
                    {area}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">
                <Users size={14} className="label-icon" /> Number of People
              </label>
              <select
                name="people"
                className="form-input form-select"
                value={form.people}
                onChange={handleChange}
              >
                {[1, 2, 3, 4, 5, 6, 7].map((n) => (
                  <option key={n} value={n}>
                    {n} {n === 1 ? "Person" : "People"}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">
                <Wallet size={14} className="label-icon" /> Budget
              </label>
              <select
                name="budget"
                className="form-input form-select"
                value={form.budget}
                onChange={handleChange}
              >
                {BUDGET_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="lifestyle-toggles">
            <label className={`toggle-card ${form.hasPets ? "active" : ""}`}>
              <input
                type="checkbox"
                name="hasPets"
                checked={form.hasPets}
                onChange={handleChange}
              />
              <div className="toggle-content">
                <PawPrint size={22} />
                <div>
                  <strong>Pets</strong>
                  <span>Need a pet-friendly society</span>
                </div>
                {form.hasPets ? (
                  <CheckCircle2 size={18} className="toggle-check" />
                ) : (
                  <XCircle size={18} className="toggle-check muted" />
                )}
              </div>
            </label>

            <label
              className={`toggle-card ${form.hasChildren ? "active" : ""}`}
            >
              <input
                type="checkbox"
                name="hasChildren"
                checked={form.hasChildren}
                onChange={handleChange}
              />
              <div className="toggle-content">
                <Baby size={22} />
                <div>
                  <strong>Children</strong>
                  <span>Prefer child-friendly amenities</span>
                </div>
                {form.hasChildren ? (
                  <CheckCircle2 size={18} className="toggle-check" />
                ) : (
                  <XCircle size={18} className="toggle-check muted" />
                )}
              </div>
            </label>
          </div>

          <div className="invest-actions">
            <button type="submit" className="btn btn-primary invest-submit">
              <Search size={18} />
              Recommend Apartments
              <ArrowRight size={18} />
            </button>
          </div>
        </form>
      ) : (
        <div className="invest-results">
          <div className="results-summary">
            <div className="summary-chips">
              <span className="chip">
                <MapPin size={14} /> {form.area}
              </span>
              <span className="chip">
                <Users size={14} /> {form.people} people
              </span>
              <span className="chip">
                <Wallet size={14} /> Up to {formatPrice(form.budget)}
              </span>
              {form.hasPets && (
                <span className="chip">
                  <PawPrint size={14} /> Pets
                </span>
              )}
              {form.hasChildren && (
                <span className="chip">
                  <Baby size={14} /> Children
                </span>
              )}
            </div>
            <button
              type="button"
              className="btn btn-secondary edit-prefs-btn"
              onClick={handleReset}
            >
              Edit Preferences
            </button>
          </div>

          {recommendations.length === 0 ? (
            <div className="empty-results">
              <Home size={40} />
              <h3>No exact matches</h3>
              <p>
                Try increasing your budget, choosing a different area, or
                relaxing pet / children filters.
              </p>
              <button
                type="button"
                className="btn btn-primary"
                style={{ maxWidth: 240, margin: "0 auto" }}
                onClick={handleReset}
              >
                Adjust Preferences
              </button>
            </div>
          ) : (
            <>
              <p className="match-count">
                {recommendations.length} apartment
                {recommendations.length !== 1 ? "s" : ""} matched your
                preferences
              </p>
              <div className="apartment-grid">
                {recommendations.map((apt, index) => (
                  <article
                    key={apt.id}
                    className={`apartment-card ${
                      selectedId === apt.id ? "selected" : ""
                    }`}
                    onClick={() =>
                      setSelectedId((id) => (id === apt.id ? null : apt.id))
                    }
                  >
                    <div
                      className="apartment-visual"
                      style={{ background: apt.imageTone }}
                    >
                      <span className="rank-badge">#{index + 1} Match</span>
                      <span className="score-badge">{apt.matchScore}% fit</span>
                      <Home size={36} strokeWidth={1.5} />
                    </div>

                    <div className="apartment-body">
                      <h3>{apt.name}</h3>
                      <p className="apartment-meta">
                        <MapPin size={14} /> {apt.area} · {apt.builder}
                      </p>

                      <div className="apartment-stats">
                        <div>
                          <span className="stat-label">Price</span>
                          <strong>{formatPrice(apt.priceLakhs)}</strong>
                        </div>
                        <div>
                          <span className="stat-label">Size</span>
                          <strong>
                            {apt.bhk} BHK · {apt.sqft} sq.ft
                          </strong>
                        </div>
                        <div>
                          <span className="stat-label">Est. ROI</span>
                          <strong className="roi">{apt.expectedRoi}</strong>
                        </div>
                      </div>

                      <div className="amenity-row">
                        {apt.petsAllowed ? (
                          <span className="tag ok">Pets OK</span>
                        ) : (
                          <span className="tag no">No Pets</span>
                        )}
                        {apt.childFriendly ? (
                          <span className="tag ok">Child Friendly</span>
                        ) : (
                          <span className="tag no">Adult Focused</span>
                        )}
                        <span className="tag">Up to {apt.maxPeople} people</span>
                      </div>

                      <ul className="reason-list">
                        {apt.reasons.slice(0, 3).map((reason) => (
                          <li key={reason}>
                            <CheckCircle2 size={14} /> {reason}
                          </li>
                        ))}
                      </ul>

                      {selectedId === apt.id && (
                        <div className="apartment-detail">
                          <p>
                            Highlights: {apt.highlights.join(" · ")}
                          </p>
                          <button
                            type="button"
                            className="btn btn-primary"
                            style={{ marginTop: "0.75rem" }}
                            onClick={(e) => e.stopPropagation()}
                          >
                            Shortlist This Home
                          </button>
                        </div>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default InvestmentInputs;
