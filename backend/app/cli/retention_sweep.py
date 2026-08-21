"""Entrypoint for the scheduled retention sweep.

Run by a Kubernetes CronJob (see infra/), not by an in-process scheduler:

- A CronJob is structurally immune to the multi-replica double-run problem.
  An in-process scheduler (APScheduler) runs in every replica, so a 3-replica
  Deployment would fire three concurrent sweeps, each issuing overlapping
  DELETEs; avoiding that needs a distributed lock or leader election, which
  is real machinery to build, test and operate. K8s already guarantees one
  Job per schedule, so the problem disappears rather than being managed.
- Purge failures surface as a failed Job with retained logs, instead of a
  background thread that died silently inside a serving pod.
- It adds no new runtime dependency, which matters for an air-gapped build.

The trade-off: nothing sweeps automatically under plain docker-compose. Run
this module manually (or from host cron) in that environment:

    python -m app.cli.retention_sweep

Exits non-zero on failure so the Job is marked failed and retried.
"""

import logging
import sys

from app.db.database import SessionLocal
from app.db.models import utc_now
from app.services import run_retention_sweep

logger = logging.getLogger(__name__)


def main() -> int:
    """Run one retention sweep under the currently effective policy.

    Resolves retention config from the DB at run time, so the sweep honours
    whatever an admin last set in the settings screen without this job
    needing a redeploy.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    db = SessionLocal()
    try:
        result = run_retention_sweep(db, now=utc_now())
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Retention sweep failed; no changes committed")
        return 1
    finally:
        db.close()

    logger.info(
        "Retention sweep purged: conversations=%d knowledge_base=%d api_keys=%d",
        result["conversations"],
        result["knowledge_base"],
        result["api_keys"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
