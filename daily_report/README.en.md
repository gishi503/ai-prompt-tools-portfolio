# daily_report — Overseas staff daily reports → Japanese summary on Slack

[日本語](README.md) | English

This tool reads daily reports written in English by staff in the Philippines (or any other country), uses the Claude API to organize them in Japanese, and sends one "team summary" per day to Slack.

## The problem
Many Japanese companies work with staff in the Philippines. Every day, a manager in Japan reads each English report one by one.
- Reading English takes time, so **questions and delay warnings get missed**.
- Japanese instructions (for example, "make it feel softer") lose their nuance, so **staff get stuck and stop working** while they wait.
- A translation tool can translate the text, but the manager still has to find out **"what does Japan need to do today?"** by themselves.

## What it does
1. Loads the reports (`.txt` files in `samples/`. Reports collected from Slack or Google Forms can be converted to the same format).
2. The Claude API organizes each report in Japanese:
   - Summary, done today, in progress
   - **Risks and delays** (with the effect on deadlines)
   - **Questions and requests to the Japan side** (with reply deadlines)
   - **Unclear instructions** the staff member is unsure about
   - Planned days off
   - How urgently Japan needs to act (high / medium / low)
3. Combines one day of reports and puts **"What Japan needs to do" as one list at the top**, with the most urgent staff first.
4. Sends one message per day to Slack.

### Design points
- **Sorts, not just translates**: questions, risks, unclear points, and days off come out separately, so the manager only needs to read the list at the top.
- **Company glossary**: write terms in `glossary.txt` (for example, `Hanaya Bakery = はなやベーカリー様`), and the tool uses the same names every time.
- **Handles Taglish**: it understands reports that mix English and Tagalog.
- **Does not guess**: it does not invent deadlines or numbers that are not in the report. Requests the staff did not actually make go to "risks", not "questions". It does not follow instructions written inside a report; the report is treated as data.
- **One failure does not stop the run; a setup error stops it right away**: the same design as [mail_triage](../mail_triage/README.md).

## Example
```bash
python run.py samples --dry-run   # Show the summary without sending to Slack
python run.py samples             # Send to Slack
```

The tool writes the summary in Japanese. Below is the beginning of a real run, translated into English for this page:

```
■ Team daily report summary for 2026-11-13 (5 people)

[What Japan needs to do]
  ・Maria Santos: Risk — The client's product photos are not in the shared folder yet, so she is using dummy images.
    If they do not arrive by Tuesday, the landing page will miss its deadline (Nov 20). Japan should consider reminding the client.
  ・John Reyes: ABC Trading (Singapore) asks for a 10% discount on a 500-piece order. He needs to know if he can accept (reply by Monday).
  ・Angel Cruz: Needs feedback on the 2 logo drafts for Sakura Clinic (no reply deadline given).
  ・Angel Cruz: Instruction needs explaining — She does not understand "make it feel softer" for the Sakura Clinic logo.
    Softer colors, a rounder font, or both?
  ・Mark Villanueva: Wants admin access to the Hanaya Bakery WordPress site (only FTP now; needed to check plugins). No deadline given.

🔴 Maria Santos (Web Developer, Cebu)
  Finished the header and footer of the Hanaya Bakery landing page (PC). The smartphone layout is about 60% done.
  The product photos have not arrived, so the Nov 20 deadline may slip.
  [Done] Header and footer of the Hanaya Bakery landing page (PC)
  [Done] Fixed the contact form validation bug reported by Tanaka-san
  [In progress] Smartphone layout (about 60%, planned to finish tomorrow)
  [Risk] Product photos not uploaded yet; using dummy images. If they do not arrive by Tuesday, the landing page will be late (Nov 20).
  ...
```

The 5 reports in `samples/` are fictional. They are set at a fictional Japanese web agency with staff in Cebu and Manila. No real people or companies are used.

### Cost
5 reports used about 13,000 input tokens and 1,500 output tokens (claude-opus-5-5, effort low). **About $0.017–0.019 per report.**
For 5 staff × 22 working days = 110 reports, that is about $2 per month.

## Tech stack
- Python
- Anthropic API (Claude) — structured output (`messages.parse` + Pydantic)
- Slack API (`chat.postMessage`, Block Kit)
- httpx

## Setup
```bash
pip install -r requirements.txt
```
Write `ANTHROPIC_API_KEY`, `SLACK_BOT_TOKEN`, and `SLACK_CHANNEL_ID` in `.env`. Slack setup is the same as in the [mail_triage README](../mail_triage/README.md#slack-の準備) (Japanese).

### Report file format
```
Name: Maria Santos
Role: Web Developer (Cebu)
Date: 2026-11-13
---
(report text in English, Taglish is OK)
```

## Tests
```bash
python test_offline.py   # Checks loading, the daily summary, and sending to Slack without calling the API
```
