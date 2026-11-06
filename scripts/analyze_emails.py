#!/usr/bin/env python3
"""
analyze_emails.py — CLI tool to fetch, classify, and analyze job application emails from Gmail.

Usage:
    python scripts/analyze_emails.py --days 30
    python scripts/analyze_emails.py --start-date 2026-01-01 --end-date 2026-03-31
    python scripts/analyze_emails.py --all --max-emails 200
    python scripts/analyze_emails.py --dry-run
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import sys

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.email_tracker import sync_gmail
from src.config import GMAIL_USER, GMAIL_APP_PASSWORD

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("email_analyzer")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gmail üzerinden iş başvurusu e-postalarını tara, Gemini ile analiz et ve kariyer karnesi oluştur."
    )
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument(
        "--days",
        type=int,
        default=None,
        help="Geriye dönük taranacak gün sayısı (Örn: --days 30). Varsayılan: 30",
    )
    date_group.add_argument(
        "--all",
        action="store_true",
        help="Tarih filtresi olmadan tüm gelen kutusunu tara.",
    )

    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Başlangıç tarihi (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Bitiş tarihi (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--max-emails",
        type=int,
        default=100,
        help="Taranacak maksimum e-posta sayısı (0 = sınırsız). Varsayılan: 100",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Veritabanındaki (jobs.db) iş durumlarını güncellemeden yalnızca analiz yap.",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Gemini AI çağrısını atla, yalnızca istatistiksel özet üret.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Analiz raporunun kaydedileceği özel dosya yolu (.md).",
    )
    return parser.parse_args()


def save_markdown_report(result: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metrics = result.get("metrics", {})
    cats = metrics.get("categories", {})
    updates = result.get("updates", [])
    insights = result.get("insights", "")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    md_lines = [
        f"# 📬 İş Başvuruları E-posta Analiz Raporu",
        f"**Tarih:** {timestamp}  ",
        f"**Sorgu:** `{result.get('search_query', 'N/A')}`  ",
        f"**İncelenen E-posta Sayısı:** {result.get('processed', 0)}  ",
        "",
        "## 📊 Özet Metrikler",
        "",
        f"| Metrik | Değer |",
        f"| :--- | :--- |",
        f"| Toplam Tespit Edilen Başvuru E-postası | **{metrics.get('total_emails', 0)}** |",
        f"| Tekil Başvurulan Şirket | **{metrics.get('unique_companies_count', 0)}** |",
        f"| Yanıt Alınan Şirket | **{metrics.get('responded_companies_count', 0)}** |",
        f"| Genel Dönüş Oranı (Response Rate) | **%{metrics.get('response_rate_percent', 0.0)}** |",
        f"| Mülakat / Davet Oranı | **%{metrics.get('interview_rate_percent', 0.0)}** |",
        f"| Ret Oranı | **%{metrics.get('rejection_rate_percent', 0.0)}** |",
        "",
        "### Kategori Dağılımı",
        f"- 🎯 **Mülakat Davetleri (INTERVIEW):** {cats.get('INTERVIEW', 0)}",
        f"- 💻 **Teknik Değerlendirme / Test (ASSESSMENT):** {cats.get('ASSESSMENT', 0)}",
        f"- ❌ **Olumsuz Sonuç (REJECTED):** {cats.get('REJECTED', 0)}",
        f"- 📥 **Başvuru Alındı Teyidi (RECEIVED):** {cats.get('RECEIVED', 0)}",
        "",
        "## 💡 Kariyer Karnesi & Strateji Değerlendirmesi",
        "",
        insights,
        "",
        "## 📋 Tespit Edilen Başvuru E-postaları",
        "",
        "| Tarih | Şirket | Pozisyon | Kategori | Özet / Not | Sıradaki Adım |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for u in updates:
        dt = u.get("date", "")[:16]
        comp = u.get("company", "-")
        pos = u.get("position", "-") or "-"
        cat = u.get("category", "-")
        summ = u.get("summary", "-")
        nxt = u.get("next_step", "-") or "-"
        md_lines.append(f"| {dt} | {comp} | {pos} | {cat} | {summ} | {nxt} |")

    output_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"\n📄 Rapor başarıyla kaydedildi: {output_path}")


def main() -> None:
    args = parse_args()

    # Determine date parameters
    days_back = args.days
    start_date = args.start_date
    end_date = args.end_date

    if not args.all and days_back is None and not (start_date or end_date):
        # Default to 30 days if no argument provided
        days_back = 30

    print("=" * 60)
    print("📬 Job Search CRM — Gmail Başvuru E-postası Analizörü")
    print("=" * 60)

    if args.all:
        print("🗓️  Tarih Filtresi: TÜM ZAMANLAR (Tüm gelen kutusu)")
    elif start_date or end_date:
        print(f"🗓️  Tarih Filtresi: {start_date or 'Başlangıç'} -> {end_date or 'Bugün'}")
    else:
        print(f"🗓️  Tarih Filtresi: Son {days_back} gün")

    print(f"⚡ Maksimum E-posta: {'Sınırsız' if args.max_emails <= 0 else args.max_emails}")
    print(f"🔒 Dry-run: {'Açık (DB güncellenmeyecek)' if args.dry_run else 'Kapalı (DB güncellenecek)'}")
    print("-" * 60)

    print("🔄 Gmail'e bağlanılıyor ve e-postalar taranıyor...")
    res = sync_gmail(
        days_back=days_back,
        start_date=start_date,
        end_date=end_date,
        max_emails=args.max_emails,
        dry_run=args.dry_run,
        include_ai_insights=not args.no_ai,
    )

    if not res.get("success"):
        print(f"\n❌ Tarama Başarısız: {res.get('error')}")
        sys.exit(1)

    updates = res.get("updates", [])
    metrics = res.get("metrics", {})
    cats = metrics.get("categories", {})
    insights = res.get("insights", "")

    print(f"\n✨ Tarama Tamamlandı! Toplam {res.get('processed', 0)} e-posta incelendi.")
    print(f"📌 İlgili Başvuru E-postası: {len(updates)}")
    print("-" * 60)
    print("📊 ÖZET METRİKLER:")
    print(f"  • Tekil Şirket Sayısı: {metrics.get('unique_companies_count', 0)}")
    print(f"  • Yanıt Alınan Şirket: {metrics.get('responded_companies_count', 0)}")
    print(f"  • Genel Dönüş Oranı:   %{metrics.get('response_rate_percent', 0.0)}")
    print(f"  • Mülakat Oranı:       %{metrics.get('interview_rate_percent', 0.0)}")
    print(f"  • Ret Oranı:           %{metrics.get('rejection_rate_percent', 0.0)}")
    print("-" * 60)
    print("🎯 KATEGORİ DAĞILIMI:")
    print(f"  • 🎯 Mülakat Davetleri:            {cats.get('INTERVIEW', 0)}")
    print(f"  • 💻 Kodlama / Değerlendirme Testi: {cats.get('ASSESSMENT', 0)}")
    print(f"  • ❌ Olumsuz Sonuç (Ret):          {cats.get('REJECTED', 0)}")
    print(f"  • 📥 Başvuru Alındı Teyidi:        {cats.get('RECEIVED', 0)}")

    if insights:
        print("\n" + "=" * 60)
        print("💡 KARİYER KARNESİ & STRATEJİ RAPORU")
        print("=" * 60)
        print(insights)
        print("=" * 60)

    # Save report
    if args.output:
        report_path = Path(args.output).resolve()
    else:
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = REPO_ROOT / "data" / "reports" / f"email_analysis_{now_str}.md"

    save_markdown_report(res, report_path)


if __name__ == "__main__":
    main()
