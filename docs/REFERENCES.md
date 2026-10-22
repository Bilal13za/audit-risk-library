# Standards and references register

## Policy
The library **does not fabricate standard references**. No ISA/IFRS paragraph numbers are cited
in any seeded record, because a wrong paragraph number is worse than none. Assertion terminology
follows ISA 315 (Revised) categories (transactions and events; account balances; presentation
and disclosure), but this is a terminology alignment, not a citation.

## Verified references
None yet. A reference becomes "Verified" only when a reviewer has checked it against the
official publication and recorded the paragraph, publication date and URL in the `standards` table.

## Unverified / professional-practice basis
All seeded records (factors, risks, controls, procedures, evidence, rules) carry:
`source_reference = "Professional practice guidance; standards references unverified - see docs/REFERENCES.md"`.
This means: the content reflects widely taught audit methodology and the reviewer's professional
judgment, but has not been traced to a specific paragraph of an authoritative standard.

## How to verify a reference
1. Locate the official publication (e.g. IAASB handbook, IASB bound volume).
2. Record in `standards`: standard_name, issuing_organisation, paragraph, publication_date,
   jurisdiction, url, verification_status='Verified'.
3. Link it via `rule_standard` and update the record's source_reference to name the standard.

## Roadmap
Priority: verify the assertion library against ISA 315 (Revised) Appendix, then the revenue
recognition and inventory procedures against ISA 501 and ISA 520. Contributions should add one
verified standard at a time rather than bulk unverified citations.
