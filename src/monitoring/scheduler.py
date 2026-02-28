"""
Clinical Intelligence Hub — Monitoring Scheduler

Orchestrates all API and Playwright monitors. Designed to be run
via launchd (macOS) on a schedule:
  - API monitors: daily
  - Playwright monitors: weekly

Stores results in SQLite, generates addendum documents for
significant findings, and provides a CLI entry point.
"""

import logging
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.models import AlertSeverity, MonitoringAlert, PatientProfile

logger = logging.getLogger("CIH-Scheduler")


class MonitoringScheduler:
    """Orchestrates all monitoring checks."""

    def __init__(self, data_dir: Path, passphrase: str):
        self.data_dir = data_dir
        self._passphrase = passphrase
        self._profile: Optional[PatientProfile] = None

    def run_api_monitors(self) -> list[MonitoringAlert]:
        """
        Run all API-based monitors (daily).

        Returns:
            List of new alerts found.
        """
        logger.info("Starting API monitoring run...")
        all_alerts = []

        # Load patient profile
        self._load_profile()
        if not self._profile:
            logger.warning("No patient profile loaded — skipping monitoring")
            return []

        # Load API keys
        api_keys = self._load_api_keys()

        # Run each monitor with error isolation
        monitors = [
            ("PubMed", self._run_pubmed, api_keys),
            ("OpenFDA", self._run_openfda, api_keys),
            ("ClinVar", self._run_clinvar, api_keys),
            ("RxNorm", self._run_rxnorm, api_keys),
            ("ClinicalTrials.gov", self._run_clinical_trials, api_keys),
            ("PharmGKB", self._run_pharmgkb, api_keys),
        ]

        for name, runner, keys in monitors:
            try:
                logger.info(f"Running {name} monitor...")
                alerts = runner(keys)
                all_alerts.extend(alerts)
                logger.info(f"  {name}: {len(alerts)} alerts")
            except Exception as e:
                logger.error(f"  {name} monitor failed: {e}")
                logger.debug(traceback.format_exc())

        # Assess relevance and store
        relevant_alerts = self._process_alerts(all_alerts)

        logger.info(
            f"API monitoring complete: {len(all_alerts)} raw, "
            f"{len(relevant_alerts)} relevant alerts"
        )
        return relevant_alerts

    def run_playwright_monitors(self) -> list[MonitoringAlert]:
        """
        Run all Playwright-based monitors (weekly).

        These scrape clinical guideline websites for updates.
        Requires Playwright to be installed.
        """
        logger.info("Starting Playwright monitoring run...")
        all_alerts = []

        self._load_profile()
        if not self._profile:
            logger.warning("No patient profile loaded — skipping monitoring")
            return []

        # Playwright monitors are optional — graceful degradation
        try:
            from src.monitoring.playwright_monitors.guideline_monitor import (
                GuidelineMonitor,
            )
            monitor = GuidelineMonitor()
            alerts = monitor.check(self._profile)
            all_alerts.extend(alerts)
        except ImportError:
            logger.info("Playwright not available — skipping guideline monitors")
        except Exception as e:
            logger.error(f"Guideline monitor failed: {e}")

        relevant_alerts = self._process_alerts(all_alerts)

        logger.info(
            f"Playwright monitoring complete: {len(all_alerts)} raw, "
            f"{len(relevant_alerts)} relevant alerts"
        )
        return relevant_alerts

    def run_all(self) -> list[MonitoringAlert]:
        """Run all monitors (API + Playwright)."""
        api_alerts = self.run_api_monitors()
        pw_alerts = self.run_playwright_monitors()
        return api_alerts + pw_alerts

    # ── Individual Monitor Runners ─────────────────────

    def _run_pubmed(self, api_keys: dict) -> list[MonitoringAlert]:
        from src.monitoring.api_monitors.pubmed_monitor import PubMedMonitor
        monitor = PubMedMonitor(api_key=api_keys.get("ncbi"))
        return monitor.check(self._profile, days_back=7)

    def _run_openfda(self, api_keys: dict) -> list[MonitoringAlert]:
        from src.monitoring.api_monitors.openfda_monitor import OpenFDAMonitor
        monitor = OpenFDAMonitor(api_key=api_keys.get("openfda"))
        return monitor.check(self._profile, days_back=30)

    def _run_clinvar(self, api_keys: dict) -> list[MonitoringAlert]:
        from src.monitoring.api_monitors.clinvar_monitor import ClinVarMonitor
        monitor = ClinVarMonitor(api_key=api_keys.get("ncbi"))
        return monitor.check(self._profile, days_back=30)

    def _run_rxnorm(self, api_keys: dict) -> list[MonitoringAlert]:
        from src.monitoring.api_monitors.rxnorm_monitor import RxNormMonitor
        monitor = RxNormMonitor()
        return monitor.check(self._profile)

    def _run_clinical_trials(self, api_keys: dict) -> list[MonitoringAlert]:
        from src.monitoring.api_monitors.clinical_trials_monitor import (
            ClinicalTrialsMonitor,
        )
        monitor = ClinicalTrialsMonitor()
        return monitor.check(self._profile)

    def _run_pharmgkb(self, api_keys: dict) -> list[MonitoringAlert]:
        from src.monitoring.api_monitors.pharmgkb_monitor import PharmGKBMonitor
        monitor = PharmGKBMonitor()
        return monitor.check(self._profile)

    # ── Alert Processing ───────────────────────────────

    def _process_alerts(self, alerts: list[MonitoringAlert]) -> list[MonitoringAlert]:
        """Assess relevance, store in DB, generate addendums."""
        if not alerts:
            return []

        from src.monitoring.alerting.relevance import RelevanceAssessor
        assessor = RelevanceAssessor()

        relevant_pairs = assessor.filter_alerts(alerts, self._profile)
        relevant_alerts = [alert for alert, _ in relevant_pairs]

        # Store in database
        self._store_alerts(relevant_alerts)

        # Generate addendums for critical/high severity
        addendum_dir = self.data_dir / "addendums"
        addendum_dir.mkdir(parents=True, exist_ok=True)
        assessor.generate_addendums(alerts, self._profile, addendum_dir)

        return relevant_alerts

    def _store_alerts(self, alerts: list[MonitoringAlert]):
        """Store alerts in SQLite database."""
        try:
            import uuid
            from src.database import Database
            db = Database(self.data_dir / "cih.db")

            for alert in alerts:
                alert_id = uuid.uuid4().hex[:12]
                severity_str = (
                    alert.severity.value
                    if hasattr(alert.severity, "value")
                    else str(alert.severity)
                )
                db.save_alert(
                    alert_id=alert_id,
                    source=alert.source,
                    title=alert.title,
                    description=alert.description,
                    relevance=alert.relevance_explanation or "",
                    severity=severity_str,
                    url=alert.url,
                )

            db.close()
        except Exception as e:
            logger.error(f"Failed to store alerts: {e}")

    # ── Profile Loading ────────────────────────────────

    def _load_profile(self):
        """Load patient profile from encrypted vault."""
        if self._profile:
            return

        try:
            from src.encryption import EncryptedVault
            vault = EncryptedVault(self.data_dir, self._passphrase)
            profile_data = vault.load_profile()
            if profile_data:
                self._profile = PatientProfile(**profile_data)
        except Exception as e:
            logger.error(f"Failed to load patient profile: {e}")

    def _load_api_keys(self) -> dict:
        """Load API keys from encrypted vault."""
        try:
            from src.encryption import EncryptedVault
            vault = EncryptedVault(self.data_dir, self._passphrase)
            return vault.load_api_keys() or {}
        except Exception as e:
            logger.debug(f"Failed to load API keys: {e}")
            return {}


# ── CLI Entry Point ────────────────────────────────────────

def main():
    """CLI entry point for running monitors."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Clinical Intelligence Hub — Monitoring"
    )
    parser.add_argument(
        "--mode",
        choices=["api", "playwright", "all"],
        default="api",
        help="Which monitors to run (default: api)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=str(Path(__file__).parent.parent.parent / "data"),
        help="Data directory path",
    )
    parser.add_argument(
        "--passphrase",
        type=str,
        help="Vault passphrase (prompted if not provided)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    data_dir = Path(args.data_dir)

    passphrase = args.passphrase
    if not passphrase:
        import getpass
        passphrase = getpass.getpass("Vault passphrase: ")

    scheduler = MonitoringScheduler(data_dir, passphrase)

    if args.mode == "api":
        alerts = scheduler.run_api_monitors()
    elif args.mode == "playwright":
        alerts = scheduler.run_playwright_monitors()
    else:
        alerts = scheduler.run_all()

    if alerts:
        print(f"\n{'=' * 50}")
        print(f"Found {len(alerts)} relevant alerts:")
        for a in alerts:
            sev = a.severity.value if hasattr(a.severity, "value") else str(a.severity)
            print(f"  [{sev}] {a.title}")
            print(f"    {a.description[:100]}...")
        print(f"{'=' * 50}")
    else:
        print("\nNo new relevant alerts found.")


if __name__ == "__main__":
    main()
