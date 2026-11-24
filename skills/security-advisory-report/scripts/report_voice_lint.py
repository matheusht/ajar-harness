#!/usr/bin/env python3
"""Deterministic anti-slop, jargon-leak, LLM-tell, and proportionality linter (v2).

CLI usage:
    python3 report_voice_lint.py <file_or_dir> \
        [--tier S|M|C|low|dry|audit] \
        [--channel ghsa|mailing-list|h1|immunefi|customer] \
        [--json] [--strict]

Schema: ajar-report-voice-lint/2 (stdlib-only Python 3).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import statistics
import sys
from dataclasses import asdict, dataclass, field
from typing import Any

TIER_BUDGETS: dict[str, dict[str, Any]] = {
    "LOW": {
        "min_words": 50,
        "max_words": 180,
        "hard_min_words": 35,
        "hard_max_words": 220,
        "max_sections": 4,
        "max_h4_plus": 0,
        "max_tables": 0,
        "requires_repro": False,
    },
    "DRY": {
        "min_words": 80,
        "max_words": 380,
        "hard_min_words": 50,
        "hard_max_words": 500,
        "max_sections": 6,
        "max_h4_plus": 2,
        "max_tables": 1,
        "requires_repro": False,
    },
    "S": {
        "min_words": 90,
        "max_words": 350,
        "hard_min_words": 60,
        "hard_max_words": 420,
        "max_sections": 6,
        "max_h4_plus": 0,
        "max_tables": 1,
        "requires_repro": True,
    },
    "M": {
        "min_words": 180,
        "max_words": 650,
        "hard_min_words": 120,
        "hard_max_words": 780,
        "max_sections": 6,
        "max_h4_plus": 2,
        "max_tables": 1,
        "requires_repro": True,
    },
    "C": {
        "min_words": 350,
        "max_words": 1000,
        "hard_min_words": 240,
        "hard_max_words": 1200,
        "max_sections": 7,
        "max_h4_plus": 4,
        "max_tables": 1,
        "requires_repro": True,
    },
    "AUDIT": {
        "min_words": None,
        "max_words": None,
        "hard_min_words": None,
        "hard_max_words": None,
        "max_sections": None,
        "max_h4_plus": None,
        "max_tables": None,
        "requires_repro": False,
    },
}

FILLER_HEADING_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:introduction|background|conclusion|concluding\s+remarks|final\s+thoughts|"
    r"key\s+takeaways|why\s+this\s+matters|security\s+implications|threat\s+landscape|recommendations\s+and\s+best\s+practices|"
    r"realistic\s+exploitation\s+scenarios|potential\s+impact|frequently\s+asked\s+questions|faq)\b",
    re.IGNORECASE,
)

# Unambiguous IDs/commands scanned even inside inline backticks.
RAW_INLINE_HARNESS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "internal claim/finding ID (clm-*/fnd-*/cor-*/pvf-*/chn-*)",
        re.compile(r"\b(?:clm|fnd|cor|pvf|chn|ano|surf|prim|cjw|door)-(?:[0-9a-f]{6,}|\*)\b", re.IGNORECASE),
    ),
    (
        "internal draft GHSA slug (ghsa-1/ghsa-3a)",
        re.compile(r"\b(?!ghsa-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}\b)ghsa-\d+[a-z]?\b", re.IGNORECASE),
    ),
    (
        "internal ajar CLI / skill / enum token",
        re.compile(
            r"\b(?:ajar-[a-z0-9_-]+|ajar\s+(?:init|quote|map|task|claim|patch|chain|gate|finish|report|door|steer|"
            r"precedent|repro|context|status|phase|finding|primitive|anomaly|coverage|binding|threat-model|ref|export-graph)\b|"
            r"found_autonomously_by_ajar|found_with_ajar|validated_by_ajar|"
            r"verified_local|survived_falsify|needs_instrumentation|"
            r"peer_symmetry|native_ffi|outside_in|inside_out|skill_mode|zero_skill|"
            r"maintainer_patched|uncapped_research|cogs_cap|"
            r"research_independence_pass|product_operability_pass|"
            r"falsifier_worker_id|proposer_worker_id)\b|@[a-z0-9.-]*\.invalid\b",
            re.IGNORECASE,
        ),
    ),
]

# Prose-level harness / scanner patterns scanned AFTER stripping inline backticks.
PROSE_HARNESS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("multi-arm jargon (e.g. 4-arm/6-arm/8-arm/9-arm)", re.compile(r"\b[2-9]-arm(?:s)?\b", re.IGNORECASE)),
    (
        "verification arm label (Arm 1..9 / arm1_*)",
        re.compile(r"\b(?:arm\s+[1-9][ab]?|arms\s+[1-9]\s*(?:&|and|/|[–-])\s*[1-9]|arm[1-9]_[a-z0-9_]+)\b", re.IGNORECASE),
    ),
    ("micropatch jargon", re.compile(r"\bmicro-?patch(?:ed|es|ing)?\b", re.IGNORECASE)),
    ("workspace steer jargon", re.compile(r"\b(?:workspace\s+steers?|active\s+steers?|operator\s+steers?|ajar\s+steers?)\b", re.IGNORECASE)),
    ("SQL closeout gate jargon (G1-G5)", re.compile(r"\b(?:closeout\s+gates?|sql\s+gates?|gates?\s+G[1-5]\b|G1[–-]G5\b)", re.IGNORECASE)),
    ("locus jargon", re.compile(r"\b(?:source\s+locus|target_locus|dry_control_locus|causal\s+locus|locus|loci)\b", re.IGNORECASE)),
    ("epistemic hook code (H1-H9 / epistemic_hooks)", re.compile(r"\b(?:epistemic[_\s]+hooks?|hooks?\s+H[1-9]\b)", re.IGNORECASE)),
    (
        "harness graph/primitive jargon",
        re.compile(
            r"\b(?:trust_gadget|guarded-by|provides-tags|requires-tags|stepping\s+stone|"
            r"crown[_\s]jewels?|open[_\s]doors?|parked[_\s]doors?|primitive_helpers)\b",
            re.IGNORECASE,
        ),
    ),
    ("chain-solver Hop noun (Hop 1..N)", re.compile(r"\bHops?\s+\d+\b")),
    (
        "synthetic scanner confidence score",
        re.compile(r"\bconfidence\s*[:=]\s*(?:\d+(?:\.\d+)?(?:\s*/\s*10|%)?|(?:high|medium|low)\b)", re.IGNORECASE),
    ),
    (
        "empty rubric placeholder key (e.g. Instances: n/a / Why Low (not Info))",
        re.compile(
            r"(?:^\s*(?:[-*]\s+)?\*{0,2}(?:instances|guards(?:/assumptions)?|assumptions)\*{0,2}\s*:\s*(?:n/?a|none)\.?\s*$|"
            r"\bwhy\s+(?:low|medium|high)\s*\(not\s+(?:info|low|medium|high)\))",
            re.IGNORECASE,
        ),
    ),
    (
        "internal campaign/tool prose reference",
        re.compile(r"\b(?:ajar\s+(?:harness|proof\s+engine|scanner|worker|engine|run\.db)|wave\s*[0-9]+[a-z]?)\b", re.IGNORECASE),
    ),
]

HARNESS_JARGON_PATTERNS: list[tuple[str, re.Pattern[str]]] = RAW_INLINE_HARNESS_PATTERNS + PROSE_HARNESS_PATTERNS

# Legitimate technical collocations masked before checking bare scanner nouns `primitive` / `sink`.
LEGIT_PRIMITIVE_SINK_RE = re.compile(
    r"\b(?:cryptographic|crypto|encryption|signing|hash|kem|aead|dh|"
    r"sync(?:hronization)?|atomic|concurrency|locking|mutex|futex|semaphore|"
    r"kernel|os|ipc|vm|wasm|evm|op(?:code)?|language|type|geometric|graphic)\s+primitives?\b|"
    r"\b(?:log(?:ging)?|event|data|trace|metric|telemetry|audio|video|media|heat|clock|"
    r"packet|message|stream|network|output|file|stderr|stdout|null|blackhole)\s+sinks?\b|"
    r"\b(?:sinkhole|kitchen\s+sink)\b",
    re.IGNORECASE,
)
BARE_SCANNER_PRIMITIVE_SINK_RE = re.compile(r"\b(?:primitives?|sinks?)\b", re.IGNORECASE)

ATTRIBUTION_TRAILER_RE = re.compile(
    r"^\s*(?:[-*]\s+)?\*{0,2}(?:Reported-by|Credits?|Signed-off-by|Co-authored-by|Reviewed-by|Acked-by|Prepared\s+by|Author)\*{0,2}\s*:",
    re.IGNORECASE,
)

PSEUDO_DIFF_TODO_RE = re.compile(r"\bSECURITY-TODO\b")

LOCAL_PATH_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("file:// URI leak", re.compile(r"file:///[^\s)\]>\"']+")),
    (
        "local home/scratch/sandbox path leak",
        re.compile(
            r"(?:/home/[a-zA-Z0-9_.-]+|/Users/[a-zA-Z0-9_.-]+|/opt/antigravity\b|"
            r"/private/var/folders/[a-zA-Z0-9_./-]+|/tmp/ajar[a-zA-Z0-9_./-]*|"
            r"~/\.ajar/|\.scratch-[a-zA-Z0-9_.-]+|[A-Za-z]:\\Users\\[a-zA-Z0-9_.-]+)"
        ),
    ),
]

# AI-slop vocabulary, filler transitions, LLM template tells, and security puffery.
BANNED_SLOP_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    # Category: ai_vocab
    ("ai_vocab", "delve*", re.compile(r"\bdelv(?:e|es|ed|ing)\b", re.IGNORECASE)),
    ("ai_vocab", "crucial/crucially", re.compile(r"\bcrucial(?:ly)?\b", re.IGNORECASE)),
    ("ai_vocab", "comprehensive*", re.compile(r"\bcomprehensive(?:ly)?\b", re.IGNORECASE)),
    ("ai_vocab", "leverage*", re.compile(r"\bleverag(?:e|es|ed|ing)\b", re.IGNORECASE)),
    ("ai_vocab", "utilize*", re.compile(r"\butiliz(?:e|es|ed|ing|ation)\b", re.IGNORECASE)),
    ("ai_vocab", "robust*", re.compile(r"\brobust(?:ly|ness)?\b", re.IGNORECASE)),
    ("ai_vocab", "seamless*", re.compile(r"\bseamless(?:ly)?\b", re.IGNORECASE)),
    (
        "ai_vocab",
        "figurative underscore verb",
        re.compile(
            r"\bunderscor(?:ed|ing)\b|\bunderscores?\s+(?:the|that|how|why|this|these|its|our|their|a|an)\b",
            re.IGNORECASE,
        ),
    ),
    ("ai_vocab", "pivotal", re.compile(r"\bpivotal\b", re.IGNORECASE)),
    ("ai_vocab", "landscape", re.compile(r"\blandscape\b", re.IGNORECASE)),
    ("ai_vocab", "testament", re.compile(r"\btestament\b", re.IGNORECASE)),
    ("ai_vocab", "foster*", re.compile(r"\bfoster(?:s|ed|ing)?\b", re.IGNORECASE)),
    ("ai_vocab", "showcase*", re.compile(r"\bshowcas(?:e|es|ed|ing)\b", re.IGNORECASE)),
    ("ai_vocab", "paramount", re.compile(r"\bparamount\b", re.IGNORECASE)),
    ("ai_vocab", "multifaceted/intricate/meticulous", re.compile(r"\b(?:multifaceted|intricate|meticulous(?:ly)?)\b", re.IGNORECASE)),
    ("ai_vocab", "serves/stands as", re.compile(r"\b(?:serves|stands|acts)\s+as\s+a\b", re.IGNORECASE)),
    (
        "ai_vocab",
        "abstract metaphor noun",
        re.compile(r"\b(?:wedge|nexus|scaffolding|paradigm|north\s+star|flywheel|ratchet\s+up)\b", re.IGNORECASE),
    ),
    # Category: ai_transition
    ("ai_transition", "moreover/furthermore/additionally", re.compile(r"\b(?:moreover|furthermore|additionally)\b", re.IGNORECASE)),
    ("ai_transition", "notably/importantly/interestingly", re.compile(r"\b(?:notably|importantly|interestingly)\b", re.IGNORECASE)),
    (
        "ai_transition",
        "it is worth/important to note",
        re.compile(r"\bit\s+(?:is\s+(?:worth\s+noting|important\s+to\s+note|crucial\s+to\s+note)|bears\s+mentioning|should\s+be\s+noted)\b", re.IGNORECASE),
    ),
    ("ai_transition", "in conclusion/summary", re.compile(r"\b(?:in\s+conclusion|in\s+summary|to\s+summarize|all\s+in\s+all)\b", re.IGNORECASE)),
    ("ai_transition", "in order to", re.compile(r"\bin\s+order\s+to\b", re.IGNORECASE)),
    ("ai_transition", "due to the fact that", re.compile(r"\bdue\s+to\s+the\s+fact\s+that\b", re.IGNORECASE)),
    ("ai_transition", "not only ... but also / not just ... but", re.compile(r"\bnot\s+(?:only|just)\s+[^.!?\n]{3,60}\bbut\s+(?:also\b)?", re.IGNORECASE)),
    ("llm_tell", "stiff 'Orthogonally to' transition", re.compile(r"\borthogonally\s+to\b", re.IGNORECASE)),
    (
        "llm_tell",
        "minimizing procedure adverb (simply/easily/trivially)",
        re.compile(r"\b(?:simply|easily|trivially)\s+(?:send|pass|call|craft|trigger|exploit|bypass|overwrite|achieve|run|invoke)\b", re.IGNORECASE),
    ),
    # Category: security_puffery
    (
        "security_puffery",
        "malicious/bad/nefarious threat actor",
        re.compile(r"\b(?:malicious\s+(?:threat\s+)?actors?|threat\s+actors?|bad\s+actors?|nefarious\s+(?:actors?|attackers?|purposes?))\b", re.IGNORECASE),
    ),
    ("security_puffery", "potentially allow / could potentially", re.compile(r"\b(?:could\s+potentially|potentially\s+allow(?:s|ing)?|may\s+potentially)\b", re.IGNORECASE)),
    (
        "security_puffery",
        "catastrophic/devastating/obliterate/severe security implications",
        re.compile(r"\b(?:catastrophic|devastating|obliterat(?:e|es|ed|ing)|critical\s+security\s+implications|pose(?:s)?\s+a\s+(?:significant|severe|critical)\s+(?:security\s+)?risk)\b", re.IGNORECASE),
    ),
    ("security_puffery", "or worse / complete compromise", re.compile(r"\b(?:crash\s+or\s+worse|undefined\s+behavior\s+or\s+worse|complete\s+system\s+compromise)\b", re.IGNORECASE)),
    (
        "security_puffery",
        "self-declared confirmed vulnerability",
        re.compile(r"\bconfirmed\s+(?:critical\s+|high-severity\s+)?(?:security\s+)?vulnerabilit(?:y|ies)\b", re.IGNORECASE),
    ),
    (
        "security_puffery",
        "prohibited assurance claim",
        re.compile(r"\b(?:complete\s+security|guaranteed\s+clean|zero\s+false\s+positives|100%\s+secure|provably\s+free\s+of)\b", re.IGNORECASE),
    ),
    # Category: maintainer_lecturing
    (
        "maintainer_lecturing",
        "generic secure-coding lecture",
        re.compile(r"\b(?:developers\s+should\s+always|it\s+is\s+best\s+practice\s+to|always\s+sanitize\s+user\s+input|adhere\s+to\s+secure\s+coding|defense-in-depth\s+best\s+practices)\b", re.IGNORECASE),
    ),
    # Category: chatbot_tell
    (
        "chatbot_tell",
        "chatbot pleasantry or corporate warranty legalese",
        re.compile(
            r"\b(?:i\s+hope\s+this\s+helps|please\s+let\s+me\s+know\s+if\s+you\s+need\s+any\s+further|feel\s+free\s+to\s+reach\s+out|"
            r"makes\s+no\s+representations\s+or\s+warranties)\b",
            re.IGNORECASE,
        ),
    ),
]

# Blind-Judge-2 structural LLM tells (checked on raw non-code lines BEFORE stripping bold markers).
RUBRIC_ECHO_BOLD_LEADIN_RE = re.compile(
    r"^\s*\*\*(?:Trust\s+boundary|Preconditions?|Root\s+cause|Security\s+impact)[^*]*:\*\*",
    re.IGNORECASE,
)
INTENDED_SCHEMA_BULLET_RE = re.compile(r"^\s*[-*]\s+\*{0,2}Intended\*{0,2}\s*:", re.IGNORECASE)
BYPASS_SCHEMA_BULLET_RE = re.compile(r"^\s*[-*]\s+\*{0,2}(?:Bypass|Actual|Observed)\*{0,2}\s*:", re.IGNORECASE)

THROAT_CLEARING_LEAD_RE = re.compile(
    r"^\s*(?:this\s+(?:report|advisory|document|note|five-patch\s+series|patch\s+series|series)\s+"
    r"(?:describes|documents|details|presents|investigates|tightens)|"
    r"during\s+(?:a|an|our)\s+(?:recent\s+)?(?:security\s+)?(?:audit|review|assessment|investigation)|"
    r"static\s+and\s+dynamic\s+(?:code\s+)?review\s+identified|"
    r"code\s+review\s+identified|"
    r"we\s+have\s+identified\s+a\s+potential)",
    re.IGNORECASE,
)

CONCRETE_ANCHOR_RE = re.compile(
    r"(?:`[^`]+`|\b[a-zA-Z0-9_/-]+\.(?:c|h|cc|cpp|rs|go|py|js|ts|java|rb|sh|sol)\b|"
    r"\b[a-zA-Z_][a-zA-Z0-9_]*\(\)|"
    r"\bv?\d+\.\d+(?:\.\d+)?\b|"
    r"\b[0-9a-f]{7,40}\b)"
)

# Stative predicate adjectives excluded from passive-voice counts.
STATIVE_ADJECTIVES = (
    r"unaffected|affected|enabled|disabled|undefined|defined|malformed|untrusted|trusted|"
    r"required|allowed|permitted|expected|unexpected|confined|bounded|unbounded|limited|unlimited|"
    r"isolated|signed|unsigned|initialized|uninitialized|aligned|misaligned|connected|disconnected|"
    r"authenticated|unauthenticated|authorized|unauthorized|configured|misconfigured|deprecated|"
    r"supported|unsupported|documented|undocumented|mounted|unmounted|locked|unlocked|"
    r"encrypted|unencrypted|compressed|uncompressed|cached|uncached|zeroed|terminated|"
    r"guarded|unguarded|exposed|preserved|satisfied|unsatisfied|reachable|unreachable"
)

PASSIVE_AUX_PARTICIPLE_RE = re.compile(
    r"\b(?:is|are|was|were|be|been|being)\s+"
    r"(?:not\s+|never\s+|only\s+|also\s+|still\s+|already\s+|silently\s+|unconditionally\s+|directly\s+|automatically\s+)?"
    rf"(?!(?:{STATIVE_ADJECTIVES})\b)"
    r"(?:[a-z]{3,}ed|written|read|taken|given|made|done|set|left|sent|run|built|spawned|passed|held|kept|known|seen|found|shown|chosen|broken|overwritten)\b",
    re.IGNORECASE,
)

FIRST_PERSON_RE = re.compile(r"\b(?:we|our|ourselves)\b", re.IGNORECASE)

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F9FF"
    "\U00002600-\U000027BF"
    "]"
)

PROTECTED_DOT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(?:e\.g|i\.e|vs|cf|etc|approx|resp|min|max|fig|sec|no|vol|al)\.", re.IGNORECASE),
    re.compile(
        r"\b[a-zA-Z0-9_<>*.-]+\.(?:c|h|cc|cpp|rs|go|py|js|ts|rb|sh|sol|md|txt|json|yml|yaml|toml|patch|rej|cfg|conf|ini|env|gitignore|lock)\b"
    ),
    re.compile(r"(?:^|(?<=[\s(\"`]))\.[a-zA-Z0-9_.-]+\b"),
    re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_<>-]*\.[a-zA-Z_][a-zA-Z0-9_<>.-]*\b"),
    re.compile(r"\bv?\d+\.\d+(?:\.\d+)*\b"),
]

METADATA_FIELD_RE = re.compile(
    r"^(?:[-*]\s+)?\*{0,2}(?:"
    r"Severity|CVSS(?:\s+v?[34]\.[01])?|CWE|Target|Category|Component|Status|Scope|Commit|Repository|Revision|Date|"
    r"Difficulty(?:\s*/\s*Preconditions?)?|Preconditions?|"
    r"Affected\s+versions?|Affected\s+files?|Affected\s+configs?|Affected\s+components?|"
    r"Introduced(?:-in|\s+in)|Baseline\s+commit|Reviewed\s+areas?|Locations?|Directory|"
    r"Signed-off-by|Co-authored-by|Reported-by|Credits?|Reviewed-by|Acked-by|Prepared\s+by|Author|"
    r"Next-review\s+trigger|base-commit"
    r")\*{0,2}\s*:",
    re.IGNORECASE,
)

EMAIL_FIRST_LINE_RE = re.compile(
    r"^(?:From\s+\S+|From:|To:|Cc:|Date:|Subject:|Message-ID:|MIME-Version:|diff --git )",
    re.IGNORECASE,
)

SHELL_OR_CODE_INDENT_RE = re.compile(
    r"(?:^\s*#!/|\bset\s+-[euo]+|\bmktemp\b|\btrap\s+|\bgit\s+|\bcurl\s+|\bpython3?\b|"
    r"\bgcc\b|\bclang\b|\bcargo\b|\bforge\b|\bpytest\b|\bmake\b|\bmkdir\b|\bcat\s+<<|"
    r"\bcd\s+|\brm\s+-rf\b|\btest_expect_success\b|#include\s+|[;{}]|/\*|\*/|"
    r"^\s{4,}(?:if|for|while|do|fi|done|return|struct|unsigned|int|const|void|char|fn|let|def|assert)\b)"
)

CLI_DOUBLE_DASH_LINE_RE = re.compile(
    r"(?:^\s*(?:\$\s+|#\s+)?(?:git|curl|sh|bash|python3?|cargo|go|npm|bun|pytest|openssl|ssh|tar|grep|rg|sed|awk)\b|"
    r"\s--\s+(?:https?://|[./~$-]|[a-zA-Z0-9_.-]+/[a-zA-Z0-9_./-]+))"
)

LIST_ITEM_START_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)]|\([a-z0-9]+\))\s+")


@dataclass
class FindingHit:
    category: str
    rule: str
    line: int
    match: str


@dataclass
class FileLintReport:
    path: str
    tier: str | None
    channel: str
    passed: bool
    mechanical_score_100: int
    prose_word_count: int
    total_non_code_word_count: int
    heading_count: int
    max_heading_depth: int
    table_count: int
    code_block_count: int
    has_reproducer_block: bool
    has_diff_or_patch: bool
    lead_word_count: int
    lead_sentence_count: int
    lead_has_concrete_anchor: bool
    lead_throat_clearing: bool
    lead_excerpt: str
    sentence_count: int
    mean_sentence_words: float
    max_sentence_words: int
    sentence_sd_words: float
    sentence_cv: float
    long_sentences_over_35: int
    severe_runons_over_50: int
    consecutive_same_starters: int
    passive_sentence_count: int
    passive_ratio: float
    em_dash_count: int
    callout_box_count: int
    bold_bullet_ratio: float
    bureaucratic_triad_count: int
    markdown_decoration_in_plaintext: int
    hard_wrapped_prose_lines: int = 0
    harness_leaks: list[FindingHit] = field(default_factory=list)
    local_path_leaks: list[FindingHit] = field(default_factory=list)
    slop_hits: list[FindingHit] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_patch_or_email(lines: list[str]) -> bool:
    for line in lines:
        if line.strip():
            return bool(EMAIL_FIRST_LINE_RE.match(line))
    return False


def _detect_markdown_hard_wrapped_prose(raw_lines: list[str], is_email: bool) -> list[int]:
    """Return 1-indexed continuation line numbers where Markdown prose/bullets hard-wrap mid-paragraph."""
    hard_wrap_lines: list[int] = []
    n = len(raw_lines)
    i = 0

    # Skip optional YAML frontmatter at top of Markdown files.
    if n >= 3 and raw_lines[0].strip() == "---":
        for end_fm in range(1, min(n, 40)):
            if raw_lines[end_fm].strip() == "---":
                i = end_fm + 1
                break
            if raw_lines[end_fm].startswith("#"):
                break

    in_email_headers = is_email and i == 0
    in_fenced = False
    fence_char = ""
    fence_len = 0
    in_diff_body = False
    prev_open_prose = False
    prev_blockquote_prose = False

    while i < n:
        lineno = i + 1
        line = raw_lines[i]

        if in_email_headers:
            if line.strip() == "":
                in_email_headers = False
            i += 1
            continue

        if not in_diff_body:
            if not in_fenced:
                fence_open = re.match(r"^\s*(`{3,}|~{3,})", line)
                if fence_open:
                    marker = fence_open.group(1)
                    in_fenced = True
                    fence_char = marker[0]
                    fence_len = len(marker)
                    prev_open_prose = False
                    prev_blockquote_prose = False
                    i += 1
                    continue
            else:
                if re.match(rf"^\s*{re.escape(fence_char)}{{{fence_len},}}\s*$", line):
                    in_fenced = False
                    fence_char = ""
                    fence_len = 0
                prev_open_prose = False
                prev_blockquote_prose = False
                i += 1
                continue

        starts_unfenced_diff = (
            line.startswith("diff --git ")
            or (line.startswith("--- a/") and i + 1 < n and raw_lines[i + 1].startswith("+++ b/"))
            or (
                line == "---"
                and i + 1 < n
                and (raw_lines[i + 1].startswith(" ") or raw_lines[i + 1].startswith("diff --git"))
            )
            or line == "-- "
        )
        if starts_unfenced_diff and not in_diff_body:
            in_diff_body = True
            prev_open_prose = False
            prev_blockquote_prose = False
            i += 1
            continue

        if in_diff_body:
            if re.match(r"^#{1,6}\s+", line) or (
                i + 1 < n
                and line.strip()
                and re.match(r"^(?:={4,}|-{4,})\s*$", raw_lines[i + 1])
                and not line.startswith(("---", "+++"))
            ):
                in_diff_body = False
            else:
                prev_open_prose = False
                prev_blockquote_prose = False
                i += 1
                continue

        # Setext headings
        if (
            i + 1 < n
            and line.strip()
            and re.match(r"^(?:={4,}|-{4,})\s*$", raw_lines[i + 1])
            and not line.lstrip().startswith("-")
            and not line.startswith("--- ")
        ):
            prev_open_prose = False
            prev_blockquote_prose = False
            i += 2
            continue

        stripped = line.strip()

        # Blank lines, ATX headings, horizontal rules, HTML comments, and Markdown table rows
        if (
            not stripped
            or re.match(r"^#{1,6}\s+", line)
            or re.match(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", line)
            or re.match(r"^\s*\|.*\|\s*$", line)
            or (stripped.startswith("<!--") and stripped.endswith("-->"))
        ):
            prev_open_prose = False
            prev_blockquote_prose = False
            i += 1
            continue

        # 4+-space indented code blocks following a blank line or Setext underline
        prev_blank = (i == 0) or (raw_lines[i - 1].strip() == "") or bool(
            i >= 1 and re.match(r"^(?:={4,}|-{4,})\s*$", raw_lines[i - 1])
        )
        if (
            not prev_open_prose
            and prev_blank
            and re.match(r"^\s{4,}\S", line)
            and not LIST_ITEM_START_RE.match(line)
            and SHELL_OR_CODE_INDENT_RE.search(line)
        ):
            i += 1
            while i < n and (raw_lines[i].strip() == "" or re.match(r"^\s{4,}\S", raw_lines[i])):
                i += 1
            prev_open_prose = False
            prev_blockquote_prose = False
            continue

        # Blockquotes (tracked separately from surrounding non-quoted prose)
        if stripped.startswith(">"):
            bq_inner = re.sub(r"^\s*(?:>\s*)+", "", line).strip()
            if (
                not bq_inner
                or re.match(r"^\[![A-Z]+\]", bq_inner)
                or re.match(r"^#{1,6}\s+", bq_inner)
                or re.match(r"^\|.*\|$", bq_inner)
                or re.match(r"^(?:-{3,}|\*{3,}|_{3,})$", bq_inner)
            ):
                prev_blockquote_prose = False
            elif LIST_ITEM_START_RE.match(bq_inner) or METADATA_FIELD_RE.match(bq_inner):
                prev_blockquote_prose = True
            else:
                if prev_blockquote_prose:
                    hard_wrap_lines.append(lineno)
                prev_blockquote_prose = True
            prev_open_prose = False
            i += 1
            continue

        # Separate list bullets / numbered items open a new item without flagging the previous line
        if LIST_ITEM_START_RE.match(line):
            prev_open_prose = True
            prev_blockquote_prose = False
            i += 1
            continue

        # Standalone non-bullet metadata / attribution trailer lines
        if METADATA_FIELD_RE.match(stripped):
            prev_open_prose = True
            prev_blockquote_prose = False
            i += 1
            continue

        # Plain prose line: if preceded immediately by an open prose or bullet line, GFM inserts <br>
        if prev_open_prose:
            hard_wrap_lines.append(lineno)
        prev_open_prose = True
        prev_blockquote_prose = False
        i += 1

    return hard_wrap_lines


def _detect_raw_plaintext_markdown(raw_lines: list[str], is_email: bool) -> int:
    """Count lines with raw Markdown syntax BEFORE structural stripping in mailing-list mode."""
    md_lines = 0
    in_headers = is_email
    in_diff = False
    for idx, line in enumerate(raw_lines):
        if in_headers:
            if line.strip() == "":
                in_headers = False
            continue
        if line.startswith("diff --git ") or (
            line.startswith("--- a/") and idx + 1 < len(raw_lines) and raw_lines[idx + 1].startswith("+++ b/")
        ):
            in_diff = True
        if in_diff:
            if line == "" and idx + 1 < len(raw_lines) and not raw_lines[idx + 1].startswith(
                ("diff ", "--- ", "+++ ", "@@", "+", "-", " ", "index ")
            ):
                in_diff = False
            else:
                continue

        stripped = line.strip()
        if not stripped:
            continue
        # Fenced blocks, ATX headings, pipe tables are always Markdown in plain-text email
        if re.match(r"^\s*(`{3,}|~{3,})", line) or re.match(r"^#{1,6}\s+\S", line) or re.match(r"^\s*\|.*\|\s*$", line):
            md_lines += 1
            continue
        # Skip 4+-space indented code blocks when checking inline backticks/bold/links
        if re.match(r"^\s{4,}\S", line):
            continue
        if re.search(r"`[^`]+`|\*\*[^*\s][^*]*\*\*|\[[^\]]+\]\(https?://[^)]+\)", line):
            md_lines += 1
    return md_lines


def _strip_code_and_extract_structure(text: str) -> dict[str, Any]:
    raw_lines = text.splitlines()
    is_email = _is_patch_or_email(raw_lines)

    prose_lines: list[tuple[int, str]] = []
    non_code_lines: list[tuple[int, str]] = []
    header_lines: list[tuple[int, str]] = []
    headings: list[tuple[int, int, str]] = []
    code_blocks: list[str] = []
    table_count = 0
    table_word_count = 0

    in_fenced = False
    current_fence: list[str] = []
    in_diff_body = False
    current_diff: list[str] = []
    in_email_headers = is_email
    in_table = False
    skipping_metadata_continuation = False

    i = 0
    n = len(raw_lines)
    while i < n:
        lineno = i + 1
        line = raw_lines[i]

        if in_email_headers:
            if line.strip() == "":
                in_email_headers = False
            else:
                header_lines.append((lineno, line))
            i += 1
            continue

        # Fenced Markdown code blocks
        if not in_diff_body:
            fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
            if fence_match:
                in_table = False
                skipping_metadata_continuation = False
                if not in_fenced:
                    in_fenced = True
                    current_fence = [line]
                else:
                    current_fence.append(line)
                    code_blocks.append("\n".join(current_fence))
                    current_fence = []
                    in_fenced = False
                i += 1
                continue

            if in_fenced:
                current_fence.append(line)
                i += 1
                continue

        # Unfenced unified diff or git format-patch separator
        starts_unfenced_diff = (
            line.startswith("diff --git ")
            or (line.startswith("--- a/") and i + 1 < n and raw_lines[i + 1].startswith("+++ b/"))
            or (
                line == "---"
                and i + 1 < n
                and (raw_lines[i + 1].startswith(" ") or raw_lines[i + 1].startswith("diff --git"))
            )
            or line == "-- "
        )
        if starts_unfenced_diff and not in_diff_body:
            in_table = False
            skipping_metadata_continuation = False
            in_diff_body = True
            current_diff = [line]
            i += 1
            continue

        if in_diff_body:
            # Exit unfenced diff if a Markdown heading or clear non-diff section follows a blank line
            if (
                re.match(r"^#{1,6}\s+", line)
                or (
                    i + 1 < n
                    and line.strip()
                    and re.match(r"^(?:={4,}|-{4,})\s*$", raw_lines[i + 1])
                    and not line.startswith(("---", "+++"))
                )
            ):
                if current_diff:
                    code_blocks.append("\n".join(current_diff))
                    current_diff = []
                in_diff_body = False
                # Fall through to process heading/prose!
            else:
                current_diff.append(line)
                i += 1
                continue

        # Setext headings (e.g. Title\n===== or Section\n-----)
        if (
            i + 1 < n
            and line.strip()
            and re.match(r"^(?:={4,}|-{4,})\s*$", raw_lines[i + 1])
            and not line.lstrip().startswith("-")
            and not line.startswith("--- ")
        ):
            in_table = False
            skipping_metadata_continuation = False
            depth = 1 if raw_lines[i + 1].lstrip().startswith("=") else 2
            headings.append((lineno, depth, line.strip()))
            i += 2
            continue

        # ATX Markdown headings
        atx_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if atx_match:
            in_table = False
            skipping_metadata_continuation = False
            headings.append((lineno, len(atx_match.group(1)), atx_match.group(2).strip()))
            i += 1
            continue

        # Indented C/shell/Python/test blocks in plain-text notes (4+ spaces after blank/heading)
        prev_blank = (i == 0) or (raw_lines[i - 1].strip() == "") or bool(
            i >= 1 and re.match(r"^(?:={4,}|-{4,})\s*$", raw_lines[i - 1])
        )
        if (
            not skipping_metadata_continuation
            and prev_blank
            and re.match(r"^\s{4,}\S", line)
            and not re.match(r"^\s{4,}(?:[-*+]|\d+\.)\s+", line)
            and SHELL_OR_CODE_INDENT_RE.search(line)
        ):
            in_table = False
            block = [line]
            i += 1
            while i < n and (raw_lines[i].strip() == "" or re.match(r"^\s{4,}\S", raw_lines[i])):
                block.append(raw_lines[i])
                i += 1
            code_blocks.append("\n".join(block))
            continue

        # Markdown pipe table rows
        if re.match(r"^\s*\|.*\|\s*$", line):
            skipping_metadata_continuation = False
            if not in_table:
                table_count += 1
                in_table = True
            if not re.match(r"^\s*\|[\s:|-]+\|\s*$", line):
                non_code_lines.append((lineno, line))
                table_word_count += _count_words(line)
            i += 1
            continue
        else:
            in_table = False

        if line.strip() == "---":
            skipping_metadata_continuation = False
            i += 1
            continue

        stripped = line.strip()
        if not stripped:
            skipping_metadata_continuation = False
            prose_lines.append((lineno, line))
            i += 1
            continue

        if METADATA_FIELD_RE.match(stripped):
            non_code_lines.append((lineno, line))
            skipping_metadata_continuation = True
            i += 1
            continue

        if skipping_metadata_continuation and re.match(r"^\s{2,}\S", line) and not re.match(r"^\s*[-*+]\s+", line):
            non_code_lines.append((lineno, line))
            i += 1
            continue
        skipping_metadata_continuation = False

        non_code_lines.append((lineno, line))

        # Exclude compact reference-only bullet items (e.g. `- lib/socks.c:942 (do_SOCKS)`)
        if re.match(r"^[-*]\s+[a-zA-Z0-9_./<>-]+(?::\d+(?:-\d+)?)?\s*(?:\([^)]*\))?\s*$", stripped):
            i += 1
            continue

        prose_lines.append((lineno, line))
        i += 1

    if current_fence:
        code_blocks.append("\n".join(current_fence))
    if current_diff:
        code_blocks.append("\n".join(current_diff))

    return {
        "is_email": is_email,
        "header_lines": header_lines,
        "prose_lines": prose_lines,
        "non_code_lines": non_code_lines,
        "headings": headings,
        "code_blocks": code_blocks,
        "table_count": table_count,
        "table_word_count": table_word_count,
    }


def _clean_markdown_inline(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"`[^`]+`", "CODESYM", text)
    text = re.sub(r"^\s*>\s*(?:\[![A-Z]+\]\s*)?", "", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    return text


def _count_words(text: str) -> int:
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    cleaned = re.sub(r"[`*_>#|]", " ", cleaned)
    tokens = re.findall(r"[A-Za-z0-9_./<>'-]+", cleaned)
    return len(tokens)


def _split_sentences(paragraph: str) -> list[str]:
    work = _clean_markdown_inline(paragraph).strip()
    if not work:
        return []
    work = re.sub(r"^(?:[-*+]|\d+\.|\([a-z0-9]+\))\s+", "", work)
    for pat in PROTECTED_DOT_PATTERNS:
        work = pat.sub(lambda m: m.group(0).replace(".", "<DOT>"), work)
    # Allow uppercase starters, digits, quotes, backticked CODESYM, or lowercase C/code identifiers (`do_SOCKS()`, `foo_bar`, `file.c:12`)
    parts = re.split(
        r"(?<=[.!?])\s+(?=[A-Z0-9\"'(]|CODESYM|[a-z_][a-zA-Z0-9_]*\(\)|[a-z_][a-z0-9_]*_[a-z0-9_]+|[a-zA-Z0-9_/-]+<DOT>[a-z]{1,4}\b)",
        work,
    )
    sentences: list[str] = []
    for part in parts:
        restored = part.replace("<DOT>", ".").strip()
        if len(re.findall(r"[A-Za-z0-9_]+", restored)) >= 3:
            sentences.append(restored)
    return sentences


def _extract_paragraphs(prose_lines: list[tuple[int, str]]) -> list[str]:
    paragraphs: list[str] = []
    buf: list[str] = []
    for _, line in prose_lines:
        stripped = line.strip()
        if not stripped:
            if buf:
                paragraphs.append(" ".join(buf))
                buf = []
            continue
        if re.match(r"^(?:[-*+]|\d+\.|\([a-z]\))\s+", stripped) or re.match(
            r"^(?:Expected Invariant|Observed Defect|Defensive Fix Invariant|Summary|Impact|Trigger|Workarounds?):\s*$",
            stripped,
        ):
            if buf and not (buf[-1].endswith(":") and len(buf[-1].split()) <= 8):
                paragraphs.append(" ".join(buf))
                buf = []
            if stripped.endswith(":") and len(stripped.split()) <= 4:
                continue
        buf.append(stripped)
    if buf:
        paragraphs.append(" ".join(buf))
    return paragraphs


def _extract_lead_paragraph(
    raw_text: str,
    headings: list[tuple[int, int, str]],
    prose_lines: list[tuple[int, str]],
) -> str:
    lines = raw_text.splitlines()
    for lineno, _, title in headings:
        if re.match(
            r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:(?:executive\s+|quantified\s+|security\s+review\s+)?summary(?:\s*(?:&|and)\s*[^:]+)?|overview|description)\s*:?$",
            title,
            re.IGNORECASE,
        ):
            collected: list[str] = []
            for j in range(lineno, len(lines)):
                cur_line = lines[j].strip()
                if re.match(r"^(?:={4,}|-{4,})\s*$", cur_line):
                    continue
                if not cur_line:
                    if collected:
                        break
                    continue
                if re.match(r"^#{1,6}\s+", cur_line) or (
                    j + 1 < len(lines) and re.match(r"^(?:={4,}|-{4,})\s*$", lines[j + 1])
                ):
                    break
                if cur_line.startswith("```") or cur_line.startswith("|"):
                    if collected:
                        break
                    continue
                if METADATA_FIELD_RE.match(cur_line) and not collected:
                    continue
                collected.append(cur_line)
            if collected:
                return " ".join(collected)

    inline_sum = re.search(
        r"(?:^|\n)\*{0,2}(?:Quantified\s+)?Summary\*{0,2}:\s*\n*(.+?)(?:\n\s*\n|\Z)",
        raw_text,
        re.DOTALL | re.IGNORECASE,
    )
    if inline_sum:
        first_chunk = inline_sum.group(1).strip().splitlines()
        prose_chunk = [c.strip() for c in first_chunk if c.strip() and not c.strip().startswith("```")]
        if prose_chunk:
            return " ".join(prose_chunk)

    paragraphs = _extract_paragraphs(prose_lines)
    for p in paragraphs:
        if not p.lstrip().startswith("> [!"):
            return p
    return paragraphs[0] if paragraphs else ""


def lint_file(
    path: pathlib.Path,
    *,
    tier: str | None = None,
    channel: str = "ghsa",
) -> FileLintReport:
    raw_text = path.read_text(encoding="utf-8", errors="replace")
    raw_lines = raw_text.splitlines()
    parsed = _strip_code_and_extract_structure(raw_text)

    is_email: bool = parsed["is_email"]
    header_lines: list[tuple[int, str]] = parsed["header_lines"]
    prose_lines: list[tuple[int, str]] = parsed["prose_lines"]
    non_code_lines: list[tuple[int, str]] = parsed["non_code_lines"]
    headings: list[tuple[int, int, str]] = parsed["headings"]
    code_blocks: list[str] = parsed["code_blocks"]
    table_count: int = parsed["table_count"]
    table_word_count: int = parsed["table_word_count"]

    prose_word_count = sum(_count_words(line) for _, line in prose_lines if line.strip())
    total_non_code_words = sum(_count_words(line) for _, line in non_code_lines if line.strip())
    budget_word_count = prose_word_count + max(0, table_word_count - (table_count * 8))

    harness_leaks: list[FindingHit] = []
    slop_hits: list[FindingHit] = []
    heading_scan_lines = [(lineno, title) for lineno, _, title in headings]

    # 1. Scan headers, headings, and non-code lines for harness leaks
    for lineno, line in header_lines + heading_scan_lines + non_code_lines:
        is_attr_line = bool(ATTRIBUTION_TRAILER_RE.match(line))
        # Check unambiguous inline/raw tokens (skipping legitimate org credit except .invalid emails & clm-* IDs)
        for label, pat in RAW_INLINE_HARNESS_PATTERNS:
            for m in pat.finditer(line):
                matched = m.group(0)
                if is_attr_line and not matched.endswith(".invalid") and not re.match(
                    r"^(?:clm|fnd|cor|pvf|chn|ano|surf|prim|cjw|door|ghsa)-", matched, re.IGNORECASE
                ) and "by_ajar" not in matched.lower():
                    continue
                harness_leaks.append(FindingHit("harness_jargon", label, lineno, matched))

        line_no_backticks = re.sub(r"`[^`]+`", " ", line)
        for label, pat in PROSE_HARNESS_PATTERNS:
            for m in pat.finditer(line_no_backticks):
                if is_attr_line and "campaign/tool" in label:
                    continue
                harness_leaks.append(FindingHit("harness_jargon", label, lineno, m.group(0)))

        # Check bare scanner `primitive` / `sink` after masking legitimate technical collocations
        masked_legit = LEGIT_PRIMITIVE_SINK_RE.sub(" ", line_no_backticks)
        for m in BARE_SCANNER_PRIMITIVE_SINK_RE.finditer(masked_legit):
            harness_leaks.append(
                FindingHit("harness_jargon", "primitive/sink abstract harness noun", lineno, m.group(0))
            )

    for idx, line in enumerate(raw_lines, start=1):
        for m in PSEUDO_DIFF_TODO_RE.finditer(line):
            harness_leaks.append(
                FindingHit("harness_jargon", "uncompiled SECURITY-TODO pseudo-diff marker", idx, m.group(0))
            )

    # 2. Scan headings and non-code lines for AI slop and Blind-Judge-2 LLM tells
    intended_lines: list[int] = []
    bypass_lines: list[int] = []
    for lineno, line in heading_scan_lines + non_code_lines:
        # Check rubric-echo bold paragraph lead-ins BEFORE stripping bold
        m_echo = RUBRIC_ECHO_BOLD_LEADIN_RE.search(line)
        if m_echo:
            slop_hits.append(
                FindingHit("llm_tell", "rubric-echo bold paragraph lead-in", lineno, m_echo.group(0).strip())
            )
        if INTENDED_SCHEMA_BULLET_RE.match(line):
            intended_lines.append(lineno)
        if BYPASS_SCHEMA_BULLET_RE.match(line):
            bypass_lines.append(lineno)

        line_no_backticks = re.sub(r"`[^`]+`", " ", line)
        for cat, label, pat in BANNED_SLOP_PATTERNS:
            for m in pat.finditer(line_no_backticks):
                slop_hits.append(FindingHit(cat, label, lineno, m.group(0)))

    if intended_lines and bypass_lines:
        slop_hits.append(
            FindingHit(
                "llm_tell",
                "prompt-schema '- Intended:' / '- Bypass:' bullet pair",
                intended_lines[0],
                "- Intended: / - Bypass:",
            )
        )

    # 3. Scan ENTIRE raw file (including lines after diff --git!) for local filesystem path leaks
    local_path_leaks: list[FindingHit] = []
    for idx, line in enumerate(raw_lines, start=1):
        if line.startswith(("--- a/", "+++ b/")):
            continue
        for label, pat in LOCAL_PATH_PATTERNS:
            for m in pat.finditer(line):
                local_path_leaks.append(FindingHit("local_path_leak", label, idx, m.group(0)))

    # 4. Lead paragraph analysis
    effective_tier = tier.upper() if tier else None
    lead_raw = _extract_lead_paragraph(raw_text, headings, prose_lines)
    lead_words = _count_words(lead_raw)
    lead_sentences = _split_sentences(lead_raw)
    lead_sentence_count = len(lead_sentences)
    lead_starts_with_bullet = bool(re.match(r"^\s*[-*]\s+", lead_raw)) and not METADATA_FIELD_RE.match(lead_raw.strip())
    lead_has_anchor = bool(CONCRETE_ANCHOR_RE.search(lead_raw))
    lead_throat_clearing = bool(THROAT_CLEARING_LEAD_RE.search(_clean_markdown_inline(lead_raw)))

    paragraphs = _extract_paragraphs(prose_lines)
    if not lead_throat_clearing and len(paragraphs) >= 2:
        if re.match(
            r"^\s*(?:static\s+and\s+dynamic\s+code\s+review|code\s+review)\s+identified\b",
            _clean_markdown_inline(paragraphs[1]),
            re.IGNORECASE,
        ):
            lead_throat_clearing = True

    all_sentences: list[str] = []
    for p in paragraphs:
        if p.lstrip().startswith("> [!"):
            continue
        all_sentences.extend(_split_sentences(p))

    sent_lengths = [len(re.findall(r"[A-Za-z0-9_]+", s)) for s in all_sentences]
    sentence_count = len(sent_lengths)
    mean_sent = round(statistics.mean(sent_lengths), 2) if sent_lengths else 0.0
    max_sent = max(sent_lengths) if sent_lengths else 0
    sd_sent = round(statistics.pstdev(sent_lengths), 2) if len(sent_lengths) >= 2 else 0.0
    cv_sent = round(sd_sent / mean_sent, 3) if mean_sent > 0 else 0.0

    long_over_35 = sum(1 for slen in sent_lengths if slen > 35)
    severe_over_50 = sum(1 for slen in sent_lengths if slen > 50)

    starters: list[str] = []
    for s in all_sentences:
        toks = re.findall(r"[A-Za-z0-9_]+", s.lower())
        starters.append(toks[0] if toks else "")
    consecutive_same_starters = sum(
        1 for a, b in zip(starters, starters[1:], strict=False) if a and a == b and a not in {"codesym"}
    )

    passive_count = sum(1 for s in all_sentences if PASSIVE_AUX_PARTICIPLE_RE.search(s))
    passive_ratio = round(passive_count / sentence_count, 3) if sentence_count else 0.0

    first_person_count = sum(1 for s in all_sentences if FIRST_PERSON_RE.search(s))
    first_person_ratio = round(first_person_count / sentence_count, 3) if sentence_count else 0.0

    em_dash_count = 0
    callout_box_count = 0
    bold_bullet_lines = 0
    nonempty_prose_lines = 0
    overwide_plaintext_lines = 0
    emoji_count = 0

    for _, line in non_code_lines:
        stripped = line.strip()
        if not stripped:
            continue
        is_meta = bool(METADATA_FIELD_RE.match(stripped))
        if not is_meta and not re.match(r"^\s*\|.*\|\s*$", line):
            nonempty_prose_lines += 1
        line_wo_code = re.sub(r"`[^`]+`", " ", stripped)
        em_dash_count += line_wo_code.count("—")
        em_dash_count += len(re.findall(r"\s–\s", line_wo_code))
        if not CLI_DOUBLE_DASH_LINE_RE.search(line_wo_code):
            em_dash_count += len(re.findall(r"(?<=[A-Za-z,;:])\s--\s(?=[A-Za-z])", line_wo_code))
        if re.match(r"^>\s*\[!(?:IMPORTANT|NOTE|WARNING|TIP|CAUTION)\]", stripped):
            callout_box_count += 1
        if not is_meta and re.match(r"^[-*]\s+\*\*[^*]+:\*\*", stripped):
            bold_bullet_lines += 1
        emoji_count += len(EMOJI_RE.findall(line_wo_code))
        if channel == "mailing-list" and len(line) > 78 and "://" not in line and not is_meta:
            overwide_plaintext_lines += 1

    markdown_in_plaintext = (
        _detect_raw_plaintext_markdown(raw_lines, is_email)
        if channel == "mailing-list"
        else 0
    )
    hard_wrap_line_nums = (
        _detect_markdown_hard_wrapped_prose(raw_lines, is_email)
        if channel != "mailing-list"
        else []
    )
    hard_wrapped_prose_lines = len(hard_wrap_line_nums)

    bold_bullet_ratio = round(bold_bullet_lines / nonempty_prose_lines, 3) if nonempty_prose_lines else 0.0

    exp_n = len(re.findall(r"^Expected Invariant:", raw_text, re.MULTILINE))
    obs_n = len(re.findall(r"^Observed Defect:", raw_text, re.MULTILINE))
    def_n = len(re.findall(r"^Defensive Fix Invariant:", raw_text, re.MULTILINE))
    bureaucratic_triad_count = min(exp_n, obs_n, def_n)

    joined_code = "\n".join(code_blocks)
    has_diff = bool(
        re.search(r"(?:^diff --git |^---\s+a/|^\+\+\+\s+b/|^@@\s+-\d+)", raw_text, re.MULTILINE)
    )
    has_repro = bool(
        re.search(
            r"(?:\bgit\s+(?:init|clone|apply|am|fetch|checkout|update-index|submodule|fsck|read-tree|mktree|hash-object|config|ls-files|rev-parse)\b|"
            r"\bcurl\s+|\bpython3?\s+|\bgcc\s+|\bclang\s+|\bcmake\s+|\bmake\b|\bmktemp\b|"
            r"\btest_expect_success\b|\bforge\s+test\b|\bcargo\s+test\b|\bpytest\b|\bgo\s+test\b|#!/bin/(?:ba)?sh|"
            r"#include\s+<)",
            joined_code,
        )
        and not (
            len(code_blocks) == 1
            and has_diff
            and not re.search(
                r"\b(?:mktemp|git\s+init|gcc|python3?|test_expect_success|forge\s+test|cargo\s+test|pytest|#!/bin/(?:ba)?sh)\b",
                joined_code,
            )
        )
    )

    heading_count = len(headings)
    section_heading_count = sum(1 for _, d, _ in headings if 2 <= d <= 3)
    h4_plus_count = sum(1 for _, d, _ in headings if d >= 4)
    filler_headings = [title for _, _, title in headings if FILLER_HEADING_RE.search(title)]
    max_heading_depth = max((d for _, d, _ in headings), default=0)

    issues: list[str] = []
    warnings: list[str] = []
    score = 100

    if harness_leaks:
        uniq = sorted({f"{h.rule}: '{h.match}' (L{h.line})" for h in harness_leaks})
        issues.append(f"Internal harness jargon leaked ({len(harness_leaks)} hits): " + "; ".join(uniq[:6]))
        score -= min(30, 8 + 3 * len(harness_leaks))

    if local_path_leaks:
        uniq_p = sorted({f"{p.match} (L{p.line})" for p in local_path_leaks})
        issues.append(f"Local filesystem path leaked ({len(local_path_leaks)} hits): " + "; ".join(uniq_p[:4]))
        score -= min(20, 8 + 2 * len(local_path_leaks))

    if slop_hits:
        uniq_s = sorted({f"[{s.category}] '{s.match}' (L{s.line})" for s in slop_hits})
        issues.append(f"Banned AI-slop / LLM-tell phrases ({len(slop_hits)} hits): " + "; ".join(uniq_s[:6]))
        score -= min(25, 5 * len(slop_hits))

    if emoji_count > 0:
        issues.append(f"Decorative emojis present ({emoji_count}).")
        score -= 5

    if filler_headings:
        warnings.append(f"Filler section heading(s) detected: {', '.join(filler_headings)}.")
        score -= min(8, 3 * len(filler_headings))

    # Channel & tier aware lead checks
    if lead_starts_with_bullet:
        issues.append("Opening lead starts with a metadata bullet dump instead of a causal lead.")
        score -= 10
    elif lead_words == 0:
        issues.append("Missing opening prose lead.")
        score -= 12
    else:
        if channel == "immunefi":
            lead_soft_cap, lead_hard_cap, max_lead_sents = 105, 135, 5
        elif effective_tier in {"LOW", "DRY", "AUDIT"}:
            lead_soft_cap, lead_hard_cap, max_lead_sents = 110, 150, 5
        else:
            lead_soft_cap, lead_hard_cap, max_lead_sents = 55, 80, 2

        if lead_words > lead_hard_cap:
            issues.append(f"Opening lead is {lead_words} words (target <= {lead_soft_cap} words; hard cap {lead_hard_cap}).")
            score -= 10
        elif lead_words > lead_soft_cap:
            warnings.append(f"Opening lead is {lead_words} words (exceeds {lead_soft_cap}-word target).")
            score -= 5

        if lead_sentence_count > max_lead_sents + 1:
            issues.append(f"Opening lead has {lead_sentence_count} sentences (target <= {max_lead_sents}).")
            score -= 6
        elif lead_sentence_count > max_lead_sents:
            warnings.append(f"Opening lead has {lead_sentence_count} sentences (prefer <= {max_lead_sents}).")
            score -= 2

        if not lead_has_anchor:
            issues.append("Opening lead lacks a concrete file, function, or version identifier.")
            score -= 6

        if lead_throat_clearing:
            warnings.append("Opening section uses generic review meta-narration instead of stating the defect directly.")
            score -= 4

    # Proportionality tier budgets
    requires_repro = True
    if effective_tier in TIER_BUDGETS:
        b = TIER_BUDGETS[effective_tier]
        requires_repro = bool(b["requires_repro"])
        if b["hard_min_words"] is not None:
            if prose_word_count < b["hard_min_words"]:
                issues.append(
                    f"Tier {effective_tier} prose word count ({prose_word_count}) is below hard floor ({b['hard_min_words']}; target {b['min_words']}-{b['max_words']})."
                )
                score -= 10
            elif prose_word_count < b["min_words"]:
                warnings.append(
                    f"Tier {effective_tier} prose word count ({prose_word_count}) is below target band ({b['min_words']}-{b['max_words']})."
                )
                score -= 3
            elif budget_word_count > b["hard_max_words"]:
                issues.append(
                    f"Tier {effective_tier} word count ({budget_word_count}) exceeds hard ceiling ({b['hard_max_words']}; target {b['min_words']}-{b['max_words']})."
                )
                score -= 12
            elif budget_word_count > b["max_words"]:
                warnings.append(
                    f"Tier {effective_tier} word count ({budget_word_count}) exceeds target band ({b['min_words']}-{b['max_words']})."
                )
                score -= 5

        if b["max_sections"] is not None and section_heading_count > b["max_sections"]:
            warnings.append(
                f"Tier {effective_tier} has {section_heading_count} section headings (target <= {b['max_sections']})."
            )
            score -= 4

        if b["max_h4_plus"] is not None and h4_plus_count > b["max_h4_plus"]:
            warnings.append(
                f"Tier {effective_tier} has {h4_plus_count} deep subheading(s) (h4+; target <= {b['max_h4_plus']})."
            )
            score -= 3

        if b["max_tables"] is not None and table_count > b["max_tables"]:
            issues.append(
                f"Tier {effective_tier} has {table_count} Markdown table(s) (allowed <= {b['max_tables']})."
            )
            score -= 6

    if severe_over_50 > 0:
        issues.append(
            f"{severe_over_50} severe run-on sentence(s) > 50 words (max = {max_sent} words; target <= 35)."
        )
        score -= min(12, 4 * severe_over_50)
    elif long_over_35 > 2:
        warnings.append(f"{long_over_35} sentences exceed 35 words (max = {max_sent} words).")
        score -= 4

    if sentence_count >= 8 and sd_sent < 3.5:
        warnings.append(
            f"Low sentence-length burstiness (SD = {sd_sent} words, CV = {cv_sent}): monotonous robotic cadence."
        )
        score -= 6

    if consecutive_same_starters >= 2:
        warnings.append(
            f"{consecutive_same_starters} consecutive sentence pairs start with the identical word."
        )
        score -= min(6, 2 * consecutive_same_starters)

    if sentence_count >= 4 and passive_ratio > 0.35:
        issues.append(
            f"High passive-voice density ({passive_ratio:.0%}, {passive_count}/{sentence_count} sentences; cap <= 35%, target <= 20%)."
        )
        score -= 8
    elif sentence_count >= 4 and passive_ratio > 0.25:
        warnings.append(
            f"Elevated passive-voice density ({passive_ratio:.0%}, {passive_count}/{sentence_count} sentences; target <= 20%)."
        )
        score -= 4

    if channel in {"ghsa", "h1", "immunefi", "mailing-list"} and sentence_count >= 8 and first_person_ratio > 0.20:
        warnings.append(
            f"Elevated first-person pronoun rate ({first_person_ratio:.0%}, {first_person_count}/{sentence_count} sentences; prefer code symbols as grammatical subjects)."
        )
        score -= 3

    if em_dash_count > 0:
        if em_dash_count >= 3:
            issues.append(f"Em-dash / spaced-dash overuse ({em_dash_count} occurrences; prefer commas or periods).")
            score -= min(10, 2 * em_dash_count)
        else:
            warnings.append(f"Em-dash / spaced-dash present ({em_dash_count} occurrence(s); prefer commas or periods).")
            score -= 2 * em_dash_count

    if callout_box_count > 0 and channel in {"ghsa", "h1", "immunefi", "mailing-list"}:
        warnings.append(
            f"GitHub alert callout boxes ({callout_box_count}) used in external advisory; prefer direct prose."
        )
        score -= 3 * callout_box_count

    if bold_bullet_ratio > 0.50 and nonempty_prose_lines >= 6:
        issues.append(
            f"Over-formatted bold-label bullet dump ({bold_bullet_ratio:.0%} of body lines use '- **Label:**')."
        )
        score -= 8

    if bureaucratic_triad_count > 0:
        warnings.append(
            f"Repetitive formal-methods triad ('Expected Invariant' / 'Observed Defect' / 'Defensive Fix Invariant' x{bureaucratic_triad_count}) restates each bug 3 times."
        )
        score -= min(10, 4 * bureaucratic_triad_count)

    if markdown_in_plaintext > 0 and channel == "mailing-list":
        issues.append(
            f"Markdown decoration ({markdown_in_plaintext} lines) inside plain-text mailing-list artifact."
        )
        score -= 6

    if overwide_plaintext_lines > 0 and channel == "mailing-list":
        warnings.append(
            f"{overwide_plaintext_lines} prose line(s) exceed 78 columns in mailing-list mode (wrap plain text at <= 72 columns)."
        )
        score -= 3

    if hard_wrapped_prose_lines > 0 and channel != "mailing-list":
        line_preview = ", ".join(f"L{ln}" for ln in hard_wrap_line_nums[:6])
        issues.append(
            "Markdown prose contains hard mid-paragraph line breaks "
            "(GFM renders single \\n as <br>); put each paragraph and bullet item on a single line "
            f"({hard_wrapped_prose_lines} continuation line(s): {line_preview})."
        )
        score -= min(12, 3 + 2 * hard_wrapped_prose_lines)

    if requires_repro and path.suffix not in {".patch"} and not re.search(r"0000-cover-letter", path.name):
        if not has_repro:
            issues.append("No self-contained reproduction command or PoC code block detected.")
            score -= 12

    score = max(0, min(100, score))
    passed = len(issues) == 0

    lead_excerpt = _clean_markdown_inline(lead_raw)
    if len(lead_excerpt) > 160:
        lead_excerpt = lead_excerpt[:157] + "..."

    return FileLintReport(
        path=str(path),
        tier=effective_tier,
        channel=channel,
        passed=passed,
        mechanical_score_100=score,
        prose_word_count=prose_word_count,
        total_non_code_word_count=total_non_code_words,
        heading_count=heading_count,
        max_heading_depth=max_heading_depth,
        table_count=table_count,
        code_block_count=len(code_blocks),
        has_reproducer_block=has_repro,
        has_diff_or_patch=has_diff,
        lead_word_count=lead_words,
        lead_sentence_count=lead_sentence_count,
        lead_has_concrete_anchor=lead_has_anchor,
        lead_throat_clearing=lead_throat_clearing,
        lead_excerpt=lead_excerpt,
        sentence_count=sentence_count,
        mean_sentence_words=mean_sent,
        max_sentence_words=max_sent,
        sentence_sd_words=sd_sent,
        sentence_cv=cv_sent,
        long_sentences_over_35=long_over_35,
        severe_runons_over_50=severe_over_50,
        consecutive_same_starters=consecutive_same_starters,
        passive_sentence_count=passive_count,
        passive_ratio=passive_ratio,
        em_dash_count=em_dash_count,
        callout_box_count=callout_box_count,
        bold_bullet_ratio=bold_bullet_ratio,
        bureaucratic_triad_count=bureaucratic_triad_count,
        markdown_decoration_in_plaintext=markdown_in_plaintext,
        hard_wrapped_prose_lines=hard_wrapped_prose_lines,
        harness_leaks=harness_leaks,
        local_path_leaks=local_path_leaks,
        slop_hits=slop_hits,
        issues=issues,
        warnings=warnings,
    )


def _iter_targets(target: pathlib.Path) -> list[pathlib.Path]:
    if target.is_file():
        return [target]
    exts = {".md", ".txt", ".patch"}
    out: list[pathlib.Path] = []
    for p in sorted(target.rglob("*")):
        if p.is_file() and p.suffix.lower() in exts and not p.name.endswith(".metadata.json"):
            out.append(p)
    return out


def _format_human(rep: FileLintReport) -> str:
    status = "PASS" if rep.passed else "FAIL"
    tier_str = f" [Tier {rep.tier}]" if rep.tier else ""
    lines = [
        f"[{status}] {rep.path}{tier_str} (channel={rep.channel}, mechanical_score={rep.mechanical_score_100}/100)",
        f"  Words: prose={rep.prose_word_count}, non_code_total={rep.total_non_code_word_count} | "
        f"Headings={rep.heading_count} (max_depth=h{rep.max_heading_depth}) | Tables={rep.table_count} | "
        f"CodeBlocks={rep.code_block_count} (repro={rep.has_reproducer_block}, diff={rep.has_diff_or_patch})",
        f"  Lead: words={rep.lead_word_count}, sentences={rep.lead_sentence_count}, "
        f"anchor={rep.lead_has_concrete_anchor}, throat_clearing={rep.lead_throat_clearing}",
        f"  LeadExcerpt: \"{rep.lead_excerpt}\"",
        f"  Cadence: sentences={rep.sentence_count}, mean={rep.mean_sentence_words}w, "
        f"max={rep.max_sentence_words}w, burstiness_sd={rep.sentence_sd_words}w (CV={rep.sentence_cv}), "
        f">35w={rep.long_sentences_over_35}, >50w={rep.severe_runons_over_50}",
        f"  Hygiene: passive={rep.passive_ratio:.1%} ({rep.passive_sentence_count}/{rep.sentence_count}), "
        f"em_dashes={rep.em_dash_count}, bold_bullet_ratio={rep.bold_bullet_ratio:.1%}, hard_wraps={rep.hard_wrapped_prose_lines}, "
        f"harness_leaks={len(rep.harness_leaks)}, local_paths={len(rep.local_path_leaks)}, slop_hits={len(rep.slop_hits)}",
    ]
    for iss in rep.issues:
        lines.append(f"  ERROR: {iss}")
    for warn in rep.warnings:
        lines.append(f"  WARN:  {warn}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic anti-AI-slop, jargon-leak, LLM-tell, and proportionality linter (v2)."
    )
    parser.add_argument("target", help="Markdown/text/patch file or directory to inspect.")
    parser.add_argument(
        "--tier",
        choices=["S", "M", "C", "low", "dry", "audit", "s", "m", "c", "LOW", "DRY", "AUDIT"],
        default=None,
        help="Proportionality tier budget: S (90-350w), M (280-650w), C (500-1000w), low (50-180w), dry (80-380w), or audit.",
    )
    parser.add_argument(
        "--channel",
        choices=["ghsa", "mailing-list", "h1", "immunefi", "customer"],
        default="ghsa",
        help="Target disclosure channel (default: ghsa).",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero exit code on warnings as well as errors.")
    args = parser.parse_args(argv)

    target_path = pathlib.Path(args.target)
    if not target_path.exists():
        print(f"error: path not found: {target_path}", file=sys.stderr)
        return 2

    files = _iter_targets(target_path)
    if not files:
        print(f"error: no .md/.txt/.patch files found under {target_path}", file=sys.stderr)
        return 2

    reports = [lint_file(f, tier=args.tier, channel=args.channel) for f in files]

    if args.json:
        payload = {
            "schema": "ajar-report-voice-lint/2",
            "file_count": len(reports),
            "all_passed": all(r.passed and (not args.strict or not r.warnings) for r in reports),
            "reports": [asdict(r) for r in reports],
        }
        print(json.dumps(payload, indent=2))
    else:
        for idx, rep in enumerate(reports):
            if idx:
                print()
            print(_format_human(rep))

    any_failed = any(not r.passed or (args.strict and bool(r.warnings)) for r in reports)
    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
