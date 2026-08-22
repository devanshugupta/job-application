"""Inbox callback tracking  pull recent mail over IMAP (one or more accounts),
find job-application callbacks (interview invites, rejections, recruiter replies,
OA links, offers, auto-acks), update the matching tracker rows, print a digest.

Process shape is RECALL-FIRST: broad capture, then prune, never silently tight.

  Stage 1 BROAD CAPTURE ("[Gmail]/All Mail" always  Gmail tabs/filters hide job
  mail from INBOX): ATS sender, OR job keyword in the SUBJECT, OR sender domain
  matching a tracked company, OR a calendar invite (VEVENT) with job context, OR
  a human sender on a corporate domain with application-context language.
  Human recruiter mail from company domains (apple.com, snowflake.com, paylocity
  scheduling) is the highest-value class and must survive this stage.

  Stage 2 PRUNE (each tier only a digest count, so misses stay debuggable):
  consumer noise (ride receipts, bank transaction alerts, store ads, pay
  statements), job-board ALERT digests, promotional mail (List-Unsubscribe from
  a non-ATS sender, promo sender local-parts).

  Stage 3 CLASSIFY deterministically (precedence rejected > offer > VEVENT ->
  interview > oa > ack > interview > recruiter_reply; a status is NEVER written
  without a matching pattern). Ambiguous mail may go through the Brain seam
  (works with no key: ManualBrain packets / "unclassified").

Other guarantees:
- Stdlib only (imaplib + email + regex). Reads are side-effect free: every FETCH
  uses BODY.PEEK so the user's real mail is never marked read.
- Two-gate row attach: job context (ATS sender or application language) AND a
  word-boundary company match. Common-English-word / short company names
  (Driver, Current, Uber...) need sender/subject evidence, never body-only.
  Recall paths: sender local-part tokens (nexstar@myworkday.com), "Thanks for
  applying to X" subject extraction, sender company domains. Calendar-gateway
  senders (calendar-notification@google.com) never count as domain evidence.
- Threads: References / In-Reply-To chains (normalized-subject fallback, per
  account); each thread resolves to its LATEST message's classification and gets
  ONE callback record. For interview/recruiter_reply threads that ask for a
  response, the account's Sent folder is checked (headers only, PEEK) for a
  later reply  none found -> needs_reply on the callback record.
- Honest transitions: status only moves forward (applied -> replied/oa/
  interview/rejected/offer); 'offer' rows are frozen; auto-acks (type 'ack')
  never change status; an email older than the row's applied_date never changes
  status; max 3 note appends per row per run (newest first); a callback msgid
  already on the row is never appended twice (cross-account forward dedupe).
- Tracker writes re-load fresh state under the file lock and write atomically.
- Idempotent: processed (account, Message-ID) pairs persist in
  data/inbox_seen.json; --dry-run writes nothing.
- Config: JOB_AGENT_EMAIL / JOB_AGENT_EMAIL_APP_PASSWORD / JOB_AGENT_IMAP_HOST
  (+_2, _3... suffixes for more accounts; App Password whitespace is stripped,
  values never logged). Default look-back: settings.json {"inbox": {"days": N}}.
"""

from __future__ import annotations

import email
import email.header
import email.message
import email.utils
import html as html_lib
import imaplib
import json
import re
import sys
from datetime import date as date_cls, datetime, timedelta
from urllib.parse import quote

from .. import config
from . import tracker

SEEN_PATH = config.INBOX_SEEN_PATH

# ------------------------------------------------------------------ constants

ATS_DOMAINS = (
    "ashbyhq.com", "greenhouse.io", "greenhouse-mail.io", "lever.co",
    "hire.lever.co", "myworkday.com", "myworkdayjobs.com", "workday.com",
    "smartrecruiters.com", "icims.com", "jobvite.com", "bamboohr.com",
    "rippling.com", "mail.paylocity.com", "paylocity.com",
)

# Broad-capture SUBJECT keywords (stage 1; pruning handles the false positives).
SUBJECT_KEYWORDS = (
    "interview", "application", "applying", "assessment", "offer",
    "unfortunately", "recruiter", "opportunity", "position", "candidate",
    "next steps", "follow up", "follow-up", "phone screen", "take-home",
    "take home", "hiring",
)

# Application-context language: gate (a) for row attach + the corporate-sender
# capture arm. Word-boundary so promo "apply now" is not "applying".
_APP_CONTEXT_RE = re.compile(
    r"\bapplying\b|\bapplication\b|\binterview\w*\b|\brecruit(?:er|ing|ment)\b|"
    r"\bposition\b|\brole\b|\brequisition\b|\bcandidate\b|\bcandidacy\b|"
    r"\bmoving forward\b|\bhiring team\b|\byour resume\b|\bphone screen\b|"
    r"\bassessment\b|\btake[- ]home\b", re.I)

_FREEMAIL = {
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "live.com", "icloud.com", "me.com", "aol.com", "proton.me", "protonmail.com",
    "asu.edu",  # school mail (immigration/advising) is not recruiter mail
}

# High-precision classification patterns, checked in precedence order.
_REJECT_RE = re.compile(
    r"unfortunately|we will not be moving forward|other candidates|"
    r"not to proceed|no longer under consideration|decided not to move forward",
    re.I)
_OFFER_RE = re.compile(r"offer letter|pleased to offer|excited to offer", re.I)
# OA: an actionable assessment, not the word "assessment" in ack boilerplate.
_OA_RE = re.compile(
    r"hackerrank|codesignal|coderpad|take[- ]home|online assessment|"
    r"complete (?:your|the) .{0,24}assessment|assessments? (?:invitation|link)",
    re.I)
_OA_STRICT_RE = re.compile(  # for ack-pattern subjects: an OA you must ACT on.
    # Bare "take home" is process-description boilerplate in acks ("our process
    # includes a take-home")  actionable phrasing only.
    r"hackerrank|codesignal|coderpad|"
    r"complete (?:your|the|this) .{0,30}(?:assessment|take[- ]home|challenge)|"
    r"assessments? (?:invitation|link)|"
    r"action required", re.I)
# Interview requires SCHEDULING evidence, not the word "interview" in
# "if selected for an interview we will..." ack boilerplate.
_SUBJ_INTERVIEW_RE = re.compile(r"interview|phone screen", re.I)
_SCHED_STRICT_RE = re.compile(  # actionable/confirmed scheduling language
    r"please schedule|schedule your|your availability|share your availability|"
    r"book a time|has been scheduled|interview (?:is )?(?:scheduled|confirmed)|"
    r"confirmed:|upcoming interview|calendar invite|meeting link|"
    r"join (?:the|your) (?:interview|call|meeting)|pick a time|choose a time",
    re.I)
_SCHED_BROAD_RE = re.compile(  # broader, for non-ack-subject mail
    r"please schedule|schedule your|your availability|share your availability|"
    r"book a time|has been scheduled|interview (?:is )?(?:scheduled|confirmed)|"
    r"confirmed:|upcoming interview|calendar invite|meeting link|"
    r"join (?:the|your) (?:interview|call|meeting)|pick a time|choose a time|"
    r"schedule (?:an?|the) (?:interview|call|chat|time|meeting)|availability|"
    r"phone screen|interview with", re.I)
# Ack-pattern SUBJECTS: these can never classify above ack without scheduling
# or actionable-OA evidence.
_ACK_SUBJECT_RE = re.compile(
    r"thank(?:s| you) for applying|application (?:email )?(?:received|submitted|"
    r"confirmation)|we(?:'ve| have)? received your (?:job )?application|"
    r"thank you for your (?:application|online submission)|"
    r"thank(?:s| you) for your interest in", re.I)
# "No (further) action (is) required/needed" is ack boilerplate  it must never
# satisfy the strict-OA "action required" token.
_NO_ACTION_RE = re.compile(
    r"\bno (?:further )?action (?:is )?(?:required|needed)\b", re.I)
_REPLY_RE = re.compile(
    r"application|recruiter|thanks? (?:you )?for applying|applying to|"
    r"received your|next steps|hiring team|talent",
    re.I)
# Automated application-received acknowledgments: recorded as callbacks (type
# 'ack') but they NEVER change status  'replied' is reserved for humans.
_ACK_RE = re.compile(
    r"thanks? (?:you )?for (?:applying|your application)|"
    r"(?:we (?:have |'ve )?)?received your (?:job )?application|"
    r"application (?:has been |was )?(?:received|submitted)|"
    r"thank you for your (?:online )?submission",
    re.I)
# Does the latest inbound message ask the user for something? (feeds needs_reply)
_ASKS_RE = re.compile(
    r"\?|availability|schedule|let (?:me|us) know|please (?:reply|respond|confirm)|"
    r"when (?:are|would|can) you|share (?:a few|your) times", re.I)

# Job-board ALERT digests: never callbacks, never notes  a count in the digest.
_ALERT_SUBJECT_RE = re.compile(
    r"new job(?:s)? (?:at|opportunities|for|posted)|jobs? that match|"
    r"match(?:ed)? with a job|this job is a match|job alert|jobs? for you|"
    r"recommended (?:for you|jobs)|job recommendations|new job opportunities|"
    r"top job picks|apply now to|is hiring:", re.I)
_ALERT_LOCALS = {"notifications", "notification", "jobalerts", "jobalert",
                 "job-alerts", "jobalerts-noreply", "jobs-noreply", "alerts"}

# Promotional mail sender local-parts (marketing, not people).
_PROMO_LOCALS = {"store-news", "promotions", "promo", "offers", "newsletter",
                 "newsletters", "deals", "marketing", "hello", "news"}

# Consumer noise: hard excludes that must never reach matching.
_NOISE_SUBJECT_RE = re.compile(
    r"your .{1,30}? (?:trip|ride|stay)\b|trip with uber|ride receipt|trip receipt|"
    r"transaction alert|payment (?:posted|due|received)|pay statement|payslip|"
    r"payroll|direct deposit|account statement|statement is (?:ready|available)|"
    r"remittance|money transfer|survey|credit card|debit card|your receipt|"
    r"here.?s your .{0,30}receipt", re.I)
_BANK_DOMAINS = ("chase.com",)
_BANK_NOISE_RE = re.compile(r"transaction|credit card|account|payment|balance", re.I)

# Company names that are common English words: match only on sender/subject
# evidence, never body-only. (Names under 5 normalized chars get the same rule.)
_COMMON_WORD_NAMES = {
    "driver", "current", "until", "uber", "chase", "target", "square", "block",
    "forward", "level", "first", "factor", "mind", "scale", "light", "prime",
}
# Meeting-platform vendors: interview invites from ANY company carry "join via
# Microsoft Teams" / "Google Meet" / "Zoom" links, so a body mention of these
# names is meaningless as company evidence  sender/subject only.
_MEETING_PLATFORM_NAMES = {"microsoft", "google", "zoom", "webex", "cisco"}

# classification -> tracker status. 'ack' is deliberately absent: an automated
# acknowledgment is recorded as a callback but never moves the status.
_STATUS_FOR = {
    "rejected": "rejected", "interview": "interview", "oa": "oa",
    "offer": "offer", "recruiter_reply": "replied",
}
# classification -> callbacks[].type (everything that gets a callback record)
_CB_TYPE = dict(_STATUS_FOR, ack="ack")

# No-downgrade ordering. A new status is written only when it ranks strictly
# higher than the row's current status; 'offer' rows are never touched at all.
_CALLBACK_RANK = {
    "found": 0, "skipped": 0, "scored": 0, "tailored": 0, "ready_to_submit": 0,
    "applied": 1, "replied": 2, "oa": 3, "interview": 4, "rejected": 5,
    "offer": 6,
}

_BODY_CAP = 8000        # chars of body considered for matching/classification
_MAX_NOTES_PER_ROW = 3  # note/callback appends per row per run (newest first)


# ------------------------------------------------------------------ helpers

def _strip_html(raw: str) -> str:
    """HTML -> readable text with a few regexes (no bs4)."""
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|tr|li|h[1-6])>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def _decode_header(value: str) -> str:
    if not value:
        return ""
    parts = []
    for chunk, charset in email.header.decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts).strip()


def _extract_body(msg: email.message.Message) -> str:
    """Plain-text body; falls back to stripped HTML. Handles multipart."""
    plain, htmlish = None, None
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        if "attachment" in str(part.get("Content-Disposition", "")).lower():
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            payload = str(part.get_payload()).encode("utf-8", "replace")
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="replace")
        except LookupError:
            text = payload.decode("utf-8", errors="replace")
        if ctype == "text/plain" and plain is None:
            plain = text
        elif ctype == "text/html" and htmlish is None:
            htmlish = text
    if plain and plain.strip():
        return plain.strip()
    if htmlish:
        return _strip_html(htmlish)
    return ""


def _parse_dtstart(value: str) -> str:
    """ICS DTSTART value -> ISO string. '20260825T170000Z' -> '2026-08-25T17:00Z',
    '20260825' -> '2026-08-25'. Empty string when unparseable."""
    v = (value or "").strip()
    m = re.match(r"(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(?:\d{2})?(Z?))?$", v)
    if not m:
        return ""
    y, mo, d, hh, mm, z = m.groups()
    if hh is None:
        return f"{y}-{mo}-{d}"
    return f"{y}-{mo}-{d}T{hh}:{mm}{z or ''}"


def _extract_calendar(msg: email.message.Message) -> dict | None:
    """text/calendar (.ics) part -> {summary, organizer, dtstart, cancelled,
    text}. Properties are read from the VEVENT block ONLY  a VTIMEZONE block
    carries its own DTSTART (e.g. 19700308T020000, the DST rule) which must
    never be mistaken for the meeting time."""
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_type() != "text/calendar":
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            payload = str(part.get_payload()).encode("utf-8", "replace")
        raw = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        raw = re.sub(r"\r?\n[ \t]", "", raw)  # unfold folded ICS lines
        m = re.search(r"BEGIN:VEVENT(.*?)END:VEVENT", raw, re.S | re.I)
        if not m:
            continue
        block = m.group(1)

        def _line(name):
            mm = re.search(rf"^{name}[^:\n]*:(.+)$", block, re.M | re.I)
            return mm.group(1).strip() if mm else ""

        summary, organizer = _line("SUMMARY"), _line("ORGANIZER")
        dtstart = _parse_dtstart(_line("DTSTART"))
        cancelled = bool(re.search(r"METHOD[^:\n]*:CANCEL", raw, re.I)
                         or re.search(r"^STATUS[^:\n]*:CANCELLED", block, re.M | re.I))
        text = " ".join(x for x in (
            f"Calendar invite: {summary}" if summary else "Calendar invite",
            f"organizer {organizer}" if organizer else "",
            f"starts {dtstart}" if dtstart else "") if x)
        return {"summary": summary, "organizer": organizer, "dtstart": dtstart,
                "cancelled": cancelled, "text": text}
    return None


_VEVENT_INTERVIEWISH_RE = re.compile(
    r"interview|phone screen|screen|call|chat|meeting|conversation|intro", re.I)


def _valid_interview_vevent(cal: dict | None, subject: str, email_date: str) -> bool:
    """A VEVENT counts as interview evidence only when it is not a cancellation,
    looks like an interview (summary/subject), and its DTSTART is not in the
    past relative to the email date (stale/bogus DTSTARTs must never classify
    or float a lane row)."""
    if not cal or cal.get("cancelled"):
        return False
    if not _VEVENT_INTERVIEWISH_RE.search(f"{cal.get('summary', '')} {subject}"):
        return False
    ds = (cal.get("dtstart") or "")[:10]
    if ds and email_date:
        try:
            if date_cls.fromisoformat(ds) < date_cls.fromisoformat(email_date) \
                    - timedelta(days=1):
                return False
        except ValueError:
            return False
    return True


def parse_message(msg: email.message.Message, account: str = "") -> dict:
    """Flatten one email.message.Message into the dict the rest of this module uses."""
    name, addr = email.utils.parseaddr(msg.get("From", ""))
    addr = addr.lower()
    date_iso, ts = "", 0.0
    try:
        dt = email.utils.parsedate_to_datetime(msg.get("Date", ""))
        if dt is not None:
            date_iso = dt.date().isoformat()
            ts = dt.timestamp()
    except (TypeError, ValueError):
        pass
    subject = _decode_header(msg.get("Subject", ""))
    message_id = (msg.get("Message-ID") or "").strip()
    if not message_id:  # synthesize a stable key so seen-tracking still works
        message_id = f"<synthetic-{hash((addr, subject, date_iso))}>"
    local = addr.split("@")[0] if "@" in addr else ""
    body = _extract_body(msg)
    cal = _extract_calendar(msg)
    # A VEVENT only counts when it is a live, interview-looking event with a
    # sane (non-past) DTSTART; cancellations / DST-rule artifacts are ignored.
    if not _valid_interview_vevent(cal, subject, date_iso):
        cal = None
    if cal:  # calendar text joins the body so filtering/classification see it
        body = f"{body}\n{cal['text']}".strip()
    return {
        "message_id": message_id,
        "account": account,
        "sender_name": _decode_header(name),
        "sender_email": addr,
        "sender_domain": addr.split("@")[-1] if "@" in addr else "",
        "sender_local": local,
        "subject": subject,
        "date": date_iso,
        "_ts": ts,
        "body": body[:_BODY_CAP],
        "references": str(msg.get("References") or ""),
        "in_reply_to": str(msg.get("In-Reply-To") or ""),
        "list_unsubscribe": bool(msg.get("List-Unsubscribe")),
        "vevent": bool(cal),
        "dtstart": (cal or {}).get("dtstart", ""),
        "vevent_summary": (cal or {}).get("summary", ""),
    }


def bare_msgid(message_id: str) -> str:
    """RFC-822 Message-ID without the surrounding angle brackets."""
    return (message_id or "").strip().strip("<>").strip()


def gmail_link(message_id: str, account: str) -> str:
    """Deep link that opens this exact email in the right logged-in Gmail
    account: authuser=<address> routes by address, not by tab order."""
    mid = quote(bare_msgid(message_id), safe="")
    return (f"https://mail.google.com/mail/?authuser={quote(account, safe='')}"
            f"#search/rfc822msgid:{mid}")


def _snippet(body: str, cap: int = 140) -> str:
    return " ".join((body or "").split())[:cap]


def _norm_company(name: str) -> str:
    """Same normalization as tracker dedupe: lowercase, strip punctuation and
    corporate suffixes, collapse whitespace."""
    c = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    c = re.sub(r"\b(inc|llc|corp|co|ltd|systems|labs|technologies)\b", "", c)
    return " ".join(c.split())


def _norm_text(text: str) -> str:
    """Normalize a haystack the same way company names are normalized, so
    'Jack & Jill, Inc.' in a body matches the tracker's 'Jack & Jill'."""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).split())


def _contains(haystack_norm: str, needle_norm: str) -> bool:
    return needle_norm != "" and f" {needle_norm} " in f" {haystack_norm} "


def _ats_sender(parsed: dict) -> bool:
    domain = parsed["sender_domain"]
    return any(domain == d or domain.endswith("." + d) for d in ATS_DOMAINS)


def has_job_context(parsed: dict) -> bool:
    """Gate (a) for ROW ATTACH: ATS/recruiting sender, or application-context
    language anywhere in the email."""
    if _ats_sender(parsed):
        return True
    return bool(_APP_CONTEXT_RE.search(f"{parsed['subject']}\n{parsed['body']}"))


# ------------------------------------------------------------------ prune tiers

def is_consumer_noise(parsed: dict) -> bool:
    """Hard excludes: ride receipts, bank transaction alerts, store ads, pay
    statements. These must never reach matching, whatever companies are tracked."""
    if parsed["sender_local"] == "store-news":       # store-news@amazon.com etc.
        return True
    if _NOISE_SUBJECT_RE.search(parsed["subject"]):
        return True
    domain = parsed["sender_domain"]
    if any(domain == d or domain.endswith("." + d) for d in _BANK_DOMAINS) \
            and _BANK_NOISE_RE.search(f"{parsed['subject']} {parsed['body'][:500]}"):
        return True
    return False


def is_alert(parsed: dict) -> bool:
    """Job-board alert digests: jobs you COULD apply to, not callbacks."""
    if _ALERT_SUBJECT_RE.search(parsed["subject"]):
        return True
    if parsed["sender_local"] in _ALERT_LOCALS and "job" in \
            f"{parsed['subject']} {parsed['body'][:300]}".lower():
        return True
    domain = parsed["sender_domain"]
    if (domain == "linkedin.com" or domain.endswith(".linkedin.com")) \
            and _ALERT_SUBJECT_RE.search(parsed["body"][:500]):
        return True
    return False


def is_promo(parsed: dict) -> bool:
    """Promotional/marketing mail. ATS senders are exempt, and so is anything
    whose SUBJECT carries application context (real callbacks are often sent
    through marketing infrastructure that adds List-Unsubscribe), and so are
    calendar invites."""
    if _ats_sender(parsed) or parsed.get("vevent"):
        return False
    local = parsed["sender_local"]
    promo_local = local in _PROMO_LOCALS or any(
        t in local for t in ("promo", "newsletter", "marketing", "offers", "deals"))
    if promo_local:  # a promo mailbox is promotional whatever the subject says
        return True
    if _APP_CONTEXT_RE.search(parsed["subject"]):
        return False
    return parsed["list_unsubscribe"]


# ------------------------------------------------------------------ stage 1

def broad_capture(parsed: dict, company_norms: list[str]) -> bool:
    """Stage 1: is this email even possibly about a job application? Broad on
    purpose  stage 2 prunes, and the digest counts every pruned tier."""
    if _ats_sender(parsed):
        return True
    subject = parsed["subject"].lower()
    if any(kw in subject for kw in SUBJECT_KEYWORDS):
        return True
    if parsed.get("vevent") and has_job_context(parsed):
        return True
    # Sender domain belongs to a tracked company (recruiter@apple.com).
    if any(_domain_match(parsed, c) for c in company_norms):
        return True
    # Human sender on a corporate (non-freemail) domain talking about an
    # application  the highest-value class: direct recruiter mail.
    domain = parsed["sender_domain"]
    if domain and domain not in _FREEMAIL and has_job_context(parsed):
        return True
    # Company mentioned anywhere with job context (Ashby-style body mentions).
    return has_job_context(parsed) and \
        any(_company_match(parsed, c) for c in company_norms)


# Back-compat alias (older name for the stage-1 gate).
prefilter = broad_capture


# ------------------------------------------------------------------ classify

def classify(parsed: dict) -> str:
    """Deterministic classification. Precedence: rejected > offer > VEVENT ->
    interview > oa > ack > interview > recruiter_reply. 'ambiguous' when nothing
    matches. Only ever meaningful on captured, pruned, job-context mail."""
    subject = parsed["subject"]
    text = f"{subject}\n{parsed['body']}"
    if _REJECT_RE.search(text):
        return "rejected"
    if _OFFER_RE.search(text):
        return "offer"
    if parsed.get("vevent"):        # a validated interview VEVENT IS the interview
        return "interview"
    # Ack-pattern subjects ("Thank you for applying...", "Application Received")
    # can NEVER rise above ack on boilerplate body words alone ("if selected for
    # an interview we will..."): they need actionable OA or strict scheduling
    # evidence to be anything more.
    if _ACK_SUBJECT_RE.search(subject) or _ack_company(subject):
        if _OA_STRICT_RE.search(text) and not _NO_ACTION_RE.search(text):
            return "oa"
        if _SUBJ_INTERVIEW_RE.search(subject) or _SCHED_STRICT_RE.search(text):
            return "interview"
        return "ack"
    if _OA_RE.search(text):
        return "oa"
    if _ACK_RE.search(text) and not _SCHED_BROAD_RE.search(text):
        return "ack"                # body-level ack, no scheduling anywhere
    if _SUBJ_INTERVIEW_RE.search(subject) or _SCHED_BROAD_RE.search(text):
        return "interview"
    if _REPLY_RE.search(text):
        return "recruiter_reply"
    return "ambiguous"


_BRAIN_SCHEMA = {
    "type": "object",
    "properties": {"classification": {
        "type": "string",
        "enum": ["rejected", "interview", "oa", "offer", "ack",
                 "recruiter_reply", "not_job_related"]}},
    "required": ["classification"],
}

_BRAIN_SYSTEM = (
    "You classify ONE email from a job seeker's inbox. Answer with exactly one "
    "classification: rejected (application declined), interview (invite or "
    "scheduling), oa (online assessment / take-home), offer (job offer), ack "
    "(automated application-received confirmation), recruiter_reply (a human "
    "recruiter reply that fits none of the above), or not_job_related. Be "
    "conservative: pick a callback class only when the email clearly says so.")


def _classify_with_brain(parsed: dict, brain) -> str:
    """Route one ambiguous email through the Brain seam. Any failure (no key,
    pending manual packet, bad response) degrades to 'unclassified'."""
    from ..brain import BrainPending
    user = (f"From: {parsed['sender_name']} <{parsed['sender_email']}>\n"
            f"Subject: {parsed['subject']}\nDate: {parsed['date']}\n\n"
            f"{parsed['body'][:2000]}")
    try:
        out = brain.structured("inbox_classify", system=_BRAIN_SYSTEM,
                               user=user, schema=_BRAIN_SCHEMA, max_tokens=200)
        cls = out.get("classification")
        return cls if cls in _BRAIN_SCHEMA["properties"]["classification"]["enum"] \
            else "unclassified"
    except BrainPending:
        parsed["_brain_pending"] = True
        return "unclassified"
    except Exception:
        return "unclassified"


# ------------------------------------------------------------------ matching

_ACK_SUBJECT_RES = (
    re.compile(r"thanks? (?:you )?for applying (?:to|at)\s+(.+?)\s*[!.]*\s*$", re.I),
    re.compile(r"your application (?:to|at|with|for)\s+(.+?)\s*[!.]*\s*$", re.I),
    re.compile(r"application (?:to|at|received (?:by|at))\s+(.+?)\s*[!.]*\s*$", re.I),
)


def _ack_company(subject: str) -> str:
    """'Thanks for applying to Higgsfield !' -> 'higgsfield' (normalized)."""
    for rx in _ACK_SUBJECT_RES:
        m = rx.search(subject or "")
        if m:
            return _norm_company(m.group(1))
    return ""


def _ack_matches(extracted: str, comp_norm: str) -> bool:
    """Trailing-word tolerance both ways: 'higgsfield' <-> 'higgsfield ai'."""
    if not extracted or not comp_norm:
        return False
    return (extracted == comp_norm
            or comp_norm.startswith(extracted + " ")
            or extracted.startswith(comp_norm + " "))


# Words that appear as the first token of junk tracker company names ("Careers
# at KKR") AND as generic sender local-parts (careers@twilio.com): matching on
# them attaches every recruiting email to one unrelated row. Never company
# evidence on their own.
_GENERIC_COMPANY_WORDS = {
    "careers", "career", "talent", "jobs", "job", "recruit", "recruiting",
    "recruitment", "hr", "hiring", "people", "team", "info", "contact",
    "admin", "notifications", "apply",
}


def _is_calendar_gateway(parsed: dict) -> bool:
    """calendar-notification@google.com sends OTHER companies' invites  its
    domain must never count as company evidence."""
    return parsed["sender_local"].startswith("calendar")


def _domain_match(parsed: dict, comp_norm: str) -> bool:
    if _is_calendar_gateway(parsed):
        return False
    labels = parsed["sender_domain"].split(".")
    registrable = labels[-2] if len(labels) >= 2 else (labels[0] if labels else "")
    squashed = comp_norm.replace(" ", "")
    first_word = comp_norm.split()[0] if comp_norm else ""
    if first_word in _GENERIC_COMPANY_WORDS:
        first_word = ""
    return bool(registrable) and (
        registrable == squashed or (first_word and registrable == first_word)
        or (len(squashed) >= 5 and squashed in registrable))


def _local_part_match(parsed: dict, comp_norm: str) -> bool:
    """nexstar@myworkday.com -> 'Nexstar Media Group': a sender local-part token
    equal to the company's FIRST word (5+ chars, so no-reply never matches).
    On an ATS domain the local part IS the tenant, so an exact match against the
    whole squashed company name is accepted at any length (hp@myworkday.com)."""
    if _is_calendar_gateway(parsed):
        return False
    tokens = [t for t in re.split(r"[^a-z0-9]+", parsed["sender_local"]) if t]
    squashed = comp_norm.replace(" ", "")
    if _ats_sender(parsed) and len(squashed) >= 2 and squashed in tokens:
        return True
    first_word = comp_norm.split()[0] if comp_norm else ""
    return (len(first_word) >= 5 and first_word not in _GENERIC_COMPANY_WORDS
            and first_word in tokens)


def _company_evidence(parsed: dict, comp_norm: str) -> int:
    """Gate (b): word-boundary company evidence, TIERED  2 = sender/subject
    (display name, subject, sender domain, ATS local-part, ack-subject
    extraction), 1 = body-only, 0 = none. Common-word / short names and
    meeting-platform vendors (Microsoft Teams / Google Meet / Zoom links appear
    in every interview invite) may never match on body evidence alone.
    Normalized haystacks are cached on the parsed dict  this runs once per
    tracked company per message."""
    if len(comp_norm) < 2:
        return 0
    head = parsed.get("_head_norm")
    if head is None:
        head = parsed["_head_norm"] = _norm_text(
            f"{parsed['sender_name']} {parsed['subject']}")
    if _contains(head, comp_norm):
        return 2
    if _domain_match(parsed, comp_norm):
        return 2
    if _local_part_match(parsed, comp_norm):
        return 2
    ack = parsed.get("_ack_norm")
    if ack is None:
        ack = parsed["_ack_norm"] = _ack_company(parsed["subject"])
    if _ack_matches(ack, comp_norm):
        return 2
    body_ok = (comp_norm not in _COMMON_WORD_NAMES and len(comp_norm) >= 5
               and comp_norm.split()[0] not in _MEETING_PLATFORM_NAMES)
    if body_ok:
        body = parsed.get("_body_norm")
        if body is None:
            body = parsed["_body_norm"] = _norm_text(parsed["body"])
        if _contains(body, comp_norm):
            return 1
    return 0


def _company_match(parsed: dict, comp_norm: str) -> bool:
    return _company_evidence(parsed, comp_norm) > 0


_ROLE_STOPWORDS = {"senior", "staff", "lead", "principal", "junior", "intern",
                   "internship", "2025", "2026", "engineer", "developer"}


def _role_overlap(parsed: dict, row: dict) -> int:
    """Distinguishing role-word overlap, for same-company disambiguation."""
    words = {w for w in re.split(r"[^a-z0-9]+", (row.get("role") or "").lower())
             if len(w) >= 4 and w not in _ROLE_STOPWORDS}
    if not words:
        return 0
    hay = _norm_text(f"{parsed['subject']} {parsed['body']}")
    return sum(1 for w in words if _contains(hay, w))


def match_row(parsed: dict, rows: list[dict]) -> dict | None:
    """Best tracker row for this email. Callers must have verified job context
    (has_job_context) first  that is gate (a) of the two-gate attach.
    Same-company rows are disambiguated by role-word overlap; with no role
    evidence, the most recent applied/interview row wins  never all rows."""
    candidates = []
    for row in rows:
        comp = _norm_company(row.get("company") or "")
        if not comp:
            continue
        tier = _company_evidence(parsed, comp)
        if tier:
            candidates.append((row, comp, tier))
    if not candidates:
        return None

    def _key(item):
        row, comp, tier = item
        active = 0 if row.get("status") in ("applied", "interview") else 1
        # Sender/subject evidence ALWAYS beats a body-only mention  a rejection
        # titled "your interest in Microsoft" must never attach to some other
        # row whose name merely appears in the footer.
        return (-tier, -len(comp), -_role_overlap(parsed, row), active,
                _neg_date(row.get("date") or ""))

    return min(candidates, key=_key)[0]


def _neg_date(stamp: str) -> tuple:
    # Most recent first: dates are "YYYY-MM-DD[ HH:MM]" so lexicographic works;
    # invert by negating each character code (cheap, avoids parsing).
    return tuple(-ord(ch) for ch in stamp)


# ------------------------------------------------------------------ threads

def _norm_subject(subject: str) -> str:
    s = re.sub(r"(?i)^\s*(?:(?:re|fwd?|fw)\s*:\s*)+", "", subject or "")
    return " ".join(s.lower().split())


def group_threads(candidates: list[dict]) -> list[list[dict]]:
    """Group by References / In-Reply-To chains, falling back to normalized
    subject (Re:/Fwd: stripped). Threads never span accounts. Returns threads
    newest-latest-message first; each thread oldest-to-newest inside."""
    key_of: dict = {}
    groups: dict = {}
    order: list = []
    for idx, p in enumerate(candidates):
        refs = re.findall(r"<[^<>]+>", f"{p['references']} {p['in_reply_to']}")
        aliases = [(p["account"], p["message_id"])] + [(p["account"], r) for r in refs]
        aliases.append((p["account"], "s:" + _norm_subject(p["subject"])))
        key = next((key_of[a] for a in aliases if a in key_of), None)
        if key is None:
            key = len(order)
            order.append(key)
            groups[key] = []
        groups[key].append(p)
        p["_idx"] = idx
        for a in aliases:
            key_of[a] = key
    threads = []
    for key in order:
        # oldest -> newest (candidates arrive newest-first, so higher idx = older)
        threads.append(sorted(groups[key], key=lambda p: (p["_ts"], -p["_idx"])))
    threads.sort(key=lambda t: t[-1]["_ts"], reverse=True)  # newest threads first
    return threads


# ------------------------------------------------------------------ seen file

def _seen_key(account: str, message_id: str) -> str:
    return f"{account}|{message_id}"


def _load_seen() -> set[str]:
    if SEEN_PATH.exists():
        try:
            return set(json.loads(SEEN_PATH.read_text()))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def _save_seen(seen: set[str]) -> None:
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(json.dumps(sorted(seen), indent=1))


# ------------------------------------------------------------------ accounts

def accounts() -> list[dict]:
    """All configured mail accounts. Account 1 uses the base env names; account
    N >= 2 uses the _N suffix (host suffix optional, same imap.gmail.com default)."""
    out = []
    n = 1
    while True:
        suffix = "" if n == 1 else f"_{n}"
        addr = config.setting(f"email{suffix}")
        pwd = config.setting(f"email_app_password{suffix}")
        if not (addr and pwd):
            break  # numbering is contiguous: stop at the first gap
        host = str(config.setting(f"imap_host{suffix}", "imap.gmail.com"))
        # Google renders App Passwords with spaces ("abcd efgh ...")  strip ALL
        # whitespace so a copy-paste with spaces still authenticates. The value
        # is never logged or printed anywhere in this module.
        out.append({"email": str(addr),
                    "password": re.sub(r"\s+", "", str(pwd)), "host": host})
        n += 1
    return out


def default_days() -> int:
    """Look-back default: config/settings.json {"inbox": {"days": N}}, else 14.
    Rhythm: one --days 90 backfill, then short daily runs (the seen-file makes
    every later run incremental)."""
    try:
        return int((config._settings().get("inbox") or {}).get("days", 14))
    except (TypeError, ValueError):
        return 14


# ------------------------------------------------------------------ IMAP fetch

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _imap_since(days: int) -> str:
    d = datetime.now() - timedelta(days=days)
    return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}"  # locale-proof


_IMAP_TIMEOUT = 60   # seconds; a dead connection must fail loudly, never hang
_FETCH_CHUNK = 100   # message ids per FETCH round-trip


def _connect(account: dict) -> imaplib.IMAP4_SSL:
    conn = imaplib.IMAP4_SSL(account["host"], timeout=_IMAP_TIMEOUT)
    conn.login(account["email"], account["password"])
    return conn


def _select_readonly(conn, mailbox: str) -> bool:
    try:
        typ, _ = conn.select(mailbox, readonly=True)
        return typ == "OK"
    except imaplib.IMAP4.error:
        return False


def fetch_messages(days: int, limit: int, account: dict,
                   conn=None) -> tuple[list[email.message.Message], int]:
    """One account's mail SINCE N days ago, newest first, capped at `limit`.
    Returns (messages, total_matching) so callers can warn about truncation.
    Searches "[Gmail]/All Mail" (Gmail tabs/filters hide job mail from INBOX),
    falling back to INBOX on non-Gmail servers. Every FETCH uses BODY.PEEK so
    the user's mail is NEVER marked read."""
    msgs: list[email.message.Message] = []
    own = conn is None
    if own:
        conn = _connect(account)
    try:
        if not _select_readonly(conn, '"[Gmail]/All Mail"'):
            if not _select_readonly(conn, "INBOX"):
                return [], 0
        typ, data = conn.search(None, "SINCE", _imap_since(days))
        if typ != "OK" or not data or not data[0]:
            return [], 0
        all_ids = data[0].split()
        ids = all_ids[-limit:][::-1]  # newest first
        # Chunked FETCH: one round-trip per _FETCH_CHUNK ids instead of one per
        # message, with visible progress so a stall is never silent.
        for i in range(0, len(ids), _FETCH_CHUNK):
            chunk = ids[i:i + _FETCH_CHUNK]
            typ, payload = conn.fetch(b",".join(chunk).decode(), "(BODY.PEEK[])")
            if typ == "OK" and payload:
                for item in payload:
                    if isinstance(item, tuple) and item[1]:
                        msgs.append(email.message_from_bytes(item[1]))
            print(f"  {account['email']}: fetched {min(i + _FETCH_CHUNK, len(ids))}"
                  f"/{len(ids)}", file=sys.stderr, flush=True)
        return msgs, len(all_ids)
    finally:
        if own:
            try:
                conn.logout()
            except Exception:
                pass


# ------------------------------------------------------------------ sent check

def _make_sent_checker(accounts_by_email: dict):
    """Returns check(latest, thread) -> True (user replied after the latest
    inbound), False (no reply found), or None (could not check). Headers-only,
    BODY.PEEK, one connection per account, opened lazily."""
    conns: dict = {}

    def _sent_conn(acct_email):
        if acct_email in conns:
            return conns[acct_email]
        acct = accounts_by_email.get(acct_email)
        conn = None
        if acct is not None:
            try:
                c = _connect(acct)
                if _select_readonly(c, '"[Gmail]/Sent Mail"') or \
                        _select_readonly(c, "Sent"):
                    conn = c
            except (imaplib.IMAP4.error, OSError):
                conn = None
        conns[acct_email] = conn
        return conn

    def check(latest: dict, thread: list[dict]):
        conn = _sent_conn(latest["account"])
        if conn is None:
            return None
        thread_ids = {p["message_id"] for p in thread}
        for p in thread:
            thread_ids.update(re.findall(r"<[^<>]+>",
                                         f"{p['references']} {p['in_reply_to']}"))
        subj = _norm_subject(latest["subject"])
        try:
            since = (datetime.fromtimestamp(latest["_ts"]) if latest["_ts"]
                     else datetime.now() - timedelta(days=30))
            since_str = f"{since.day:02d}-{_MONTHS[since.month - 1]}-{since.year}"
            typ, data = conn.search(None, "SINCE", since_str)
            if typ != "OK" or not data or not data[0]:
                return False
            for mid in data[0].split()[-200:]:
                typ, payload = conn.fetch(
                    mid, "(BODY.PEEK[HEADER.FIELDS "
                         "(REFERENCES IN-REPLY-TO SUBJECT DATE)])")
                if typ != "OK" or not payload or not payload[0] \
                        or not isinstance(payload[0], tuple):
                    continue
                hdr = email.message_from_bytes(payload[0][1])
                try:
                    hdt = email.utils.parsedate_to_datetime(hdr.get("Date", ""))
                    hts = hdt.timestamp() if hdt else 0
                except (TypeError, ValueError):
                    hts = 0
                if hts <= latest["_ts"]:
                    continue
                refs = set(re.findall(r"<[^<>]+>",
                                      f"{hdr.get('References', '')} "
                                      f"{hdr.get('In-Reply-To', '')}"))
                if refs & thread_ids:
                    return True
                if subj and _norm_subject(_decode_header(hdr.get("Subject", ""))) == subj:
                    return True
            return False
        except (imaplib.IMAP4.error, OSError):
            return None

    check._conns = conns  # exposed for cleanup
    return check


def _close_checker(check) -> None:
    for conn in getattr(check, "_conns", {}).values():
        if conn is not None:
            try:
                conn.logout()
            except Exception:
                pass


_SETUP_HELP = """\
Inbox is not configured yet. One-time setup (works for personal Gmail AND ASU Gmail):

  1. Create a Google App Password (requires 2-Step Verification):
     Google Account -> Security -> 2-Step Verification -> App passwords
     (direct link: https://myaccount.google.com/apppasswords)
     Name it "job-applier" and copy the 16-character password.
  2. Add these lines to the repo's .env file (it stays gitignored):
     JOB_AGENT_EMAIL=you@example.com
     JOB_AGENT_EMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx
     JOB_AGENT_IMAP_HOST=imap.gmail.com        # optional, this is the default
     A second account (e.g. ASU Gmail) uses numbered suffixes; repeat steps 1-2
     in that account:
     JOB_AGENT_EMAIL_2=you@asu.edu
     JOB_AGENT_EMAIL_APP_PASSWORD_2=xxxxxxxxxxxxxxxx
     JOB_AGENT_IMAP_HOST_2=imap.gmail.com      # optional
     (and _3, _4, ... for more accounts)
  3. Backfill once with `python -m src.cli inbox --days 90`, then run short
     daily sweeps (the seen-file makes them incremental).

Note: use the App Password, never your real account password. For ASU Gmail the
host is still imap.gmail.com; if IMAP is disabled, enable it in Gmail Settings ->
Forwarding and POP/IMAP."""


# ------------------------------------------------------------------ tracker update

def _derive_status_from_callbacks(cbs: list[dict], current: str) -> str:
    """Recompute a callback-tier status from the callback set (highest rank
    wins; acks carry no status). A row must never keep a stale 'interview'
    status when no interview callback supports it any more."""
    if current not in ("replied", "oa", "interview", "rejected"):
        return current  # applied/found/etc. and frozen 'offer' are left alone
    ranks = [_CALLBACK_RANK[c.get("type")] for c in cbs
             if c.get("type") in _CALLBACK_RANK and c.get("type") != "ack"]
    if not ranks:
        return "applied"
    best = max(ranks)
    return next(s for s, r in _CALLBACK_RANK.items() if r == best)


def _apply_update(row: dict, cls: str, parsed: dict, dry_run: bool, *,
                  note_budget: dict, n_msgs: int = 1,
                  needs_reply: bool | None = None,
                  reprocess: bool = False,
                  thread_mids: list[str] | None = None) -> tuple[str, str]:
    """Write one thread's outcome onto its tracker row. Returns (old, new)
    status. Re-loads fresh tracker state under the file lock right before
    writing (so a concurrent dashboard-server write is never clobbered), writes
    atomically, dedupes callbacks by Message-ID across accounts (forwarding
    preserves Message-ID  the first-processed record wins), caps note appends,
    and never changes status for 'ack' or for mail older than applied_date."""
    target = _STATUS_FOR.get(cls)  # None for 'ack'

    def _transition(cur: str) -> str:
        if cur == "offer" or target is None:
            return cur
        stale = bool(parsed["date"] and (row.get("applied_date") or "")[:10]
                     and parsed["date"] < (row.get("applied_date") or "")[:10])
        if not stale and _CALLBACK_RANK.get(target, -1) > _CALLBACK_RANK.get(cur, 0):
            return target
        return cur

    old = row.get("status") or "found"
    if dry_run or not row.get("url"):
        return old, _transition(old)

    mid = bare_msgid(parsed["message_id"])
    with tracker._db_lock():
        db = tracker._load_applications()
        fresh = tracker._find_by_url(db["applications"], row["url"])
        if fresh is None:  # row vanished mid-run; nothing safe to write
            return old, old
        old = fresh.get("status") or "found"
        if old == "offer":  # frozen: never touched in any way
            return old, old
        new = _transition(old)
        changed = False
        if new != old:
            fresh["status"] = new
            changed = True
        existing_cbs = list(fresh.get("callbacks") or [])
        if reprocess and thread_mids:
            # A thread is ONE callback: incremental runs saw reminders alone and
            # appended one record each, so on reprocess collapse every record
            # from this thread's OTHER messages into the single kept record.
            others = {bare_msgid(m) for m in thread_mids} - {mid}
            kept = [cb for cb in existing_cbs
                    if bare_msgid(cb.get("msgid", "")) not in others]
            if len(kept) != len(existing_cbs):
                existing_cbs = kept
                fresh["callbacks"] = existing_cbs
                changed = True
        dup_idx = next((i for i, cb in enumerate(existing_cbs)
                        if bare_msgid(cb.get("msgid", "")) == mid), None)
        cb = {
            "date": parsed["date"] or datetime.now().date().isoformat(),
            "type": _CB_TYPE[cls],
            "subject": parsed["subject"][:80],
            "snippet": _snippet(parsed["body"]),
            "msgid": mid,
            "link": gmail_link(parsed["message_id"], parsed.get("account", "")),
            "account": parsed.get("account", "") or
            (existing_cbs[dup_idx].get("account", "") if dup_idx is not None else ""),
        }
        if n_msgs > 1:
            cb["messages"] = n_msgs
        if parsed.get("dtstart"):
            cb["dtstart"] = parsed["dtstart"]
        if parsed.get("vevent_summary"):
            cb["summary"] = parsed["vevent_summary"][:80]
        if needs_reply is not None:
            cb["needs_reply"] = bool(needs_reply)
        row_key = row.get("url")
        if dup_idx is not None and reprocess:
            # Reprocess: REPLACE the stored record for this message in place
            # (corrects type/subject/dtstart), never a duplicate; fix the note.
            old_cb = existing_cbs[dup_idx]
            existing_cbs[dup_idx] = cb
            fresh["callbacks"] = existing_cbs
            notes = fresh.get("notes") or ""
            pat = (rf"email {re.escape(old_cb.get('date', ''))}: \w+ - "
                   rf"{re.escape(old_cb.get('subject', '')[:60])}")
            fixed = re.sub(pat, f"email {cb['date']}: {cls} - "
                                f"{parsed['subject'][:60]}", notes, count=1)
            if fixed != notes:
                fresh["notes"] = fixed
            changed = True
        elif dup_idx is None and note_budget.get(row_key, 0) < _MAX_NOTES_PER_ROW:
            note_budget[row_key] = note_budget.get(row_key, 0) + 1
            note = f"email {parsed['date']}: {cls} - {parsed['subject'][:60]}"
            notes = (fresh.get("notes") or "").strip()
            fresh["notes"] = f"{notes}; {note}" if notes else note
            if not fresh.get("callback_date"):
                fresh["callback_date"] = parsed["date"] or \
                    datetime.now().date().isoformat()
            fresh["callbacks"] = existing_cbs + [cb]
            changed = True
        if reprocess:
            # Statuses set by earlier (possibly wrong) classifications must be
            # re-derived from the corrected callback set: highest rank wins,
            # ack-only rows fall back to 'applied'.
            derived = _derive_status_from_callbacks(
                fresh.get("callbacks") or [], fresh.get("status") or "found")
            if derived != fresh.get("status"):
                fresh["status"] = derived
                new = derived
                changed = True
        if changed:
            tracker._save_db(db)
        # mirror the fresh values onto the in-memory row for later threads
        for k in ("status", "notes", "callbacks", "callback_date"):
            if k in fresh:
                row[k] = fresh[k]
    return old, new


# ------------------------------------------------------------------ main flow

def run_inbox(days: int | None = None, dry_run: bool = False, limit: int = 200,
              messages: list | None = None, brain=None,
              sent_checker=None, reprocess: bool = False) -> dict:
    """The whole inbox pass over every configured account.

    `messages` is injectable for tests (no network): a list of
    email.message.Message, or of (account_email, Message) tuples.
    `sent_checker(latest, thread)` -> True/False/None is injectable too."""
    if days is None:
        days = default_days()
    account_errors: list[str] = []
    truncated: list[str] = []
    own_checker = False
    if messages is None:
        accts = accounts()
        if not accts:
            print(_SETUP_HELP)
            return {"ok": False, "reason": "not_configured"}
        tagged: list[tuple[str, email.message.Message]] = []
        for acct in accts:
            try:
                msgs, total = fetch_messages(days, limit, acct)
                for m in msgs:
                    tagged.append((acct["email"], m))
                if total > len(msgs):
                    truncated.append(
                        f"{acct['email']}: {total} messages in the {days}-day "
                        f"window, processed newest {len(msgs)} (raise --limit "
                        f"for a full sweep)")
            except (imaplib.IMAP4.error, OSError) as e:
                account_errors.append(f"{acct['email']}: {e}")
        if sent_checker is None:
            sent_checker = _make_sent_checker({a["email"]: a for a in accts})
            own_checker = True
    else:
        default_acct = str(config.setting("email") or "")
        tagged = [m if isinstance(m, tuple) else (default_acct, m)
                  for m in messages][:limit]

    rows = tracker.list_applications()
    company_norms = sorted({_norm_company(r.get("company") or "") for r in rows
                            if _norm_company(r.get("company") or "")})
    seen = _load_seen()

    groups: dict[str, list[dict]] = {}
    unmatched: list[dict] = []
    newly_seen: set[str] = set()
    candidates: list[dict] = []
    skipped_seen = filtered_out = noise = alerts = promos = 0

    for acct_email, msg in tagged:
        parsed = parse_message(msg, account=acct_email)
        key = _seen_key(acct_email, parsed["message_id"])
        if not reprocess and (key in seen or parsed["message_id"] in seen):
            skipped_seen += 1   # legacy un-keyed entries also count as seen
            continue
        parsed["_seen_key"] = key
        # Prune tiers run FIRST and are each counted, so every drop is
        # debuggable in the digest (broad-then-prune, never silently tight).
        if is_consumer_noise(parsed):
            noise += 1
            newly_seen.add(key)
            continue
        if is_alert(parsed):
            alerts += 1
            newly_seen.add(key)
            continue
        if is_promo(parsed):
            promos += 1
            newly_seen.add(key)
            continue
        # Stage 1 broad capture: everything else that is possibly job mail.
        if not broad_capture(parsed, company_norms):
            filtered_out += 1
            continue
        candidates.append(parsed)

    note_budget: dict[str, int] = {}
    try:
        for thread in group_threads(candidates):
            latest = thread[-1]
            cls = classify(latest)
            if cls == "ambiguous":
                cls = _classify_with_brain(latest, brain) \
                    if (brain and not dry_run) else "unclassified"
            if cls == "not_job_related":
                for p in thread:
                    newly_seen.add(p["_seen_key"])
                continue

            # needs_reply: only for classes where a human may be waiting, only
            # when the latest inbound actually asks for something.
            needs_reply = None
            if cls in ("interview", "recruiter_reply") and sent_checker is not None \
                    and _ASKS_RE.search(f"{latest['subject']}\n{latest['body']}"):
                replied = sent_checker(latest, thread)
                if replied is not None:
                    needs_reply = not replied

            # Gate (a) for row attach; match latest first, then earlier messages
            # (an ack naming the company may sit earlier than a bare reply).
            row = None
            for p in reversed(thread):
                if has_job_context(p):
                    row = match_row(p, rows)
                    if row is not None:
                        break
            entry = {"subject": latest["subject"], "date": latest["date"],
                     "sender": latest["sender_email"], "classification": cls,
                     "account": latest["account"]}
            if len(thread) > 1:
                entry["messages"] = len(thread)
            if needs_reply:
                entry["needs_reply"] = True
            if row is None:
                unmatched.append(entry)
            elif cls in _CB_TYPE:
                old, new = _apply_update(row, cls, latest, dry_run,
                                         note_budget=note_budget,
                                         n_msgs=len(thread),
                                         needs_reply=needs_reply,
                                         reprocess=reprocess,
                                         thread_mids=[p["message_id"]
                                                      for p in thread])
                entry.update({"company": row.get("company"),
                              "role": row.get("role"), "old": old, "new": new})
                groups.setdefault(cls, []).append(entry)
            else:
                # Matched but no callback pattern: report only, never touch the row.
                entry.update({"company": row.get("company"),
                              "role": row.get("role"),
                              "old": row.get("status"), "new": row.get("status")})
                groups.setdefault(cls, []).append(entry)
            if not latest.get("_brain_pending"):
                for p in thread:
                    newly_seen.add(p["_seen_key"])
    finally:
        if own_checker:
            _close_checker(sent_checker)

    if not dry_run and newly_seen:
        _save_seen(seen | newly_seen)

    # Interviews among the unmatched are the most important lines in the digest.
    _prio = {"offer": 0, "interview": 1, "oa": 2, "rejected": 3,
             "recruiter_reply": 4, "ack": 5, "unclassified": 6}
    unmatched.sort(key=lambda e: _prio.get(e["classification"], 9))

    counts = {"scanned": len(tagged), "skipped_seen": skipped_seen,
              "filtered_out": filtered_out, "noise": noise,
              "alerts": alerts, "promos": promos}
    _print_digest(groups, unmatched, dry_run=dry_run, counts=counts,
                  account_errors=account_errors, truncated=truncated)
    return {"ok": True, "groups": groups, "unmatched": unmatched,
            "account_errors": account_errors, "truncated": truncated, **counts}


_ORDER = ("offer", "interview", "oa", "rejected", "recruiter_reply", "ack",
          "unclassified")
_TITLES = {"offer": "OFFERS", "interview": "INTERVIEWS", "oa": "ONLINE ASSESSMENTS",
           "rejected": "REJECTIONS", "recruiter_reply": "RECRUITER REPLIES",
           "ack": "APPLICATION ACKS (recorded, status unchanged)",
           "unclassified": "UNCLASSIFIED (no rule matched; no row touched)"}


def _print_digest(groups, unmatched, *, dry_run, counts, account_errors=(),
                  truncated=()) -> None:
    tag = " [dry-run: nothing written]" if dry_run else ""
    total = sum(len(v) for v in groups.values())
    print(f"=== INBOX DIGEST{tag} ===")
    print(f"scanned {counts['scanned']} email(s): {counts['skipped_seen']} already "
          f"seen, {counts['filtered_out']} not job-related; pruned "
          f"{counts['noise']} consumer noise, {counts['alerts']} job alerts, "
          f"{counts['promos']} promos; {total} matched, "
          f"{len(unmatched)} unmatched\n")
    for warn in truncated:
        print(f"  ! truncated: {warn}")
    for err in account_errors:
        print(f"  ! account failed, skipped this run: {err}")
    if truncated or account_errors:
        print()
    for cls in _ORDER:
        entries = groups.get(cls)
        if not entries:
            continue
        print(f"--- {_TITLES[cls]} ({len(entries)}) ---")
        for e in entries:
            move = f"{e['old']} -> {e['new']}" if e.get("old") != e.get("new") \
                else f"{e.get('old')} (note only)"
            via = f" | via {e['account']}" if e.get("account") else ""
            thr = f" | thread of {e['messages']}" if e.get("messages") else ""
            owed = " | reply owed" if e.get("needs_reply") else ""
            print(f"  {e.get('company', '?')} | {e.get('role', '?')} | {move} | "
                  f"{e['subject'][:60]} | {e['date']}{thr}{owed}{via}")
        print()
    if unmatched:
        print(f"--- UNMATCHED, possible new outreach ({len(unmatched)}) ---")
        for e in unmatched:
            via = f" | via {e['account']}" if e.get("account") else ""
            thr = f" | thread of {e['messages']}" if e.get("messages") else ""
            print(f"  [{e['classification']}] {e['sender']} | "
                  f"{e['subject'][:60]} | {e['date']}{thr}{via}")
        print()
    if not total and not unmatched:
        print("No new job-related callbacks found in this window.")
