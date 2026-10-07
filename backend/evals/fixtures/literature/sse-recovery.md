# Streaming recovery note

The live SSE channel is not an event log and does not replay old frames. Every event has a monotonically increasing sequence number, allowing the UI to ignore stale duplicates within a run.

When the connection is lost or the page is refreshed, the UI should call the research snapshot endpoint with the thread identifier. The returned checkpoint projection restores current tasks, evidence, review state, and report. This restores state, not the complete event history.
