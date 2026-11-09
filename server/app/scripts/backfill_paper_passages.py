"""Backfill missing PDF passages and full-text vectors.

Usage: python -m app.scripts.backfill_paper_passages [--batch-size 100] [--dry-run]

Dry runs issue SELECTs only. Every scan advances a keyset cursor, including
empty or malformed papers. The maintenance path leaves text-index triggers in
their original state and never disables them for other application requests.
"""

import argparse
import logging
import time

from psycopg2.errors import ForeignKeyViolation
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

MISSING_PAPERS = """
    FROM papers p
    WHERE p.raw_content IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM paper_passages pp WHERE pp.paper_id = p.id)
"""


def positive_batch_size(value: str) -> int:
    """Reject invalid sizes before opening a database session."""
    try:
        size = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("batch size must be a positive integer") from None
    if size <= 0:
        raise argparse.ArgumentTypeError("batch size must be a positive integer")
    return size


def backfill(
    batch_size: int = 100,
    dry_run: bool = False,
    *,
    session_factory=None,
    build_passages=None,
) -> dict:
    """Index each eligible paper at most once in this invocation.

    Optional dependencies permit isolated verification without constructing the
    application's configured engine. Production callers use the real factory
    and the same passage builder as ordinary PDF indexing.
    """
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
        raise ValueError("batch_size must be a positive integer")
    if session_factory is None:
        from app.database.database import SessionLocal

        session_factory = SessionLocal
    if build_passages is None:
        from app.database.crud.paper_crud import paper_crud

        build_passages = paper_crud.build_passages

    db = session_factory()
    started = time.monotonic()
    report = {
        "dry_run": dry_run,
        "papers_found": 0,
        "papers_scanned": 0,
        "papers_indexed": 0,
        "papers_planned": 0,
        "papers_skipped": 0,
        "paper_errors": 0,
        "existing_missing_vectors": 0,
        "vectors_updated": 0,
    }
    try:
        report["papers_found"] = db.execute(text("SELECT COUNT(*) " + MISSING_PAPERS)).scalar_one()
        # Fix an upper boundary so continuous imports cannot extend this run.
        upper_id = db.execute(
            text("SELECT p.id " + MISSING_PAPERS + " ORDER BY p.id DESC LIMIT 1")
        ).scalar_one_or_none()
        report["existing_missing_vectors"] = db.execute(
            text("SELECT COUNT(*) FROM paper_passages WHERE ts_vector IS NULL")
        ).scalar_one()
        logger.info(
            "Found %s papers without passages and %s existing passages without vectors",
            report["papers_found"], report["existing_missing_vectors"],
        )
        after_id = None
        while upper_id is not None:
            rows = db.execute(
                text(
                    "SELECT p.id, p.raw_content " + MISSING_PAPERS
                    + (" AND p.id > :after_id" if after_id is not None else "")
                    + " AND p.id <= :upper_id ORDER BY p.id LIMIT :limit"
                ),
                {"after_id": after_id, "upper_id": upper_id, "limit": batch_size},
            ).fetchall()
            if not rows:
                break
            next_id = rows[-1][0]
            if after_id is not None and next_id <= after_id:
                raise RuntimeError("Paper scan did not advance")
            # Advance even when building a passage fails or yields no content.
            after_id = next_id
            wrote_batch = False
            for paper_id, raw_content in rows:
                report["papers_scanned"] += 1
                if not raw_content.strip():
                    report["papers_skipped"] += 1
                    continue
                try:
                    # PostgreSQL text cannot contain NUL. Ordinary indexing also
                    # strips it; do not create a permanently unindexable batch.
                    passages = build_passages(raw_content.replace("\x00", ""))
                    if not passages:
                        report["papers_skipped"] += 1
                        continue
                except Exception:
                    report["paper_errors"] += 1
                    logger.exception("Unable to build passages for paper %s", paper_id)
                    continue
                if dry_run:
                    report["papers_planned"] += 1
                    logger.info("[DRY RUN] Paper %s: would index %s passages", paper_id, len(passages))
                    continue
                try:
                    # Isolate a concurrent paper deletion from its batch peers.
                    with db.begin_nested():
                        db.execute(
                            text(
                                "INSERT INTO paper_passages (paper_id, start_line, end_line, content) "
                                "VALUES (:paper_id, :start_line, :end_line, :content) "
                                "ON CONFLICT (paper_id, start_line) DO NOTHING"
                            ),
                            [{"paper_id": paper_id, **passage} for passage in passages],
                        )
                    report["papers_indexed"] += 1
                    wrote_batch = True
                except IntegrityError as exc:
                    if not isinstance(exc.orig, ForeignKeyViolation):
                        raise
                    report["papers_skipped"] += 1
                    logger.warning("Paper %s was deleted during passage insertion", paper_id)
            if wrote_batch:
                db.commit()

        if dry_run:
            logger.info(
                "[DRY RUN] Would repair %s existing missing vectors; no changes committed",
                report["existing_missing_vectors"],
            )
        else:
            # Normal inserts use the existing trigger. Repair older missing
            # vectors in bounded batches without changing trigger state.
            upper_vector = db.execute(
                text("SELECT COALESCE(MAX(id), 0) FROM paper_passages WHERE ts_vector IS NULL")
            ).scalar_one()
            after_vector = 0
            while after_vector < upper_vector:
                ids = db.execute(
                    text(
                        "SELECT id FROM paper_passages WHERE ts_vector IS NULL "
                        "AND id > :after_id AND id <= :upper_id ORDER BY id LIMIT :limit"
                    ),
                    {"after_id": after_vector, "upper_id": upper_vector, "limit": batch_size},
                ).scalars().all()
                if not ids:
                    break
                if ids[-1] <= after_vector:
                    raise RuntimeError("Vector scan did not advance")
                result = db.execute(
                    text(
                        "UPDATE paper_passages "
                        "SET ts_vector = to_tsvector('pg_catalog.english', coalesce(content, '')) "
                        "WHERE ts_vector IS NULL AND id > :after_id AND id <= :last_id"
                    ),
                    {"after_id": after_vector, "last_id": ids[-1]},
                )
                db.commit()
                report["vectors_updated"] += result.rowcount
                after_vector = ids[-1]
        logger.info("Backfill finished in %.1fs: %s", time.monotonic() - started, report)
        return report
    except BaseException:
        # Dry run is SELECT-only, including its failure path. Closing the
        # session releases its read transaction without an explicit commit.
        if not dry_run:
            db.rollback()
        raise
    finally:
        db.close()


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=positive_batch_size, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    backfill(batch_size=args.batch_size, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
