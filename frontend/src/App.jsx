import React, { useState } from 'react';
import { Building2, Search, ArrowRight } from 'lucide-react';
import PhoneLogin from './components/PhoneLogin';
import OTPVerify from './components/OTPVerify';
import EcFinder from './components/EcFinder';
import ResultCard from './components/ResultCard';

function App() {
  const [step, setStep] = useState(1);
  const [phoneNumber, setPhoneNumber] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [ecImage, setEcImage] = useState('');
  const [propertyType, setPropertyType] = useState('Non Agricultural');

  // Move to next step
  const handleNext = () => setStep(step + 1);

  // Handle successful login request
  const onLoginInitiated = (phone, session) => {
    setPhoneNumber(phone);
    setSessionId(session);
    handleNext(); // Go to OTP
  };

  // Handle successful OTP verification
  const onOTPVerified = () => {
    handleNext(); // Go to Finder
  };

  // Handle successful Fetch
  const onEcFetched = (imageUrl, type) => {
    setEcImage(imageUrl);
    if (type) setPropertyType(type);
    handleNext(); // Go to Result
  };

  return (
    <div className="app-container">
      <nav className="app-nav">
        <div className="logo">
          <Building2 size={28} color="var(--accent-secondary)" />
          <span>Elva Asti</span>
        </div>
      </nav>

      <main className="main-content">
        {step === 1 && <PhoneLogin onLoginInitiated={onLoginInitiated} />}
        {step === 2 && <OTPVerify sessionId={sessionId} phoneNumber={phoneNumber} onOTPVerified={onOTPVerified} />}
        {step === 3 && <EcFinder sessionId={sessionId} onEcFetched={onEcFetched} />}
        {step === 4 && <ResultCard sessionId={sessionId} imageUrl={ecImage} propertyType={propertyType} onReset={() => setStep(1)} />}
      </main>
    </div>
  );
}

export default App;
