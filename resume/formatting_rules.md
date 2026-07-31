# Resume rewriting rules

These are the rules the agent MUST follow when tailoring a resume to a specific job
description (JD). They are loaded by the `read_resume_rules` tool and enforced via the
system prompt. Order matters  work top to bottom.

## 0. Honesty (non-negotiable, overrides everything below)
Only re-order, re-word, and emphasize **true** content from the user's profile/resume.
Never invent skills, employers, titles, dates, tools, or metrics. If a metric isn't
known, rephrase to describe impact qualitatively rather than fabricating a number.

## 0a. The reviewer is a HUMAN, not just an ATS
The resume is read by HR, a hiring manager, and a Sr. SDE  not only a keyword filter.
Keyword/ATS coverage is *one* input; it does not win on its own. What wins: bullets
that describe real, sensible, impactful work and read well in a 20-second skim. Optimize
for "a senior engineer would respect this and want to interview," not for keyword count.

## 0b. Aim to get it right on the first pass (improve rules, not loop count)
The goal is that tailoring is strong enough the FIRST time that we rarely iterate. The
scorer allows at most ONE corrective re-pass. When the score is low, the fix is to make
the bullets genuinely better (more impact, tighter JD-alignment)  and, over time, to
sharpen THESE rules so first-pass quality keeps rising  not to loop many times.

## 1. Understand what the role actually demands (not the marketing)
Before touching a single bullet, read the JD like a hiring manager and separate
**signal from boilerplate**:

- **Ignore the fluff.** Lines like "Are you enthusiastic about the latest advancements
  in robotics?", mission statements, benefits, and culture copy do NOT tell you what
  to put on the resume. They contribute nothing to the match. Skip them.
- **Extract the real technical demands** from the Responsibilities + Basic/Preferred
  Qualifications: the concrete skills, tools, systems, and domain the role screens for.
- **Build the practitioner's toolkit (co-occurring tech).** Beyond the words the JD
  literally lists, enumerate the adjacent tools/techniques that someone doing this job
  well would almost certainly have touched  the things the hiring manager *assumes*
  without writing them down. Reason from the named skill to its ecosystem:
  - "ETL / data pipelines" → Kafka, S3, SQS, Airflow, Spark, dbt, Parquet, partitioning.
  - "information retrieval / search relevance" → two-tower / dual-encoder, embeddings,
    FAISS / vector DB, ANN, recommendation & ranking, learning-to-rank, BM25.
  - "field robotics deployment" → commissioning, electro-mechanical integration,
    Allen-Bradley/RSLogix PLCs, reading CAD, on-site troubleshooting, networked equipment.
  - "LLM / agents" → RAG, tool-use, evals, prompt/context engineering, guardrails.
- **Infer the expected WORK-TYPES (not just nouns).** List the kinds of work a person
  in this role is expected to have done, as activities  these become bullet *content*,
  not skills-list entries. E.g. for a data engineer: "ran a data migration", "built BI
  dashboards", "designed a schema", "owned pipeline reliability/SLAs". For the robotics
  role: "led an on-site install", "commissioned equipment", "wrote runbooks". A reviewer
  expects to *see these activities described*, so the bullets should speak to them.
- **Then filter to the truth.** Take the union (explicit + co-occurring toolkit +
  work-types) and keep ONLY what the candidate genuinely has from their real history.
  Use the survivors to (a) choose which skills to put in the Technical Skills line and
  (b) decide which true bullets to reframe so they describe the expected work-types in
  the role's language. Never add a tool or activity the candidate hasn't actually done.
- Note **must-haves vs. nice-to-haves** and the **seniority/scope** signal.

Write this target list down (internally) first. Every later step serves THIS list 
the role's true technical demands  not the JD's wording verbatim and never its fluff.
If a JD phrase carries no technical signal, it does not influence the resume.

## 2. The first two bullets must hit the exact ask
The top two bullet points of the most relevant experience MUST map directly to the
JD's top requirements from step 1  in the JD's own language. A reviewer reading only
the first two lines should immediately think "this person does the thing we need."

**This rule applies even when the job is a weak match.** For a poor-fit role, still
force the first two bullets to adhere to the job profile (using only true content) 
that is what gets the resume past the first skim. The rest of the resume can stay
closer to the candidate's strongest real work.

## 3. Keywords (ATS)
Naturally fold the JD's key terms/skills into the bullets where they are truthful for
the candidate. Match the JD's exact phrasing for tools/skills (e.g. "Kubernetes" not
"k8s" if the JD says Kubernetes). Use `ats_score` to check coverage  but never stuff
keywords or add untrue ones to raise the score.

**Fixed-core Technical Skills.** Regardless of JD, never drop these genuinely-used
skills from the Technical Skills line: Languages always includes Python, SQL, Kotlin;
ML (when an ML/ML-adjacent group is present) always includes PyTorch, TensorFlow,
scikit-learn, Koog. Append other true, JD-relevant tools (MLflow, LangGraph, XGBoost,
…) on top of that core  never in place of it, and never anything untrue.

## 4. XYZ impact rule for every bullet
Frame each bullet as **"Accomplished X, by doing Y, measured by Z."**
- X = the result/impact, Y = the action/how, Z = the metric or scope.
- Lead with the impact, not the task. "Cut p99 latency 40% by sharding the write path"
  beats "Responsible for working on database performance."

## 5. Language quality
- Plain and readable. No filler words ("responsible for", "helped with",
  "various", "successfully", "in order to").
- **Do not repeat the same adjective or verb twice** across the bullet set  vary the
  strong verbs (built, shipped, cut, scaled, owned, led, automated, designed...).
- Active voice, past tense for prior roles.

## 6. Bullet length  a FULL line, 16–28 words (NOT a fragment)
Every bullet must be a **complete, substantive sentence of ~16–28 words** that fills most
of one line  NOT a clipped phrase. This is a hard floor: a bullet under ~14 words is too
thin and MUST be expanded with the missing X/Y/Z detail.
- ✗ Too short (REJECT): "Built FAISS retrieval serving 1M users." (6 words  a fragment)
- ✗ Too short (REJECT): "ML engineer: retrieval, ranking, evaluation at scale." (not even a bullet)
- ✓ Right (~24 words): "Built an embedding-based retrieval and ranking pipeline (FAISS + NDCG) serving 1M
  users at 0.5s end-to-end latency, lifting click-through 16% via iterative offline/online evaluation."
- The Summary is **2–3 lines maximum (~30–50 words)**, not one short sentence  it should
  state role + domain + scale + a signature credential, like a real resume summary. It must
  fit in 2–3 printed lines; anything longer MUST be trimmed. No line can wrap to a 4th line.
- Keep each bullet to ONE printed line (no wrapping to 3+ lines), but USE that line  aim for the
  upper end. Preserve the concrete metrics/tech that were already in the master bullet;
  tailoring re-frames toward the JD, it does NOT shorten or strip detail.
- **Hard max: no single bullet wraps to more than 2 printed lines.** If a bullet exceeds 2 lines,
  split it or cut trailing qualifications until it fits.

## 6a. Latest experience bullets MUST match the role JD
The bullet set under the **most recent job** (top of Work Experience) must mirror the
JD's core requirements identified in step 1  these are the bullets the reviewer reads
first and weights most heavily. At least 3 of the 5 bullets must directly address the
JD's explicit must-haves using the JD's own terms. Bullets that describe work unrelated
to the JD's core demand should be moved down or replaced with JD-aligned alternatives
drawn from the candidate's true history. The first two bullets follow rule 2 (exact ask).

## 7. The skim test (final gestalt check)
A reviewer who only reads the bold headers and first lines, or skims the whole page in
~10 seconds, should come away feeling **"this is the right person for this role."**
After rewriting, re-read only the top lines and ask whether that's true. If not, fix
the first two bullets again (step 2) before finishing.

---

### Worked example
JD asks for: distributed systems, AWS, on-call ownership.

❌ Before: "Responsible for various backend services and helped improve performance."
✅ After (bullet 1, ~23w): "Scaled a distributed order service on AWS to 50k req/s, cutting p99 latency 35% through write-path sharding and read-replica caching."
✅ After (bullet 2, ~21w): "Owned on-call for 12 microservices, reducing pages 60% by introducing SLO-based alerting and automated runbooks for the top incidents."

Both top bullets hit the JD's exact asks, use its keywords, follow XYZ, vary verbs
(Scaled / Owned), avoid filler, and are FULL ~20+ word lines  never clipped fragments.
