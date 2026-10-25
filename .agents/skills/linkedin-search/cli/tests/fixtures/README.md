# Detail fixture

`detail-meridian-excerpt.html` is synthetic sample data written for this CLI's local
parsing tests. The company ("Meridian Analytics"), job title, description body,
location ("Exampleland"), job ID and dates are all invented placeholders — no content
is collected from any real posting, no person or company is quoted, and the file
references no external source.

Only the page shape is reproduced. The file keeps the node hierarchy and class
anchors a real LinkedIn detail page exposes: a topcard title element, a
closed-posting banner inside the top card, the rich description paragraph/list
block (`show-more-less-html__markup`, including `<p><br></p>` separators and
inline `<u>` headers), and a job-criteria list.

The CLI regression test serves this fixture over loopback in a child process and
accepts only the exact expected guest endpoint path. It makes no network requests
and does not regenerate the fixture during tests.
