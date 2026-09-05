"""
Configuration and environment variable loading.
All secrets and tunable constants live here.
"""
import os
from pathlib import Path
try:
    from dotenv import load_dotenv
    _ROOT = Path(__file__).resolve().parent.parent
    load_dotenv(_ROOT / ".env", override=False)
except ImportError:
    _ROOT = Path(__file__).resolve().parent.parent


# ─── Required Secrets ─────────────────────────────────────────────────────────
def _require(key: str) -> str:
    """
    Returns the env var value, or empty string if not set.
    Individual modules validate their own secrets when actually called —
    this prevents the dashboard from crashing when Telegram/Sheets are not configured.
    """
    return os.getenv(key, "")


def _validate(key: str, value: str, context: str = "") -> str:
    """Call this inside functions that actually need the secret."""
    if not value:
        where = f" (needed for: {context})" if context else ""
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set{where}. "
            f"Copy .env.example to .env and fill in the values."
        )
    return value


TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID: str   = _require("TELEGRAM_CHAT_ID")

GOOGLE_SHEET_ID: str    = _require("GOOGLE_SHEET_ID")

# Service account credentials: either a file path OR base64-encoded JSON (CI)
GCP_SA_KEY_B64: str  = os.getenv("GCP_SA_KEY_B64", "")
GCP_SA_KEY_FILE: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

GEMINI_API_KEY: str = _require("GEMINI_API_KEY")

# ─── Gmail & Follow-up Settings ───────────────────────────────────────────────
GMAIL_USER: str         = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "")
FOLLOW_UP_DAYS: int     = int(os.getenv("FOLLOW_UP_DAYS", "7"))

# ─── Optional Settings ────────────────────────────────────────────────────────
USER_AGENT: str = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
)

# ─── Paths ────────────────────────────────────────────────────────────────────
DB_PATH: Path = _ROOT / "data" / "jobs.db"
MASTER_CV_PATH: Path = _ROOT / "data" / "master_cv.json"
OUTPUT_DIR: Path = _ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
(DB_PATH.parent).mkdir(exist_ok=True)

# ─── Filter: Location Keywords ────────────────────────────────────────────────
BERLIN_KEYWORDS = [
    "berlin",
    "10",      # Berlin postcodes start with 1
]

REMOTE_KEYWORDS = [
    "remote",
    "home office",
    "homeoffice",
    "home-office",
    "anywhere",
    "bundesweit",
    "deutschlandweit",
    "full remote",
    "fully remote",
]

# ─── Filter: Language — HARD REJECT patterns (regex, case-insensitive) ─────────
# If ANY of these patterns match the job text → job is immediately rejected.
GERMAN_MANDATORY_PATTERNS: list[str] = [
    # Command / Knowledge / Skills / Fluency in German
    r"(?:command|knowledge|skills?|fluency|proficien\w*)\s+(?:of|in)\s+german",
    r"(?:good|fluent|strong|solid|excellent|fair|sound|working|business)\s+(?:command|knowledge|skills?|fluency)\s+of\s+german",
    r"german\s+(?:language\s+)?(?:skills?|knowledge|command|fluency)\s*(?:are|is)?\s*(?:required|mandatory|essential|needed)",
    # German required / mandatory / must / alongside
    r"german\s+(?:and\s+english\s+)?(?:is\s+|are\s+)?(?:required|mandatory|essential|a\s+must|necessary)",
    r"(?:required|mandatory|essential):\s*.*german",
    r"languages?:\s*.*german(?!\s*(?:is\s+)?(?:a\s+plus|optional|nice))",
    r"fluent\s+in\s+german",
    r"speak\s+german",
    r"german\s+(?:alongside|as\s+well\s+as)\s+english",
    r"both\s+(?:german\s+and\s+english|english\s+and\s+german)",
    r"(?:german|deutsch)\s*(?:\([^)]*\))?\s*:\s*(?:b[12]|c[12]|good|fluent|required|mandatory|verhandlungssicher|sehr\s+gut|gut)",
    r"\b(?:b[12]|c[12])\s+(?:german|deutsch)\b",
    r"\b(?:german|deutsch)\s+(?:b[12]|c[12])\b",
    # German expressions
    r"\bdeutschkenntnisse\b",
    r"\bverhandlungssicher\w*\b",
    r"\bdeutsch\s+in\s+wort\s+und\s+schrift\b",
    r"auf\s+deutsch\s+und\s+englisch",
    r"deutsch\s+und\s+englisch",
    r"englisch\s+und\s+deutsch",
    r"\b(?:sehr\s+gute|gute|flie(?:ß|ss)ende|muttersprachliche)\s+deutsch\w*\b",
    r"\bdeutsch\s+(?:ist\s+)?(?:voraussetzung|erforderlich|pflicht)\b",
    r"\bdeutsch\s+als\s+(?:mutter|arbeits)sprache\b",
]

# Context patterns where 'German' is mentioned but NOT as a required language
# (e.g. 'German is a plus', 'German university', 'German resident')
GERMAN_OPTIONAL_PATTERNS: list[str] = [
    r"german\s+(?:or\s+\w+\s+)?(?:is\s+)?(?:a\s+plus|optional|nice\s+to\s+have|beneficial|not\s+required|not\s+mandatory|an\s+advantage)",
    r"(?:von\s+vorteil|kein\s+muss|nicht\s+zwingend|nicht\s+erforderlich|optional|plus)",
    r"german\s+(?:resident|university|market|contract|office|entity|branch|citizen|work\s+permit|labor\s+market)",
]

# ─── Filter: Language — POSITIVE English signals ───────────────────────────────
ENGLISH_KEYWORDS: list[str] = [
    # Explicit working-language statements
    "working language is english",
    "working language: english",
    "our company language is english",
    "company language is english",
    "business language is english",
    "language of work is english",
    "language: english",
    # Environment / culture
    "english-speaking",
    "english speaking team",
    "international team",
    "international environment",
    "english environment",
    "communication in english",
    "english as the primary language",
    # Skill requirement framing that implies English is acceptable
    "fluent in english",
    "proficient in english",
    "english required",
    "english is required",
    "english is a must",
    "english (mandatory)",
    "english (required)",
    # Simple occurrence (used as a soft signal in heuristic fallback)
    "english",
]

# ─── Filter: Position Type Keywords ───────────────────────────────────────────
# Job must match at least ONE of these in title or description.
WORKING_STUDENT_PATTERNS: list[str] = [
    r"\bwerkstudent\w*\b",
    r"\bworking\s+student\b",
    r"\bstudentische\s+hilfskraft\b",
    r"\bstud\.\s*hilfskraft\b",
    r"\bstudent\s+assistant\b",
]

INTERN_PATTERNS: list[str] = [
    r"\bintern\b",
    r"\binternship\b",
    r"\bpraktikant\w*\b",
    r"\bpraktikum\b",
]

# ─── Filter: Tech-Only Job Category Keywords ──────────────────────────────────
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Data & AI": [
        "data science", "data scientist", "machine learning", "deep learning",
        "artificial intelligence", " ai ", " ai,", "(ai)", "nlp",
        "natural language processing", "computer vision", "llm",
        "large language model", "generative ai", "rag", "vector",
        "data analytics", "data analyst", "business intelligence", " bi ",
        "tableau", "power bi", "looker", "looker studio", "dbt",
        "data engineering", "data engineer", "etl", "data pipeline",
        "spark", "airflow", "data warehouse", "snowflake", "bigquery",
        "databricks", "mlops", "model training", "feature engineering",
    ],
    "Software & IT": [
        "software engineer", "software developer", "software development",
        "backend", "back-end", "frontend", "front-end",
        "full stack", "fullstack", "full-stack",
        "web developer", "web development", "application developer",
        "python", "java", "typescript", "javascript", "react", "angular",
        "vue", "node.js", "django", "fastapi", "flask", "spring boot",
        "cloud", "aws", "azure", "gcp", "google cloud",
        "devops", "kubernetes", "docker", "terraform", "ci/cd",
        "cybersecurity", "information security", "penetration testing",
        "qa ", "quality assurance", "test automation", "selenium",
        "embedded", "c++", "rust", "golang", "go ", "kotlin", "swift",
        "mobile developer", "android", "ios", "flutter",
        "api development", "microservices", "rest api",
        "linux", "system programming", "networking",
    ],
    "Business Tech": [
        "product manager", "product owner", "product management",
        "business analyst", "business analysis",
        "it project manager", "it project", "it consultant",
        "tech consulting", "digital transformation",
        "scrum master", "agile coach",
    ],
}

# Minimum match score for a job to be sent (0–100)
MIN_MATCH_SCORE: int = 30

# ─── Scraping / Request Settings ──────────────────────────────────────────────
REQUEST_TIMEOUT: int = 30          # seconds
REQUEST_RETRIES: int = 3
REQUEST_DELAY: float = 1.5         # seconds between requests

# ─── Google Sheets Column Layout ──────────────────────────────────────────────
SHEET_HEADERS = [
    "Date Found", "Position", "Company", "Location", "Work Mode",
    "URL", "Source", "Language", "Status", "Notes",
]
SHEET_STATUS_COL = 9   # Column index (1-based) of the "Status" field
