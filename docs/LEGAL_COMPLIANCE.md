# Morning Brief — India Legal/Editorial Compliance Controls

This is an engineering checklist, not legal advice. Obtain review from qualified Indian media/IP/privacy counsel before commercial launch and re-check changing rules.

## Implemented in code

- RSS articles are summarized rather than reproduced; source citations are retained.
- Automatic approval uses the configured similarity threshold (default 30%) only as a necessary condition.
- Mandatory human-review triggers cover crime/corruption/wrongdoing, court/sub-judice language, elections, communal/religious/caste topics, health/medical claims, financial/market claims, minors, self-harm, named-entity sensitive contexts, verifier unavailability/low-confidence, and contradictions.
- Every enabled blocking verification layer is treated as blocking when it fails; the approval gate no longer relies on a manually incomplete list of flags.
- Similarity and long-phrase scores, verifier report/model, citations, review metadata and verification flags are retained on stories.
- Automatic approval and human-review decisions are distinguishable through the story status/flags and audit trail.
- Source compliance registry supports ToS URL, licence status, review date, reviewer, usage notes and commercial-use status.
- AI-generation disclosure and privacy notice are exposed at `/legal/disclosure` and `/legal/privacy-notice` and in the web UI at `/legal`.
- Email delivery requires explicit news-email consent and supports withdrawal from Preferences.
- Content issue reporting is stored in a review queue at `/legal/reports` for admins.
- Email footer discloses AI summarization, source attribution and preference management.

## Still requires operator/legal action before launch

- Review every source's RSS ToS/robots.txt and complete `/legal/source-registry` before commercial ingestion.
- Do not scrape paywalls/login walls or ingest source images/video/audio without rights.
- Confirm publisher classification and appoint/publish the required India grievance contact and escalation process if applicable.
- Confirm any current MIB notification/reporting obligations before launch.
- Publish final privacy notice, grievance contact and retention/deletion policy after counsel review.
- Maintain an incident-response and breach-notification process.
- Confirm cross-border processing terms for LLM/email vendors before sending any subscriber-linked personal data to them.
- Establish correction/takedown SOPs and legal response timelines.
- Review election-period and sub-judice editorial policy.
- Consider media/cyber liability insurance as the service scales.

## Important

A similarity score is not a copyright safe harbor and does not establish factual accuracy or defamation safety. The product must continue to use source-linked verification and human review for sensitive stories.
