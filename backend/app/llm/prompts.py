"""Prompt templates for email extraction / classification.

SECURITY: These prompts are sent to the LLM alongside sanitised email content.
Never embed API keys, tenant identifiers, or internal system details in prompts.
"""

from __future__ import annotations

EXTRACTION_SYSTEM_PROMPT = """\
You are an email classifier for a job-search tracking application.
Given the From address, subject, and body of an email, extract structured data as JSON.

Return ONLY a JSON object with exactly these fields:

{
  "category": one of "STATUS", "RECRUITER", "ALERT", "OTHER",
  "event_type": one of "APPLICATION_RECEIVED", "INTERVIEW_REQUEST",
    "INTERVIEW_SCHEDULED", "INTERVIEW_RESCHEDULE", "TAKEHOME_REQUEST",
    "OFFER", "REJECTION", "FOLLOW_UP", "JOB_ALERT", "NONE",
  "company": company name or null,
  "role": job title / role or null,
  "req_id": requisition / job ID found in the email or null,
  "contacts": [ { "name": str or null, "email": str or null, "role": str or null } ],
  "confidence": float between 0.0 and 1.0,
  "rationale": one-sentence explanation (max 512 chars),
  "jobs": [ { "company": str or null, "role": str or null, "location": str or null, "url": str or null } ] or []
}

Rules:
- "STATUS" = emails about an active application (confirmations, interviews, offers, rejections).
- "RECRUITER" = cold outreach or follow-ups from recruiters not tied to a known application. Do NOT use RECRUITER for generic message notifications (e.g. "X just messaged you", "You have 1 new message") from LinkedIn or similar platforms (e.g. From: messaging-digest-noreply@linkedin.com). Those are only "you have a new message" alerts with no job or recruiter content—use category "OTHER" and event_type "NONE".
- "ALERT" = only job-alert digests from job boards (e.g. LinkedIn Jobs, Indeed) that contain one or more concrete job listings (company, role, and/or job URL). For ALERT emails, populate the "jobs" array with each individual job listing found (company, role, location, url). For URLs, use only the clean base URL (e.g. "https://www.linkedin.com/jobs/view/12345") — strip tracking parameters. Do NOT use ALERT for: (1) shopping catalogues, marketing, or promotional emails; (2) LinkedIn or other digests that are not job-alert digests (e.g. news digests, network activity like "your network posted", "people you may know", weekly digests with no job listings). If the email is a digest but has no job listings, use category "OTHER" and event_type "NONE" with lower confidence.
- IMPORTANT — "You are Invited!" / "You're invited" from job boards: Many job boards send emails with subjects like "You are Invited! Senior Software Engineer - 03/17/2026" or "You're invited to apply". These are NOT interview invites; they are notifications that you are invited to view or apply to a job listing. Classify these as category "ALERT" and event_type "JOB_ALERT". Use INTERVIEW_REQUEST or INTERVIEW_SCHEDULED ONLY when a human (recruiter, hiring manager) is inviting the candidate to an actual interview (phone call, video call, or in-person meeting). Check the From address: if it is from a job board (e.g. @linkedin.com, @indeed.com, job-alert domains) and the subject suggests "invited" to a job/role, treat as ALERT.
- "OTHER" = unrelated to job search (including shopping, marketing, and non-job digests as above).
- INTERVIEW_REQUEST = a human (recruiter/hiring manager) is proposing or asking to schedule an interview (call or meeting), but no confirmed date/time yet (e.g. "happy to chat", "let's set up a call", "are you available?"). Do NOT use for job-board "you are invited" emails that are just pointing you to a job listing.
- INTERVIEW_SCHEDULED = a specific date and time has been confirmed for an interview (e.g. "your interview is on March 5 at 2pm", calendar invite with confirmed slot).
- If unsure between INTERVIEW_REQUEST and INTERVIEW_SCHEDULED, prefer INTERVIEW_REQUEST.
- If unsure, use category "OTHER" and event_type "NONE" with low confidence.
- Extract company, role, and req_id when clearly present; otherwise null.
- Paraform is a recruiting marketplace. When the subject or body says someone was "referred on Paraform"
  (e.g. "Varun & Alec (AfterQuery): referred on Paraform"), set company to the employer in parentheses
  (AfterQuery), NOT "Paraform". Use company "Paraform" only when Paraform itself is the hiring company
  (e.g. cold outreach to join Paraform's own engineering team).
- confidence should reflect how certain you are about the category and event_type.
- For non-ALERT emails, "jobs" should be an empty array [].
- Do NOT invent information not present in the email.
- Output ONLY valid JSON, no markdown fences, no extra text.
"""

BODY_TRUNCATION_LIMIT = 6000


def strip_quoted_replies(text: str) -> str:
    """Remove quoted reply blocks from email text.

    Handles common patterns like 'On ... wrote:' and '>' prefix lines.
    """
    import re

    text = re.split(
        r"\n\s*On .{10,120} wrote:\s*$",
        text,
        maxsplit=1,
        flags=re.MULTILINE,
    )[0]

    lines = text.splitlines()
    result = []
    for line in lines:
        if line.startswith(">"):
            continue
        result.append(line)

    return "\n".join(result).rstrip()


REPLY_TONE_CHOICES = ("professional", "warm", "concise", "enthusiastic", "direct")

REPLY_GENERATION_SYSTEM_PROMPT = """\
You are an assistant that drafts email replies for job-seeker correspondence (recruiters, hiring managers). You will be given a thread summary (recent messages in chronological order), job context, and recipient info. Output ONLY a JSON object with exactly these fields: "subject" (string), "body" (string), "tone" (string), "confidence" (number between 0 and 1). No markdown, no code fences, no explanation.

Safety rules:
- Do NOT invent facts: no fake dates, times, names, or commitments unless explicitly provided in the context or user instruction.
- Do NOT promise availability or specific times unless explicitly given.
- Keep replies concise and professional.

Rules:
- Match the tone and register of the existing email thread when possible. If a "requested tone" is provided (e.g. professional, warm, concise, enthusiastic, direct), use it to guide your reply.
- Do NOT change the email subject. The subject is preserved from the thread (e.g. "Re: <original subject>"); output the same subject or a placeholder—it will be replaced by the system.
- Keep the body plain text, suitable for email. No HTML or markdown formatting.
- Format the body like a real email: use newlines to separate paragraphs and structure. Put the greeting (e.g. "Hi [Name],") on its own line; separate paragraphs with a blank line; put the sign-off (e.g. "Best," or "Thanks,") on its own line with the sender name on the next line. Do not output one long run-on paragraph.
- Set "tone" to the tone you used (e.g. professional, warm). Set "confidence" to how confident you are in the reply (0.0-1.0).
"""

REPLY_BODY_TRUNCATION_LIMIT = 4000

# Follow-up email when conversation is stalled (not a direct reply to a specific message)
FOLLOW_UP_GENERATION_SYSTEM_PROMPT = """\
You are an assistant that drafts short follow-up emails for job seekers when a recruiter conversation has stalled. You will be given the job context, recipient info, and the recent thread. Output ONLY a JSON object with exactly these fields: "subject" (string), "body" (string), "tone" (string), "confidence" (number between 0 and 1). No markdown, no code fences, no explanation.

Rules:
- Be polite and professional. Reference the prior conversation (e.g. "Following up on our conversation", "After our interview").
- Do NOT sound pushy or demanding. Keep a friendly, respectful tone.
- Keep the body under approximately 120 words. Be concise.
- Use a subject that fits the thread (e.g. "Re: <original subject>" or "Following up – <role> at <company>").
- Plain text only; no HTML or markdown.
- Do NOT invent facts, dates, or commitments. Set "tone" to the tone you used and "confidence" to 0.0-1.0.
"""

FOLLOW_UP_BODY_MAX_WORDS = 120


def build_followup_user_content(context: dict) -> str:
    """Build user message for follow-up generation from job/thread/recruiter context."""
    parts: list[str] = []
    parts.append(
        f"Job: company={context.get('job_company') or 'Unknown'}, "
        f"role={context.get('job_role') or 'Unknown'}, "
        f"current_stage={context.get('job_stage') or 'SOURCED'}"
    )
    parts.append(f"Recipient:\n{context.get('recipient_info') or 'Recipient not specified.'}")
    parts.append("")

    time_since = context.get("time_since_last_activity_days")
    if time_since is not None:
        parts.append(f"Time since last activity: {time_since} days ago.")
        parts.append("")

    thread_messages = context.get("thread_messages") or []
    if thread_messages:
        parts.append("Recent messages in this thread (chronological):")
        for i, m in enumerate(thread_messages, 1):
            sender = m.get("sender", "(unknown)")
            timestamp = m.get("timestamp", "(no date)")
            body = m.get("body_text", "(no body)")
            if len(body) > 500:
                body = body[:500] + "\n[...truncated...]"
            parts.append(f"  {i}. From: {sender} | Date: {timestamp}\n     Body: {body}")
        parts.append("")

    parts.append(
        "Generate a short, polite follow-up email the job seeker can send to nudge the recruiter. "
        "Reference the prior conversation. Do not sound pushy. Keep under ~120 words."
    )
    parts.append(
        'Return only valid JSON with exactly these fields: "subject", "body", "tone", "confidence" (confidence a number 0-1).'
    )
    return "\n".join(parts)


REPLY_AGENT_SYSTEM_PROMPT = """\
You are an assistant that drafts email replies for job-seeker correspondence. You have tools to load the user's job-search profile (locations, compensation, company size preferences) and real Google Calendar availability.

Workflow:
1. Read the thread and user instruction.
2. If scheduling or availability is relevant, call get_calendar_availability (use the user's timezone from profile when possible).
3. If you need compensation, location, or company-size context, call get_user_profile.
4. When you have enough context, stop calling tools and wait for the final instruction to output JSON variants.

Safety:
- Do NOT invent facts. Use tool results for availability and preferences.
- You may propose specific times only when get_calendar_availability returns slots, or when the user instruction or profile availability_notes provide them.
- If calendar is not connected and no times are given, use a neutral placeholder like [availability] in the body OR ask them to suggest times—do not fabricate dates.
- Respect location and compensation preferences when declining or negotiating (only when relevant to the thread).
- Keep each variant appropriate to its tone: concise, warm, enthusiastic, reject.
- The "reject" variant politely declines an interview, offer, or opportunity (use profile preferences only when relevant; never accept or schedule in reject).
"""

REPLY_AGENT_FINAL_USER_INSTRUCTION = """\
Now output ONLY a JSON object with key "variants": an array of exactly 4 objects ordered concise, warm, enthusiastic, reject.
Each object: variant_id, tone, subject, body (plain text with \\n for paragraphs), confidence (0-1).
Use string variant_id values exactly: "concise", "warm", "enthusiastic", "reject" (not numbers).
Do not call any more tools. No markdown fences."""

# Multi-variant: one call returns 4 variants (concise, warm, enthusiastic, reject)
REPLY_MULTI_VARIANT_SYSTEM_PROMPT = """\
You are an assistant that drafts email replies for job-seeker correspondence. You will be given the full email thread (all messages), job context, and recipient info. You must output exactly FOUR reply variants in one JSON object.

Output ONLY a JSON object with a single key "variants" whose value is an array of exactly 4 objects. Each object must have:
- "variant_id": one of "concise", "warm", "enthusiastic", "reject" (use these exact strings; one per variant).
- "tone": same as variant_id.
- "subject": string (subject line for that variant).
- "body": string (plain text body, no HTML or markdown).
- "confidence": number between 0 and 1.

Order the array as: concise first, then warm, then enthusiastic, then reject.

Safety rules:
- Do NOT invent facts: no fake dates, times, names, or commitments unless explicitly in context or user instruction.
- Do NOT promise availability or specific times unless explicitly given.
- concise = short and direct; warm = friendly and personable; enthusiastic = positive and eager.
- reject = polite, professional decline (pass on interview, offer, or role). Thank them; be respectful; do not accept, schedule, or express interest. You may briefly cite location/comp/fit from profile if relevant. Do not burn bridges or be rude.

Rules:
- Do NOT change the email subject; it is preserved from the thread. Output a placeholder if required—the system will use the thread subject.
- Format the body like a real email: use actual newlines (\\n in the JSON string) to separate paragraphs and structure. Put the greeting (e.g. "Hi [Name],") on its own line; separate paragraphs with a blank line; put the sign-off (e.g. "Best," or "Thanks,") on its own line with the sender name on the next line. Do not output one long run-on paragraph.
- No markdown, no code fences, no explanation. Output only the JSON object.
"""


def build_reply_multi_variant_user_content(context: dict) -> str:
    """Build user message for multi-variant reply (same context as single reply, different task)."""
    parts: list[str] = []
    thread_messages = context.get("thread_messages") or []
    if thread_messages:
        parts.append(
            f"Full thread — all {len(thread_messages)} messages in chronological order:"
        )
        for i, m in enumerate(thread_messages, 1):
            sender = m.get("sender", "(unknown)")
            timestamp = m.get("timestamp", "(no date)")
            body = m.get("body_text", "(no body)")
            parts.append(f"  {i}. From: {sender} | Date: {timestamp}\n     Body: {body}")
        parts.append("")
    else:
        parts.append("Thread summary: (No messages in thread. Compose short professional reply variants for this job.)")
        parts.append("")

    parts.append(
        f"Job: company={context.get('job_company') or 'Unknown'}, "
        f"role={context.get('job_role') or 'Unknown'}, "
        f"current_stage={context.get('job_stage') or 'SOURCED'}"
    )
    parts.append(f"Recipient:\n{context.get('recipient_info') or 'Recipient not specified.'}")
    parts.append("")
    parts.append(f"User: {context.get('user_name') or 'User'}")
    if context.get("user_profile_summary"):
        parts.append(context["user_profile_summary"])
    if context.get("user_instruction"):
        parts.append(f"User instruction (follow this): {context['user_instruction']}")
    parts.append("")
    parts.append(
        "Generate exactly four reply variants: concise, warm, enthusiastic, and reject (polite decline). "
        "Do not invent facts. Do not promise specific times unless given. "
        "Format each body like a proper email: greeting on its own line, paragraphs separated by blank lines, "
        "sign-off (e.g. Best,) on its own line and name on the next. Use newlines in the body string; do not use one long paragraph."
    )
    parts.append(
        "Return only valid JSON: one object with key \"variants\" and value an array of 4 objects, "
        "each with variant_id, tone, subject, body, confidence (number 0-1)."
    )
    return "\n".join(parts)


def build_reply_user_content(
    job_company: str | None,
    job_role: str | None,
    job_stage: str,
    thread_snippet: str,
    recipient_info: str,
    tone: str,
    user_instruction: str | None,
) -> str:
    """Build user message for reply generation (legacy single-snippet). Truncates long thread content."""
    parts: list[str] = []
    parts.append(f"Job: company={job_company or 'Unknown'}, role={job_role or 'Unknown'}, current_stage={job_stage}")
    parts.append(f"Recipient / context:\n{recipient_info}")
    parts.append(
        f"Tone: Match the tone of the email thread below. Use professional as the default when unclear. "
        f"Requested tone for this reply: {tone}."
    )
    if user_instruction and user_instruction.strip():
        parts.append(f"User instruction (follow this): {user_instruction.strip()}")
    if len(thread_snippet) > REPLY_BODY_TRUNCATION_LIMIT:
        thread_snippet = thread_snippet[:REPLY_BODY_TRUNCATION_LIMIT] + "\n[...truncated...]"
    parts.append(f"Email thread (most recent message or excerpt):\n{thread_snippet}")
    parts.append('Return ONLY a JSON object with "subject", "body", "tone", "confidence".')
    return "\n\n".join(parts)


def build_reply_user_content_from_context(context: dict) -> str:
    """Build user message from structured ReplyContext (thread summary first, then job/user, then instructions)."""
    parts: list[str] = []

    # Thread summary (chronological)
    thread_messages = context.get("thread_messages") or []
    if thread_messages:
        parts.append(
            f"Full thread — all {len(thread_messages)} messages in chronological order:"
        )
        for i, m in enumerate(thread_messages, 1):
            sender = m.get("sender", "(unknown)")
            timestamp = m.get("timestamp", "(no date)")
            body = m.get("body_text", "(no body)")
            parts.append(f"  {i}. From: {sender} | Date: {timestamp}\n     Body: {body}")
        parts.append("")
    else:
        parts.append("Thread summary: (No messages in thread. Compose a short professional reply for this job.)")
        parts.append("")

    # Job and recipient
    parts.append(
        f"Job: company={context.get('job_company') or 'Unknown'}, "
        f"role={context.get('job_role') or 'Unknown'}, "
        f"current_stage={context.get('job_stage') or 'SOURCED'}"
    )
    parts.append(f"Recipient:\n{context.get('recipient_info') or 'Recipient not specified.'}")
    parts.append("")

    # User and tone
    parts.append(f"User: {context.get('user_name') or 'User'}")
    parts.append(f"Requested tone: {context.get('tone') or 'professional'}")
    if context.get("user_instruction"):
        parts.append(f"User instruction (follow this): {context['user_instruction']}")
    parts.append("")

    # Task and safety
    parts.append(
        "Generate a short professional reply based on the thread above. "
        "Follow the user instruction if provided."
    )
    parts.append(
        "Do not invent facts. Do not promise specific times or availability unless explicitly given. "
        "Keep the reply concise and professional."
    )
    parts.append(
        'Return only valid JSON with exactly these fields: "subject", "body", "tone", "confidence" (confidence a number 0-1).'
    )
    return "\n".join(parts)


def build_user_content(
    subject: str | None,
    body_text: str | None,
    from_address: str | None = None,
    attachment_texts: list[tuple[str, str]] | None = None,
) -> str:
    """Build the user message from email fields. Truncates long bodies."""
    parts: list[str] = []

    parts.append(f"From: {from_address or '(no from)'}")
    parts.append(f"Subject: {subject or '(no subject)'}")

    body = strip_quoted_replies((body_text or "").strip())
    if len(body) > BODY_TRUNCATION_LIMIT:
        body = body[:BODY_TRUNCATION_LIMIT] + "\n[...truncated...]"
    parts.append(f"Body:\n{body}" if body else "Body: (empty)")

    if attachment_texts:
        att_lines = []
        for filename, excerpt in attachment_texts:
            att_lines.append(f"- {filename}: {excerpt}")
        parts.append("Attachments:\n" + "\n".join(att_lines))

    return "\n\n".join(parts)


# --------------- Resume review (suggestions) ---------------

RESUME_REVIEW_SYSTEM_PROMPT = """\
You are an expert resume reviewer. You will be given a resume in one of two forms: (1) Markdown — the full document; or (2) structured contact info plus configurable sections (each section has a name and either text or a list of items). Your job is to suggest concrete improvements for job applications and ATS.

Return ONLY a JSON object with a single key "suggestions" whose value is an array of suggestion objects. Each object must have exactly these fields:
- "section": string identifying where the change applies. For Markdown resumes use "markdown" and put the exact span to replace in current_value and the replacement in suggested_value (or describe the edit in suggested_value if a single replacement is not practical). For structured resumes use the section name (e.g. "Summary", "Experience", "Skills") or "sections[N]" for the N-th section (0-based), and for list sections use "sections[N].items[M].body" or ".heading" or ".subheading".
- "suggestion_type": one of "wording", "add_detail", "ats_friendly", "consistency", "missing".
- "current_value": optional string, a short excerpt of the current content (omit if not applicable).
- "suggested_value": optional string, the replacement text or concrete instruction (omit if just a comment).
- "comment": string, a short reason for the suggestion (required).

Give 3–8 suggestions. Focus on: clarity, action verbs, quantifiable results, keyword alignment for ATS, and missing sections. Do not suggest removing experience; only improve or add. If the resume is already strong, you may return an empty suggestions array.
Output ONLY valid JSON, no markdown fences, no explanation outside the JSON.
"""


def build_resume_review_user_content(parsed_json: dict) -> str:
    """Build user message for resume review from parsed_json (Markdown or contact + sections)."""
    if parsed_json.get("format") == "markdown":
        md = parsed_json.get("markdown") or ""
        return (
            "Resume content to review (Markdown):\n\n"
            "---\n\n"
            f"{md}\n\n"
            "---"
        )
    parts = ["Resume content to review (structured):", ""]
    contact = parsed_json.get("contact") or {}
    if not contact and parsed_json.get("name") is not None:
        contact = {
            "name": parsed_json.get("name", ""),
            "email": parsed_json.get("email", ""),
            "phone": parsed_json.get("phone", ""),
        }
    if contact.get("name"):
        parts.append(f"Name: {contact.get('name')}")
    if contact.get("email"):
        parts.append(f"Email: {contact.get('email')}")
    if contact.get("phone"):
        parts.append(f"Phone: {contact.get('phone')}")
    parts.append("")
    for i, sec in enumerate(parsed_json.get("sections") or []):
        if not isinstance(sec, dict):
            continue
        name = sec.get("name", f"Section {i}")
        parts.append(f"[Section {i}] {name}")
        if sec.get("content_type") == "text" and sec.get("text"):
            parts.append(sec["text"])
        for j, it in enumerate(sec.get("items") or []):
            if isinstance(it, dict):
                h = it.get("heading", "")
                sh = it.get("subheading", "")
                b = it.get("body", "")
                if h or sh:
                    parts.append(f"  Item {j}: {h} — {sh}".strip(" —"))
                if b:
                    parts.append(f"    {b}")
        parts.append("")
    return "\n".join(parts)
