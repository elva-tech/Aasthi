# builder_wrapper.py
"""
BUILDER RISK SCORE (Wrapper)

✅ FINAL MEANING (EVERYWHERE):
- risk_score is 0..100 where HIGHER = MORE RISK (worse)
- LOWER = SAFER (better)

Computes:
  1) Rule-based risk score (0..100, higher = more risk)
  2) LLM advisory risk score (0..100, higher = more risk)
     - Gemini is asked for a SAFETY score (higher safer) then converted to RISK score internally:
       risk = 100 - safety
  3) Final blended risk score (default 70% rule + 30% LLM)

Notes:
- Uses SQLite db: db/builder.db
- Seeds example data if DB is empty (optional)
- Returns JSON output safe for json.dumps
"""

from __future__ import annotations
from google import genai
import os
import json
import sys
from typing import Any, Dict, List, Optional
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import Column, Integer, String, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, joinedload

# ----------------------------
# DB setup
# ----------------------------
BASE_DIR = Path(__file__).parent
DB_DIR = BASE_DIR / "db"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "builder.db"

engine = create_engine(f"sqlite:///{DB_PATH}", future=True)
SessionLocal = sessionmaker(bind=engine, future=True)

def get_session():
    return SessionLocal()

Base = declarative_base()

# ----------------------------
# Models
# ----------------------------
class Builder(Base):
    __tablename__ = "builders"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    city = Column(String)
    years_active = Column(Integer)

    projects = relationship("Project", back_populates="builder")
    professionals = relationship("Professional", back_populates="builder")
    issues = relationship("Issue", back_populates="builder")

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    builder_id = Column(Integer, ForeignKey("builders.id"))
    name = Column(String)
    status = Column(String)
    delay_months = Column(Integer)

    builder = relationship("Builder", back_populates="projects")

class Professional(Base):
    __tablename__ = "professionals"
    id = Column(Integer, primary_key=True)
    builder_id = Column(Integer, ForeignKey("builders.id"))
    role = Column(String)
    name = Column(String)
    projects_completed = Column(Integer)
    year_established = Column(Integer)

    builder = relationship("Builder", back_populates="professionals")

class Issue(Base):
    __tablename__ = "issues"
    id = Column(Integer, primary_key=True)
    builder_id = Column(Integer, ForeignKey("builders.id"))
    type = Column(String)
    count = Column(Integer)

    builder = relationship("Builder", back_populates="issues")

Base.metadata.create_all(engine)

# ----------------------------
# Seed example data
# ----------------------------
def seed_example_data() -> bool:
    """
    Returns True if seeded, False if skipped (already exists)
    """
    session = get_session()
    try:
        if session.query(Builder).count() > 0:
            return False

        builder = Builder(name="Prestige Group", city="Bangalore", years_active=25)
        session.add(builder)
        session.flush()

        projects = [
            Project(builder_id=builder.id, name="Prestige Lakeside Habitat", status="completed", delay_months=6),
            Project(builder_id=builder.id, name="Prestige Falcon City", status="completed", delay_months=3),
        ]

        professionals = [
            Professional(builder_id=builder.id, role="architect", name="Rana Ram", projects_completed=22, year_established=2002),
            Professional(builder_id=builder.id, role="structural_engineer", name="Ramkumar G", projects_completed=20, year_established=2002),
            Professional(builder_id=builder.id, role="contractor", name="Larsen & Toubro Limited", projects_completed=600, year_established=1913),
        ]

        issues = [Issue(builder_id=builder.id, type="delay", count=1)]

        session.add_all(projects + professionals + issues)
        session.commit()
        return True
    finally:
        session.close()


# ----------------------------
# Rule-based engine
# Returns RISK score (0..100): higher = more risk (worse)
# ----------------------------
def calculate_builder_risk(builder: Builder) -> Dict[str, Any]:
    """
    Internally computes a SAFETY points total (0..100, higher safer),
    then converts it to RISK score: risk = 100 - safety.
    """
    safety = 0
    reasons: List[str] = []

    # 1) RERA compliance (30) – placeholder heuristic
    rera_points = 30
    safety += rera_points
    reasons.append("RERA compliance: no revoked/suspended signals in DB (placeholder)")

    # 2) Delivery history (25)
    completed_projects = len(builder.projects or [])
    delayed_projects = sum(1 for p in (builder.projects or []) if (p.delay_months or 0) > 0)

    if completed_projects > 0:
        delay_ratio = delayed_projects / completed_projects
        delivery_points = max(0, int(25 * (1 - delay_ratio)))
    else:
        delivery_points = 10  # limited info fallback

    safety += delivery_points
    reasons.append(f"Delivery: {delayed_projects} delayed out of {completed_projects} projects")

    # 3) Professional strength (20)
    profs = builder.professionals or []
    if profs:
        avg_projects = sum(int(p.projects_completed or 0) for p in profs) / len(profs)
    else:
        avg_projects = 0

    if avg_projects >= 20:
        prof_points = 20
    elif avg_projects >= 10:
        prof_points = 15
    else:
        prof_points = 10

    safety += prof_points
    reasons.append(f"Professionals: avg projects completed ≈ {round(avg_projects, 1)}")

    # 4) Scale & experience (15)
    years = int(builder.years_active or 0)
    if years >= 20:
        scale_points = 15
    elif years >= 10:
        scale_points = 10
    else:
        scale_points = 5

    safety += scale_points
    reasons.append(f"Experience: active for {years} years")

    # 5) Issues (10)
    issue_count = sum(int(i.count or 0) for i in (builder.issues or []))
    issue_points = max(0, 10 - issue_count * 2)

    safety += issue_points
    if issue_count > 0:
        reasons.append(f"Issues: total issue count={issue_count} (penalty applied)")
    else:
        reasons.append("Issues: none recorded")

    safety = max(0, min(100, safety))

    # ✅ Convert to risk score (what user wants)
    risk_score = 100 - safety
    risk_score = max(0, min(100, risk_score))

    # ✅ risk level based on risk score (higher = worse)
    if risk_score >= 75:
        risk_level = "HIGH"
    elif risk_score >= 30:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return {"risk_score": int(risk_score), "risk_level": risk_level, "reasons": reasons}


# ----------------------------
# LLM signals + prompt
# ----------------------------
def build_llm_signals(builder: Builder) -> Dict[str, Any]:
    projects = builder.projects or []
    total_projects = len(projects)
    delayed = sum(1 for p in projects if (p.delay_months or 0) > 0)
    avg_delay = (
        sum(int(p.delay_months or 0) for p in projects) / max(1, total_projects)
    )

    return {
        "builder_name": builder.name,
        "city": builder.city,
        "years_active": int(builder.years_active or 0),
        "total_projects": total_projects,
        "delayed_projects": delayed,
        "average_delay_months": round(avg_delay, 2),
        "professionals": [
            {"role": p.role, "projects_completed": int(p.projects_completed or 0)}
            for p in (builder.professionals or [])
        ],
        "issues": [{"type": i.type, "count": int(i.count or 0)} for i in (builder.issues or [])],
    }


def build_llm_prompt(signals: Dict[str, Any]) -> str:

    return f"""
# ROLE

You are a Senior Real Estate Due Diligence Consultant,
Builder Reputation Analyst, RERA Compliance Advisor,
and Construction Risk Assessment Specialist.

# CONTEXT

A prospective buyer wants to evaluate whether a builder is
reliable enough to purchase a property.

Use ONLY the structured JSON data provided.

Do NOT assume or invent any facts.

# OBJECTIVE

Estimate the Builder Safety Score.

Safety Score:

100 = Excellent Builder

0 = Extremely Unsafe Builder

The application will internally convert this to:

Risk Score = 100 - Safety Score

# EVALUATION FRAMEWORK

Evaluate the builder using the following factors.

1. Experience

• Years Active

2. Delivery Performance

• Total Projects

• Delayed Projects

• Average Delay

3. Professional Strength

• Architects

• Structural Engineers

• Contractors

• Projects completed by professionals

4. Builder Issues

• Delay Issues

• Complaint Count

• Other Recorded Issues

5. Overall Builder Stability

• Experience

• Delivery Consistency

• Professional Capability

# SCORING GUIDELINES

Experience

25+ years
Excellent

15–24 years
Good

5–14 years
Average

Below 5 years
Limited experience

Delivery

No delays
Excellent

Minor delays
Moderate deduction

Frequent delays
Significant deduction

Professionals

Large experienced team
Higher Safety

Small or inexperienced team
Lower Safety

Issues

No issues
Highest Safety

Few issues
Moderate deduction

Repeated issues
Significant deduction

# IMPORTANT RULES

• Never invent information.

• Never assume missing data.

• Missing information should reduce confidence,
NOT automatically reduce Safety Score.

• Use ONLY supplied JSON.

• Keep reasons concise.

• Reasons must reference available evidence.

# SAFETY SCORE

90–100

Excellent Builder

75–89

Good Builder

60–74

Average Builder

40–59

Needs Caution

0–39

Poor Builder

# CONFIDENCE

0.90–1.00

Most information available.

0.60–0.89

Moderate information.

0.30–0.59

Sparse information.

Below 0.30

Very limited information.

# INPUT

{json.dumps(signals, ensure_ascii=False, indent=2)}

# OUTPUT

Return ONLY valid JSON.

{{
    "score":0,

    "risk_level":"LOW|MEDIUM|HIGH",

    "confidence":0.0,

    "reasons":[
        "...",
        "...",
        "..."
    ]
}}

# FINAL VALIDATION

Before returning:

✓ Score between 0 and 100.

✓ Higher score means SAFER builder.

✓ Risk Level matches Safety Score.

✓ Confidence matches data completeness.

✓ Reasons are supported by the supplied JSON.

✓ Return ONLY valid JSON.
""".strip()


def _get_builder_llm_key() -> str:
    key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()

    if not key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY in .env")

    return key

def call_llm(prompt: str) -> Dict[str, Any]:
    """
    Returns dict with:
      - score: RISK score (0..100, higher = more risk)
      - risk_level: as returned by model (normalized)
      - confidence: 0..1
      - reasons: list[str]
    """
    try:
        api_key = _get_builder_llm_key()
    except Exception as e:
        raise RuntimeError(f"LLM unavailable: {e}")

    try:

        client = Anthropic(api_key=api_key)

        resp = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=3000,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        text = ""

        for block in resp.content:
            if hasattr(block, "text"):
                text += block.text

        text = text.strip()
        text = text.replace("```json", "").replace("```", "").strip()

        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1 or end <= start:
            raise ValueError(
                "No JSON object found in model output."
            )

        out = json.loads(
            text[start:end + 1]
        )

        # normalize model output
        safety_score = int(
            out.get("score", 60)
        )

        safety_score = max(
            0,
            min(100, safety_score)
        )

        # Convert SAFETY -> RISK
        risk_score = 100 - safety_score

        risk_score = max(
            0,
            min(100, risk_score)
        )

        lvl = str(
            out.get("risk_level", "MEDIUM")
        ).upper()

        if lvl not in {"LOW", "MEDIUM", "HIGH"}:
            lvl = "MEDIUM"

        conf = float(
            out.get("confidence", 0.4)
        )

        conf = max(
            0.0,
            min(1.0, conf)
        )

        reasons = out.get(
            "reasons",
            []
        )

        if not isinstance(reasons, list):
            reasons = [str(reasons)]

        return {
            "score": int(risk_score),
            "risk_level": lvl,
            "confidence": conf,
            "reasons": reasons[:8]
        }

    except Exception as e:
        raise RuntimeError(
            f"LLM scoring failed: {e}"
        )
# ----------------------------
# Blend (default: 70% rules + 30% LLM)
# ----------------------------
def blend_scores(rule_risk: int, llm_risk: int, rule_weight: float = 0.7) -> int:
    final = rule_weight * float(rule_risk) + (1.0 - rule_weight) * float(llm_risk)
    return int(round(max(0, min(100, final))))

# ----------------------------
# Wrapper API
# ----------------------------
def run_builder_wrapper(
    builder_name: Optional[str] = None,
    seed_if_empty: bool = False,
    run_llm: bool = True,
    rule_weight: float = 0.7
) -> Dict[str, Any]:
    """
    Returns JSON:
    {
      "document_type": "BUILDER",
      "db_path": "...",
      "seeded": true/false,
      "builder": {...},
      "rule_based": {...},   # risk_score higher=worse
      "llm": {...},          # score higher=worse
      "final": {...}         # risk score higher=worse
    }
    """
    seeded = False
    if seed_if_empty:
        seeded = seed_example_data()

    session = get_session()
    try:
        q = session.query(Builder).options(
            joinedload(Builder.projects),
            joinedload(Builder.professionals),
            joinedload(Builder.issues),
        )

        if builder_name:
            builder = q.filter(Builder.name.ilike(f"%{builder_name}%")).first()
        else:
            builder = q.first()

        if not builder:
            return {
                "document_type": "BUILDER",
                "db_path": str(DB_PATH),
                "seeded": seeded,
                "error": "No builder found in database"
            }

        builder_summary = {
            "name": builder.name,
            "city": builder.city,
            "years_active": int(builder.years_active or 0),
            "projects": [
                {"name": p.name, "status": p.status, "delay_months": int(p.delay_months or 0)}
                for p in (builder.projects or [])
            ],
            "issues": [{"type": i.type, "count": int(i.count or 0)} for i in (builder.issues or [])],
        }

        rule = calculate_builder_risk(builder)

        llm = None
        if run_llm:
            signals = build_llm_signals(builder)
            prompt = build_llm_prompt(signals)
            llm = call_llm(prompt)

        if llm is not None:
            final_score = blend_scores(int(rule["risk_score"]), int(llm["score"]), rule_weight=rule_weight)
        else:
            final_score = int(rule["risk_score"])

        # ✅ final risk level (higher score = worse)
        if final_score >= 75:
            final_level = "HIGH"
        elif final_score >= 30:
            final_level = "MEDIUM"
        else:
            final_level = "LOW"

        return {
            "document_type": "BUILDER",
            "db_path": str(DB_PATH),
            "seeded": bool(seeded),
            "builder": builder_summary,
            "rule_based": rule,
            "llm": {
                "enabled": bool(run_llm),
                "output": llm,
            },
            "final": {
                "rule_weight": rule_weight,
                "llm_weight": (1.0 - rule_weight) if run_llm else 0.0,
                "risk_score": int(final_score),
                "risk_level": final_level
            }
        }
    finally:
        session.close()


# ----------------------------
# CLI quick test
# ----------------------------
if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else None
    out = run_builder_wrapper(builder_name=name, seed_if_empty=True, run_llm=True, rule_weight=0.7)
    print(json.dumps(out, indent=2, ensure_ascii=False))
