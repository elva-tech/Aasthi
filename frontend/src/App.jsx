import React, { useEffect, useState } from "react";
import { Building2, Moon, Sun } from "lucide-react";
import InvestmentInputs from "./components/InvestmentInputs";
import Landing from "./components/Landing";
import PropertyInputs from "./components/PropertyInputs";
import ResultCard from "./components/ResultCard";

function getInitialTheme() {
  const stored = localStorage.getItem("aasthi-theme");
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

function App() {
  const [step, setStep] = useState(0);
  const [theme, setTheme] = useState(getInitialTheme);

  const [propertyDetails, setPropertyDetails] = useState({
    propertyType: "Apartment",
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("aasthi-theme", theme);
  }, [theme]);

  const toggleTheme = () =>
    setTheme((t) => (t === "dark" ? "light" : "dark"));

  const handleDueDiligence = () => setStep(1);
  const handleInvestment = () => setStep(3);

  const handlePropertySubmit = (details) => {
    setPropertyDetails(details);
    setStep(2);
  };

  const handleReset = () => {
    setPropertyDetails({ propertyType: "Apartment" });
    setStep(0);
  };

  const goHome = () => setStep(0);

  return (
    <div className="app-container">
      <nav className="app-nav">
        <button type="button" className="logo logo-btn" onClick={goHome}>
          <Building2 size={24} color="var(--accent-secondary)" />
          <span>Aasthi</span>
        </button>

        <div className="nav-actions">
          {step !== 0 && (
            <button type="button" className="nav-link" onClick={goHome}>
              Home
            </button>
          )}
          <button
            type="button"
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label="Toggle theme"
          >
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </nav>

      <main className="main-content">
        {step === 0 && (
          <Landing
            onDueDiligence={handleDueDiligence}
            onInvestment={handleInvestment}
          />
        )}

        {step === 1 && (
          <PropertyInputs onSubmit={handlePropertySubmit} onBack={goHome} />
        )}

        {step === 2 && (
          <ResultCard propertyDetails={propertyDetails} onReset={handleReset} />
        )}

        {step === 3 && <InvestmentInputs onBack={goHome} />}
      </main>
    </div>
  );
}

export default App;
