---
name: factory-brain
description: Where the factory brain lives. One file per repository with durable facts maintainers recorded through reviewed hub changes.
---
# Factory brain

Each repository the factory works on has one file here, `<owner>-<repo>.md`, holding short, durable facts about it: build quirks, non-obvious verification steps, recurring review findings, conventions. The factory weaves the file into every station's message, because stations can't read hub files.

Facts get here only through a reviewed hub change: a person says "remember for the team: ...", or attended factory work proposes a note, and a hub manager applies the exact edit. Unattended work (the label, CI repairs) never proposes. It writes "Suggested factory brain note" in its reply for a maintainer to record. Keep each file under 40,000 characters, curated and short.
