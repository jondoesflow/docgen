"""Cue-driven extraction of requirements, decisions, actions and RRAID seeds.

Everything here is *detection*, not interpretation. A cue phrase decides that a
sentence is worth surfacing; the sentence itself is carried through verbatim as
the evidence, together with who said it and which source line it is on. Nothing
is paraphrased, scored or invented — the consultant (or the optional LLM tier)
does that, and can always check the extracted quote against the tape.

Cue phrases live in `rules/transcript_cues.yaml` and are overridable per
project via `rules_dir`, exactly like the licensing and naming rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from docgen.snapshot.transcript import (
    ActionItem,
    CandidateObject,
    DecisionItem,
    DiscoveryFinding,
    Evidence,
    ExternalSystem,
    LabelledStatement,
    ParkedItem,
    RequirementSeed,
    Utterance,
)
from docgen.transcripts.formats import RawActionRow, RawMarker, RawParkedRow

# A sentence must be substantial enough to stand alone in a requirements table,
# and short enough not to be a whole monologue.
MIN_WORDS = 5
MAX_WORDS = 70

# Similarity above which an inline [ACTION:]/[PARKED:] marker and a row in the
# end-of-document register are treated as the same item.
_DEDUPE_SCORE = 78

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"'\[(]?[A-Z0-9])")
_STAGE_DIRECTION = re.compile(r"\[(?:laughs?|laughter|pause|sighs?|inaudible|cross\s?talk)[^\]]*\]", re.IGNORECASE)
# "DO to send the analysis" / "Kaya Petrov will collate the formats"
_OWNER_INITIALS = re.compile(r"^(?P<owner>[A-Z]{2,5})\b\s*(?:to\s+|will\s+|:\s*)?(?P<rest>.+)$")
_OWNER_NAME = re.compile(r"^(?P<owner>[A-Z][a-z]+(?:\s[A-Z][a-z]+){0,2})\s+(?:to|will)\s+(?P<rest>.+)$")
_TRAILING_DUE = re.compile(r"\s+[-–]\s+(?P<due>(?:\d+\s+weeks?|\d+\s+days?|by\b.*|\d{1,2}\s+\w{3,9}))\s*$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Compiled rule set
# ---------------------------------------------------------------------------


def _compile(patterns) -> list[re.Pattern]:
    compiled: list[re.Pattern] = []
    for pattern in patterns or []:
        try:
            compiled.append(re.compile(str(pattern), re.IGNORECASE))
        except re.error:
            continue  # a bad override pattern must never break a run
    return compiled


@dataclass
class CueRules:
    requirement_cues: list[re.Pattern] = field(default_factory=list)
    requirement_exclusions: list[re.Pattern] = field(default_factory=list)
    priority_cues: list[tuple[str, list[re.Pattern]]] = field(default_factory=list)
    kind_cues: dict[str, list[re.Pattern]] = field(default_factory=dict)
    section_kind_hints: dict[str, list[str]] = field(default_factory=dict)
    decision_cues: list[re.Pattern] = field(default_factory=list)
    finding_cues: dict[str, list[re.Pattern]] = field(default_factory=dict)
    # design-stage material
    object_min_mentions: int = 3
    object_max_words: int = 3
    object_exclusions: list[re.Pattern] = field(default_factory=list)
    attribute_hints: set[str] = field(default_factory=set)
    system_cues: list[re.Pattern] = field(default_factory=list)
    statement_groups: list[tuple[str, str, list[re.Pattern]]] = field(default_factory=list)

    @classmethod
    def from_rules(cls, data: dict | None) -> "CueRules":
        data = data or {}
        objects = data.get("data_objects") or {}
        groups = data.get("statement_groups") or {}
        return cls(
            requirement_cues=_compile(data.get("requirement_cues")),
            requirement_exclusions=_compile(data.get("requirement_exclusions")),
            priority_cues=[
                (str(entry.get("priority", "unclassified")), _compile(entry.get("patterns")))
                for entry in data.get("priority_cues", [])
                if isinstance(entry, dict)
            ],
            kind_cues={key: _compile(value) for key, value in (data.get("kind_cues") or {}).items()},
            section_kind_hints={
                key: [str(v).lower() for v in value or []]
                for key, value in (data.get("section_kind_hints") or {}).items()
            },
            decision_cues=_compile(data.get("decision_cues")),
            finding_cues={key: _compile(value) for key, value in (data.get("finding_cues") or {}).items()},
            object_min_mentions=int(objects.get("min_mentions", 3) or 3),
            object_max_words=int(objects.get("max_words", 3) or 3),
            object_exclusions=_compile(objects.get("exclusions")),
            attribute_hints={str(h).lower() for h in objects.get("attribute_hints") or []},
            system_cues=_compile(data.get("system_cues")),
            statement_groups=[
                (str(key), str((value or {}).get("label", key)), _compile((value or {}).get("patterns")))
                for key, value in groups.items()
                if isinstance(value, dict)
            ],
        )


def _first_match(patterns: list[re.Pattern], text: str) -> str | None:
    for pattern in patterns:
        found = pattern.search(text)
        if found:
            return found.group(0).strip()
    return None


# ---------------------------------------------------------------------------
# Sentences
# ---------------------------------------------------------------------------


def split_sentences(text: str) -> list[str]:
    cleaned = _STAGE_DIRECTION.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return []
    return [part.strip() for part in _SENTENCE_SPLIT.split(cleaned) if part.strip()]


def _usable(sentence: str) -> bool:
    if sentence.endswith("?"):
        return False
    words = sentence.split()
    return MIN_WORDS <= len(words) <= MAX_WORDS


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


# ---------------------------------------------------------------------------
# Requirements / decisions / findings
# ---------------------------------------------------------------------------


def _evidence(utterance: Utterance, section_title: str, sentence: str, cue: str) -> Evidence:
    return Evidence(
        quote=sentence,
        speaker_key=utterance.speaker_key,
        speaker_name=utterance.speaker_name,
        section_id=utterance.section_id,
        section_title=section_title,
        line=utterance.line,
        cue=cue,
    )


def _classify_kind(rules: CueRules, sentence: str, section_title: str) -> str:
    for kind in ("constraint", "non_functional"):
        if _first_match(rules.kind_cues.get(kind, []), sentence):
            return kind
    lowered = section_title.lower()
    for kind, hints in rules.section_kind_hints.items():
        if any(hint in lowered for hint in hints):
            return kind
    return "functional"


def _classify_priority(rules: CueRules, sentence: str) -> tuple[str, str]:
    for priority, patterns in rules.priority_cues:
        cue = _first_match(patterns, sentence)
        if cue:
            return priority, cue
    return "unclassified", ""


def extract_items(
    utterances: list[Utterance],
    section_titles: dict[str, str],
    rules: CueRules,
) -> tuple[list[RequirementSeed], list[DecisionItem], list[DiscoveryFinding]]:
    requirements: list[RequirementSeed] = []
    decisions: list[DecisionItem] = []
    findings: list[DiscoveryFinding] = []

    seen_requirements: set[str] = set()
    seen_decisions: set[str] = set()
    seen_findings: set[tuple[str, str]] = set()
    counters = {"risk": 0, "assumption": 0, "issue": 0, "dependency": 0, "constraint": 0}
    prefixes = {"risk": "RSK", "assumption": "ASM", "issue": "ISS",
                "dependency": "DEP", "constraint": "CON"}

    for utterance in utterances:
        section_title = section_titles.get(utterance.section_id, "")
        for sentence in split_sentences(utterance.text):
            if not _usable(sentence):
                continue
            key = _normalise(sentence)
            if not key:
                continue

            excluded = _first_match(rules.requirement_exclusions, sentence)
            cue = None if excluded else _first_match(rules.requirement_cues, sentence)
            if cue and key not in seen_requirements:
                seen_requirements.add(key)
                priority, priority_cue = _classify_priority(rules, sentence)
                requirements.append(RequirementSeed(
                    id=f"REQ-{len(requirements) + 1:03d}",
                    statement=sentence,
                    area=section_title,
                    kind=_classify_kind(rules, sentence, section_title),
                    priority=priority,
                    priority_cue=priority_cue,
                    evidence=_evidence(utterance, section_title, sentence, cue),
                ))

            decision_cue = _first_match(rules.decision_cues, sentence)
            if decision_cue and key not in seen_decisions:
                seen_decisions.add(key)
                decisions.append(DecisionItem(
                    id=f"DEC-{len(decisions) + 1:03d}",
                    statement=sentence,
                    evidence=_evidence(utterance, section_title, sentence, decision_cue),
                ))

            for category in ("risk", "issue", "dependency", "constraint", "assumption"):
                finding_cue = _first_match(rules.finding_cues.get(category, []), sentence)
                if not finding_cue or (category, key) in seen_findings:
                    continue
                seen_findings.add((category, key))
                counters[category] += 1
                findings.append(DiscoveryFinding(
                    id=f"{prefixes[category]}-{counters[category]:03d}",
                    category=category,
                    statement=sentence,
                    evidence=_evidence(utterance, section_title, sentence, finding_cue),
                ))

    return requirements, decisions, findings


# ---------------------------------------------------------------------------
# Actions and parked items
# ---------------------------------------------------------------------------


def _marker_owner(text: str) -> tuple[str, str, str | None]:
    """Split `DO to send the call-reason analysis - 2 weeks` into parts."""
    due: str | None = None
    trailing = _TRAILING_DUE.search(text)
    if trailing:
        due = trailing.group("due").strip()
        text = text[: trailing.start()].strip()
    owner = ""
    match = _OWNER_INITIALS.match(text) or _OWNER_NAME.match(text)
    if match:
        owner = match.group("owner")
        text = match.group("rest").strip()
    return owner, text.strip().rstrip("."), due


def _similar(left: str, right: str) -> bool:
    return fuzz.partial_ratio(_normalise(left), _normalise(right)) >= _DEDUPE_SCORE


def build_actions(
    rows: list[RawActionRow],
    markers: list[RawMarker],
    section_titles: dict[str, str],
    resolve_speaker,
) -> list[ActionItem]:
    """Register rows are authoritative; an inline marker that matches one only
    contributes its source line (where the action was actually raised)."""
    inline = [(marker, *_marker_owner(marker.text)) for marker in markers if marker.kind == "action"]
    used: set[int] = set()
    actions: list[ActionItem] = []

    for row in rows:
        owner_key, owner_name = resolve_speaker(row.owner)
        evidence = Evidence(
            quote=row.description,
            speaker_key=owner_key,
            speaker_name=owner_name,
            line=row.line,
            cue="action register",
        )
        for index, (marker, _owner, description, _due) in enumerate(inline):
            if index in used or not _similar(row.description, description):
                continue
            used.add(index)
            evidence = Evidence(
                quote=marker.text,
                speaker_key=owner_key,
                speaker_name=owner_name,
                section_id=marker.section_id,
                section_title=section_titles.get(marker.section_id, ""),
                line=marker.line,
                cue="[ACTION:] marker, confirmed in the action register",
            )
            break
        actions.append(ActionItem(
            id=row.id, owner_key=owner_key, owner_name=owner_name,
            description=row.description, due=row.due, source="register", evidence=evidence,
        ))

    extra = 0
    for index, (marker, owner, description, due) in enumerate(inline):
        if index in used:
            continue
        extra += 1
        owner_key, owner_name = resolve_speaker(owner)
        actions.append(ActionItem(
            id=f"ACT-{extra:03d}",
            owner_key=owner_key,
            owner_name=owner_name,
            description=description,
            due=due,
            source="inline_marker",
            evidence=Evidence(
                quote=marker.text, speaker_key=owner_key, speaker_name=owner_name,
                section_id=marker.section_id, section_title=section_titles.get(marker.section_id, ""),
                line=marker.line, cue="[ACTION:] marker",
            ),
        ))
    return actions


def build_parked(
    rows: list[RawParkedRow],
    markers: list[RawMarker],
    section_titles: dict[str, str],
) -> list[ParkedItem]:
    inline = [marker for marker in markers if marker.kind == "parked"]
    used: set[int] = set()
    items: list[ParkedItem] = []

    for row in rows:
        evidence = Evidence(quote=row.description, line=row.line, cue="parked register")
        for index, marker in enumerate(inline):
            if index in used or not _similar(row.description, marker.text):
                continue
            used.add(index)
            evidence = Evidence(
                quote=marker.text, section_id=marker.section_id,
                section_title=section_titles.get(marker.section_id, ""),
                line=marker.line, cue="[PARKED:] marker, confirmed in the parked register",
            )
            break
        items.append(ParkedItem(id=row.id, description=row.description, source="register", evidence=evidence))

    extra = 0
    for index, marker in enumerate(inline):
        if index in used:
            continue
        extra += 1
        items.append(ParkedItem(
            id=f"PARK-{extra:03d}",
            description=marker.text,
            source="inline_marker",
            evidence=Evidence(
                quote=marker.text, section_id=marker.section_id,
                section_title=section_titles.get(marker.section_id, ""),
                line=marker.line, cue="[PARKED:] marker",
            ),
        ))
    return items


# ---------------------------------------------------------------------------
# Design-stage material
# ---------------------------------------------------------------------------

# Function words and discourse verbs. A candidate noun phrase may not contain
# any of these, which is what keeps "the thing we need to do" out of the data
# model while keeping "chain of custody" in it.
_STOPWORDS = {
    "a", "about", "above", "actually", "after", "again", "against", "all", "also", "always",
    "am", "an", "and", "any", "anything", "are", "as", "at", "back", "be", "because", "been",
    "before", "being", "below", "best", "better", "between", "both", "but", "by", "can",
    "cannot", "come", "comes", "could", "did", "do", "does", "doing", "done", "down", "each",
    "either", "else", "enough", "even", "ever", "every", "everyone", "everything", "few",
    "first", "for", "from", "further", "get", "gets", "getting", "give", "given", "go", "goes",
    "going", "gone", "good", "got", "had", "has", "have", "having", "he", "her", "here", "hers",
    "him", "his", "how", "however", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
    "keep", "kind", "know", "last", "least", "less", "let", "like", "little", "long", "look",
    "looking", "made", "make", "makes", "making", "many", "may", "maybe", "me", "mean", "means",
    "might", "mine", "more", "most", "much", "must", "my", "need", "needed", "needs", "never",
    "new", "next", "no", "nobody", "none", "nor", "not", "nothing", "now", "of", "off", "often",
    "on", "once", "one", "only", "or", "other", "others", "ought", "our", "ours", "out", "over",
    "own", "part", "particularly", "per", "perhaps", "probably", "put", "quite", "rather",
    "really", "right", "run", "running", "runs", "said", "same", "say", "saying", "says", "see",
    "seen", "several", "shall", "she", "should", "since", "so", "some", "someone", "something",
    "sometimes", "sort", "still", "such", "sure", "take", "taken", "takes", "than", "that",
    "the", "their", "theirs", "them", "themselves", "then", "there", "these", "they", "thing",
    "things", "think", "this", "those", "though", "thought", "three", "through", "to", "today",
    "together", "too", "two", "under", "until", "up", "us", "use", "used", "using", "very",
    "want", "wanted", "wants", "was", "way", "ways", "we", "well", "went", "were", "what",
    "when", "where", "whether", "which", "while", "who", "whole", "whom", "whose", "why",
    "will", "with", "within", "without", "would", "yes", "yet", "you", "your", "yours",
    # spoken numbers, which are frequent and never a business object
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
    "hundred", "thousand", "million", "billion", "half", "quarter", "double", "twice",
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth",
    "tenth", "cent", "percent",
}

_WORD = re.compile(r"[a-z][a-z'-]*")

# Word shapes that are never a business object however often they are said.
_NOT_AN_OBJECT = re.compile(r"'|^\d|ly$|^(?:isn|aren|wasn|weren|hasn|haven|didn|doesn|don|won|wouldn|couldn|shouldn)$")
_TITLE_WORD = re.compile(r"\b[A-Z][a-z]+\b")


def _singular(word: str) -> str:
    """Naive singularisation — enough to merge 'samples' with 'sample'."""
    lowered = word.lower()
    if lowered.endswith("ies") and len(lowered) > 4:
        return lowered[:-3] + "y"
    if lowered.endswith(("ss", "us", "is", "s's")):
        return lowered
    if lowered.endswith("ses") and len(lowered) > 4:
        return lowered[:-2]
    if lowered.endswith("s") and len(lowered) > 3:
        return lowered[:-1]
    return lowered


def extract_candidate_objects(
    utterances: list[Utterance],
    section_titles: dict[str, str],
    rules: CueRules,
) -> list[CandidateObject]:
    """Noun phrases the client keeps saying — candidate tables, with counts.

    Frequency is the whole argument: this asserts nothing about the data model,
    it reports that a term was used N times and shows the first time it was
    said. Curating that into tables is the consultant's job.
    """
    counts: dict[str, int] = {}
    surfaces: dict[str, dict[str, int]] = {}
    speakers: dict[str, list[str]] = {}
    attributes: dict[str, list[str]] = {}
    # Per section: how often the term is used there, and the first time it is.
    # The quote is taken from the section where the term is *most* used — its
    # first mention is usually incidental ("my job today is to..."), whereas its
    # home section is where the business actually talks about the thing.
    per_section: dict[str, dict[str, int]] = {}
    first_in_section: dict[tuple[str, str], tuple[Utterance, str, str]] = {}

    for utterance in utterances:
        for sentence in split_sentences(utterance.text):
            tokens = _WORD.findall(sentence.lower())
            for size in range(1, max(1, rules.object_max_words) + 1):
                for start in range(len(tokens) - size + 1):
                    words = tokens[start:start + size]
                    if any(word in _STOPWORDS or len(word) < 3 or _NOT_AN_OBJECT.search(word)
                           for word in words):
                        continue
                    surface = " ".join(words)
                    key = " ".join(_singular(word) for word in words)
                    if any(pattern.search(key) or pattern.search(surface)
                           for pattern in rules.object_exclusions):
                        continue
                    counts[key] = counts.get(key, 0) + 1
                    surfaces.setdefault(key, {})
                    surfaces[key][surface] = surfaces[key].get(surface, 0) + 1
                    who = utterance.speaker_name or utterance.speaker_key
                    if who and who not in speakers.setdefault(key, []):
                        speakers[key].append(who)
                    section_id = utterance.section_id
                    section_title = section_titles.get(section_id, "")
                    per_section.setdefault(key, {})
                    per_section[key][section_id] = per_section[key].get(section_id, 0) + 1
                    first_in_section.setdefault((key, section_id), (utterance, sentence, section_title))
                    # an attribute-ish word adjacent to the phrase
                    neighbour = tokens[start + size] if start + size < len(tokens) else None
                    if neighbour and neighbour in rules.attribute_hints:
                        if neighbour not in attributes.setdefault(key, []):
                            attributes[key].append(neighbour)

    objects: list[CandidateObject] = []
    for key, count in counts.items():
        if count < rules.object_min_mentions:
            continue
        home_section = max(per_section[key].items(), key=lambda item: item[1])[0]
        utterance, sentence, section_title = first_in_section[(key, home_section)]
        surface = max(surfaces[key].items(), key=lambda item: item[1])[0]
        objects.append(CandidateObject(
            name=key,
            surface_form=surface,
            mentions=count,
            speakers=speakers.get(key, []),
            attribute_terms=attributes.get(key, []),
            evidence=_evidence(utterance, section_title, sentence, f"{count} mentions"),
        ))
    objects.sort(key=lambda o: (-o.mentions, o.name))
    return objects


def extract_external_systems(
    utterances: list[Utterance],
    section_titles: dict[str, str],
    rules: CueRules,
) -> list[ExternalSystem]:
    counts: dict[str, int] = {}
    first: dict[str, tuple[Utterance, str, str]] = {}

    for utterance in utterances:
        for sentence in split_sentences(utterance.text):
            for pattern in rules.system_cues:
                for match in pattern.finditer(sentence):
                    try:
                        raw = match.group("system")
                    except IndexError:
                        continue
                    if not raw:
                        continue
                    name = re.sub(r"\s+", " ", raw.strip().strip(".,;:")).lower()
                    parts = name.split()
                    if parts:  # "lab systems" and "lab system" are one interface
                        parts[-1] = _singular(parts[-1])
                        name = " ".join(parts)
                    # a greedy pattern can swallow filler ("been through two system") —
                    # a real system name carries no function words
                    if len(name) < 3 or any(part in _STOPWORDS for part in parts):
                        continue
                    counts[name] = counts.get(name, 0) + 1
                    first.setdefault(name, (utterance, sentence, section_titles.get(utterance.section_id, "")))

    systems: list[ExternalSystem] = []
    for name, count in counts.items():
        utterance, sentence, section_title = first[name]
        systems.append(ExternalSystem(
            name=name,
            mentions=count,
            evidence=_evidence(utterance, section_title, sentence, "system reference"),
        ))
    systems.sort(key=lambda s: (-s.mentions, s.name))
    return systems


def extract_statements(
    utterances: list[Utterance],
    section_titles: dict[str, str],
    rules: CueRules,
) -> list[LabelledStatement]:
    """Verbatim statements routed to a design document by category."""
    statements: list[LabelledStatement] = []
    seen: set[tuple[str, str]] = set()
    counters: dict[str, int] = {}

    for utterance in utterances:
        for sentence in split_sentences(utterance.text):
            if not _usable(sentence):
                continue
            key = _normalise(sentence)
            for category, label, patterns in rules.statement_groups:
                cue = _first_match(patterns, sentence)
                if not cue or (category, key) in seen:
                    continue
                seen.add((category, key))
                counters[category] = counters.get(category, 0) + 1
                # Readable in a Ref column — the internal slug never reaches a reader.
                statements.append(LabelledStatement(
                    id=f"{category.upper().replace('_', '-')}-{counters[category]:03d}",
                    category=category,
                    label=label,
                    statement=sentence,
                    evidence=_evidence(utterance, section_titles.get(utterance.section_id, ""), sentence, cue),
                ))
    return statements


def build_marker_decisions(
    markers: list[RawMarker],
    section_titles: dict[str, str],
    start_index: int,
) -> list[DecisionItem]:
    decisions: list[DecisionItem] = []
    for marker in markers:
        if marker.kind != "decision":
            continue
        decisions.append(DecisionItem(
            id=f"DEC-{start_index + len(decisions) + 1:03d}",
            statement=marker.text,
            evidence=Evidence(
                quote=marker.text, section_id=marker.section_id,
                section_title=section_titles.get(marker.section_id, ""),
                line=marker.line, cue="[DECISION:] marker",
            ),
        ))
    return decisions
