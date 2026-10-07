# Retrieval evaluation note

Recall@K measures how many labeled relevant units appear among the first K retrieved results. Mean Reciprocal Rank gives more credit when the first relevant result appears earlier. nDCG evaluates ordering when relevance labels have graded strength rather than a single binary value.

These retrieval metrics do not measure whether the final generated answer is faithful. Answer grounding and citation correctness must be evaluated separately.
