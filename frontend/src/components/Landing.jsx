import React from "react";
import {
  ArrowRight,
  Building2,
  Check,
  ClipboardCheck,
  FileSearch,
  Home,
  MapPin,
  Search,
  ShieldCheck,
  Star,
  TrendingUp,
  Users,
} from "lucide-react";

const DUE_DILIGENCE_FEATURES = [
  "EC Verification",
  "Khata Validation",
  "Court Case Search",
  "BESCOM & Water Records",
  "Builder & RERA Checks",
  "Final Risk Report",
];

const INVESTMENT_FEATURES = [
  "Lifestyle-based Matching",
  "Area & Budget Filters",
  "Pet & Family Fit",
  "Apartment Recommendations",
  "ROI Snapshot",
  "Shortlist Ready Homes",
];

const HOW_IT_WORKS = [
  {
    icon: <Search size={24} />,
    title: "Enter Preferences",
    desc: "Share your area, budget, household size, and lifestyle needs.",
  },
  {
    icon: <FileSearch size={24} />,
    title: "We Analyze",
    desc: "Our engine checks legal records, risk factors, and apartment data.",
  },
  {
    icon: <ClipboardCheck size={24} />,
    title: "Get Results",
    desc: "Receive a risk report or curated apartment recommendations instantly.",
  },
  {
    icon: <Home size={24} />,
    title: "Make a Decision",
    desc: "Shortlist verified homes and proceed with confidence.",
  },
];

const TESTIMONIALS = [
  {
    text: "Aasthi's due diligence saved us from buying a disputed property. The risk report caught issues we'd have never found on our own.",
    author: "Priya Sharma",
    role: "First-time buyer, Whitefield",
    initials: "PS",
  },
  {
    text: "The apartment finder matched us perfectly — pet-friendly, within budget, and near good schools. We moved in last month!",
    author: "Rahul & Meena K.",
    role: "Family of 4, Sarjapur Road",
    initials: "RK",
  },
  {
    text: "As a real estate agent, I use Aasthi's verification for every listing. It builds instant trust with my clients.",
    author: "Vikram Patel",
    role: "Property Consultant, Bangalore",
    initials: "VP",
  },
];

function Landing({ onDueDiligence, onInvestment }) {
  return (
    <div className="landing-page">
      {/* ── Hero ── */}
      <section className="landing-hero">
        <span className="landing-badge">
          <Building2 size={14} />
          India&apos;s Real Estate Intelligence Platform
        </span>

        <h1 className="landing-title">
          Verify. Discover.
          <br />
          Move In With Confidence.
        </h1>

        <p className="landing-subtitle">
          Run legal due diligence on any property or find apartments that match
          your budget, area, family size, and lifestyle — all from one platform.
        </p>
      </section>

      {/* ── Stats ── */}
      <section className="stats-bar">
        <div className="stat-item">
          <span className="stat-value">2,500+</span>
          <span className="stat-desc">Properties Verified</span>
        </div>
        <div className="stat-item">
          <span className="stat-value">10+</span>
          <span className="stat-desc">Bangalore Areas</span>
        </div>
        <div className="stat-item">
          <span className="stat-value">98%</span>
          <span className="stat-desc">Accuracy Rate</span>
        </div>
        <div className="stat-item">
          <span className="stat-value">4.8</span>
          <span className="stat-desc">User Rating</span>
        </div>
      </section>

      {/* ── Service Cards ── */}
      <section className="landing-cards">
        <article
          className="landing-card landing-card-blue"
          onClick={onDueDiligence}
          onKeyDown={(e) => e.key === "Enter" && onDueDiligence()}
          role="button"
          tabIndex={0}
        >
          <div className="landing-card-icon blue">
            <ShieldCheck size={28} color="white" />
          </div>

          <h2>Due Diligence</h2>
          <p>
            Verify legal ownership and surface hidden risks before you buy a
            property.
          </p>

          <ul className="feature-list">
            {DUE_DILIGENCE_FEATURES.map((item) => (
              <li key={item}>
                <Check size={15} /> {item}
              </li>
            ))}
          </ul>

          <button
            type="button"
            className="btn btn-primary"
            onClick={(e) => {
              e.stopPropagation();
              onDueDiligence();
            }}
          >
            Start Verification
            <ArrowRight size={18} />
          </button>
        </article>

        <article
          className="landing-card landing-card-green"
          onClick={onInvestment}
          onKeyDown={(e) => e.key === "Enter" && onInvestment()}
          role="button"
          tabIndex={0}
        >
          <div className="landing-card-icon green">
            <TrendingUp size={28} color="white" />
          </div>

          <h2>Investment Intelligence</h2>
          <p>
            Get apartment recommendations based on area, household size, pets,
            children, and budget.
          </p>

          <ul className="feature-list">
            {INVESTMENT_FEATURES.map((item) => (
              <li key={item}>
                <Check size={15} /> {item}
              </li>
            ))}
          </ul>

          <button
            type="button"
            className="btn btn-primary btn-green"
            onClick={(e) => {
              e.stopPropagation();
              onInvestment();
            }}
          >
            Find Apartments
            <ArrowRight size={18} />
          </button>
        </article>
      </section>

      {/* ── How It Works ── */}
      <section className="how-section">
        <h2>How It Works</h2>
        <p>Four simple steps from search to move-in.</p>

        <div className="how-steps">
          {HOW_IT_WORKS.map((step, i) => (
            <div className="how-step" key={step.title}>
              <div className="how-step-number">{i + 1}</div>
              <div className="how-step-icon">{step.icon}</div>
              <h3>{step.title}</h3>
              <p>{step.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Testimonials ── */}
      <section className="testimonials-section">
        <h2>What Our Users Say</h2>
        <p>Trusted by thousands of buyers across Bangalore.</p>

        <div className="testimonials-grid">
          {TESTIMONIALS.map((t) => (
            <div className="testimonial-card" key={t.author}>
              <div className="testimonial-stars">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Star key={i} size={14} fill="#f59e0b" stroke="none" />
                ))}
              </div>
              <p className="testimonial-text">&ldquo;{t.text}&rdquo;</p>
              <div className="testimonial-author">
                <div className="testimonial-avatar">{t.initials}</div>
                <div className="testimonial-author-info">
                  <strong>{t.author}</strong>
                  <span>{t.role}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="landing-footer">
        <div className="footer-links">
          <button type="button" className="footer-link" onClick={onDueDiligence}>
            Due Diligence
          </button>
          <button type="button" className="footer-link" onClick={onInvestment}>
            Apartment Finder
          </button>
          <span className="footer-link">Privacy Policy</span>
          <span className="footer-link">Terms of Service</span>
        </div>
        <p>&copy; {new Date().getFullYear()} Aasthi. Built for Indian real estate buyers.</p>
      </footer>
    </div>
  );
}

export default Landing;
