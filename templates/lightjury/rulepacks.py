"""LightJury — per-domain rule-packs (the grounding corpus for RAG).

Each of the six launch domains has a curated set of rules/principles. A rule is a
small, self-contained, SOURCE-LABELLED unit the jury can retrieve and CITE. These
are general, widely-recognised principles — NOT the statute of any one place — so
the panel reasons like a careful, impartial person who knows the common ground
rules, and says so honestly in its disclaimer.

Structure:
    RULE_PACKS[domain] = {
        "label":     short human name of the domain,
        "disclaimer": one honest sentence about what this grounding is/ isn't,
        "intro":     one sentence used to open the legalese opinion for this domain,
        "fields":    the intake fields this domain reads (for prompt wording),
        "user_rules": True if this domain ALSO grounds on rules the user pastes
                      (community server rules / DAO bylaws),
        "rules":     [ {"id","title","text","source"} , ... ],
    }

A rule's "id" is what a juror cites (e.g. "CON-3"). "source" names where the
principle comes from in plain terms, so a citation is traceable and honest.
"""

# ── Consumer ──────────────────────────────────────────────────────────────────
_CONSUMER = {
    "label": "Consumer dispute",
    "disclaimer": (
        "Grounded in general consumer-protection and sale-of-goods principles "
        "common to most jurisdictions — not the specific statute where you live."
    ),
    "intro": (
        "This matter came before the panel as a consumer dispute between a buyer "
        "and a seller or provider."
    ),
    "fields": ["situation", "other_side", "outcome"],
    "user_rules": False,
    "rules": [
        {"id": "CON-1", "title": "Goods must match their description",
         "text": "A product or service must reasonably match how it was described, "
                 "advertised, or shown at the point of sale. A material gap between "
                 "what was promised and what was delivered weighs against the seller.",
         "source": "General sale-of-goods principle (implied term of description)"},
        {"id": "CON-2", "title": "Fitness for ordinary purpose",
         "text": "Goods should work for the ordinary purpose such goods are used for, "
                 "and for any specific purpose the buyer made known and relied on the "
                 "seller to meet.",
         "source": "Implied warranty of merchantability / fitness for purpose"},
        {"id": "CON-3", "title": "Defective or not-as-described → remedy",
         "text": "If goods are faulty, not as described, or not fit for purpose, the "
                 "buyer is ordinarily owed a remedy: repair, replacement, or refund. "
                 "A reasonable, timely rejection strengthens the buyer's position.",
         "source": "General consumer remedy principle"},
        {"id": "CON-4", "title": "Misrepresentation",
         "text": "A seller who makes a false statement of fact that induces the "
                 "purchase is responsible for the gap between what was represented and "
                 "reality, whether the statement was deliberate or careless.",
         "source": "Misrepresentation principle"},
        {"id": "CON-5", "title": "Reasonable notice and opportunity to cure",
         "text": "The buyer should usually give the seller fair notice of the problem "
                 "and a reasonable chance to fix it before escalating, unless doing so "
                 "would be futile or unsafe.",
         "source": "Good-faith / mitigation principle"},
        {"id": "CON-6", "title": "Clear, agreed terms govern",
         "text": "Written terms both sides actually agreed to (returns window, "
                 "warranty, 'as-is' sales) carry weight, but terms that are hidden, "
                 "one-sided, or sprung after the sale carry much less.",
         "source": "Freedom of contract, limited by unfair-terms principle"},
        {"id": "CON-7", "title": "Proof of the transaction",
         "text": "Receipts, order confirmations, messages, and photos of the item "
                 "carry real weight. The party who can show the record is in a "
                 "stronger position than the party relying on memory alone.",
         "source": "Evidence / burden principle"},
    ],
}

# ── Money / small-claims ──────────────────────────────────────────────────────
_MONEY = {
    "label": "Money dispute",
    "disclaimer": (
        "Grounded in general contract and debt principles common to small-claims "
        "matters — not the specific statute or limitation period where you live."
    ),
    "intro": (
        "This matter came before the panel as a money dispute over an alleged debt, "
        "loan, or sum owed between the parties."
    ),
    "fields": ["situation", "other_side", "outcome"],
    "user_rules": False,
    "rules": [
        {"id": "MON-1", "title": "A real agreement creates a real obligation",
         "text": "Money is owed where there was an agreement — spoken, written, or "
                 "shown by conduct — that one person would pay another. The clearer "
                 "the agreement, the stronger the claim.",
         "source": "Contract formation principle"},
        {"id": "MON-2", "title": "Loan vs. gift",
         "text": "Money handed over is a loan (repayable) only if both sides "
                 "understood it as repayable. If it was genuinely given as a gift, it "
                 "is not owed back. Look for what was said and done at the time.",
         "source": "Loan / gift distinction"},
        {"id": "MON-3", "title": "Proof of the amount and the terms",
         "text": "The person claiming the money should be able to show the amount and "
                 "the terms — transfers, messages, IOUs, witnesses. Vague or shifting "
                 "figures weaken a claim.",
         "source": "Evidence / burden principle"},
        {"id": "MON-4", "title": "Partial performance and part-payment",
         "text": "Payments already made, or value already provided, must be credited. "
                 "A dispute is about the balance genuinely outstanding, not the gross "
                 "figure.",
         "source": "Accounting / set-off principle"},
        {"id": "MON-5", "title": "Unjust enrichment",
         "text": "Even without a clear agreement, someone who received a clear benefit "
                 "at another's expense, in circumstances where keeping it for free is "
                 "unfair, may owe its reasonable value.",
         "source": "Unjust-enrichment principle"},
        {"id": "MON-6", "title": "Delay and reasonableness",
         "text": "Long, unexplained delay in asking for money, or in paying it, is "
                 "relevant to fairness. Most places also limit how old a claim can be; "
                 "the panel notes this generally without applying a specific period.",
         "source": "Laches / limitation awareness (general)"},
        {"id": "MON-7", "title": "Conditions attached to the money",
         "text": "If repayment or payment was tied to a condition ('pay me back when "
                 "you can', 'once the work is done'), whether that condition was met "
                 "matters as much as the headline promise.",
         "source": "Conditional-obligation principle"},
    ],
}

# ── Roommate / tenant ─────────────────────────────────────────────────────────
_ROOMMATE = {
    "label": "Roommate / tenant dispute",
    "disclaimer": (
        "Grounded in general tenancy and shared-living fairness principles — not the "
        "landlord-tenant statute or local ordinance where you live."
    ),
    "intro": (
        "This matter came before the panel as a dispute between people sharing a "
        "home — roommates, or a tenant and landlord."
    ),
    "fields": ["situation", "other_side", "outcome"],
    "user_rules": False,
    "rules": [
        {"id": "HOM-1", "title": "The agreement sets the baseline",
         "text": "A lease or roommate agreement — written or clearly understood — "
                 "sets who pays what, who does what, and the house rules. Its terms "
                 "are the starting point for any dispute.",
         "source": "Tenancy / housemate agreement principle"},
        {"id": "HOM-2", "title": "Shared costs split fairly",
         "text": "Rent, utilities, and shared supplies are normally split as agreed, "
                 "or else fairly by use and benefit. Someone who paid more than their "
                 "share is owed the difference; someone who used far more should bear "
                 "more.",
         "source": "Shared-expense fairness principle"},
        {"id": "HOM-3", "title": "Security deposit is held, not earned",
         "text": "A deposit is the payer's money held against genuine damage or unpaid "
                 "dues. It should be returned, minus documented, beyond-normal-wear "
                 "deductions. Keeping it without itemised reason weighs heavily "
                 "against the holder.",
         "source": "Security-deposit principle"},
        {"id": "HOM-4", "title": "Normal wear is not damage",
         "text": "Ordinary wear from everyday living is not chargeable damage. The "
                 "line is between a home that was lived in and a home that was harmed "
                 "beyond that.",
         "source": "Wear-and-tear principle"},
        {"id": "HOM-5", "title": "Quiet enjoyment and basic respect",
         "text": "Everyone sharing a home is owed reasonable quiet, privacy, and use "
                 "of common space. Persistent noise, guests, or intrusion that a "
                 "reasonable person couldn't live with weighs against the person "
                 "causing it.",
         "source": "Quiet-enjoyment principle"},
        {"id": "HOM-6", "title": "Habitability and repairs",
         "text": "A rented home should be safe and liveable; the landlord generally "
                 "handles major repairs, the occupant handles damage they caused and "
                 "day-to-day upkeep.",
         "source": "Habitability / repair-responsibility principle"},
        {"id": "HOM-7", "title": "Fair notice before leaving or changing terms",
         "text": "Moving out, ending a share, or changing the arrangement normally "
                 "calls for reasonable notice so others can adjust. Walking out "
                 "abruptly and leaving others with the bill weighs against the leaver.",
         "source": "Reasonable-notice principle"},
        {"id": "HOM-8", "title": "Proof: the record beats memory",
         "text": "Move-in photos, the written agreement, payment records, and dated "
                 "messages carry weight. The party who kept records is in a stronger "
                 "position.",
         "source": "Evidence / burden principle"},
    ],
}

# ── Relationship / personal ───────────────────────────────────────────────────
_RELATIONSHIP = {
    "label": "Relationship dispute",
    "disclaimer": (
        "Grounded in general fairness and good-faith relationship norms, not statutes "
        "— it may not match the law where you live."
    ),
    "intro": (
        "This matter came before the panel upon the submission of one party to a "
        "personal dispute."
    ),
    "fields": ["relationship", "situation", "other_side", "outcome"],
    "user_rules": False,
    "rules": [
        {"id": "REL-1", "title": "Good faith is owed both ways",
         "text": "Both people are owed honesty, good faith, and basic respect. A "
                 "breach of that — lying, manipulating, acting in bad faith — weighs "
                 "heavily against the person who did it.",
         "source": "Good-faith relationship norm"},
        {"id": "REL-2", "title": "Clear agreements beat vague expectations",
         "text": "Explicit promises, shared plans, and money or duties clearly agreed "
                 "carry more weight than unspoken expectations. Name the agreement if "
                 "there was one.",
         "source": "Agreement-vs-expectation norm"},
        {"id": "REL-3", "title": "Separate what happened from how it felt",
         "text": "Facts and feelings are both real but not the same. A fair read "
                 "distinguishes what actually occurred from each person's reaction to "
                 "it.",
         "source": "Fact / feeling distinction"},
        {"id": "REL-4", "title": "Reciprocity and pattern",
         "text": "Did each person hold up their side? Was this a one-off or a "
                 "pattern? Repeated behaviour weighs more than a single lapse.",
         "source": "Reciprocity norm"},
        {"id": "REL-5", "title": "Proportionality",
         "text": "A response should fit what triggered it. An overreaction can put "
                 "the responder partly in the wrong even if they started out wronged.",
         "source": "Proportionality norm"},
        {"id": "REL-6", "title": "Shared fault is a real answer",
         "text": "Many personal conflicts are shared fault or honest "
                 "misunderstanding. Saying so is more honest than forcing a single "
                 "winner.",
         "source": "Shared-responsibility norm"},
        {"id": "REL-7", "title": "Steelman the absent party",
         "text": "Only one side is here. Before deciding, build the strongest fair "
                 "version of the other person's account so the panel is not an echo "
                 "chamber.",
         "source": "Anti-echo-chamber norm"},
    ],
}

# ── Community / moderation ────────────────────────────────────────────────────
_MOD = {
    "label": "Community / moderation dispute",
    "disclaimer": (
        "Grounded FIRST in the community's own posted rules (which you provide), and "
        "then in general fair-process principles. It is not a platform's official "
        "appeal and binds no one."
    ),
    "intro": (
        "This matter came before the panel as a community moderation dispute, weighed "
        "against the community's own stated rules and general principles of fair "
        "enforcement."
    ),
    "fields": ["situation", "other_side", "outcome"],
    "user_rules": True,
    "rules": [
        {"id": "MOD-1", "title": "The community's own rules come first",
         "text": "A community is judged against the rules it actually posted. An "
                 "action squarely within a clear, pre-existing rule is presumptively "
                 "fair; an action with no rule behind it is presumptively not.",
         "source": "Posted-rules-govern principle"},
        {"id": "MOD-2", "title": "No retroactive or invented rules",
         "text": "People can only be held to rules that existed and were knowable "
                 "when they acted. Punishing conduct under a rule made up afterward "
                 "weighs against the moderator.",
         "source": "No-retroactivity principle"},
        {"id": "MOD-3", "title": "Consistent enforcement",
         "text": "Rules should apply evenly. Singling one person out for something "
                 "others do freely, or selective enforcement driven by a grudge, "
                 "weighs against the moderator.",
         "source": "Even-handed-enforcement principle"},
        {"id": "MOD-4", "title": "Notice and a chance to respond",
         "text": "Except for clear emergencies (spam, raids, threats), fair process "
                 "usually means some warning and a chance to explain before a serious "
                 "sanction like a permanent ban.",
         "source": "Fair-process / notice principle"},
        {"id": "MOD-5", "title": "Proportionate sanctions",
         "text": "The sanction should fit the breach. A permanent ban for a first "
                 "minor slip is disproportionate; leniency for repeated serious harm "
                 "is too little.",
         "source": "Proportionality principle"},
        {"id": "MOD-6", "title": "Moderators are not above the rules",
         "text": "Those enforcing the rules are bound by them too, including rules "
                 "against harassment and abuse of power. Conflicts of interest should "
                 "be disclosed or stepped away from.",
         "source": "No-one-above-the-rules principle"},
        {"id": "MOD-7", "title": "A route to appeal",
         "text": "Fair communities give some way to contest a decision. The absence "
                 "of any appeal, or ignoring a good-faith appeal, weighs against the "
                 "moderation.",
         "source": "Right-of-appeal principle"},
    ],
}

# ── DAO governance ────────────────────────────────────────────────────────────
_DAO = {
    "label": "DAO governance dispute",
    "disclaimer": (
        "Grounded FIRST in the DAO's own bylaws, charter, and passed proposals (which "
        "you provide), then in general DUNA / decentralized-governance principles. It "
        "is advisory and binds no one and no contract."
    ),
    "intro": (
        "This matter came before the panel as a DAO governance dispute, weighed "
        "against the DAO's own governing documents and general principles of "
        "legitimate on-chain governance."
    ),
    "fields": ["situation", "other_side", "outcome"],
    "user_rules": True,
    "rules": [
        {"id": "DAO-1", "title": "The charter and bylaws are the constitution",
         "text": "A DAO is judged against its own charter, bylaws, and the rules it "
                 "ratified. Action taken within those rules is presumptively "
                 "legitimate; action outside them is presumptively not.",
         "source": "Governing-documents-first principle"},
        {"id": "DAO-2", "title": "A valid vote controls",
         "text": "A proposal that passed under the DAO's stated rules — quorum, "
                 "threshold, voting window — carries authority and should be executed "
                 "as passed. One that missed quorum or threshold does not.",
         "source": "Valid-vote principle"},
        {"id": "DAO-3", "title": "Process was followed",
         "text": "Fair governance means the stated process was actually followed: "
                 "proper proposal, disclosure, discussion period, and voting window. "
                 "Rushing or skipping steps undermines legitimacy.",
         "source": "Due-process-of-governance principle"},
        {"id": "DAO-4", "title": "Token-weighted, but not lawless",
         "text": "Most DAOs vote by token weight, not one-member-one-vote. That is "
                 "legitimate, but a majority still cannot breach the charter, expropriate "
                 "a minority, or act in bad faith.",
         "source": "Token-weight / minority-protection principle"},
        {"id": "DAO-5", "title": "No retroactive rule changes",
         "text": "Members are bound by the rules in force when they acted. Changing "
                 "the rules after the fact to reach a desired outcome weighs against "
                 "the party that did it.",
         "source": "No-retroactivity principle"},
        {"id": "DAO-6", "title": "Conflicts of interest and self-dealing",
         "text": "Those proposing or executing should disclose conflicts and not vote "
                 "themselves funds or power through hidden self-dealing. Undisclosed "
                 "self-interest weighs heavily against a decision.",
         "source": "Conflict-of-interest principle"},
        {"id": "DAO-7", "title": "Execution must match what passed",
         "text": "What is implemented on-chain should match what the proposal actually "
                 "said. A gap between the approved text and what was executed is itself "
                 "a governance breach.",
         "source": "Faithful-execution principle"},
        {"id": "DAO-8", "title": "DUNA / legal-wrapper duties",
         "text": "Where the DAO is a DUNA or similar legal entity, it also owes the "
                 "basic duties of that wrapper — honest recordkeeping, member rights, "
                 "and acting within its stated purpose.",
         "source": "DUNA legal-wrapper principle"},
    ],
}

RULE_PACKS = {
    "consumer": _CONSUMER,
    "money": _MONEY,
    "roommate": _ROOMMATE,
    "relationship": _RELATIONSHIP,
    "mod": _MOD,
    "dao": _DAO,
}

# Domains the frontend may send that map onto a pack above.
ALIASES = {
    "tenant": "roommate",
    "landlord": "roommate",
    "small_claims": "money",
    "smallclaims": "money",
    "debt": "money",
    "loan": "money",
    "community": "mod",
    "moderation": "mod",
    "governance": "dao",
    "personal": "relationship",
}

DEFAULT_DOMAIN = "relationship"


def resolve_domain(category):
    """Map a raw category string to a known rule-pack key."""
    key = (category or "").strip().lower()
    if key in RULE_PACKS:
        return key
    if key in ALIASES:
        return ALIASES[key]
    return DEFAULT_DOMAIN


def get_pack(category):
    """Return the rule-pack dict for a category (falls back to the default)."""
    return RULE_PACKS[resolve_domain(category)]


def all_domains():
    return list(RULE_PACKS.keys())
