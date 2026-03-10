from __future__ import annotations

import json
import os
from datetime import datetime
from functools import wraps
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)


def load_local_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key:
                    continue
                # Keep explicit OS env vars if already set.
                if key not in os.environ:
                    os.environ[key] = value.strip().strip('"').strip("'")
    except OSError:
        # If .env cannot be read, proceed with existing environment values.
        return


load_local_env()

# Replace these with your real values in production.
app.secret_key = os.getenv("FLASK_SECRET_KEY", "")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "",
)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///linkedin_optimizer.db"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# SQLAlchemy supports PostgreSQL URLs directly.
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class ProfileAnalysis(db.Model):
    __tablename__ = "profile_analyses"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    score = db.Column(db.Integer, nullable=False)
    analysis_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def infer_field(text: str) -> str:
    lowered = text.lower()
    if any(k in lowered for k in ["python", "data", "machine learning", "sql", "analyst"]):
        return "data"
    if any(k in lowered for k in ["react", "frontend", "ui", "javascript", "css"]):
        return "frontend"
    if any(k in lowered for k in ["node", "backend", "api", "flask", "django"]):
        return "backend"
    return "software"


def recommend_skills(field: str) -> List[str]:
    skill_map = {
        "data": ["Python", "SQL", "Pandas", "Data Visualization", "Machine Learning", "Git"],
        "frontend": ["React", "JavaScript", "TypeScript", "HTML", "CSS", "Git"],
        "backend": ["Python", "Flask", "Node.js", "REST APIs", "PostgreSQL", "Git"],
        "software": ["Python", "Data Structures", "React", "Node.js", "SQL", "Git"],
    }
    return skill_map[field]


def recommend_keywords(field: str) -> List[str]:
    keyword_map = {
        "data": ["Data Analyst", "Python Developer", "Business Intelligence", "SQL Analyst"],
        "frontend": ["Frontend Developer", "React Developer", "UI Engineer", "JavaScript Developer"],
        "backend": ["Backend Developer", "API Developer", "Python Developer", "Software Engineer"],
        "software": ["Software Developer", "Frontend Developer", "Data Analyst", "Python Developer"],
    }
    return keyword_map[field]


def improve_experience(experience: str) -> str:
    if not experience.strip():
        return ""
    if len(experience.split()) < 7:
        return (
            f"Led a project where I {experience.strip().rstrip('.')} "
            "and improved performance, usability, and delivery quality."
        )
    return f"Delivered measurable outcomes by {experience.strip().rstrip('.')} with strong focus on impact."


def optimize_headline(headline: str, skills: List[str], field: str) -> str:
    role_map = {
        "data": "Data Analyst",
        "frontend": "Frontend Developer",
        "backend": "Backend Developer",
        "software": "Software Developer",
    }
    role = role_map[field]
    top_skills = " | ".join(skills[:2]) if skills else "Problem Solver"
    base = headline.strip() if headline.strip() else "Aspiring Professional"
    return f"{base} | {role} | {top_skills} | Open to Opportunities"


def generate_about(education: str, skills: List[str], interests: str, field: str) -> str:
    role_map = {
        "data": "data-driven solutions",
        "frontend": "intuitive user experiences",
        "backend": "scalable backend systems",
        "software": "impactful software products",
    }
    focus = role_map[field]
    skill_text = ", ".join(skills[:4]) if skills else "software engineering fundamentals"
    edu = education.strip() if education.strip() else "a strong academic background"
    int_text = interests.strip() if interests.strip() else "continuous learning and collaboration"
    return (
        f"I am a motivated professional with {edu}. My core strengths include {skill_text}. "
        f"I enjoy building {focus} and I am particularly interested in {int_text}. "
        "I am open to internships and full-time opportunities where I can contribute and grow."
    )


def call_gemini_text(prompt: str) -> str:
    if not GEMINI_API_KEY:
        app.logger.warning("GEMINI_API_KEY is missing.")
        return ""

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    req = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
            candidates = result.get("candidates", [])
            if not candidates:
                app.logger.warning("Gemini returned no candidates.")
                return ""
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                app.logger.warning("Gemini returned empty parts.")
                return ""
            return parts[0].get("text", "").strip()
    except HTTPError as e:
        app.logger.warning("Gemini HTTPError %s: %s", e.code, e.reason)
        return ""
    except URLError as e:
        app.logger.warning("Gemini URLError: %s", e.reason)
        return ""
    except TimeoutError:
        app.logger.warning("Gemini request timed out.")
        return ""
    except json.JSONDecodeError:
        app.logger.warning("Gemini response JSON parsing failed.")
        return ""


def parse_gemini_json(raw_text: str) -> Dict[str, Any]:
    cleaned = raw_text.strip()
    if "```" in cleaned:
        cleaned = cleaned.replace("```json", "```").replace("```JSON", "```")
        chunks = cleaned.split("```")
        cleaned = chunks[1].strip() if len(chunks) >= 2 else cleaned
    if not cleaned.startswith("{"):
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and first < last:
            cleaned = cleaned[first : last + 1]
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return {}
    return {}


def gemini_enhance(form_data: Dict[str, str], fallback_analysis: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"""
You are an expert LinkedIn profile reviewer.
Analyze the user's profile data and return strict JSON only. Do not add markdown.

Required JSON structure:
{{
  "score": <integer 0-100>,
  "section_status": {{
    "headline": <true/false>,
    "about": <true/false>,
    "experience": <true/false>,
    "skills": <true/false>,
    "keywords": <true/false>
  }},
  "optimized": {{
    "headline": "<improved headline>",
    "about": "<improved about section>",
    "experience": "<improved experience description>",
    "skills": ["<skill1>", "<skill2>", "..."],
    "keywords": ["<keyword1>", "<keyword2>", "..."]
  }},
  "improvement_suggestions": ["<suggestion1>", "<suggestion2>", "..."]
}}

Rules:
- Keep suggestions practical and concise.
- Skills list: 5-8 items.
- Keywords list: 4-8 items.
- Score should reflect completeness and quality.

User Input:
{json.dumps(form_data)}
"""
    raw = call_gemini_text(prompt)
    parsed = parse_gemini_json(raw)
    if not parsed:
        fallback_analysis["ai_source"] = "fallback"
        return fallback_analysis

    ai_analysis = dict(fallback_analysis)
    ai_score = parsed.get("score")
    if isinstance(ai_score, int):
        ai_analysis["score"] = max(0, min(100, ai_score))

    parsed_section_status = parsed.get("section_status")
    if isinstance(parsed_section_status, dict):
        for key in ai_analysis["section_status"]:
            if key in parsed_section_status:
                ai_analysis["section_status"][key] = bool(parsed_section_status[key])

    parsed_optimized = parsed.get("optimized")
    if isinstance(parsed_optimized, dict):
        ai_analysis["optimized"]["headline"] = str(
            parsed_optimized.get("headline", ai_analysis["optimized"]["headline"])
        ).strip()
        ai_analysis["optimized"]["about"] = str(
            parsed_optimized.get("about", ai_analysis["optimized"]["about"])
        ).strip()
        ai_analysis["optimized"]["experience"] = str(
            parsed_optimized.get("experience", ai_analysis["optimized"]["experience"])
        ).strip()

        ai_skills = parsed_optimized.get("skills")
        if isinstance(ai_skills, list) and ai_skills:
            ai_analysis["optimized"]["skills"] = [str(item).strip() for item in ai_skills[:8] if str(item).strip()]

        ai_keywords = parsed_optimized.get("keywords")
        if isinstance(ai_keywords, list) and ai_keywords:
            ai_analysis["optimized"]["keywords"] = [
                str(item).strip() for item in ai_keywords[:8] if str(item).strip()
            ]

    ai_suggestions = parsed.get("improvement_suggestions")
    if isinstance(ai_suggestions, list) and ai_suggestions:
        ai_analysis["improvement_suggestions"] = [
            str(item).strip() for item in ai_suggestions[:8] if str(item).strip()
        ]

    ai_analysis["ai_source"] = "gemini"
    return ai_analysis


def analyze_profile(form_data: Dict[str, str]) -> Dict[str, Any]:
    headline = form_data.get("headline", "").strip()
    about = form_data.get("about", "").strip()
    experience = form_data.get("experience", "").strip()
    skills_raw = form_data.get("skills", "").strip()
    profile_content = form_data.get("profile_content", "").strip()
    education = form_data.get("education", "").strip()
    interests = form_data.get("interests", "").strip()

    combined_text = " ".join([headline, about, experience, skills_raw, profile_content])
    field = infer_field(combined_text)
    recommended_skills = recommend_skills(field)
    recommended_keywords = recommend_keywords(field)

    skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
    if not skills:
        skills = recommended_skills[:3]

    section_status = {
        "headline": bool(headline),
        "about": bool(about),
        "experience": bool(experience),
        "skills": bool(skills_raw),
        "keywords": any(k.lower() in combined_text.lower() for k in recommended_keywords),
    }
    score = int((sum(section_status.values()) / len(section_status)) * 100)

    improved_headline = optimize_headline(headline, skills, field)
    generated_about = generate_about(education, skills, interests, field)
    improved_experience = improve_experience(experience)

    suggestions = []
    if not section_status["headline"]:
        suggestions.append("Add a clear headline with role + skills + goal.")
    if not section_status["about"]:
        suggestions.append("Write a concise About section with achievements and interests.")
    if not section_status["experience"]:
        suggestions.append("Describe experience using action verbs and measurable outcomes.")
    if not section_status["skills"]:
        suggestions.append("Add at least 5-8 skills relevant to your target role.")
    if not section_status["keywords"]:
        suggestions.append("Include recruiter keywords naturally in headline and about section.")

    base_analysis: Dict[str, Any] = {
        "score": score,
        "section_status": section_status,
        "current": {
            "headline": headline or "Not provided",
            "about": about or "Not provided",
            "experience": experience or "Not provided",
            "skills": skills,
        },
        "optimized": {
            "headline": improved_headline,
            "about": generated_about,
            "experience": improved_experience or "Add project-based experience with impact metrics.",
            "skills": recommended_skills,
            "keywords": recommended_keywords,
        },
        "improvement_suggestions": suggestions,
    }

    return gemini_enhance(form_data, base_analysis)


def current_user() -> User | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


@app.route("/")
def landing():
    return render_template("pages/landing.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        action = request.form.get("action", "login").strip().lower()
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not email or not password:
            flash("Email and password are required.", "danger")
            return redirect(url_for("login"))

        if action == "signup":
            if not name:
                flash("Name is required for signup.", "danger")
                return redirect(url_for("login"))
            existing = User.query.filter_by(email=email).first()
            if existing:
                flash("Email already registered. Please login.", "warning")
                return redirect(url_for("login"))

            user = User(name=name, email=email, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            session["user_id"] = user.id
            session["user"] = {"name": user.name, "email": user.email}
            flash("Account created successfully.", "success")
            return redirect(url_for("dashboard"))

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))

        session["user_id"] = user.id
        session["user"] = {"name": user.name, "email": user.email}
        flash("Logged in successfully.", "success")
        return redirect(url_for("dashboard"))

    return render_template("pages/login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("landing"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    if not user:
        session.clear()
        return redirect(url_for("login"))

    records = (
        ProfileAnalysis.query.filter_by(user_id=user.id)
        .order_by(ProfileAnalysis.created_at.desc())
        .limit(10)
        .all()
    )
    history = [
        {"date": row.created_at.strftime("%Y-%m-%d %H:%M"), "score": row.score}
        for row in records
    ]
    latest = json.loads(records[0].analysis_json) if records else {}
    return render_template("pages/dashboard.html", history=history, latest=latest)


@app.route("/analyzer", methods=["GET", "POST"])
@login_required
def analyzer():
    if request.method == "POST":
        user = current_user()
        if not user:
            session.clear()
            return redirect(url_for("login"))

        analysis = analyze_profile(request.form.to_dict())
        record = ProfileAnalysis(
            user_id=user.id,
            score=int(analysis["score"]),
            analysis_json=json.dumps(analysis),
        )
        db.session.add(record)
        db.session.commit()

        session["latest_analysis"] = analysis
        if analysis.get("ai_source") == "gemini":
            flash("Profile analyzed successfully using Gemini AI.", "success")
        else:
            flash("Gemini response failed. Showing fallback analysis.", "warning")
        return redirect(url_for("suggestions"))

    return render_template("pages/analyzer.html")


@app.route("/suggestions")
@login_required
def suggestions():
    analysis = session.get("latest_analysis")
    if analysis:
        return render_template("pages/suggestions.html", analysis=analysis)

    user = current_user()
    if not user:
        session.clear()
        return redirect(url_for("login"))

    latest_record = (
        ProfileAnalysis.query.filter_by(user_id=user.id)
        .order_by(ProfileAnalysis.created_at.desc())
        .first()
    )
    if not latest_record:
        flash("Run an analysis first.", "warning")
        return redirect(url_for("analyzer"))

    analysis = json.loads(latest_record.analysis_json)
    session["latest_analysis"] = analysis
    return render_template("pages/suggestions.html", analysis=analysis)


@app.route("/history")
@login_required
def history():
    user = current_user()
    if not user:
        session.clear()
        return redirect(url_for("login"))

    records = (
        ProfileAnalysis.query.filter_by(user_id=user.id)
        .order_by(ProfileAnalysis.created_at.desc())
        .all()
    )
    history_items = [
        {"date": row.created_at.strftime("%Y-%m-%d %H:%M"), "score": row.score}
        for row in records
    ]
    return render_template("pages/history.html", history=history_items)


@app.route("/settings")
@login_required
def settings():
    return render_template("pages/settings.html")


@app.route("/checklist")
@login_required
def checklist():
    return render_template("pages/checklist.html")


def init_db() -> None:
    try:
        with app.app_context():
            db.create_all()
    except SQLAlchemyError as exc:
        app.logger.exception("Database initialization failed: %s", exc)


init_db()


if __name__ == "__main__":
    app.run(debug=True)
