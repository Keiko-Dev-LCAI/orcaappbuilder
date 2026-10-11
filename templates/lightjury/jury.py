"""LightJury — the jury engine (six domains, RAG-grounded).

A real panel of FIVE independent AI jurors. Each juror is a distinct on-chain
AIVM worker (we dedupe by worker address and redraw duplicates), given the same
case packet, deliberating on its own, returning a vote + reasoning. We then
aggregate into a majority verdict with the dissent noted.

Honesty is the whole product here:
  * Five GENUINELY independent jurors — never one model wearing five hats.
  * The deliberation takes real minutes (AIVM calls are serialized on-chain);
    the UI says so plainly rather than hiding it.
  * A free safety screen runs BEFORE any charge, so nobody in a crisis is
    billed for a verdict that should never be rendered.

Grounding is domain-specific (see rulepacks.py): each dispute type carries its
own curated rule-pack of general principles. For community/DAO disputes the
panel ALSO grounds on the rules the user pastes in, and for any case the panel
reads the text of uploaded documents. Relevant rules + evidence are retrieved
(retrieve.py) and injected, and each juror must CITE the tags it relied on. The
panel reasons from general principles — never binding law — and says "this is a
judgment call" when it is.
"""

import json
import re

import aivm_client
import rulepacks
import retrieve

PANEL_SIZE = 5
# How many extra draws we'll spend trying to replace a duplicate worker before
# accepting a smaller-but-still-honest distinct panel. Keeps gas bounded if the
# gateway keeps handing back the same worker.
MAX_REDRAWS = 6
JUROR_TIMEOUT = 360

# Each seat on the panel brings a distinct deliberative lens, so the five
# genuinely-independent jurors reason from different angles instead of returning
# near-identical text. The lens shapes HOW a juror weighs the case; every juror
# still renders a fair OVERALL verdict (it does not judge on its angle alone).
JUROR_LENSES = [
    "Fairness & reciprocity — weigh most heavily whether each person held up "
    "their side and whether the outcome is even-handed.",
    "Intent & good faith — weigh most heavily each person's honesty and "
    "intentions: bad faith, carelessness, or an honest mistake?",
    "Agreements & expectations — weigh most heavily any explicit or implied "
    "agreements and the ordinary expectations reasonable people in this "
    "relationship would hold.",
    "The absent party — weigh most heavily the perspective of the person who "
    "isn't here to speak; steelman them hard before you decide.",
    "Practical resolution — weigh most heavily what a workable, proportionate "
    "way forward looks like, not only who is strictly 'right.'",
]

ADVISORY_PREFIX = (
    "This is the reasoned opinion of a five-member panel of independent AIs. "
    "It is advisory only — not a binding ruling and not a substitute for a "
    "licensed professional."
)

# How many retrieved chunks of pasted rules / uploaded documents to inject.
MAX_USER_RULE_CHUNKS = 5
MAX_DOC_CHUNKS = 5


# ── Safety screen (free, runs before payment) ─────────────────────────────────
# Crude but honest v1 keyword/pattern screen. If anything here trips, we break
# out of the verdict flow and surface real help instead of charging for a
# verdict. Erring toward surfacing help is the right failure mode.
_SAFETY_PATTERNS = [
    r"\bkill (myself|yourself|him|her|them)\b",
    r"\b(suicid|kill myself|end my life|want to die|don'?t want to live)\b",
    r"\b(self.?harm|cut myself|hurt myself)\b",
    r"\b(he|she|they|my (partner|boyfriend|girlfriend|husband|wife|ex)) (hits?|hit|beats?|beat|chok|strangl|punch|slap|kick|threaten|threatened|rapes?|raped|assault)",
    r"\b(hits? me|beats? me|chok|strangl|punched me|slapped me|kicked me|threw|threatened to (kill|hurt|hit))\b",
    r"\b(rape|raped|sexual assault|molest|forced me)\b",
    r"\b(abus(e|ed|ive)|domestic violence|restraining order|afraid for my (life|safety)|scared he('?ll| will) hurt)\b",
    r"\b(stalk|stalking|won'?t leave me alone|following me|tracking my)\b",
    r"\bchild (abuse|neglect)|\bhurt(ing)? (the|our|my) (kid|child|baby)\b",
]
_SAFETY_RX = [re.compile(p, re.IGNORECASE) for p in _SAFETY_PATTERNS]

SAFETY_MESSAGE = (
    "It sounds like there may be something serious going on here — more serious "
    "than a verdict should weigh in on. You deserve real support, not an AI "
    "ruling. Please reach out to someone who can actually help."
)

SAFETY_RESOURCES = [
    {"name": "Call or text 988 (US) — Suicide & Crisis Lifeline", "detail": "24/7, free, confidential"},
    {"name": "Call 911 (US) or your local emergency number", "detail": "if you are in immediate danger"},
    {"name": "National Domestic Violence Hotline (US)", "detail": "1-800-799-7233, or text START to 88788"},
    {"name": "Outside the US", "detail": "contact your local emergency services or a trusted person near you"},
]


def screen_for_safety(text):
    """Return (flagged: bool, info: dict|None). info carries the help message."""
    blob = text or ""
    for rx in _SAFETY_RX:
        if rx.search(blob):
            return True, {
                "flagged": True,
                "message": SAFETY_MESSAGE,
                "resources": SAFETY_RESOURCES,
            }
    return False, None


# ── Grounding: collect the citable rules + evidence for a case ────────────────
def _case_query(case):
    return " ".join([
        case.get("relationship", ""), case.get("situation", ""),
        case.get("other_side", ""), case.get("outcome", ""),
    ]).strip()


def collect_grounding(case):
    """Return (pack, citables) for this case.

    citables is an ordered list of dicts {id,title,text,source,kind}: the domain
    rule-pack (always), plus the most relevant chunks of any pasted community/DAO
    rules and of any uploaded documents, retrieved against the case text. Each
    item carries a short [TAG] a juror can cite.
    """
    pack = rulepacks.get_pack(case.get("category"))
    citables = []
    for r in pack["rules"]:
        citables.append({
            "id": r["id"], "title": r["title"], "text": r["text"],
            "source": r["source"], "kind": "rule",
        })

    query = _case_query(case)

    if pack.get("user_rules"):
        pasted = (case.get("user_rules") or "").strip()
        if pasted:
            domain = rulepacks.resolve_domain(case.get("category"))
            src = ("the community's own posted rules" if domain == "mod"
                   else "the DAO's own governing documents")
            passages = [{"text": c} for c in retrieve.chunk_text(pasted)]
            top = retrieve.retrieve(query, passages, k=MAX_USER_RULE_CHUNKS)
            for n, p in enumerate(top, 1):
                citables.append({
                    "id": f"RULE-{n}", "title": f"Submitted rule excerpt {n}",
                    "text": p["text"], "source": src, "kind": "user_rule",
                })

    doc_passages = []
    for d in (case.get("documents") or []):
        name = (d.get("name") or "document").strip() or "document"
        for c in retrieve.chunk_text(d.get("text", "")):
            doc_passages.append({"text": c, "name": name})
    if doc_passages:
        top = retrieve.retrieve(query, doc_passages, k=MAX_DOC_CHUNKS)
        for n, p in enumerate(top, 1):
            nm = p.get("name", "document")
            citables.append({
                "id": f"DOC-{n}", "title": f"Evidence excerpt {n} — {nm}",
                "text": p["text"], "source": f"submitted document: {nm}",
                "kind": "doc",
            })

    return pack, citables


def _format_grounding(pack, citables):
    lines = [
        f"GROUNDING for this {pack['label'].lower()}. Apply these and CITE the "
        "ones you actually rely on by their [TAG]. Never cite a tag you did not "
        "use, and never invent a tag.",
        "",
    ]
    for c in citables:
        lines.append(f"[{c['id']}] {c['title']} — {c['text']} "
                     f"(source: {c['source']})")
    return "\n".join(lines)


# ── Juror prompt ──────────────────────────────────────────────────────────────
def build_juror_prompt(case, juror_index, pack, citables):
    situation = case.get("situation", "").strip()
    relationship = case.get("relationship", "").strip()
    outcome = case.get("outcome", "").strip()
    other_side = case.get("other_side", "").strip()

    lens = JUROR_LENSES[(juror_index - 1) % len(JUROR_LENSES)]
    valid_tags = ", ".join(c["id"] for c in citables)

    parts = [
        f"You are Juror #{juror_index} of five INDEPENDENT jurors on LightJury. "
        "You are deliberating alone. Do not assume what the other jurors think.",
        "",
        _format_grounding(pack, citables),
        "",
        f"Your lens as Juror #{juror_index} — {lens} Apply this lens, but still "
        "weigh the other dimensions and reach a fair overall verdict.",
        "",
        "THE DISPUTE (submitted by one party):",
    ]
    if "relationship" in pack["fields"]:
        parts.append(f"- Relationship: {relationship or 'not stated'}")
    parts.append(f"- What happened, in their words: {situation or 'not stated'}")
    if other_side:
        parts.append(f"- What they say the other side would say: {other_side}")
    if outcome:
        parts.append(f"- What the submitter is hoping for: {outcome}")
    parts += [
        "",
        "Deliberate fairly. Steelman the absent party first. Ground your reasoning "
        "in the tags above and cite the ones you used. Then decide.",
        "",
        "Respond with ONLY a JSON object, nothing before or after it, in exactly "
        "this shape:",
        '{',
        '  "favored": one of "submitter" | "other_party" | "shared" | "no_fault",',
        '  "headline": "one plain sentence: who is more in the right and why",',
        '  "reasoning": "2-4 sentences of impartial reasoning",',
        f'  "citations": a JSON array of tags you relied on (choose from: {valid_tags}),',
        '  "confidence": an integer 0-100 for how sure you are',
        '}',
    ]
    return "\n".join(parts)


# ── Robust parsing of a juror's reply ─────────────────────────────────────────
# AIVM long replies can arrive with a telemetry frame and/or the answer doubled
# (a known worker double-send on long outputs). Keep juror replies short and
# extract the first well-formed JSON object defensively.
_VALID_FAVORED = {"submitter", "other_party", "shared", "no_fault"}


def _clean_citations(raw):
    """Normalize a juror's citations into a list of bare tag strings."""
    out = []
    items = []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        items = re.split(r"[,\s]+", raw)
    for x in items:
        s = str(x).strip().strip("[]() ").upper()
        if s and s not in out:
            out.append(s[:16])
    return out[:12]


def _extract_json_objects(text):
    """Yield candidate JSON object substrings by brace matching."""
    objs = []
    depth = 0
    start = None
    for i, ch in enumerate(text or ""):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    objs.append(text[start:i + 1])
                    start = None
    return objs


def parse_juror_reply(text):
    """Return a normalized vote dict, or a low-confidence abstain if unparseable."""
    for candidate in _extract_json_objects(text or ""):
        try:
            obj = json.loads(candidate)
        except Exception:
            continue
        if not isinstance(obj, dict) or "favored" not in obj:
            continue
        favored = str(obj.get("favored", "")).strip().lower().replace(" ", "_")
        if favored not in _VALID_FAVORED:
            favored = "no_fault"
        try:
            conf = int(round(float(obj.get("confidence", 50))))
        except Exception:
            conf = 50
        conf = max(0, min(100, conf))
        return {
            "favored": favored,
            "headline": str(obj.get("headline", "")).strip()[:400] or "(no headline)",
            "reasoning": str(obj.get("reasoning", "")).strip()[:1200] or "(no reasoning given)",
            "citations": _clean_citations(obj.get("citations")),
            "confidence": conf,
            "parsed": True,
        }
    # Unparseable — abstain honestly rather than invent a vote.
    return {
        "favored": "no_fault",
        "headline": "This juror could not reach a clear decision.",
        "reasoning": (text or "").strip()[:400] or "(no reply)",
        "citations": [],
        "confidence": 0,
        "parsed": False,
    }


# ── Draw 5 distinct jurors and deliberate ─────────────────────────────────────
def deliberate(case, progress_cb=None):
    """Run the full panel. Returns a panel-result dict.

    progress_cb(done, total, note) is called as each juror finishes so the UI
    can show honest progress during the multi-minute wait.
    """
    votes = []
    seen_workers = set()
    redraws_left = MAX_REDRAWS
    index = 0

    # Grounding depends only on the case, so build it once and reuse per juror.
    pack, citables = collect_grounding(case)
    valid_ids = {c["id"] for c in citables}

    while len(votes) < PANEL_SIZE:
        index += 1
        prompt = build_juror_prompt(case, len(votes) + 1, pack, citables)
        try:
            text, worker = aivm_client.infer_juror(prompt, timeout=JUROR_TIMEOUT)
        except Exception as e:
            # One juror failing shouldn't sink the panel; record and continue,
            # but don't loop forever.
            if redraws_left <= 0:
                raise RuntimeError(f"Jury engine error: {str(e)[:200]}")
            redraws_left -= 1
            if progress_cb:
                progress_cb(len(votes), PANEL_SIZE, "a juror dropped — redrawing")
            continue

        # Enforce distinct jurors: if this worker already served, redraw (within
        # the gas budget) so the panel is genuinely five different AIs.
        if worker and worker in seen_workers and redraws_left > 0:
            redraws_left -= 1
            if progress_cb:
                progress_cb(len(votes), PANEL_SIZE, "drew a repeat juror — redrawing")
            continue

        if worker:
            seen_workers.add(worker)
        vote = parse_juror_reply(text)
        # Keep only citations that match a real grounding tag.
        vote["citations"] = [c for c in vote.get("citations", []) if c in valid_ids]
        vote["worker"] = worker
        votes.append(vote)
        if progress_cb:
            progress_cb(len(votes), PANEL_SIZE, "a juror returned a verdict")

    panel = aggregate(votes)
    panel["distinct_workers"] = len(seen_workers)
    panel["pack"] = pack
    panel["citables"] = citables
    panel["opinion"] = compose_opinion(case, panel)
    return panel


# ── Aggregate five votes into one verdict ─────────────────────────────────────
_FAVORED_LABEL = {
    "submitter": "in favor of the person who brought the dispute",
    "other_party": "in favor of the other person",
    "shared": "shared responsibility on both sides",
    "no_fault": "no clear fault — an honest misunderstanding",
}


def aggregate(votes):
    counted = [v for v in votes if v.get("parsed")]
    tally = {}
    for v in counted:
        tally[v["favored"]] = tally.get(v["favored"], 0) + 1

    if tally:
        winner = max(tally, key=lambda k: tally[k])
        agree_count = tally[winner]
    else:
        winner = "no_fault"
        agree_count = 0

    majority = [v for v in votes if v.get("favored") == winner and v.get("parsed")]
    dissent = [v for v in votes if v.get("favored") != winner and v.get("parsed")]
    avg_conf = int(round(sum(v["confidence"] for v in majority) / len(majority))) if majority else 0

    return {
        "verdict": winner,
        "verdict_label": _FAVORED_LABEL.get(winner, winner),
        "agree_count": agree_count,
        "panel_size": len(votes),
        "tally": tally,
        "confidence": avg_conf,
        "votes": votes,
        "majority": majority,
        "dissent": dissent,
    }


# ── Compose the written opinion (plain + legalese) ────────────────────────────
def compose_opinion(case, panel):
    agree = panel["agree_count"]
    size = panel["panel_size"]
    label = panel["verdict_label"]
    conf = panel["confidence"]

    pack = panel.get("pack") or rulepacks.get_pack(case.get("category"))

    majority_points = [v["reasoning"] for v in panel["majority"] if v.get("reasoning")]
    dissent_points = [v["reasoning"] for v in panel["dissent"] if v.get("reasoning")]
    lead_headline = panel["majority"][0]["headline"] if panel["majority"] else (
        panel["votes"][0]["headline"] if panel["votes"] else "")

    # Sources the panel actually cited (deduped, in first-cited order).
    by_id = {c["id"]: c for c in panel.get("citables", [])}
    cited_ids = []
    for v in panel["votes"]:
        if not v.get("parsed"):
            continue
        for cid in v.get("citations", []):
            if cid in by_id and cid not in cited_ids:
                cited_ids.append(cid)
    cited = [by_id[c] for c in cited_ids]

    # Plain English
    plain = [
        f"The verdict: {label}.",
        f"{agree} of {size} jurors agreed. Panel confidence: {conf}%.",
        "",
        lead_headline,
    ]
    if majority_points:
        plain.append("")
        plain.append("Why the panel ruled this way:")
        for p in majority_points:
            plain.append(f"• {p}")
    if dissent_points:
        plain.append("")
        plain.append(f"The {len(dissent_points)} dissenting juror(s) saw it differently:")
        for p in dissent_points:
            plain.append(f"• {p}")
    if cited:
        plain.append("")
        plain.append("What the panel grounded its decision on:")
        for c in cited:
            plain.append(f"• [{c['id']}] {c['title']} — {c['source']}")
    plain.append("")
    plain.append(ADVISORY_PREFIX + " " + pack["disclaimer"])
    plain_text = "\n".join(plain)

    # Legalese
    rel = (case.get("relationship") or "").strip()
    intro = (
        f"{pack['intro']} The panel comprised five independent "
        "artificial-intelligence jurors convened by LightJury, each considering "
        "the matter independently upon the same record."
    )
    if rel and "relationship" in pack["fields"]:
        intro += f" The relationship between the parties, as stated: {rel}."
    legal = [
        "OPINION OF THE PANEL",
        "",
        intro,
        "",
        f"FINDING. Upon deliberation, the panel finds, by a vote of {agree} to "
        f"{size - agree}, {label}. The panel's aggregate confidence in this finding "
        f"is {conf} percent.",
        "",
        "REASONING. The majority reasons as follows:",
    ]
    for i, p in enumerate(majority_points, 1):
        legal.append(f"  ({i}) {p}")
    if dissent_points:
        legal.append("")
        legal.append("DISSENT. The minority would hold otherwise, reasoning:")
        for i, p in enumerate(dissent_points, 1):
            legal.append(f"  ({i}) {p}")
    if cited:
        legal.append("")
        legal.append("AUTHORITIES CITED. The panel grounded its reasoning in:")
        for c in cited:
            legal.append(f"  [{c['id']}] {c['title']} — {c['source']}")
    legal.append("")
    legal.append(
        "DISPOSITION. The foregoing is rendered as the reasoned, advisory opinion "
        "of the panel. It is NOT a binding ruling, carries no legal force, and does "
        f"not constitute legal advice. {pack['disclaimer']} Parties are encouraged "
        "to use it as an independent, impartial second opinion only.")
    legal_text = "\n".join(legal)

    return {"plain": plain_text, "legalese": legal_text}
