"""Bounded research retrieval with authorization at every read."""
import hashlib
import uuid

from sqlalchemy import func, or_
from sqlalchemy.orm import load_only

from app.database.models import Annotation, Highlight, Paper, PaperNote, PaperPassage, Project, ProjectPaper, ProjectRole
from app.mcp.notes import note_etag


def project_access(user_id):
    return or_(Project.admin_id == user_id, Project.id.in_(
        ProjectRole.__table__.select().with_only_columns(ProjectRole.project_id).where(ProjectRole.user_id == user_id)))


def readable_paper(user_id):
    return or_(Paper.user_id == user_id, Paper.id.in_(
        ProjectPaper.__table__.select().with_only_columns(ProjectPaper.paper_id)
        .join(Project, Project.id == ProjectPaper.project_id).where(project_access(user_id))))


def passage_id(passage):
    digest = hashlib.sha256(passage.content.encode()).hexdigest()[:24]
    return f"passage:{passage.paper_id}:{passage.start_line}:{digest}"


class ResearchReader:
    def __init__(self, db, user, origin):
        self.db, self.user, self.origin = db, user, origin

    def project(self, project_id):
        row = self.db.query(Project).filter(Project.id == uuid.UUID(project_id), project_access(self.user.id)).one_or_none()
        if row is None:
            raise ValueError("Project not found")
        return row

    def paper(self, paper_id):
        row = self.db.query(Paper).options(load_only(Paper.id, Paper.title, Paper.user_id)).filter(Paper.id == uuid.UUID(paper_id), readable_paper(self.user.id)).one_or_none()
        if row is None:
            raise ValueError("Paper not found")
        return row

    def citation_url(self, paper, project_id=None):
        if paper.user_id == self.user.id:
            return f"{self.origin}/paper/{paper.id}"
        projects = self.db.query(Project).join(ProjectPaper, ProjectPaper.project_id == Project.id).filter(
            ProjectPaper.paper_id == paper.id, project_access(self.user.id))
        if project_id is not None:
            projects = projects.filter(Project.id == uuid.UUID(project_id))
        project = projects.order_by(Project.id).first()
        if project is None:
            raise ValueError("Paper not found")
        # Shared papers are opened through the project's existing reader panel.
        return f"{self.origin}/projects/{project.id}"

    def metadata(self, paper):
        return {"id": str(paper.id), "title": (paper.title or "Untitled")[:1000],
                "url": self.citation_url(paper), "authors": [a[:300] for a in (paper.authors or [])[:50]],
                "abstract": (paper.abstract or "")[:4000], "is_owner": paper.user_id == self.user.id}

    def evidence(self, query, project_id=None, limit=20):
        if not query.strip() or len(query) > 200 or not 1 <= limit <= 30:
            raise ValueError("Query must contain 1–200 characters; limit must be 1–30")
        tsquery = func.websearch_to_tsquery('english', query)
        rows = self.db.query(PaperPassage, Paper).join(Paper, Paper.id == PaperPassage.paper_id).options(
            load_only(Paper.id, Paper.title, Paper.user_id))
        if project_id is not None:
            project = self.project(project_id)
            rows = rows.filter(Paper.id.in_(self.db.query(ProjectPaper.paper_id).filter(ProjectPaper.project_id == project.id)))
        else:
            rows = rows.filter(Paper.user_id == self.user.id)
        rows = rows.filter(PaperPassage.ts_vector.op('@@')(tsquery)).order_by(
            func.ts_rank_cd(PaperPassage.ts_vector, tsquery).desc(), Paper.id, PaperPassage.start_line).limit(limit + 1).all()
        results = []
        for passage, paper in rows[:limit]:
            results.append({"id": passage_id(passage), "paper_id": str(paper.id),
                "title": f"{(paper.title or 'Untitled')[:1000]} — lines {passage.start_line}–{passage.end_line}",
                "url": self.citation_url(paper, project_id), "excerpt": passage.content[:1200],
                "excerpt_truncated": len(passage.content) > 1200,
                "start_line": passage.start_line, "end_line": passage.end_line})
        return {"results": results, "has_more": len(rows) > limit,
                "scope": "project" if project_id is not None else "owned_library",
                "coverage": "Indexed PDF passages only; no match does not establish absence from unindexed papers."}

    def fetch(self, item_id):
        try:
            if len(item_id) > 150:
                raise ValueError()
            kind, paper_id, line, digest = item_id.split(':')
            if kind != 'passage' or int(line) < 1:
                raise ValueError()
            paper = self.paper(paper_id)
        except (ValueError, AttributeError):
            raise ValueError("Evidence item not found") from None
        passage = self.db.query(PaperPassage).filter(PaperPassage.paper_id == paper.id, PaperPassage.start_line == int(line)).one_or_none()
        if passage is None or passage_id(passage) != item_id:
            raise ValueError("Evidence item changed or is unavailable; search again")
        source_lines = (paper.raw_content or "").split("\n")
        if not 1 <= passage.start_line <= passage.end_line <= len(source_lines) or "\n".join(source_lines[passage.start_line - 1:passage.end_line]) != passage.content:
            raise ValueError("Evidence index differs from current extracted text; reindex before citing")
        if len(passage.content) > 20000:
            raise ValueError("Passage exceeds 20000 characters; use read_paper_text with bounded offsets")
        return {"id": item_id, "title": f"{(paper.title or 'Untitled')[:1000]} — lines {passage.start_line}–{passage.end_line}",
                "text": passage.content, "url": self.citation_url(paper),
                "metadata": {"paper_id": str(paper.id), "start_line": passage.start_line, "end_line": passage.end_line,
                             "location_basis": "1-indexed lines in extracted text; not PDF page numbers", "kind": "source_text"}}

    def note(self, paper_id, limit=50000, offset=0):
        if offset < 0 or not 1 <= limit <= 50000:
            raise ValueError("Note offset must be nonnegative; limit must be 1–50000")
        # Paper notes are private even when the paper itself is shared.
        self.paper(paper_id)
        note = self.db.query(PaperNote).filter(PaperNote.paper_id == uuid.UUID(paper_id), PaperNote.user_id == self.user.id).one_or_none()
        content = note.content if note else None
        return {"content": content[offset:offset + limit] if content is not None else None,
                "etag": note_etag(content) if content is not None else None,
                "offset": offset, "total_characters": len(content) if content is not None else 0,
                "next_offset": offset + limit if content is not None and len(content) > offset + limit else None,
                "truncated": content is not None and len(content) > offset + limit}

    def highlights(self, paper_id, limit=20):
        self.paper(paper_id)
        rows = self.db.query(Highlight).filter(Highlight.paper_id == uuid.UUID(paper_id), Highlight.user_id == self.user.id).order_by(Highlight.id).limit(limit + 1).all()
        return {"items": [{"id": str(h.id), "text": h.raw_text[:2000], "truncated": len(h.raw_text) > 2000,
                           "page_number": h.page_number, "start_offset": h.start_offset, "end_offset": h.end_offset,
                           "role": h.role} for h in rows[:limit]], "has_more": len(rows) > limit}

    def annotations(self, paper_id, limit=20):
        self.paper(paper_id)
        rows = self.db.query(Annotation, Highlight).outerjoin(Highlight, (Highlight.id == Annotation.highlight_id) & (Highlight.user_id == self.user.id) & (Highlight.paper_id == Annotation.paper_id)).filter(
            Annotation.paper_id == uuid.UUID(paper_id), Annotation.user_id == self.user.id).order_by(Annotation.id).limit(limit + 1).all()
        return {"items": [{"id": str(a.id), "content": a.content[:2000], "truncated": len(a.content) > 2000, "role": a.role,
                           "highlight": {"id": str(h.id), "text": h.raw_text[:2000], "truncated": len(h.raw_text) > 2000,
                                         "page_number": h.page_number} if h else None} for a, h in rows[:limit]], "has_more": len(rows) > limit}

    def context(self, project_id, offset=0, limit=10):
        if offset < 0 or not 1 <= limit <= 10:
            raise ValueError("Offset must be nonnegative; limit must be 1–10")
        project = self.project(project_id)
        rows = self.db.query(Paper).filter(Paper.id.in_(self.db.query(ProjectPaper.paper_id).filter(ProjectPaper.project_id == project.id))).options(
            load_only(Paper.id, Paper.title, Paper.authors, Paper.abstract, Paper.user_id)).order_by(Paper.id).offset(offset).limit(limit + 1).all()
        papers = []
        for paper in rows[:limit]:
            papers.append({**self.metadata(paper), "note": self.note(str(paper.id), 4000),
                           "highlights": self.highlights(str(paper.id), 5), "annotations": self.annotations(str(paper.id), 5)})
        return {"project": {"id": str(project.id), "title": (project.title or '')[:1000],
                            "description": (project.description or '')[:8000],
                            "description_truncated": len(project.description or '') > 8000,
                            "url": f"{self.origin}/projects/{project.id}"},
                "papers": papers, "next_offset": offset + limit if len(rows) > limit else None,
                "private_context": "Only your own notes, highlights and annotations; shared paper access does not share private notes."}
