"""
Clinical Intelligence Hub — Playwright Guideline Monitors

Scrapes clinical guideline websites for updates relevant to
the patient. Runs weekly.

Target sites:
  - ADA (American Diabetes Association) guidelines
  - AHA (American Heart Association) guidelines
  - USPSTF screening recommendations
  - Drug manufacturer safety pages

Requires: playwright (pip install playwright && playwright install chromium)
"""

import logging
from typing import Optional

from src.models import AlertSeverity, MonitoringAlert, PatientProfile

logger = logging.getLogger("CIH-Monitor-Playwright")


class GuidelineMonitor:
    """Scrapes clinical guideline websites for updates."""

    def __init__(self):
        self._browser = None
        self._page = None

    def check(self, profile: PatientProfile) -> list[MonitoringAlert]:
        """
        Check guideline websites for relevant updates.

        Args:
            profile: Patient profile to check against

        Returns:
            List of monitoring alerts
        """
        alerts = []
        timeline = profile.clinical_timeline

        if not timeline:
            return []

        try:
            self._init_browser()
        except Exception as e:
            logger.error(f"Playwright browser init failed: {e}")
            logger.info("Install with: pip install playwright && playwright install chromium")
            return []

        try:
            # Check guideline sites based on patient conditions
            active_conditions = {
                dx.name.lower()
                for dx in (timeline.diagnoses or [])
                if dx.status and dx.status.lower() in ("active", "chronic")
            }

            # ADA — if patient has diabetes
            diabetes_terms = {"diabetes", "type 2 diabetes", "type 1 diabetes", "dm2", "dm1"}
            if active_conditions & diabetes_terms:
                ada_alerts = self._check_ada_guidelines()
                alerts.extend(ada_alerts)

            # AHA — if patient has cardiovascular conditions
            cardio_terms = {"hypertension", "heart failure", "atrial fibrillation", "coronary artery disease", "cad"}
            if active_conditions & cardio_terms:
                aha_alerts = self._check_aha_guidelines()
                alerts.extend(aha_alerts)

            # USPSTF — screening recommendations (always relevant)
            uspstf_alerts = self._check_uspstf_screening(profile)
            alerts.extend(uspstf_alerts)

        except Exception as e:
            logger.error(f"Guideline monitoring failed: {e}")
        finally:
            self._close_browser()

        logger.info(f"Playwright monitoring found {len(alerts)} alerts")
        return alerts

    def _check_ada_guidelines(self) -> list[MonitoringAlert]:
        """Check ADA Standards of Care for updates."""
        alerts = []
        try:
            self._page.goto(
                "https://diabetesjournals.org/care/issue",
                timeout=30000,
            )
            self._page.wait_for_load_state("domcontentloaded")

            # Look for "Standards of Care" articles
            titles = self._page.query_selector_all("h5.item-title a, .article-title a")
            for title in titles[:5]:
                text = title.text_content().strip()
                if "standard" in text.lower() or "guideline" in text.lower():
                    href = title.get_attribute("href") or ""
                    alerts.append(MonitoringAlert(
                        source="ADA",
                        title="ADA Guideline Update",
                        description=f"New ADA publication: {text[:200]}",
                        relevance_explanation="Patient has diabetes. ADA guidelines may affect treatment.",
                        severity=AlertSeverity.MODERATE,
                        url=f"https://diabetesjournals.org{href}" if href.startswith("/") else href,
                    ))
        except Exception as e:
            logger.debug(f"ADA check failed: {e}")

        return alerts

    def _check_aha_guidelines(self) -> list[MonitoringAlert]:
        """Check AHA for new cardiovascular guidelines."""
        alerts = []
        try:
            self._page.goto(
                "https://www.heart.org/en/professional/quality-improvement/guidelines-and-statements",
                timeout=30000,
            )
            self._page.wait_for_load_state("domcontentloaded")

            # Look for recent guideline entries
            items = self._page.query_selector_all(".content-list-item, .guideline-card, article")
            for item in items[:3]:
                text = item.text_content().strip()[:300]
                if text:
                    alerts.append(MonitoringAlert(
                        source="AHA",
                        title="AHA Guideline Update",
                        description=f"AHA update: {text[:200]}",
                        relevance_explanation="Patient has cardiovascular condition. AHA guidelines may affect treatment.",
                        severity=AlertSeverity.MODERATE,
                        url="https://www.heart.org/en/professional/quality-improvement/guidelines-and-statements",
                    ))
        except Exception as e:
            logger.debug(f"AHA check failed: {e}")

        return alerts

    def _check_uspstf_screening(self, profile: PatientProfile) -> list[MonitoringAlert]:
        """Check USPSTF for relevant screening recommendations."""
        alerts = []
        try:
            self._page.goto(
                "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation-topics/uspstf-a-and-b-recommendations",
                timeout=30000,
            )
            self._page.wait_for_load_state("domcontentloaded")

            # Look for updated recommendations
            rows = self._page.query_selector_all("tr, .recommendation-row, article")
            for row in rows[:5]:
                text = row.text_content().strip()
                if "updated" in text.lower() or "new" in text.lower():
                    alerts.append(MonitoringAlert(
                        source="USPSTF",
                        title="Screening Recommendation Update",
                        description=f"USPSTF update: {text[:200]}",
                        relevance_explanation="Updated screening recommendation may apply to this patient.",
                        severity=AlertSeverity.LOW,
                        url="https://www.uspreventiveservicestaskforce.org/uspstf/recommendation-topics",
                    ))
        except Exception as e:
            logger.debug(f"USPSTF check failed: {e}")

        return alerts

    # ── Browser Management ─────────────────────────────

    def _init_browser(self):
        """Initialize Playwright browser."""
        try:
            from playwright.sync_api import sync_playwright

            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)
            self._page = self._browser.new_page(
                user_agent="ClinicalIntelligenceHub/1.0 (Medical Monitoring)"
            )
        except ImportError:
            raise ImportError(
                "Playwright not installed. "
                "Run: pip install playwright && playwright install chromium"
            )

    def _close_browser(self):
        """Close Playwright browser."""
        try:
            if self._page:
                self._page.close()
            if self._browser:
                self._browser.close()
            if hasattr(self, "_pw") and self._pw:
                self._pw.stop()
        except Exception:
            pass
