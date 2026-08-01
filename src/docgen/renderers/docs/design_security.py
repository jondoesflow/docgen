"""Security & Access Model — pre-build, from a discovery transcript.

After build this document is role × table privilege matrices read from the
metadata. Before build it is the requirements those matrices will have to
satisfy: who the users are, what they may see, what has to be provable, and
which of those are non-negotiable because an auditor or a regulator says so.
"""

from __future__ import annotations

from docgen.renderers.base import RenderContext
from docgen.renderers.docmodel import Callout, Document, Paragraph, Placeholder, Section, Table
from docgen.renderers.docs.transcript_design import (
    DesignDocRenderer,
    requirement_table,
    requirements_matching,
    statement_table,
)
from docgen.snapshot.transcript import TranscriptSnapshot

# Words that mark a candidate term as a group of people rather than a thing —
# used to seed the candidate role list from the client's own job titles.
PEOPLE_WORDS = (
    "manager", "managers", "director", "directors", "analyst", "analysts", "engineer",
    "engineers", "sampler", "samplers", "supervisor", "supervisors", "technician",
    "technicians", "administrator", "administrators", "operator", "operators", "team",
    "teams", "staff", "user", "users", "customer", "customers", "client", "clients",
    "contact", "contacts", "approver", "approvers", "auditor", "auditors", "signatory",
    "signatories", "sponsor", "board", "assistant", "officer", "lead", "leads",
)


class SecurityDesignRenderer(DesignDocRenderer):
    key = "security"
    title = "Security & Access Model"
    purpose = (
        "Who gets access to what, and how that will be proved. The role matrix cannot be built "
        "until the roles exist — but every rule it has to encode was stated in the session, and "
        "is captured here with the words that were used."
    )

    def build(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Document:
        doc = self.shell(snapshot)
        doc.add(self._populations(snapshot))
        doc.add(self._candidate_roles(snapshot, ctx))
        doc.add(self._access_rules(snapshot, ctx))
        doc.add(self._matrix(snapshot))
        doc.add(self._audit(snapshot))
        return doc

    # -- sections ------------------------------------------------------------

    def _populations(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("User populations")
        statements = snapshot.statements_in("user_population")
        if statements:
            section.add(Paragraph("Everything said in the session about who needs access and how "
                                  "many of them there are. These numbers drive both the security "
                                  "model and the licensing position:"))
            section.add(statement_table(statements))
        else:
            section.add(Callout("warning", "No user populations were stated. Both the security "
                                           "model and the licence count depend on this — get the "
                                           "numbers before the estimate."))
        section.add(Placeholder(
            hint="Per population: how many, internal or external, which sites, what device, what "
                 "they need to do, and whether they are named users or shared."))
        return section

    def _candidate_roles(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Section:
        section = Section("Candidate roles")
        rows = []
        for participant in snapshot.participants:
            if participant.role:
                rows.append([participant.role, "Attendee job title",
                             participant.name or participant.key, "[Consultant]"])
        for candidate in snapshot.candidate_objects:
            if candidate.name.split()[-1] in PEOPLE_WORDS and candidate.mentions >= 3:
                rows.append([candidate.surface_form, f"Said {candidate.mentions} times",
                             ", ".join(candidate.speakers[:2]) or "—", "[Consultant]"])
        if rows:
            section.add(Paragraph("Groups of people named in the session. These are candidates for "
                                  "security roles, not a role list — several will collapse into "
                                  "one role and some are not system users at all:"))
            section.add(Table(
                headers=["Named group", "Where it came from", "Mentioned by", "Becomes a role?"],
                rows=rows,
            ))
        else:
            section.add(Paragraph("No user groups were named in this session."))
        section.add(ctx.narrative(
            "design_roles",
            {"groups": [r[0] for r in rows],
             "access_statements": [s.statement for s in snapshot.statements_in("access_control")]},
            hint="Propose the role structure: the smallest set of roles that covers these groups, "
                 "what each can do, and where the boundaries between them fall.",
        ))
        return section

    def _access_rules(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Section:
        section = Section("Access rules stated in the session")
        statements = snapshot.statements_in("access_control")
        security_reqs = [r for r in snapshot.requirements_of("non_functional")
                         if any(word in r.statement.lower() for word in
                                ("access", "secur", "confidential", "audit", "permission",
                                 "competent", "approval", "cleared", "restrict"))]
        if statements:
            section.add(statement_table(statements))
        if security_reqs:
            section.add(Section("Security requirements").add(requirement_table(security_reqs)))
        if not statements and not security_reqs:
            section.add(Callout("warning", "No access or confidentiality rules were stated. That is "
                                           "unusual enough to be worth checking rather than "
                                           "assuming there are none."))
        section.add(ctx.narrative(
            "design_access_rules",
            {"statements": [s.statement for s in statements],
             "requirements": [r.statement for r in security_reqs]},
            hint="Translate these into the access model: which restrictions are role-based, which "
                 "are record-level, which need an explicit access list, and which are enforced by "
                 "process rather than by the system.",
        ))
        return section

    def _matrix(self, snapshot: TranscriptSnapshot) -> Section:  # noqa: ARG002
        section = Section("Role and privilege matrix")
        section.add(Paragraph(
            "Complete once roles and entities are agreed — one row per role, one column per "
            "entity, with the privilege level in each cell. After build, this matrix is generated "
            "from the solution metadata and can be compared against what was agreed here."))
        section.add(Table(
            headers=["Role", "Entity", "Create", "Read", "Write", "Delete", "Scope"],
            rows=[["[Consultant]", "[Consultant]", "", "", "", "", ""]],
        ))
        section.add(Section("Field-level security").add(Placeholder(
            hint="Any attribute that only some users may see or edit — pricing, margin, personal "
                 "data, anything commercially or legally restricted.")))
        return section

    def _audit(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Audit and provability")
        statements = snapshot.statements_in("retention")
        auditable = requirements_matching(snapshot, "audit", "demonstrate", "who has accessed",
                                          "trail", "record of who", "superseded", "evidence")
        if statements or auditable:
            if auditable:
                section.add(requirement_table(auditable))
            if statements:
                section.add(statement_table(statements))
            section.add(Paragraph("Anything the client has to demonstrate to a regulator, auditor "
                                  "or court has to be designed for, not added later."))
        else:
            section.add(Paragraph("No audit requirements were stated in this session."))
        section.add(Placeholder(
            hint="What is audited, how long the audit record is kept, who can read it, and how it "
                 "is produced when someone asks for it."))
        return section
