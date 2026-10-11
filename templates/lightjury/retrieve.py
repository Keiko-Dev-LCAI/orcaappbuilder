"""LightJury — tiny pure-Python retrieval (the R in RAG).

No external service, no embeddings model, no network — just BM25 keyword ranking
over short passages. That keeps a dispute's evidence private (nothing leaves the
server) and fast. Used to pull the most relevant chunks of a user's pasted
community/DAO rules and of any uploaded documents into each juror's prompt, so a
juror can CITE what it actually relied on.

Embeddings are an obvious later upgrade; this is the honest v1 that ships today.
"""

import math
import re

_WORD = re.compile(r"[a-z0-9]+")

# Small, generic stop-word list — enough to stop common words from dominating the
# ranking without needing a dependency.
_STOP = set((
    "the a an and or of to in on for with at by from as is are was were be been "
    "being this that these those it its i you he she they we me my your his her "
    "their our them us do does did have has had will would can could should may "
    "might must not no so if then than but about into out up down over under "
    "again further once here there all any both each few more most other some "
    "such only own same too very just also now"
).split())


def tokenize(text):
    return [t for t in _WORD.findall((text or "").lower())
            if t not in _STOP and len(t) > 1]


def chunk_text(text, max_words=110, min_words=12):
    """Split free text into coherent passages of roughly max_words.

    Splits on blank lines and sentence/line boundaries first, then greedily packs
    pieces up to the word budget. Tiny trailing fragments are merged back.
    """
    text = (text or "").strip()
    if not text:
        return []
    # Primary split: blank lines and single newlines, then sentence enders.
    raw = re.split(r"\n\s*\n|\r\n|\n", text)
    pieces = []
    for block in raw:
        block = block.strip()
        if not block:
            continue
        # Further split long blocks on sentence boundaries.
        sentences = re.split(r"(?<=[.!?])\s+", block)
        pieces.extend(s.strip() for s in sentences if s.strip())

    chunks = []
    cur = []
    cur_n = 0
    for p in pieces:
        n = len(p.split())
        if cur_n + n > max_words and cur:
            chunks.append(" ".join(cur))
            cur, cur_n = [], 0
        cur.append(p)
        cur_n += n
    if cur:
        chunks.append(" ".join(cur))

    # Merge any too-small trailing chunk into the previous one.
    merged = []
    for c in chunks:
        if merged and len(c.split()) < min_words:
            merged[-1] = merged[-1] + " " + c
        else:
            merged.append(c)
    return merged


class _BM25:
    def __init__(self, docs_tokens, k1=1.5, b=0.75):
        self.docs = docs_tokens
        self.N = len(docs_tokens)
        self.k1 = k1
        self.b = b
        self.doc_len = [len(d) for d in docs_tokens]
        self.avgdl = (sum(self.doc_len) / self.N) if self.N else 0.0
        # document frequency
        self.df = {}
        for d in docs_tokens:
            for t in set(d):
                self.df[t] = self.df.get(t, 0) + 1
        # term frequency per doc
        self.tf = []
        for d in docs_tokens:
            counts = {}
            for t in d:
                counts[t] = counts.get(t, 0) + 1
            self.tf.append(counts)

    def _idf(self, term):
        n = self.df.get(term, 0)
        # BM25 idf with +1 smoothing to stay non-negative.
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def score(self, query_tokens, i):
        if not self.avgdl:
            return 0.0
        score = 0.0
        tf = self.tf[i]
        dl = self.doc_len[i]
        for t in query_tokens:
            if t not in tf:
                continue
            idf = self._idf(t)
            freq = tf[t]
            denom = freq + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            score += idf * (freq * (self.k1 + 1)) / denom
        return score


def retrieve(query, passages, k=5):
    """Return the top-k passages most relevant to query.

    passages: list of dicts, each with at least a "text" field (extra fields like
              "id"/"source" are passed through untouched).
    Returns the same dicts, ranked, best first, each with an added "_score".
    If nothing scores above zero, returns the first k passages unranked so the
    jury always has *something* grounded rather than nothing.
    """
    passages = [p for p in (passages or []) if (p.get("text") or "").strip()]
    if not passages:
        return []
    q = tokenize(query)
    if not q:
        return passages[:k]
    docs_tokens = [tokenize(p["text"]) for p in passages]
    bm = _BM25(docs_tokens)
    scored = []
    for i, p in enumerate(passages):
        s = bm.score(q, i)
        scored.append((s, i, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    if scored and scored[0][0] <= 0:
        return passages[:k]
    out = []
    for s, i, p in scored[:k]:
        item = dict(p)
        item["_score"] = round(s, 3)
        out.append(item)
    return out
