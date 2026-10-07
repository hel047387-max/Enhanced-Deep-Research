# Bilingual embedding selection note

Embedding selection should use a labeled query set drawn from the target Chinese-English corpus. Each query needs one or more human-labeled relevant units. Candidate models must be compared with the same document chunks, filters, and result limits.

Record Recall@K before reranking and nDCG after reranking. Provider claims and general leaderboards are useful screening signals, but they are not substitutes for the target-corpus experiment.
