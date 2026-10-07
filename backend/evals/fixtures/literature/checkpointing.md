# Workflow checkpointing note

The workflow uses `thread_id` as the stable key for LangGraph checkpoint state. A resumed run can receive a new `run_id`, but it continues from the checkpoint associated with the same `thread_id`.

Checkpoint restoration rebuilds the latest committed research state. It does not replay the previous Server-Sent Events. After a browser refresh, the client should request the current snapshot for the thread.
