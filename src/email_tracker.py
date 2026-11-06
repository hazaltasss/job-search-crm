"""
email_tracker.py — Gmail Integration & AI Email Classifier for Job Applications.

1. Connects to Gmail via IMAP (SSL) using an App Password.
2. Scans recent emails related to job applications and interviews.
3. Uses Gemini 1.5 Flash to accurately classify the email:
   - INTERVIEW: Interview invitation, screening call, or scheduling request
   - REJECTED: Application unsuccessful notification
   - ASSESSMENT: Online coding test, Hackerrank, or assessment link
   - RECEIVED: Application received confirmation
   - UNRELATED: Non-application emails
4. Automatically updates job statuses and notes in SQLite (jobs.db).
"""
from __future__ import annotations
import email
from email.header import decode_header
import imaplib
import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import google.generativeai as genai

from src.config import GMAIL_USER, GMAIL_APP_PASSWORD, GEMINI_API_KEY
from src.database import get_applied_jobs, update_job_from_email, find_job_by_company

logger = logging.getLogger(__name__)

_CLASSIFIER_PROMPT = """
You are an intelligent email analyzer assisting a candidate with tracking their job applications in Germany/Europe.

Analyze the following email and determine if it is related to a job application or candidacy:

From: {sender}
Subject: {subject}
Date: {date}
Body snippet:
{body}

Classify this email into EXACTLY ONE of the following categories:
- "INTERVIEW": Invitation to an interview, screening call, technical discussion, or link to schedule an interview (e.g. Calendly).
- "ASSESSMENT": Invitation to complete an online coding challenge (e.g. HackerRank, Codility, LeetCode), take-home test, or questionnaire.
- "REJECTED": Notification that the candidate was not selected, application was unsuccessful, or the position was cancelled/filled.
- "RECEIVED": Automated confirmation that the application was received and is under review.
- "UNRELATED": Marketing, newsletters, job alert digests (e.g. LinkedIn job alerts), spam, or not related to a specific active candidacy.

IMPORTANT: Provide the "summary" and "next_step" in professional, clear TURKISH.

Return ONLY a valid JSON object with the following structure (no markdown formatting, no code fences):
{{
  "is_job_related": true,
  "category": "INTERVIEW",
  "company": "Company Name",
  "position": "Job Title (if mentioned in email, else empty)",
  "summary": "Türkçe 1 cümlelik net özet (Örn: 'Zalando 45 dakikalık teknik mülakat daveti ve randevu linki iletti' veya 'Delivery Hero başvurunun olumsuz sonuçlandığını bildirdi')",
  "next_step": "Adayın yapması gereken sıradaki aksiyon (Örn: 'Cuma gününe kadar Calendly üzerinden randevu seçin' veya 'Yok')"
}}
"""


def _clean_header(val: str) -> str:
    """Decode encoded email headers (e.g. UTF-8 base64)."""
    if not val:
        return ""
    decoded_parts = decode_header(val)
    parts = []
    for content, encoding in decoded_parts:
        if isinstance(content, bytes):
            parts.append(content.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(str(content))
    return "".join(parts)


def _extract_body(msg: email.message.Message) -> str:
    """Extract plain text body from email message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disp = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in content_disp:
                payload = part.get_payload(decode=True)
                if payload:
                    body += payload.decode("utf-8", errors="replace") + "\n"
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode("utf-8", errors="replace")
    return body.strip()


def classify_email_with_gemini(sender: str, subject: str, date: str, body: str) -> dict:
    """Send email snippet to Gemini for classification."""
    if not GEMINI_API_KEY:
        raise EnvironmentError("GEMINI_API_KEY is not set.")

    from src.ai_assistant import extract_json_from_text, generate_content_with_fallback

    prompt = _CLASSIFIER_PROMPT.format(
        sender=sender,
        subject=subject,
        date=date,
        body=body[:2000] if body else "(No text content)",
    )

    try:
        config = genai.types.GenerationConfig(
            temperature=0.1,
            max_output_tokens=1024,
            response_mime_type="application/json",
        )
        response = generate_content_with_fallback(prompt, generation_config=config)
    except Exception:
        response = generate_content_with_fallback(prompt)

    raw = response.text.strip() if (response and response.text) else ""

    try:
        return extract_json_from_text(raw)
    except Exception:
        logger.warning("Failed to parse Gemini classification JSON: %s", raw)
        return {
            "is_job_related": False,
            "category": "UNRELATED",
            "company": "",
            "summary": "Could not parse email",
            "next_step": "",
        }


def build_imap_search_query(
    days_back: Optional[int] = None,
    start_date: Optional[date | datetime | str] = None,
    end_date: Optional[date | datetime | str] = None,
) -> str:
    """Build an IMAP search query string based on days_back or start/end dates."""
    def _to_date(val: Optional[date | datetime | str]) -> Optional[date]:
        if val is None:
            return None
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, date):
            return val
        if isinstance(val, str):
            val = val.strip()
            if not val:
                return None
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y"):
                try:
                    return datetime.strptime(val, fmt).date()
                except ValueError:
                    pass
        return None

    s_dt = _to_date(start_date)
    e_dt = _to_date(end_date)

    if not s_dt and days_back is not None and days_back > 0:
        s_dt = (datetime.now(timezone.utc) - timedelta(days=days_back)).date()

    if s_dt and e_dt:
        return f'(SINCE "{s_dt.strftime("%d-%b-%Y")}" BEFORE "{e_dt.strftime("%d-%b-%Y")}")'
    elif s_dt:
        return f'(SINCE "{s_dt.strftime("%d-%b-%Y")}")'
    elif e_dt:
        return f'(BEFORE "{e_dt.strftime("%d-%b-%Y")}")'
    return "ALL"


def calculate_email_metrics(updates: list[dict]) -> dict:
    """Calculate funnel statistics and category breakdowns from classified emails."""
    total = len(updates)
    if total == 0:
        return {
            "total_emails": 0,
            "unique_companies_count": 0,
            "unique_companies": [],
            "categories": {
                "INTERVIEW": 0,
                "ASSESSMENT": 0,
                "REJECTED": 0,
                "RECEIVED": 0,
                "OFFER": 0,
                "OTHER": 0,
            },
            "responded_companies_count": 0,
            "response_rate_percent": 0.0,
            "interview_rate_percent": 0.0,
            "rejection_rate_percent": 0.0,
            "active_interviews": [],
            "assessments": [],
            "rejections": [],
        }

    categories = {
        "INTERVIEW": 0,
        "ASSESSMENT": 0,
        "REJECTED": 0,
        "RECEIVED": 0,
        "OFFER": 0,
        "OTHER": 0,
    }
    company_categories: dict[str, set[str]] = {}
    active_interviews = []
    assessments = []
    rejections = []
    unique_companies: list[str] = []

    for u in updates:
        cat = str(u.get("category", "OTHER")).upper()
        if cat not in categories:
            cat = "OTHER"
        categories[cat] += 1

        comp = str(u.get("company", "")).strip()
        if comp and comp != "Bilinmeyen Şirket":
            if comp not in unique_companies:
                unique_companies.append(comp)
            if comp not in company_categories:
                company_categories[comp] = set()
            company_categories[comp].add(cat)

        item_entry = {
            "company": comp or "Bilinmeyen Şirket",
            "position": u.get("position", ""),
            "date": u.get("date", ""),
            "summary": u.get("summary", ""),
            "next_step": u.get("next_step", ""),
        }
        if cat == "INTERVIEW":
            active_interviews.append(item_entry)
        elif cat == "ASSESSMENT":
            assessments.append(item_entry)
        elif cat == "REJECTED":
            rejections.append(item_entry)

    unique_companies_count = len(unique_companies)
    # Responded companies: companies that returned an INTERVIEW, ASSESSMENT, REJECTED, or OFFER
    responded_companies = [
        c for c, cats in company_categories.items()
        if any(action_cat in cats for action_cat in ("INTERVIEW", "ASSESSMENT", "REJECTED", "OFFER"))
    ]
    responded_count = len(responded_companies)

    base_count = unique_companies_count if unique_companies_count > 0 else total
    response_rate = round((responded_count / base_count) * 100, 1) if base_count > 0 else 0.0

    interview_companies = [c for c, cats in company_categories.items() if "INTERVIEW" in cats or "OFFER" in cats]
    interview_rate = round((len(interview_companies) / base_count) * 100, 1) if base_count > 0 else 0.0

    rejection_companies = [c for c, cats in company_categories.items() if "REJECTED" in cats]
    rejection_rate = round((len(rejection_companies) / base_count) * 100, 1) if base_count > 0 else 0.0

    return {
        "total_emails": total,
        "unique_companies_count": unique_companies_count,
        "unique_companies": unique_companies,
        "categories": categories,
        "responded_companies_count": responded_count,
        "response_rate_percent": response_rate,
        "interview_rate_percent": interview_rate,
        "rejection_rate_percent": rejection_rate,
        "active_interviews": active_interviews,
        "assessments": assessments,
        "rejections": rejections,
    }


def generate_career_insights(metrics: dict, updates: list[dict], use_ai: bool = True) -> str:
    """
    Generate actionable career intelligence and analysis summary based on email metrics.
    Uses Gemini when use_ai is True and API key is present; otherwise falls back to structured report.
    """
    total = metrics.get("total_emails", 0)
    uniq = metrics.get("unique_companies_count", 0)
    cats = metrics.get("categories", {})
    interviews = cats.get("INTERVIEW", 0)
    assessments = cats.get("ASSESSMENT", 0)
    rejections = cats.get("REJECTED", 0)
    received = cats.get("RECEIVED", 0)
    resp_rate = metrics.get("response_rate_percent", 0.0)
    int_rate = metrics.get("interview_rate_percent", 0.0)

    if use_ai and GEMINI_API_KEY:
        from src.ai_assistant import generate_content_with_fallback
        prompt = f"""
Aşağıda Almanya'da (Berlin/Remote) İngilizce çalışan Werkstudent & Staj pozisyonlarına başvuran Hazal Taş'ın (M.Sc. Data Analytics & AI, B.Sc. Bilgisayar Mühendisliği) e-postalarından çıkarılan güncel başvuru analizi verileri yer alıyor:

- İncelenen Toplam Başvuru E-postası: {total}
- Tekil Şirket Sayısı: {uniq}
- Mülakat Daveti Alan Şirketler/E-postalar: {interviews}
- Teknik Değerlendirme Testi (Assessment): {assessments}
- Olumsuz Dönüş (Ret): {rejections}
- Başvuru Alındı Teyidi (İncelemede): {received}
- Genel Dönüş Oranı: %{resp_rate}
- Mülakata Dönüşüm Oranı: %{int_rate}

Son e-posta özetlerinden bazıları:
{json.dumps([{'c': u.get('company'), 'cat': u.get('category'), 's': u.get('summary')} for u in updates[:15]], ensure_ascii=False, indent=2)}

Lütfen Hazal için profesyonel, motive edici, veriye dayalı ve net Türkçe bir "Kariyer Analiz Karnesi & Strateji Raporu" oluştur.
Şu başlıkları içersin:
1. 📈 Başvuru Performansı & Funnel Analizi (Dönüş oranları piyasa standartlarına göre nasıl?)
2. 🎯 Aktif Fırsatlar & Öncelikli Aksiyonlar (Mülakat ve test davetleri için öneriler)
3. 💡 Özgeçmiş ve Başvuru Stratejisi İpuçları (Retleri azaltmak ve kabul şansını artırmak için tavsiyeler)

Format: Temiz ve şık Markdown.
"""
        try:
            resp = generate_content_with_fallback(prompt)
            if resp and resp.text:
                return resp.text.strip()
        except Exception as e:
            logger.warning("Gemini career insights generation failed: %s", e)

    # Heuristic fallback report
    lines = [
        "### 📊 Başvuru Karnesi ve Süreç Analizi",
        "",
        f"- **İncelenen Toplam Başvuru E-postası:** {total}",
        f"- **Tekil Şirket:** {uniq}",
        f"- **Genel Dönüş Oranı:** %{resp_rate}",
        f"- **Mülakat / Davet:** {interviews} (%{int_rate})",
        f"- **Teknik Test / Assessment:** {assessments}",
        f"- **Olumsuz (Ret):** {rejections}",
        f"- **İncelemede / Alındı:** {received}",
        "",
        "#### 💡 Süreç Değerlendirmesi",
    ]
    if interviews > 0:
        lines.append(f"- **Mülakat Aşaması:** Tebrikler! {interviews} mülakat/görüşme davetiniz mevcut. Şirketlerin kültür ve teknik beklentilerine göre hazırlık yapıp randevu takvimlerini gecikmeden teyit edin.")
    if assessments > 0:
        lines.append(f"- **Teknik Değerlendirmeler:** {assessments} adet online test davetiniz var. Testlerin son geçerlilik tarihlerini kaçırmadan sakin bir ortamda tamamlayın.")
    if rejections > 0:
        lines.append(f"- **Piyasa Geri Bildirimi:** {rejections} şirketten olumsuz dönüş alınmış. Almanya pazarında ortalama yanıt alma oranı %10-15 bandındadır; başvuruları Berlin ve Remote odaklı düzenli tutmaya devam edin.")
    if received > 0:
        lines.append(f"- **Devam Eden Başvurular:** {received} şirkette başvurunuz aktif incelemede. 2 haftayı geçen başvurular için kısa ve profesyonel takip (follow-up) e-postası gönderebilirsiniz.")

    return "\n".join(lines)


def sync_gmail(
    days_back: Optional[int] = 14,
    start_date: Optional[date | datetime | str] = None,
    end_date: Optional[date | datetime | str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    max_emails: Optional[int] = 50,
    dry_run: bool = False,
    include_ai_insights: bool = True,
) -> dict:
    """
    Connect to Gmail via IMAP, find application-related emails matching the date criteria,
    classify them with Gemini, and update job records in SQLite.
    """
    active_user = (user or os.getenv("GMAIL_USER") or GMAIL_USER or "").strip()
    active_password = (password or os.getenv("GMAIL_APP_PASSWORD") or GMAIL_APP_PASSWORD or "").strip()

    if not active_user or not active_password:
        return {
            "success": False,
            "error": "GMAIL_USER veya GMAIL_APP_PASSWORD ayarlanmamış. Lütfen yukarıdan e-posta ve 16 haneli uygulama şifrenizi girin.",
            "processed": 0,
            "updates": [],
            "metrics": calculate_email_metrics([]),
            "insights": "",
        }

    updates = []
    search_query = build_imap_search_query(
        days_back=days_back if not (start_date or end_date) else None,
        start_date=start_date,
        end_date=end_date,
    )

    # Comprehensive English & German application keywords
    KEYWORDS = [
        # English
        "application", "applied", "interview", "status", "candidate", "candidacy",
        "careers", "career", "recruiting", "recruitment", "talent", "position",
        "assessment", "challenge", "hackerrank", "codility", "hirevue", "offer",
        "rejection", "regret", "unsuccessful", "moving forward", "next steps",
        "thank you for your interest", "thank you for applying", "invitation to",
        # German
        "bewerbung", "eingangsbestätigung", "absage", "einladung", "vorstellungsgespräch",
        "stellenangebot", "karriere", "kandidat", "kandidatin", "leider", "bedauern",
        "vielen dank", "auswahlverfahren", "rückmeldung", "abgesagt", "stellenanzeige",
    ]

    try:
        logger.info("Connecting to Gmail IMAP for %s with query %s...", active_user, search_query)
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(active_user, active_password)
        mail.select("INBOX")

        status, message_numbers = mail.search(None, search_query)

        if status != "OK" or not message_numbers[0]:
            mail.logout()
            metrics = calculate_email_metrics([])
            return {
                "success": True,
                "processed": 0,
                "updates": [],
                "metrics": metrics,
                "insights": generate_career_insights(metrics, [], use_ai=False),
                "message": f"Belirtilen tarih aralığında ({search_query}) e-posta bulunamadı.",
                "search_query": search_query,
            }

        msg_ids = message_numbers[0].split()
        if max_emails and max_emails > 0:
            recent_ids = msg_ids[-max_emails:]
        else:
            recent_ids = msg_ids

        logger.info("Scanning %d emails (Query: %s)...", len(recent_ids), search_query)

        for mid in reversed(recent_ids):
            try:
                _, data = mail.fetch(mid, "(RFC822)")
                if not data or not data[0] or not isinstance(data[0], tuple):
                    continue
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)

                subject = _clean_header(msg.get("Subject", ""))
                sender = _clean_header(msg.get("From", ""))
                date_str = msg.get("Date", "")
                body = _extract_body(msg)

                # Pre-filter: Check subject and sender first
                subject_lower = subject.lower()
                sender_lower = sender.lower()
                has_kw = any(kw in subject_lower or kw in sender_lower for kw in KEYWORDS)

                # If not matched in headers, check first 600 characters of body
                if not has_kw and body:
                    body_snippet = body[:600].lower()
                    has_kw = any(kw in body_snippet for kw in KEYWORDS)

                if not has_kw:
                    continue

                # Classify with Gemini
                analysis = classify_email_with_gemini(sender, subject, date_str, body)
                if not analysis.get("is_job_related") or analysis.get("category") == "UNRELATED":
                    continue

                company = analysis.get("company", "").strip()
                category = analysis.get("category", "RECEIVED").upper()
                summary = analysis.get("summary", "").strip()
                position = analysis.get("position", "").strip()
                next_step = analysis.get("next_step", "").strip()

                # Match with a job in DB
                matched_job = find_job_by_company(company) if company else None

                status_map = {
                    "INTERVIEW": "interview",
                    "REJECTED": "rejected",
                    "ASSESSMENT": "assessment",
                }
                new_status = status_map.get(category)

                update_info = {
                    "subject": subject,
                    "sender": sender,
                    "date": date_str[:25] if date_str else "",
                    "company": company or "Bilinmeyen Şirket",
                    "position": position,
                    "category": category,
                    "summary": summary,
                    "next_step": next_step,
                    "matched_job": matched_job["title"] if matched_job else None,
                    "matched_company": matched_job["company"] if matched_job else company,
                    "new_status": new_status,
                    "db_updated": False,
                }

                if not dry_run and matched_job and new_status:
                    note = f"[{category}] {summary} ({date_str[:16]})"
                    update_job_from_email(matched_job["id"], new_status, note)
                    update_info["db_updated"] = True

                updates.append(update_info)

            except Exception as item_err:
                logger.warning("Error processing email ID %s: %s", mid, item_err)
                continue

        mail.logout()
        metrics = calculate_email_metrics(updates)
        insights = generate_career_insights(metrics, updates, use_ai=include_ai_insights)
        return {
            "success": True,
            "processed": len(recent_ids),
            "updates": updates,
            "metrics": metrics,
            "insights": insights,
            "search_query": search_query,
        }

    except Exception as exc:
        logger.error("Gmail sync failed: %s", exc)
        err_str = str(exc)
        if "AUTHENTICATIONFAILED" in err_str or "Invalid credentials" in err_str:
            friendly_err = (
                "Google kimlik doğrulama başarısız oldu (Invalid credentials).\n\n"
                "⚠️ Normal Gmail hesabınızın şifresi IMAP ile çalışmaz; Google güvenlik kuralları gereği 16 haneli 'Uygulama Şifresi' (App Password) gereklidir.\n\n"
                "📌 Çözüm Adımları (1 Dakika):\n"
                "1. https://myaccount.google.com/apppasswords adresine gidin (veya Google Hesabı > Güvenlik > 2 Adımlı Doğrulama > Uygulama Şifreleri).\n"
                "2. Bir isim girip (örn: 'JobCRM') 'Oluştur' butonuna tıklayın.\n"
                "3. Size verilen sarı kutudaki 16 haneli şifreyi kopyalayın.\n"
                "4. Dashboard'da 'Çıkış Yap' diyerek yeni 16 haneli şifreyi girip kaydedin."
            )
        else:
            friendly_err = err_str

        return {
            "success": False,
            "error": friendly_err,
            "processed": 0,
            "updates": [],
            "metrics": calculate_email_metrics([]),
            "insights": "",
        }
