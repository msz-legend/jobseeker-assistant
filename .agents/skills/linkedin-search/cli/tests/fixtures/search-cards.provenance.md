# Offline search cards

`search-cards.json` stores the markup of two `<li>` search cards as synthetic sample
data for the CLI's local parsing tests, encoded as a single JSON string. Nothing is
collected from a real source: the company ("Meridian Analytics"), titles ("Backend
Engineer", "Data Engineer"), job IDs (4399900001, 4399900002), impression/reference/
tracking values, logo URLs, location and dates are all placeholders.

The cards keep the node shape of a live guest search response that the parser must
handle: the search-card wrapper with its entity URN, the full-link anchor, the
sr-only title span plus the `<h3>` title, the subtitle company link, the location
span, a benefits block, and the listdate `<time>` element with its datetime
attribute.

The JSON string encoding preserves the markup verbatim for the test harness. The
valid-flag controls serve these cards over loopback HTTP; their child CLI preload
accepts only the expected search endpoint and redirects that request to loopback.
Tests assert the actual URL parameters, successful output, IDs and client-side
result limits. No fixture regeneration or portal request occurs during tests; this
isolates these controls locally and is not an OS-level egress policy.
