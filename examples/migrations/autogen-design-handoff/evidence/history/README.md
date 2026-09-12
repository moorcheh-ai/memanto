# Preserved failed audit

The live run starting 2026-09-12 09:37:55 UTC used target top-3 retrieval as its
main recall gate. It imported and exported all eight records losslessly but
passed only 5/6 recall checks, so the corrected failure gate exited nonzero.
The review-clearance instruction was not among the three ranked results.

AutoGen ListMemory returns all eight source records, making that comparison
unequal in context volume. The final run separates full-context parity (8/8
records, 6/6 answers) from the informational top-3 audit (still 5/6). Source
records, questions and expected answers did not change. These files retain the
failed run rather than hiding it or repeatedly retrying for a perfect score.
