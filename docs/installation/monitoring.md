# Monitoring your Saveroom server 

Saveroom can be configured to ship logs, metrics and traces using
the [Open Telemetry standard](https://opentelemetry.io/). You can use these to monitor
your Saveroom instance.

Enable this by setting the env var `BASEROW_ENABLE_OTEL=true` and then depending on
where you want to send telemetry set the
appropriate [OTEL env vars](https://opentelemetry.io/docs/reference/specification/sdk-environment-variables/#general-sdk-configuration).
You probably want to set `OTEL_EXPORTER_OTLP_ENDPOINT` also.
> In our default docker-compose files we have only added passthroughs for the following
> OTEL specific env vars.
> * OTEL_EXPORTER_OTLP_ENDPOINT
> * OTEL_RESOURCE_ATTRIBUTES
>
> If you want to use more, you need to edit the compose files
> yourself and add the env var passthroughs you need.

By default, Saveroom will send the following telemetry:

- Saveroom application logging. 
- Some basic metrics.
- Various spans over some of our critical functions and handler methods.
- Automatic instrumentation provided by OTEL libraries for:
    - S3 usage by the `botocore` library
    - SQL queries
    - Redis queries
    - HTTP queries
    - Celery tasks
    - Django requests/responses

## WebSocket and realtime metrics

WebSocket metrics are independent of trace sampling. Group them by deployment or pod
and `process.pid`: an aggregate can hide one blocked ASGI worker. These metrics use
bounded operation/outcome labels and exclude JWTs, payloads, user/table IDs, and
client-supplied WebSocket IDs. See [WebSocket concurrency and replay](../technical/websockets.md)
for the execution and recovery model.

| Metric | Interpretation |
| --- | --- |
| `baserow.websocket_phase_duration` | Milliseconds for `handshake` (application arrival to accept), `authentication`, `connect`, `accept`, `replay_cursor`, and `replay_query`, by outcome. Count `phase=handshake,outcome=accepted` observations for accepted handshakes per worker. |
| `baserow.websocket_handshakes_pending` | Applications that arrived but have not accepted or rejected. |
| `baserow.websocket_sync_queue_duration` / `baserow.websocket_sync_execution_duration` | Milliseconds before the executor starts work versus milliseconds on its thread, including database connection cleanup. |
| `baserow.websocket_sync_pending` / `baserow.websocket_sync_executing` | Awaiting callers, including queued and running calls, versus work actually executing. Executing work can outlive a cancelled caller. |
| `baserow.websocket_event_loop_lag` | Scheduling delay in milliseconds, sampled once per second while WebSocket applications are active. |
| `baserow.websocket_replay_requests` | Decisions by `baseline`, `replayed`, `refresh`, `overloaded`, `deadline_exceeded`, `query_timeout`, `database_error`, `cancelled`, or `error`. Refresh `reason` distinguishes `missing_cursor`, `unknown_history`, `cursor_ahead`, `expired_payload`, and `event_limit`; other outcomes use `none`. |
| `baserow.websocket_replay_duration` / `baserow.websocket_replay_events` | Caller wait in milliseconds and number of events returned by a completed decision. |
| `baserow.websocket_replay_inflight` / `baserow.websocket_replay_capacity` | Occupied slots and initialized replay pool capacity, including work still running after cancellation or a deadline. |
| `baserow.websocket_replay_queued` / `baserow.websocket_replay_queue_capacity` / `baserow.websocket_replay_queue_duration` | Waiting requests, admission queue capacity, and wait in milliseconds, including cancelled/expired waits. Admission precedes the separate synchronous executor queue measurement. |
| `baserow.websocket_replay_database_errors` | Database errors by reason, including errors occurring after the caller's deadline. |
| `baserow.realtime_recording_events` | Attempted recording envelopes by `destination=users/page` and handler `outcome=success/error`. A successful handler does not guarantee an enclosing transaction committed. |
| `baserow.realtime_recording_batch_size` / `baserow.realtime_recording_duration` | Envelopes per attempted batch and handler duration in milliseconds, including adaptation and database work. |
| `baserow.realtime_cleanup_deleted` / `baserow.realtime_cleanup_batch_size` | Deleted events and rows per successfully committed cleanup batch. |
| `baserow.realtime_cleanup_batch_duration` | Batch duration in milliseconds, including expired-history summary updates and commit. Failed batches have `outcome=error` and contribute no deleted rows. |
| `baserow.realtime_cleanup_run_deleted` / `baserow.realtime_cleanup_run_duration` | Committed progress and run duration in milliseconds, by outcome. Earlier commits still count if a later batch fails. |
| `baserow.realtime_cleanup_skipped` | Scheduled attempts skipped for `reason=overlap` (another task owns the lease) or `reason=lock_error` (lease acquisition failed). |

Synchronous operations distinguish `authentication`, `page_permission`,
`presence_space`, `recording`, and `replay`. `executor=thread_sensitive` denotes the
shared thread in ordinary WebSocket scopes; a synchronous Celery caller can instead
use its task thread. `executor=isolated` identifies replay's separate executor.
`presence_space` measures page-type resolution, including public-view queries.
Database-free dispatch makes no cleanup submission. Channels' final disconnect
cleanup is retained but is not included in these operation metrics.

Compare queue and execution time for each operation on each worker. Long execution
identifies work occupying a thread; queue delays show its waiting callers. High
event-loop lag points to synchronous work on the loop, CPU starvation, or process
resource pressure instead. During cancellation, pending and executing are not a
strict subtraction for queue length. Replay has its own explicit queued metric.

Duration histograms contain completed observations. Pending gauges help expose work
that has not finished. Slow operations log warnings after one second, rate-limited
per phase and operation to one every 30 seconds per process. Debug phase logs use a
server-generated connection correlation ID. Event-loop lag becomes observable only
after the loop responds again; worker stacks and database wait events help diagnose
a complete stall. These instruments add no diagnostic database queries.

### Capacity and storage interpretation

Replay capacity appears only after a worker initializes its pool; importing the
module in another process does not add capacity. Compare occupancy, queued work,
overloads, and deadline outcomes per initialized worker, and use configured ASGI
worker counts when sizing a deployment. For steady traffic, estimate utilization
as request rate multiplied by mean thread execution time divided by replay
concurrency. Caller latency understates demand when work continues after a timeout,
and averages do not predict reconnect bursts.

Potential replay database connections scale as pods × ASGI workers per pod × replay
concurrency, in addition to HTTP, authentication, Celery, and other database users.
Keep this total within the database or pool budget. A result-size limit and async
deadline do not bound recording writes or terminate blocked connection attempts.

The handshake timer starts when the application is invoked and excludes proxy
waiting. Correlate it with ingress attempts, upstream selection and timings; HTTP
health checks alone do not establish WebSocket responsiveness. Channel-capacity
warnings describe full recipient queues, not a connection limit or proof that Redis
has exhausted memory.

Compare recording rate with committed cleanup deletions over time. A cleanup run
ending with `budget` retained its earlier commits but exhausted its time allowance;
`success` can still leave locked rows for the next run. Repeated overlap or lock
errors explain runs that never reached the database. Track oldest full-event age,
event-table size, history-summary count and size,
`pg_stat_user_tables` live/dead tuple estimates and vacuum/analyze timestamps, and
database I/O alongside these metrics. Deletion and vacuum make space reusable;
they do not normally reduce allocated table files. Replay refresh fallbacks also
create HTTP reads, so include that traffic when assessing capacity.

Cleanup deletes expired business payloads while preserving routing summaries for
exact audiences. Summaries have no fixed size bound: distinct audiences can
accumulate, although new ignored sockets alone do not create additional rows.
Measure summary growth alongside recent event volume and cleanup progress.

For users-channel replay, compare rows and heap blocks visited with events actually
returned. Recipient selection should use `target_user_ids` and `all_users`, with
`ws_realtime_targets_idx` and `ws_realtime_all_users_idx` available to the planner.
There is no full-payload GIN index. Include recipient-trigger work in recording
measurements; smaller indexes do not by themselves guarantee faster inserts.

Refresh reasons separate storage coverage from event volume: `expired_payload`
means relevant missed history was compacted or falls outside the replay window;
`unknown_history` means the cursor predates the known history boundary after
activation or reset; `event_limit` means too many replayable changes remain.
