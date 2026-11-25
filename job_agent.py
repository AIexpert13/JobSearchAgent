"""Job-matching agent: reads your profile, finds matching public job listings,
and drafts tailored application material for you to review and submit yourself.

It does NOT log into LinkedIn or submit applications.

Env vars:
  ANTHROPIC_API_KEY   (required)
  TARGET_ROLE         e.g. "Senior Data Analyst"
  LOCATION            e.g. "London, UK or remote"
  TOP_N               how many jobs to prepare material for (default 5)
  EMAIL_TO / EMAIL_FROM / EMAIL_APP_PASSWORD   (optional, Gmail app password)
"""
import asyncio
import os
import smtplib
import ssl
from datetime import date
from email.message import EmailMessage
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

TARGET_ROLE = os.environ.get("TARGET_ROLE", "your target role")
LOCATION = os.environ.get("LOCATION", "remote")
TOP_N = os.environ.get("TOP_N", "3")
FRESH_DAYS = os.environ.get("FRESH_DAYS", "3")

SYSTEM_PROMPT = (
    "You are an expert career coach and technical recruiter. "
    "Use web search and fetch to find CURRENT job openings on public sources "
    "(company careers pages, job boards, public LinkedIn job posts that load without login). "
    "Never log in anywhere. Never invent job listings, links or dates. "
    "STRICT HONESTY RULE: when tailoring a CV or cover letter, only reorder, reword "
    "and emphasise experience that appears in the candidate's profile. Never add skills, "
    "employers, titles, degrees or numbers the profile does not contain. If a job needs "
    "something the profile lacks, list it as a gap instead."
)


def build_prompt(profile: str) -> str:
    return f"""Today is {date.today().isoformat()}.

CANDIDATE PROFILE
-----------------
{profile}
-----------------

Target role: {TARGET_ROLE}. Location preference: {LOCATION}.

Tasks:
1. Search for current openings that match the profile. Aim to review about 15 and
   keep the best {TOP_N}. Only include listings posted in the last {FRESH_DAYS} days
   (if a posting date is not shown, say "date not shown"). Skip anything without a
   working link. If nothing new and relevant is found, say so in one line instead of
   padding the report with old listings.
2. For each kept job give: title, company, location, link, posted date if shown,
   fit score out of 10 with a one-line reason, and key gaps.
3. For each kept job, draft:
   a) a 3-line tailored profile summary,
   b) 4-5 CV bullets reworded from the candidate's real experience to match the job,
   c) a cover letter under 200 words.
4. Finish with PROFILE IMPROVEMENTS: headline, About section and skills to
   add or reorder on the candidate's profile, based on patterns across these jobs
   (only things the candidate can truthfully claim).

Output as clean Markdown, one section per job."""


async def run() -> str:
    profile = Path("profile.md").read_text(encoding="utf-8")
    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=["WebSearch", "WebFetch"],
        max_turns=40,
    )
    report = ""
    async for message in query(prompt=build_prompt(profile), options=options):
        if isinstance(message, ResultMessage):
            report = message.result or ""
    return report


def send_email(body: str) -> None:
    to_addr = os.environ.get("EMAIL_TO")
    from_addr = os.environ.get("EMAIL_FROM")
    password = os.environ.get("EMAIL_APP_PASSWORD")
    if not (to_addr and from_addr and password):
        print("Email settings missing; saved to file only.")
        return
    msg = EmailMessage()
    msg["Subject"] = f"Daily job matches - {date.today().strftime('%a %d %b %Y')}"
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(from_addr, password)
        s.send_message(msg)
    print(f"Email sent to {to_addr}")


if __name__ == "__main__":
    text = asyncio.run(run())
    if not text:
        raise SystemExit("Agent returned no report.")
    Path("job_report.md").write_text(text, encoding="utf-8")
    print("Saved job_report.md")
    send_email(text)
