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

import socket
# Force IPv4 socket resolution globally to eliminate macOS / local ISP IPv6 SYN_SENT packet timeouts
_orig_getaddrinfo = socket.getaddrinfo

def _getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

socket.getaddrinfo = _getaddrinfo_ipv4


# ─── Required Secrets ─────────────────────────────────────────────────────────
def _require(key: str) -> str:
    """
    Returns the env var value, or empty string if not set.
    Individual modules validate their own secrets when actually called.
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

# ─── Configurable Target Preferences (Tunable via .env) ──────────────────────
TARGET_LOCATIONS: list[str] = [
    loc.strip()
    for loc in os.getenv("TARGET_LOCATIONS", "Berlin, Remote").split(",")
    if loc.strip()
]

TARGET_JOB_TYPES: list[str] = [
    t.strip()
    for t in os.getenv("TARGET_JOB_TYPES", "working student, internship").split(",")
    if t.strip()
]

TARGET_SEARCH_KEYWORDS: list[str] = [
    k.strip()
    for k in os.getenv(
        "TARGET_SEARCH_KEYWORDS",
        "working student, werkstudent, working student software, working student data, working student ai, working student qa, working student test, working student support, working student it, werkstudent it, werkstudent software, werkstudent qa, werkstudent test, werkstudent support, internship software, internship data, internship qa, internship it",
    ).split(",")
    if k.strip()
]

# ─── Filter: Location Keywords & City Rules ───────────────────────────────────
BERLIN_KEYWORDS = [
    "berlin",
]

# Genuine remote signals in location field
LOCATION_REMOTE_KEYWORDS = [
    "remote",
    "bundesweit",
    "deutschlandweit",
    "anywhere",
    "full remote",
    "fully remote",
]

# Backward compatibility alias
REMOTE_KEYWORDS = LOCATION_REMOTE_KEYWORDS

# Explicit full-remote patterns required when a job is outside Berlin
FULL_REMOTE_PATTERNS: list[str] = [
    r"\b100%\s*remote\b",
    r"\bfull(?:y)?\s*remote\b",
    r"\bvollständig\s*remote\b",
    r"\bpermanent\s*remote\b",
    r"\bwork\s+from\s+anywhere\b",
    r"\bremote\s+in\s+germany\b",
    r"\bremote\s+(?:across|within)\s+germany\b",
    r"\b100%\s*home\s*office\b",
]

# Onsite / hybrid signals that require physical presence in non-Berlin offices
ONSITE_HYBRID_SIGNALS: list[str] = [
    r"\bhybrid\b",
    r"\bvor\s*ort\b",
    r"\bon-?site\b",
    r"\bpräsenz\b",
    r"\bim\s*büro\b",
    r"\bin\s+our\s+office\b",
    r"\bin\s+unserem\s+büro\b",
    r"\btage\s+(?:pro\s+woche\s+)?im\s+büro\b",
    r"\bdays?\s+(?:per\s+week\s+)?in\s+(?:the\s+)?office\b",
    r"\boffice\s+presence\b",
    r"\bregelmäßig\s+im\s+büro\b",
    r"\bstandort\s+(?:in\s+)?(?:hamburg|münchen|munich|köln|cologne|frankfurt|stuttgart|düsseldorf|essen|dortmund|hannover|leipzig)\b",
]

# Major German physical cities and regions outside Berlin
NON_BERLIN_CITIES: list[str] = [
    "hamburg", "buxtehude", "münchen", "munich", "köln", "cologne", "frankfurt",
    "stuttgart", "düsseldorf", "dusseldorf", "leipzig", "dresden",
    "hannover", "hanover", "nürnberg", "nuremberg", "essen", "bremen",
    "dortmund", "bonn", "karlsruhe", "mannheim", "augsburg", "wiesbaden",
    "aachen", "kiel", "freiburg", "mainz", "rostock", "ulm", "regensburg",
    "würzburg", "wolfsburg", "darmstadt", "heidelberg", "erlangen", "ingolstadt",
    "lohne", "lüneburg", "gütersloh", "walldorf", "potsdam", "grünheide",
]

# Patterns detecting office mandates or mandatory residency in a non-Berlin city
NON_BERLIN_OFFICE_PATTERNS: list[str] = [
    r"\b(?:standort(?:\s+ist)?|arbeitsort(?:\s+ist)?|office|headquarters|hq|center|site)\s*(?:ist\s+|in\s+|:\s*|\n\s*|\s)+(?:hamburg|münchen|munich|frankfurt|köln|cologne|stuttgart|düsseldorf|essen|dortmund|hannover|leipzig|nürnberg|nuremberg|bremen|dresden|karlsruhe|mannheim|augsburg|bonn|lohne|lüneburg|ingolstadt|erlangen)\b",
    r"\b(?:based in|located in|living in|reside in|wohnsitz in|come to the office in|presence in|präsenz in|tage im büro in)\s+(?:our\s+office\s+in\s+|unserem\s+büro\s+in\s+|the\s+office\s+in\s+)?(?:hamburg|münchen|munich|frankfurt(?:\s+am\s+main)?|köln|cologne|stuttgart|düsseldorf|essen|dortmund|hannover|leipzig|nürnberg|nuremberg|lohne|lüneburg)\b",
    r"\b(?:münchen|munich|hamburg|frankfurt|köln|cologne|stuttgart|düsseldorf|nürnberg)\s+(?:office|hub|location)\s+(?:only|required|mandatory)\b",
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
    r"\bstudentische\w*\b",
    r"\bstudent\s+(?:worker|aide|job|developer|analyst|tester|support|assistant)\b",
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
        "data quality", "data annotation", "data labeling", "data cleaning",
        "prompt engineering", "ai evaluation",
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
        "embedded", "c++", "rust", "golang", "go ", "kotlin", "swift",
        "mobile developer", "android", "ios", "flutter",
        "api development", "microservices", "rest api",
        "linux", "system programming", "networking",
    ],
    "QA & Testing": [
        "qa", "qa engineer", "qa tester", "quality assurance",
        "software tester", "software testing", "test automation",
        "test engineer", "test automation engineer", "manual testing",
        "test case", "test cases", "test execution", "bug reporting",
        "bug tracking", "postman", "api testing", "swagger", "cypress",
        "playwright", "selenium", "pytest", "unit testing", "regression testing",
        "integration testing", "performance testing", "load testing",
    ],
    "IT & Technical Support": [
        "tech support", "technical support", "it support", "application support",
        "app support", "helpdesk", "it helpdesk", "technical customer support",
        "saas support", "tier 1", "tier 2", "desktop support", "it specialist",
        "it assistant", "system administrator", "sysadmin", "support engineer",
        "customer solutions", "customer support engineer", "technical operations",
        "troubleshooting", "service desk",
    ],
    "Tech Ops & Business Tech": [
        "product manager", "product owner", "product management",
        "business analyst", "business analysis",
        "it project manager", "it project", "it consultant",
        "tech consulting", "digital transformation",
        "scrum master", "agile coach",
        "tech operations", "tech ops", "product operations", "prodops",
        "crm operations", "crm manager", "hubspot", "salesforce",
        "process automation", "zapier", "make.com",
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
