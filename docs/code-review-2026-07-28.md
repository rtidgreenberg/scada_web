# scada_web — Code Review Findings

**Status:** Point-in-time review · **Date:** 2026-07-28
**Revision:** rev 2 — every finding re-verified against the tree, still at
`015e653` with a clean working tree, so both passes describe the same code.
Corrections are
marked **Correction.** inline and never rewrite the original finding text. Three
findings added: [CR-034](#cr-034), [CR-035](#cr-035), [CR-036](#cr-036). The
`HIGH` count is now four (rev 1 prose said "four" when three were listed; CR-034
makes it true). The suggested sequence changed in three places — see
[Suggested sequence](#suggested-sequence).

**Revision:** rev 3 — steps 1–2 of the sequence implemented on branch
`fix/log-writers-and-process-teardown`. Four findings RESOLVED, two PARTIAL, one
added ([CR-037](#cr-037), found by the acceptance run). Commit-to-finding mapping
is in the [Resolution log](#resolution-log); per-finding detail is on the
`**Status:**` line of each affected finding. **The pipeline suite has now been
run** — see [Verification performed](#verification-performed), which supersedes
rev 1's and rev 2's "not performed" caveat.

**Revision:** rev 4 — steps 3–6 of the sequence implemented on `main` (two
commits, `2dbaecf` and `1a9ea5d`). Thirteen more findings RESOLVED:
[CR-003](#cr-003), [CR-004](#cr-004), [CR-011](#cr-011), [CR-013](#cr-013),
[CR-019](#cr-019), [CR-020](#cr-020), [CR-021](#cr-021), [CR-025](#cr-025),
[CR-026](#cr-026), [CR-029](#cr-029), [CR-030](#cr-030), [CR-031](#cr-031),
[CR-036](#cr-036). No findings added. The `HIGH` count drops to zero — CR-003
was the last open `HIGH` item. Commit-to-finding mapping appended to the
[Resolution log](#resolution-log); per-finding detail on each affected
finding's `**Status:**` line, as in rev 3. **Full suite re-run after each
commit** — see [Verification performed](#verification-performed) for both runs
(56 passed, then 61 passed after CR-003 added its own regression test), zero
leaked processes on teardown either time.
**Reviewed at commit:** `015e653` (feat: migrate scada_web to Python generated types)
**Scope:** Full first-party tree — `scada_web/`, `sim/`, `scada_select/src/`, `UI/`,
`scripts/`, `tests/`, `dds/`, `docs/`. Excludes `references/` (submodule) and
`scada_select/build/` (generated).
**Lens:** consistency, simplicity, clarity. Not a security review; not a
performance audit beyond what reads as accidental.

Findings are numbered `CR-nnn`, never renumbered. Each carries a severity, the
evidence that supports it, and a recommendation. Rationale for *decisions* still
belongs in [design-decisions.md](design-decisions.md) — where a finding argues
for reopening a decision, it links there rather than restating it.

**Severity.** `HIGH` — causes incorrect behaviour, data loss, or silent failure
in normal operation. `MEDIUM` — costs real maintenance or misleads a reader.
`LOW` — cleanup; safe to batch.

---

## Summary

The codebase is in good shape. Comment discipline is unusually strong, and the
"why" comments on the load-bearing DDS decisions — `new_data` masking lifecycle
events, `period_ms == 0` semantics, write-timeout-as-drop — are genuinely
valuable and should be preserved through any refactor.

The findings below are overwhelmingly **drift**: two representations of one idea
that have diverged, or documented behaviour that was never wired up. Three of
the four `HIGH` items are silent — they produce no error and no log line, which
is why they've survived. The fourth ([CR-034](#cr-034)) is the opposite failure
mode: it converts a reportable error into an indefinite hang.

**rev 4 update:** all four `HIGH` items are now RESOLVED
([CR-001](#cr-001), [CR-002](#cr-002), [CR-003](#cr-003), [CR-034](#cr-034)).
Remaining open work is `MEDIUM` and `LOW`.

| ID | Finding | Severity | Area | Status |
|---|---|---|---|---|
| [CR-001](#cr-001) | `exec cmd \| tee` defeats signal delivery; start scripts leak processes | HIGH | scripts, tests | **RESOLVED** `ea25bed` |
| [CR-002](#cr-002) | Two writers on each Python log file; rotation silently stops working | HIGH | logging | **RESOLVED** `e2dcd14` |
| [CR-003](#cr-003) | SR-003 reconciliation is implemented but never called | HIGH | scada_web | **RESOLVED** `1a9ea5d` |
| [CR-004](#cr-004) | A separation change with nothing subscribed never reaches the wire | MEDIUM | scada_web | **RESOLVED** `2dbaecf` |
| [CR-005](#cr-005) | The view layer's rename is a no-op on emitted JSON | MEDIUM | scada_web | OPEN |
| [CR-006](#cr-006) | Python `gen/` regenerates manually while C++ regenerates automatically | MEDIUM | build | OPEN |
| [CR-007](#cr-007) | The sim still hand-builds DynamicTypes, citing a superseded decision | MEDIUM | sim | OPEN |
| [CR-008](#cr-008) | "period" and "minimum separation" name one concept in five places | MEDIUM | cross-cutting | OPEN |
| [CR-009](#cr-009) | Selector log style diverges from the Python components | LOW | scada_select | OPEN |
| [CR-010](#cr-010) | The same `DataState` is constructed and justified twice | LOW | scada_select | OPEN |
| [CR-011](#cr-011) | Separation changes fan out through the per-uid ADD callback | MEDIUM | scada_web | **RESOLVED** `2dbaecf` |
| [CR-012](#cr-012) | `_TYPE_MAP` hand-maintains what the generated module already binds | LOW | scada_web | OPEN |
| [CR-013](#cr-013) | `_sample_to_view_dict` dispatches by `isinstance` with a silent fallback | LOW | scada_web | **RESOLVED** `2dbaecf` |
| [CR-014](#cr-014) | Three start scripts duplicate ~75 lines each, and have drifted | MEDIUM | scripts | OPEN |
| [CR-015](#cr-015) | `serve-ui.ps1` exists twice, byte-identical | LOW | scripts | OPEN |
| [CR-016](#cr-016) | The WebSocket protocol accepts four aliases for one field | MEDIUM | scada_web, UI | OPEN |
| [CR-017](#cr-017) | `create_app()` mutates a module-level singleton | MEDIUM | scada_web | OPEN |
| [CR-018](#cr-018) | `@app.on_event` is deprecated in the pinned FastAPI range | LOW | scada_web | OPEN |
| [CR-019](#cr-019) | Dead code inventory (13 items) | MEDIUM | cross-cutting | **RESOLVED** `2dbaecf` |
| [CR-020](#cr-020) | `types_xml` plumbing outlived the XML type library | LOW | scada_web | **RESOLVED** `2dbaecf` |
| [CR-021](#cr-021) | Sample payload is serialized once per interested client | LOW | scada_web | **RESOLVED** `2dbaecf` |
| [CR-022](#cr-022) | The UI rebuilds all 500 rows on every pushed sample | MEDIUM | UI | OPEN |
| [CR-023](#cr-023) | `unionScalar` re-derives a wire contract the server no longer emits | LOW | UI | OPEN |
| [CR-024](#cr-024) | Runtime dataclasses lost their type annotations to `Any` | LOW | scada_web | OPEN |
| [CR-025](#cr-025) | The `KIND_STRING` decode path is unverified and unexercised | LOW | scada_web | **RESOLVED** `2dbaecf` |
| [CR-026](#cr-026) | `InterestManager` validates separation with a duplicated block | LOW | scada_web | **RESOLVED** `2dbaecf` |
| [CR-027](#cr-027) | `scada-web-architecture.md` still lists work that is now done | LOW | docs | OPEN |
| [CR-028](#cr-028) | OQ-38 describes an XML dependency that no longer exists | LOW | docs | **PARTIAL** `b78e934` |
| [CR-029](#cr-029) | Two tests skip forever against a deleted endpoint | MEDIUM | tests | **RESOLVED** `2dbaecf` |
| [CR-030](#cr-030) | `except (TimeoutError, Exception)` turns protocol errors into passes | LOW | tests | **RESOLVED** `2dbaecf` |
| [CR-031](#cr-031) | Assertions guarded into non-existence | MEDIUM | tests | **RESOLVED** `2dbaecf` |
| [CR-032](#cr-032) | Session-scoped fixtures leak state between test modules | MEDIUM | tests | OPEN |
| [CR-033](#cr-033) | Four different `sys.path` insertions across the suite | LOW | tests | OPEN |
| [CR-034](#cr-034) | `proc.stdout.read()` on a live process hangs the fixture instead of reporting | HIGH | tests | **RESOLVED** `ea25bed` |
| [CR-035](#cr-035) | Captured stdout is never drained; a full pipe buffer stalls the component | MEDIUM | tests | **RESOLVED** `ea25bed` |
| [CR-036](#cr-036) | The static mount swallows unmatched `/api/v1` routes into an opaque 404 | LOW | scada_web | **RESOLVED** `2dbaecf` |
| [CR-037](#cr-037) | Every tag in a rate band shares a due time, so bands publish in bursts | LOW | sim | OPEN |
| [CR-R01](#cr-r01) | Docs described DD-052; code implemented the superseded DD-045 | — | scada_web | RESOLVED |
| [CR-R02](#cr-r02) | `/api/v1/topics/{name}/type` could never succeed | — | scada_web | RESOLVED |
| [CR-R03](#cr-r03) | Stale `scada_web/PlcValue.xml` shadowed the canonical library | — | scada_web | RESOLVED |

---

## Operational correctness

### CR-001
**`exec cmd | tee` defeats signal delivery; the start scripts leak processes.**

- **Severity:** HIGH · **Area:** [`scripts/`](../scripts/), [`tests/conftest.py`](../tests/conftest.py)
- **Status:** **RESOLVED** by `e2dcd14` + `ea25bed`. The two Python scripts lost
  their pipeline with the `tee` ([CR-002](#cr-002)), so `exec` now replaces the
  shell; `start-select.sh` keeps its tee through process substitution instead of a
  pipe. Verified by A/B on the shapes (old leaks the component on SIGTERM, new
  terminates it and still writes the log) and by four full-suite runs with **zero
  leaked processes** after every teardown. The `.bat` equivalents named in
  [CR-014](#cr-014) were not examined.

**Finding.** All three start scripts end in this shape —
[start-web.sh:151](../scripts/start-web.sh#L151),
[start-select.sh:161](../scripts/start-select.sh#L161),
[start-sim.sh:168](../scripts/start-sim.sh#L168):

```bash
exec python3 -m scada_web 2>&1 | tee -a "$SCRIPT_DIR/logs/scada_web.log"
```

`exec` inside a pipeline replaces only the left-hand *subshell*, not the script's
own process. The parent `bash` stays alive waiting on the pipeline, so the
process tree is `bash → [python3, tee]`.
[conftest.py:102-111](../tests/conftest.py#L102-L111) sends `SIGTERM` to the
`bash` PID and `proc.wait()` returns cleanly — while `python3` /
`scada_selector` keep running, holding the DDS domain and port 8765.

**Impact.** Test teardown reports success while leaking a process per fixture.
Subsequent runs contend for the port and the domain, which presents as flaky
integration tests with no obvious cause. The same applies to Ctrl-C in
interactive use: the banner disappears, the component does not.

**Recommendation.** Drop `exec` and forward signals explicitly, or stop piping:

```bash
trap 'kill -TERM "$child" 2>/dev/null' TERM INT
python3 -m scada_web "${EXTRA_ARGS[@]}" >> "$LOG" 2>&1 &
child=$!
wait "$child"
```

Note this interacts with [CR-002](#cr-002) — if the Python side keeps its own
file handler, the redirect here is redundant and should be dropped entirely.

**Correction (rev 2).** Two things wrong with the recommendation above.

*The trap snippet does not work as written.* Bash runs a trap only when a
foreground `wait` returns, and that `wait` returns immediately with status
`128+n` — *before* the child has exited. A single `wait "$child"` therefore falls
through while the child is still shutting down, and the script exits without
reaping it. A correct trap version needs a second `wait` in a loop.

*The trap is avoidable entirely.* The pipeline is the only reason `exec` fails.
Redirect instead of piping and `exec` works, which means the component becomes
PID `$$` and signals reach it with no shell involvement:

```bash
# start-select.sh — process substitution keeps console output AND the log file.
exec > >(tee -a "$SCRIPT_DIR/logs/scada_select.log") 2>&1
exec "$SELECTOR_BIN" --config "$CONFIG" ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
```

After [CR-002](#cr-002) the two Python components need no redirect at all —
`exec python3 -m scada_web ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}` is the whole
tail. So **CR-002 should be fixed first**: it removes the pipeline from two of
the three scripts, and CR-001 reduces to the selector alone. The sequence in
rev 1 had this backwards.

The `${ARR[@]+"${ARR[@]}"}` form is also what collapses the duplicated
two-branch `if` present in all three scripts — it is `set -u`-safe on an empty
array, which is why the branch existed.

**Scope correction.** This finding cites `conftest.py` for the SIGTERM that
returns cleanly, which is right, but the fixture has two further process-handling
defects that compound it: [CR-034](#cr-034) and [CR-035](#cr-035). Fix all three
together — signal delivery alone still leaves the suite able to hang.

---

### CR-002
**Two writers on each Python log file; rotation silently stops working.**

- **Severity:** HIGH · **Area:** logging
- **Status:** **RESOLVED** by `e2dcd14`. Python keeps its `RotatingFileHandler`;
  the `tee` is gone from `start-web.sh` and `start-sim.sh`. Verified after a full
  suite run: every line in `logs/scada_web.log` appears exactly once. The
  duplicated `basicConfig` block noted in the correction below was **not**
  extracted — both components still carry their own copy.

**Finding.** [`__main__.py:23`](../scada_web/__main__.py#L23) attaches a
`RotatingFileHandler` to `logs/scada_web.log`, *and* the start script tees
stdout to the same path. Every line is written twice. When the handler rotates,
`tee` continues writing to the now-unlinked inode, so rotation stops bounding
disk usage and the newest lines land in a file nothing reads. Identical setup
for `sim.log` — [plc_publisher.py:55](../sim/plc_publisher.py#L55) plus
[start-sim.sh:168](../scripts/start-sim.sh#L168).

[copilot-instructions.md](../.github/copilot-instructions.md) documents the
5 MB / 3-backup rotation as working, and directs all debugging to start from
these files — so the primary diagnostic surface is the thing that's corrupted.

**Recommendation.** One writer per file. Either let Python own its log and drop
the tee (preferred — keeps rotation, and `logging` already emits to console via
`StreamHandler`), or drop the file handler and let `tee` own it. The selector
already works the second way, which is a reasonable house style to converge on
if you'd rather have one rule.

**Correction (rev 2).** Take the first option, not the house-style convergence,
and do it **before** [CR-001](#cr-001). Three reasons, in order of weight:

1. Dropping the file handler would make
   [copilot-instructions.md](../.github/copilot-instructions.md) wrong — it
   documents 5 MB / 3-backup rotation as a working property. Fixing the code is
   cheaper than amending the doc and losing the property.
2. It removes the pipeline from `start-web.sh` and `start-sim.sh`, which is most
   of [CR-001](#cr-001). Doing CR-001 first means writing signal-forwarding code
   for a pipeline that is about to be deleted.
3. `logging.basicConfig` already has a `StreamHandler`, so console output is
   unchanged — there is nothing to trade away.

Two details while in there:

- The `basicConfig` block is byte-identical in
  [`__main__.py:17-29`](../scada_web/__main__.py#L17-L29) and
  [`plc_publisher.py:50-62`](../sim/plc_publisher.py#L50-L62) and is worth
  extracting — but the sim's placement is load-bearing. Both the
  `sys.path.insert` and the logging setup must precede the `field_simulation` /
  `plc_types` imports, which is why those imports sit below it. Keep that
  ordering constraint as a comment if you extract; see [CR-033](#cr-033).
- `RotatingFileHandler` is not multi-process-safe. One writer per file makes that
  moot, but state it in a comment — a second process opening the same path
  reproduces exactly the corruption this finding is about.

---

### CR-003
**SR-003 reconciliation is implemented but never called.**

- **Severity:** HIGH · **Area:** [`scada_web/interest.py`](../scada_web/interest.py)
- **Status:** **RESOLVED** by `1a9ea5d`. Wired exactly as the rev 2 correction
  below specifies: `gateway.py` attaches a `DataWriterListener` to every writer
  and exposes `on_publication_matched(topic_name, status)`; `server.py`'s new
  `_on_publication_matched` checks `current_count_change == current_count` (the
  0→N transition) on the `ValueRequest` writer specifically, then sends PERIOD
  before replaying `reconcile()`'s ADDs — the exact ordering the correction's
  snippet showed. The `_last_period_ms` global the snippet still referenced was
  already gone by this point (removed in [CR-011](#cr-011)'s `2dbaecf`), so the
  applied fix has one fewer line than the snippet: no reset needed, since
  `_send_period` no longer suppresses on unchanged values in a way that matters
  here. `tests/test_reconcile.py` (new) asserts the transition check directly
  against a fake gateway — no DDS pipeline needed — and the full suite (61
  tests) passed against the live selector, confirming the listener attaches
  without disrupting normal startup matching.

**Finding.** [interest.py:3-7](../scada_web/interest.py#L3-L7) states that
SR-001 through SR-004 are implemented. SR-001, SR-002 and SR-004 are.
`reconcile()` ([interest.py:134](../scada_web/interest.py#L134)) has no caller —
nothing in [server.py](../scada_web/server.py) detects a selector restart or
replays the interest set.

[system-architecture.md:402](system-architecture.md#L402) says of SR-003:
*"the one most likely to be missed. Its symptom is a permanently blank
display."*

**Recommendation.** Either wire it — a publication-matched or liveliness-changed
listener on the `SelectedValue` reader, replaying `reconcile()` output as ADD
commands — or downgrade the module docstring to state plainly that SR-003 is
scaffolding and not yet active. The current docstring is the problem: it makes
the gap invisible to the next reader.

Wiring it also gives `active_periods()`, `client_count` and `active_uid_count`
their first callers, retiring three entries from [CR-019](#cr-019).

**Correction (rev 2).** The finding understates this. `reconcile()` is not merely
uncalled — **wiring it as the code stands today would not restore the
separation**, so SR-003 would still be unsatisfied. Two independent obstacles:

*`_last_period_ms` suppresses the write that matters.* It is a module global
([server.py:48](../scada_web/server.py#L48)) gating the `PERIOD` write at
[server.py:276](../scada_web/server.py#L276). A restarted selector has forgotten
the period; the gateway has not. Replaying the interest set through
`_on_interest_add` therefore emits every `ADD` and **skips the one `PERIOD`**,
leaving the selector on its own configured default. This is a third consequence of
the shape [CR-011](#cr-011) describes, alongside the two it already lists.

*The trigger in the recommendation is the wrong entity.* The
`presentation::value_request` profile is `RELIABLE` + **`VOLATILE`**
([dds/qos/profiles.xml](../dds/qos/profiles.xml)), so a `ValueRequest` written
before the selector's ControlPlane reader is matched is discarded, not queued.
A listener on the `SelectedValue` *reader* fires on the selector's data-plane
writer, which carries no guarantee about its control-plane reader — so the replay
can be issued into a void. The correct trigger is `on_publication_matched` on the
**`ValueRequest` writer**, `current_count` rising from 0: that is exactly the
moment a VOLATILE write can land.

```python
# server.py — PERIOD first, then the ADD burst, so no tag is briefly at the wrong rate.
def _reconcile_selector() -> None:
    """SR-003: ValueRequest writer (re)matched — replay the full interest set."""
    global _last_period_ms
    _last_period_ms = None                      # the restarted selector forgot it
    _send_period(_interest.min_separation_ms)   # unconditional, even if no uids
    for uid in _interest.reconcile():
        _send_add(uid)
```

This needs `_on_interest_add` split into `_send_add` / `_send_period`, which is
precisely what [CR-011](#cr-011) does. **Sequence CR-011 before CR-003** — after
it, CR-003 is roughly the dozen lines above. Rev 1 had CR-003 at step 5 and
CR-011 at step 8.

The fallback recommendation — downgrade the docstring — stands unchanged and is
the right move if this slips. It is also the more urgent half: an accurate
docstring is what lets the next reader find the gap.

---

### CR-004
**A separation change with nothing subscribed never reaches the wire.**

- **Severity:** MEDIUM · **Area:** [`scada_web/`](../scada_web/), [`UI/`](../UI/)
- **Status:** **RESOLVED** by `2dbaecf`, for free as this finding's own
  recommendation predicted. [CR-011](#cr-011)'s dedicated `on_period` callback
  fires unconditionally on every actual change, regardless of active-uid count.
  `tests/test_interest.py` covers the empty-refcount case as a regression test.

**Finding.** The `PERIOD` command is only ever written from inside
`_on_interest_add` ([server.py:276-283](../scada_web/server.py#L276-L283)), and
`set_min_separation` reaches it by looping over active uids
([interest.py:86-88](../scada_web/interest.py#L86-L88)). With `_refcounts`
empty, the loop body never runs and no `PERIOD` is written.

So pressing **SET PERIOD** in the UI before subscribing to anything updates the
server's internal state, logs `interest_min_separation_update`, reports
`minimum separation set to N ms` to the operator
([index.html:375](../UI/index.html#L375)) — and puts nothing on the wire. The
value is applied later, on the next `ADD`.

**Impact.** Deferred rather than lost, so it self-corrects. But the UI
affirmatively reports success for an action with no observable effect, which is
the kind of thing that costs an hour during commissioning.

**Recommendation.** Resolved for free by [CR-011](#cr-011) — a dedicated
`on_period` callback fires regardless of how many uids are active. If CR-011 is
deferred, at minimum make the UI status message conditional on there being an
active subscription.

**Correction (rev 2).** The fallback is the wrong shape. A client-side
`if (watchedCount > 0)` guard puts a copy of server-owned state in the browser,
which is a second instance of the [CR-011](#cr-011) problem rather than a
mitigation of it. If CR-011 slips, have the server acknowledge instead —
`{"ack": "min_separation", "ms": N, "applied": true|false}` — and let the UI
report "will apply on next subscribe" when `applied` is false. Take CR-011 and
neither is needed.

---

## Architecture and consistency

### CR-005
**The view layer's rename is a no-op on emitted JSON.**

- **Severity:** MEDIUM · **Area:** [`scada_web/views.py`](../scada_web/views.py)
- **Relates to:** [DD-053](design-decisions.md#dd-053)

**Finding.** Each view renames a wire field into a slim view name, and
`to_dict()` renames it straight back:

| DDS field | View attribute | Emitted JSON key |
|---|---|---|
| `smoothedValue` | `TagValue.value` | `smoothedValue` |
| `rawValue` | `TagValue.raw_value` | `rawValue` |
| `valueTime` | `TagValue.timestamp` | `valueTime` |
| `longName` | `TagMeta.name` | `longName` |
| `hostname` | `TagMeta.hostname` | `hostname` |

Evidence: [views.py:59-72](../scada_web/views.py#L59-L72) and
[views.py:87-102](../scada_web/views.py#L87-L102).

The emitted JSON is field-for-field the DDS shape, so DD-053's stated goal —
decoupling the client schema from the wire type — is not yet achieved. What the
layer currently buys is two names for every field. The reason is legible: the UI
reads `d.smoothedValue` and `d.longName`
([index.html:238](../UI/index.html#L238),
[:228](../UI/index.html#L228)), so keeping the wire names kept the browser
working through the migration.

**Recommendation.** Pick one and state it:

1. **Commit to the slim names.** Emit `{uid, value, rawValue, timestamp}` and
   update the ~6 UI call sites. The rename then means something, and the wire
   type can change without touching the browser — which is what DD-053 promises.
2. **Drop the intermediate names.** Name the dataclass fields for the wire and
   let `to_dict()` be `dataclasses.asdict()`. Honest about what it does, half
   the code, and DD-053 gets amended to "views are a projection, not a rename".
3. **Keep it, and comment it.** State that view names are internal and the JSON
   deliberately mirrors the wire for now.

Option 1 if the view layer is meant to earn its keep; option 2 if it isn't. What
exists now reads as option 1 stopped halfway.

**Correction (rev 2).** The framing is wrong, and it points at the wrong option.
The choice is not "does the view layer earn its keep" — **it already does, and not
through the rename.** `_value_t_to_scalar` and `_limits_to_dict`
([views.py:17-45](../scada_web/views.py#L17-L45)) flatten a five-member union into
a plain JSON number, and flatten all six `Limits_t` members with it. That
*is* the wire decoupling DD-053 asks for; [CR-023](#cr-023) is the evidence it
already works, since the browser's union-unwrapping code is now unreachable.

So **take option 2**, not option 1. Name the dataclass fields for the wire
(snake_case per house style: `smoothed_value`, `raw_value`, `value_time`), keep
`to_dict()` as an explicit snake→wire mapping in one place, and amend DD-053 to
say the projection is *shape* — union to scalar, subset of fields — not *naming*.
Zero UI churn.

Option 1 costs ~6 UI edits to buy insulation against IDL field renames, and
[DD-043](design-decisions.md#dd-043) makes the IDL the single source of truth —
those names are the most stable identifiers in the system. That is paying real
churn for protection against the thing least likely to move.

---

### CR-006
**Python `gen/` regenerates manually while C++ regenerates automatically.**

- **Severity:** MEDIUM · **Area:** build
- **Relates to:** [DD-043](design-decisions.md#dd-043), [DD-052](design-decisions.md#dd-052)

**Finding.** [CMakeLists.txt:38-43](../scada_select/CMakeLists.txt#L38-L43) runs
`connextdds_rtiddsgen_run` against `dds/idl/PlcValue.idl` on every C++ build,
explicitly so no hand-copied duplicate can drift.
[`scada_web/gen/PlcValue.py`](../scada_web/gen/PlcValue.py) is committed with
`DO NOT MODIFY` at the top and has no build-time equivalent.

DD-052 deliberately commits the generated output and records the command, so
this is not an undocumented step. The gap is **asymmetry plus no drift check**:
editing the IDL updates the C++ types automatically and leaves the Python types
stale, with no error at build time and no error at import time. The mismatch
first appears as a wire-level deserialization failure at runtime.

**Recommendation.** Keep the committed output (DD-052's reasoning holds — the
type set is static). Add a drift guard:

- `scripts/gen-python-types.sh` wrapping the DD-052 command, so regeneration is
  one command rather than a copy-paste from a decision log.
- A CI step, or a `make check-gen` target, that regenerates into a temp dir and
  fails on diff. This is the cheap version of DD-043's guarantee for the Python
  half.
- Reference both from [scada-web-architecture.md](../scada_web/docs/scada-web-architecture.md)
  alongside the codegen note.

`docs/questions.md:1447` already proposed exactly this shape (option D) for the
XML path; the argument transfers unchanged to the Python path.

**Correction (rev 2).** Make the drift guard a **pytest test**, not only a CI step
or a `make` target:

```python
# tests/test_gen_drift.py
def test_generated_python_types_match_idl(tmp_path):
    """DD-052 commits gen/ output; this is the guard DD-043 already gives C++."""
    subprocess.run([RTIDDSGEN, "-language", "python", "-d", str(tmp_path), IDL],
                   check=True)
    assert (tmp_path / "PlcValue.py").read_text() == GEN_PY.read_text()
```

A CI-only guard catches drift after it is pushed; a test catches it before, on the
machine that edited the IDL. This is also the one new test on the list that pays
for itself on first run.

**Sequencing.** This must land before [CR-007](#cr-007) — see the correction
there.

---

### CR-007
**The sim still hand-builds DynamicTypes, citing a superseded decision.**

- **Severity:** MEDIUM · **Area:** [`sim/plc_types.py`](../sim/plc_types.py)
- **Relates to:** [DD-002](design-decisions.md#dd-002) (SUPERSEDED), [DD-052](design-decisions.md#dd-052)

**Finding.** [`plc_types.py`](../sim/plc_types.py) builds all nine types through
`DynamicType` builders across 242 lines, and its docstring
([plc_types.py:6-8](../sim/plc_types.py#L6-L8)) justifies this by citing DD-002
— which [design-decisions.md:53](design-decisions.md#L53) marks *SUPERSEDED by
DD-052*.

After the migration the repo runs two different Python type strategies against
one IDL, and the hand-built one is justified by a rescinded decision.

**Recommendation.** Converge the sim onto generated types. Deletable once it
does: the nine `_build_*` functions (~130 lines), `set_value_t`, `get_value_t`,
`_set_char_array`, and the hand-copied constants
([plc_types.py:24-30](../sim/plc_types.py#L24-L30)) — the generated module binds
`MAX_STRING_VALUE_LENGTH`, `FIELD_DOMAIN_ID` and `PRESENTATION_DOMAIN_ID`
already ([PlcValue.py:20-38](../scada_web/gen/PlcValue.py#L20-L38)), which also
retires three [CR-019](#cr-019) entries.
[test_sim.py:109](../tests/test_sim.py#L109) and
[test_scada_select.py:33](../tests/test_scada_select.py#L33) build readers from
`build_plc_types()` and would simplify alongside.

**Counter-consideration, worth recording before acting.** The sim is currently
the only thing proving that an independently-written type definition and the
generated one agree on the wire. Converging removes that cross-check. That is
probably the right trade — the IDL becomes the single source, which is what
DD-043 wants — but it is a real property being given up, not a free cleanup, and
should be an explicit decision rather than a side effect.

**Correction (rev 2).** The counter-consideration deserves more weight than "worth
recording," and it produces a hard ordering constraint: **do [CR-006](#cr-006)
first.**

As things stand, the hand-built sim types are the *only* mechanism by which a
codegen or IDL mistake surfaces as a test failure instead of a field incident —
two independent implementations of one wire contract, checked against each other
every pipeline run. Converging the sim before CR-006's drift guard exists removes
that check while nothing has replaced it, which is a net loss in coverage even
though it is a net win in line count. With the guard in place, "the IDL is the
single source of truth" is actually enforced, and the cross-check can be given up
honestly.

Record it as a **new DD**, not an edit to DD-002. DD-002 is superseded; the
decision being made here is "surrender the independent-implementation cross-check
in exchange for a mechanical drift guard," which is a different question and needs
its own entry so the surrendered property stays findable.

---

### CR-008
**"period" and "minimum separation" name one concept in five places.**

- **Severity:** MEDIUM · **Area:** cross-cutting

**Finding.** The two terms do not mean the same thing, and the codebase uses
them interchangeably:

| Layer | Name used |
|---|---|
| IDL | `PeriodRequest_t.period_ms`, `Command_t::PERIOD` |
| C++ | `SelectionTable::set_period()` / `period_ms()`, over a field named `min_separation_ms_` ([SelectionTable.hpp:46-52](../scada_select/src/SelectionTable.hpp#L46-L52)) |
| Python | `set_min_separation()`, `default_min_separation_ms`, module global `_last_period_ms` |
| WebSocket | `set_period` and `set_min_separation` actions; `period_ms` and `min_separation_ms` keys |
| UI | `reqPeriod` input, "SET PERIOD" button, `set_min_separation` action, "Minimum separation" tooltip ([index.html:120](../UI/index.html#L120)) |

A reader tracing one value crosses four vocabularies. The C++ accessor pair is
the sharpest case: a method called `period_ms()` returning a field called
`min_separation_ms_`.

**Recommendation.** Standardize on **`min_separation_ms`** everywhere you
control — Python, C++, UI, docs — and keep `period_ms` only where the IDL forces
it, at the ValueRequest construction site. Note the translation once, at that
boundary. Do this before [CR-016](#cr-016), which it largely subsumes.

**Correction (rev 2).** Split it and do the compiler-checked half first. The C++
accessor rename (`set_period`/`period_ms` → `set_min_separation`/
`min_separation_ms`, aligning with the existing `min_separation_ms_` field) is
zero-risk: every missed call site is a build error. The Python and UI renames are
string-matched and cross the WebSocket protocol, so they need [CR-016](#cr-016)
settled in the same change or the two will disagree mid-flight.

Leave the IDL alone. Renaming `PeriodRequest_t.period_ms` or `Command_t::PERIOD`
is a wire-compatibility change for a cosmetic gain, and the recommendation above
already accepts `period_ms` at that boundary.

---

### CR-009
**Selector log style diverges from the Python components.**

- **Severity:** LOW · **Area:** [`scada_select/src/main.cxx`](../scada_select/src/main.cxx)

**Finding.** Commit `67eaff7` is *"add structured logging to all components"*.
The Python side emits `key=value` (`ws_connected client=%s`,
`reader_created topic=%s type=%s`). The selector emits English prose to
`std::cerr` behind an integer verbosity dial —
[main.cxx:357-360](../scada_select/src/main.cxx#L357-L360). No single grep
covers both, so the cross-component sweep that
[copilot-instructions.md](../.github/copilot-instructions.md) prescribes
(`grep -i error logs/*.log`) only half works.

**Recommendation.** Low urgency, but "all components" is not yet true. Either
bring the selector to `key=value` or amend the claim. If the selector converges,
`replaced_dropped_sample_count` and the write-timeout counters are the lines
that most benefit — they are the ones you would want to chart.

**Correction (rev 2).** Scope the conversion rather than treating it as
all-or-nothing. Convert only the **error and counter** lines — the ones
`grep -i error logs/*.log` is meant to catch, and the ones worth charting. The
verbosity-gated narration can stay prose; it is read by a human watching a terminal,
not swept. Roughly eight lines in
[main.cxx](../scada_select/src/main.cxx) qualify, e.g.
[:357-360](../scada_select/src/main.cxx#L357-L360) becoming
`replaced_dropped_samples count=N total=M`. That makes "all components" true for the
purpose the claim is used for, at a fraction of the churn.

---

### CR-010
**The same `DataState` is constructed and justified twice.**

- **Severity:** LOW · **Area:** [`scada_select/src/`](../scada_select/src/)

**Finding.** `kUnreadAnyInstance`
([main.cxx:44-47](../scada_select/src/main.cxx#L44-L47)) and an identical local
in [MetaDataPlane.cxx:14-17](../scada_select/src/MetaDataPlane.cxx#L14-L17),
each preceded by its own paragraph explaining why it is not
`DataState::new_data()`. The rationale is correct and worth keeping — but it is
written twice, so it can be updated once.

**Recommendation.** One `constexpr`/`inline` constant in a shared header, with
the explanation attached to it. Both call sites then reference the single
statement of the rule.

---

## Simplicity

### CR-011
**Separation changes fan out through the per-uid ADD callback.**

- **Severity:** MEDIUM · **Area:** [`scada_web/interest.py`](../scada_web/interest.py), [`scada_web/server.py`](../scada_web/server.py)
- **Status:** **RESOLVED** by `2dbaecf`, per the rev 2 correction's shape:
  `AddCallback`/`DeleteCallback`/`PeriodCallback` all take a single argument,
  `set_min_separation` fires `on_period` once directly, and `_last_period_ms`
  is deleted. This is the keystone commit the rest of rev 4 built on --
  [CR-004](#cr-004) closed as a side effect, and [CR-003](#cr-003) became
  wireable in `1a9ea5d`.

**Finding.** [interest.py:86-88](../scada_web/interest.py#L86-L88) implements
"change the global separation" by re-firing `on_add(uid, period)` for every
active uid. Downstream
([server.py:264-283](../scada_web/server.py#L264-L283)) each of those writes a
redundant `ADD`, and a module-level `_last_period_ms` dedupes the one `PERIOD`
write that matters. Changing one global scalar with 200 tags watched emits 200
redundant `ADD` commands and one `PERIOD`.

Two consequences follow from the shape: [CR-004](#cr-004) (empty-set case never
reaches the wire), and `_last_period_ms` being a second copy of state
`InterestManager` already owns.

**Recommendation.** Add a third callback alongside `on_add` / `on_delete`:

```python
PeriodCallback = Callable[[int], None]   # min_separation_ms → send PERIOD
```

`set_min_separation` then fires it once, directly. That removes the fan-out, the
redundant ADDs, the global, and CR-004 — and it makes the code agree with the
model, which already treats separation as global
([interest.py:130-132](../scada_web/interest.py#L130-L132)).

**Correction (rev 2).** This is the keystone item, and rev 1 scheduled it too late
(step 8). It is a prerequisite for a *correct* [CR-003](#cr-003) — see the
correction there — as well as closing [CR-004](#cr-004) and deleting
`_last_period_ms`. Move it ahead of CR-003.

One addition: `on_add` should also **lose its second parameter**.

```python
AddCallback    = Callable[[int], None]   # uid → send ADD
DeleteCallback = Callable[[int], None]   # uid → send DELETE
PeriodCallback = Callable[[int], None]   # min_separation_ms → send PERIOD
```

Leaving `on_add(uid, min_separation_ms)` in place keeps signalling that an `ADD`
carries a period, which is the misreading that produced the fan-out in the first
place. Three consequences follow from the shape, not two — the third is CR-003's
suppressed `PERIOD` replay.

---

### CR-012
**`_TYPE_MAP` hand-maintains what the generated module already binds.**

- **Severity:** LOW · **Area:** [`scada_web/gateway.py`](../scada_web/gateway.py)

**Finding.** [gateway.py:36-40](../scada_web/gateway.py#L36-L40) maps
`"PLC::MetaData" → PLC.MetaData` by hand, and
[gateway.py:124](../scada_web/gateway.py#L124) raises *"add it to _TYPE_MAP"*.
But `PLC` is `idl.get_module("PLC")` and the generated file binds every type
onto it already ([PlcValue.py:117](../scada_web/gen/PlcValue.py#L117),
[:135](../scada_web/gen/PlcValue.py#L135),
[:188](../scada_web/gen/PlcValue.py#L188)).

**Recommendation.**

```python
def _resolve_type(self, type_name: str) -> type:
    _, _, name = type_name.rpartition("::")
    cls = getattr(PLC, name, None)
    if cls is None:
        raise KeyError(f"unknown type '{type_name}' — not in the generated PLC module")
    return cls
```

A new topic type then works with no code change, and the registry has one copy
instead of two.

**Correction (rev 2). The snippet above is unsafe as written — do not apply it
verbatim.** The diagnosis is right; the replacement is a regression.

`PLC` is an `idl.get_module("PLC")` namespace, and the generated file binds far
more than types onto it: integer constants
([PlcValue.py:22-38](../scada_web/gen/PlcValue.py#L22-L38)), type aliases that are
plain builtins (`PLC.Hostname_t = str`,
[:42](../scada_web/gen/PlcValue.py#L42)), and **topic-name string constants**
(`PLC.MetaDataTopic = "PLC::MetaDataTopic"`,
[:100](../scada_web/gen/PlcValue.py#L100),
[:139](../scada_web/gen/PlcValue.py#L139)).

That last one is the live hazard. [config.py:154](../scada_web/config.py#L154)
defaults `type_name` to the *topic* name when `type:` is omitted, so a config
entry like `- name: "PLC::SelectedValueTopic"` with no `type:` resolves
`getattr(PLC, "SelectedValueTopic")` to the **string**
`"PLC::SelectedValueTopic"`. The `is None` guard passes, and the failure lands
inside `dds.Topic(dp, name, str)` as an obscure type error — strictly worse than
today's `KeyError: add it to _TYPE_MAP`.

The fix needs a positive check that the resolved object is an IDL type, not merely
non-`None`:

```python
def _resolve_type(self, type_name: str) -> type:
    _, _, name = type_name.rpartition("::")
    cls = getattr(PLC, name, None)
    if not isinstance(cls, type) or not hasattr(cls, "__idl_type_support__"):
        raise KeyError(
            f"'{type_name}' does not name a type in the generated PLC module")
    return cls
```

Verify the attribute name `rti.idl` actually stamps on generated classes at the
pinned Connext Python version before committing — `idl.get_type_support(cls)` is
the documented accessor but raises rather than returning `None` on a non-type, so
it needs the `isinstance` guard ahead of it either way. If neither can be pinned
down cheaply, an explicit tuple of permitted types is a legitimate compromise: it
still has one copy of the list, unlike `_TYPE_MAP`, which has a second copy of the
names.

---

### CR-013
**`_sample_to_view_dict` dispatches by `isinstance` with a silent fallback.**

- **Severity:** LOW · **Area:** [`scada_web/server.py`](../scada_web/server.py)
- **Status:** **RESOLVED** by `2dbaecf`, exactly per the rev 2 correction: a
  `_VIEW_DISPATCH: dict[type, Any]` keyed on `type(data)` (not `isinstance`),
  with a comment noting generated IDL types are not subclassed so exact-type
  dispatch loses no coverage. The old fallback's `KeyError` is now raised
  instead of returning `{"raw": str(data)}`.

**Finding.** [server.py:299-306](../scada_web/server.py#L299-L306) is an
`isinstance` chain ending in `return {"raw": str(data)}` — so a topic whose type
is not yet handled ships a stringified Python repr to the browser instead of
failing.

**Recommendation.** A `{PLC.IdValue: TagValue.from_idvalue, ...}` dispatch dict
plus a raised `KeyError` is both shorter and louder. A malformed payload
reaching the browser is strictly worse than a 500 on an unhandled type.

**Correction (rev 2).** The dict must be keyed on `type(data)`, not looked up by
`isinstance` — otherwise it is the same chain with extra steps. Generated IDL types
are not subclassed, so exact-type dispatch loses nothing here; say so in a comment
so the difference is deliberate rather than accidental.

---

### CR-014
**Three start scripts duplicate ~75 lines each, and have drifted.**

- **Severity:** MEDIUM · **Area:** [`scripts/`](../scripts/)

**Finding.** [start-sim.sh](../scripts/start-sim.sh),
[start-select.sh](../scripts/start-select.sh) and
[start-web.sh](../scripts/start-web.sh) each carry their own copy of
`find_connext_home`, `find_rtisetenv` and `find_license`. They have already
diverged: `start-sim.sh` keeps numbered step comments and an intermediate
`newest` variable the others dropped, and emits error text
(`Searched: ~/rti_connext_dds-*, /opt/...`) the others do not. A fourth copy of
the license search lives in
[conftest.py:34-56](../tests/conftest.py#L34-L56), under a comment stating it
*"mirrors scripts/start-*.sh find_license"* — which is the tell.

**Recommendation.** Extract `scripts/lib/connext-env.sh`, source it from all
three, and have the test fixture shell out to it rather than reimplement the
search in Python. The Windows `.bat` equivalents deserve the same treatment
if they are still maintained.

**Correction (rev 2).** The fixture should not shell out to it — it should
**delete its copy outright.** `_find_and_set_license()`
([conftest.py:34-59](../tests/conftest.py#L34-L59)) exists only to pre-seed
`RTI_LICENSE_FILE` in the environment, and all three fixtures already launch their
component via `bash scripts/start-*.sh`
([conftest.py:118](../tests/conftest.py#L118),
[:134](../tests/conftest.py#L134), [:151](../tests/conftest.py#L151)) — which does
the search itself. The fourth copy is not merely duplicated, it is redundant.
Shelling out would add a subprocess per session and an stdout-parsing contract to
replace something that can just be removed.

---

### CR-015
**`serve-ui.ps1` exists twice, byte-identical.**

- **Severity:** LOW · **Area:** [`scripts/`](../scripts/), [`UI/`](../UI/)

**Finding.** [`UI/serve-ui.ps1`](../UI/serve-ui.ps1) and
[`scripts/serve-ui.ps1`](../scripts/serve-ui.ps1) are identical (verified by
`diff`).

**Recommendation.** Keep the one in `scripts/` — it matches the location of
every other launcher — and delete the other.

**Correction (rev 2).** `grep -ri serve-ui` across docs, `README`s and the `.bat`
launchers first. A document pointing at `UI/serve-ui.ps1` is the only way this
deletion bites, and it is the cheapest possible check.

---

### CR-016
**The WebSocket protocol accepts four aliases for one field.**

- **Severity:** MEDIUM · **Area:** [`scada_web/server.py`](../scada_web/server.py)

**Finding.** [server.py:192](../scada_web/server.py#L192) accepts both
`set_min_separation` and `set_period` as actions;
[server.py:199-226](../scada_web/server.py#L199-L226) accepts `period_ms` and
`min_separation_ms` at message level *and* nested per-uid, reconciling the
nested case with a set comprehension that raises if two uids disagree — for a
field the protocol defines as global.

That is 27 lines of alias reconciliation, and every accepted alias is a variant
that must stay tested.

**Recommendation.** After [CR-008](#cr-008) settles the vocabulary, accept one
action name and one key. Reject the rest with a clear error rather than
absorbing them. The per-uid nested form should go first — it encodes a
per-uid model the system does not have.

**Correction (rev 2).** The compatibility cost is lower than "every accepted alias
is a variant that must stay tested" implies: **the shipped UI only ever sends one
form.** `submitPeriod` sends `{action: "set_min_separation", period_ms: N}`
([index.html:370](../UI/index.html#L370)) and `subscribeUid` sends no separation key
at all. Every other branch in
[server.py:199-226](../scada_web/server.py#L199-L226) is unreachable from the only
client that exists — so this is dead-code removal, not a protocol break, and it
does not need a deprecation window.

Take the per-uid nested form first as recommended: the set comprehension plus
disagreement check ([server.py:206-217](../scada_web/server.py#L206-L217)) is 12 of
the 27 lines, defending a model the system does not have, against a client that
never sends it.

---

### CR-017
**`create_app()` mutates a module-level singleton.**

- **Severity:** MEDIUM · **Area:** [`scada_web/server.py`](../scada_web/server.py)

**Finding.** `app` is constructed at import time
([server.py:38](../scada_web/server.py#L38)), routes are attached by decorator,
and `create_app()` assigns four module globals and mutates that singleton
([server.py:51-89](../scada_web/server.py#L51-L89)). Calling it twice adds CORS
twice and re-mounts the static directory. `_gateway`, `_interest`, `_config`,
`_ws_clients` and `_last_period_ms` are all module state.

**Impact.** There is no way to stand up an isolated instance in-process, which
is why every REST and WebSocket test spawns a three-process DDS pipeline. The
current suite takes tens of seconds and depends on an RTI license to assert
things like "unknown topic returns 404".

**Recommendation.** Move construction inside `create_app()`: routes on an
`APIRouter`, dependencies on `app.state`. The REST and WS surfaces then become
`TestClient` tests measured in milliseconds, and the DDS pipeline is reserved
for what genuinely needs it. This is the largest item on the list — worth it if
the suite is expected to grow, deferrable if not.

**Correction (rev 2).** The impact statement undersells it. Slow tests are the
symptom; the cause is that **nothing in `scada_web` is unit-testable at all.**
`tests/test_interest.py` is fast and green only because `InterestManager` happens
to be a pure object with no import-time DDS dependency. Every other module in the
package requires an RTI license and a three-process pipeline to exercise one line.

That is the mechanism behind several other findings on this list, not a separate
concern: [CR-003](#cr-003) shipped unwired, [CR-025](#cr-025)'s `KIND_STRING` decode
is unexercised, and [CR-031](#cr-031)'s assertions were guarded away — in each case
because there was no cheap place to put the test that would have caught it. So the
"deferrable if the suite is not expected to grow" framing inverts the causation:
the suite is not growing *because* of this item.

Still schedule it late — after [CR-011](#cr-011) and [CR-016](#cr-016) have settled
the shapes it would otherwise move twice — and pair it with
[CR-018](#cr-018).

---

### CR-018
**`@app.on_event` is deprecated in the pinned FastAPI range.**

- **Severity:** LOW · **Area:** [`scada_web/server.py`](../scada_web/server.py)

**Finding.** [server.py:81](../scada_web/server.py#L81) and
[:85](../scada_web/server.py#L85) use `@app.on_event("startup"/"shutdown")`,
deprecated since FastAPI 0.93. [`requirements.txt`](../requirements.txt) pins
`fastapi>=0.100`, so every run emits a `DeprecationWarning`.

**Recommendation.** Move to the `lifespan` context manager. Natural to do
alongside [CR-017](#cr-017), since both concern app construction.

**Correction (rev 2).** Not merely natural — do it *only* alongside CR-017, never
before. `lifespan` is passed to the `FastAPI()` constructor, and that constructor
call is the import-time singleton at
[server.py:38](../scada_web/server.py#L38) which CR-017 exists to move. Converting
this first means editing the same line twice.

---

### CR-019
**Dead code inventory.**

- **Severity:** MEDIUM (in aggregate) · **Area:** cross-cutting
- **Status:** **RESOLVED** by `2dbaecf`. All items deleted except the two
  exceptions this finding itself named: `topic_by_name` (kept, per
  [CR-R02](#cr-r02)) and the `interest.py` accessors
  (`active_periods`/`client_count`/`active_uid_count`/`reconcile`) --
  `reconcile` in particular now has a caller as of [CR-003](#cr-003)'s
  `1a9ea5d`. `pyflakes` clean across `scada_web/`, `sim/`, `tests/` afterward.

**Finding.** Confirmed unreferenced across the tree (`grep` over all
first-party sources; `pyflakes` for imports):

| Location | Item | Note |
|---|---|---|
| [config.py:94-110](../scada_web/config.py#L94-L110) | `participant_by_name`, `topic_by_name`, `writer_by_name` | no callers |
| [config.py:32](../scada_web/config.py#L32) | `ParticipantConfig.qos_xml` | parsed, never read |
| [config.py:67-68](../scada_web/config.py#L67-L68) | `websocket_path`, `rest_prefix` | parsed, present in [config.yaml:74-75](../scada_web/config.yaml), never read — routes hardcode `/ws` and `/api/v1` |
| [config.py:36-49](../scada_web/config.py#L36-L49) | `FilterConfig`, `TopicConfig.filter` | plumbed to the gateway, used by no config file |
| [gateway.py:21](../scada_web/gateway.py#L21) | `from dataclasses import field` | unused import |
| [gateway.py:77](../scada_web/gateway.py#L77) | `_running` | assigned three times, never read |
| [gateway.py:222-225](../scada_web/gateway.py#L222-L225) | `writers` property | no callers |
| [interest.py:130-151](../scada_web/interest.py#L130-L151) | `active_periods`, `reconcile`, `client_count`, `active_uid_count` | `reconcile` is [CR-003](#cr-003) |
| [field_simulation.py:49](../sim/field_simulation.py#L49) | `Tag.noise_stddev` | noise is baked into `value_fn` via `_noisy` |
| [field_simulation.py:54](../sim/field_simulation.py#L54) | `smoothed_value(self, t, ...)` | `t` unused |
| [plc_types.py:29-30](../sim/plc_types.py#L29-L30) | `FIELD_DOMAIN_ID`, `PRESENTATION_DOMAIN_ID` | every call site hardcodes `15`/`16`; see [CR-007](#cr-007) |
| [conftest.py:14](../tests/conftest.py#L14), [test_e2e.py:11](../tests/test_e2e.py#L11), [test_scada_web.py:12](../tests/test_scada_web.py#L12) | `import asyncio` | unused |
| [test_sim.py:12,22](../tests/test_sim.py#L12) | `math`, `Limits`, `Tag` | unused |

**Recommendation.** Delete, with two exceptions worth keeping deliberately:
`topic_by_name` is the natural helper if the type endpoint ever returns
([CR-R02](#cr-r02)), and the `interest.py` accessors survive if
[CR-003](#cr-003) is wired.

Config that silently does nothing is the worst item here —
`websocket_path` and `rest_prefix` appear in a committed YAML file and invite an
operator to change them, with no effect and no warning. Delete the keys from
both the dataclass and the YAML, or honour them.

**Correction (rev 2).** Two entries are characterised wrongly; the rest of the
table verified as stated.

*`FilterConfig` / `TopicConfig.filter` is not "plumbed to the gateway."* It is
parsed at [config.py:156](../scada_web/config.py#L156) and then **dropped** —
`_create_readers` ([gateway.py:136-153](../scada_web/gateway.py#L136-L153)) never
reads `tc.filter`. So this is not a feature awaiting a config file that uses it;
there is no implementation behind it in either layer. Content-filtered topics would
be a real feature, but nothing here is a partial one. Delete it outright, and note
that it belongs in the same class as `websocket_path` — config that validates and
does nothing.

*`websocket_path` / `rest_prefix` — agreed, and this is correctly identified as the
worst entry.* Verified: parsed at
[config.py:185-186](../scada_web/config.py#L185-L186), present under a
`# --- Web server ---` heading in [config.yaml:71-75](../scada_web/config.yaml),
never read. An operator who successfully changes `port` in that same block has
every reason to expect the two keys beneath it to work the same way. Delete from
dataclass and YAML in one commit.

The docstring item folded in from [CR-020](#cr-020) —
[config.py:6-7](../scada_web/config.py#L6-L7) still naming an XML type library as
the source of types — is in this same file and should ride along.

---

### CR-020
**`types_xml` plumbing outlived the XML type library.**

- **Severity:** LOW · **Area:** [`scada_web/config.py`](../scada_web/config.py)
- **Status:** **RESOLVED** by `2dbaecf`. Field, parser, and docstring paragraph
  removed together, folded into the [CR-019](#cr-019) sweep as recommended.

**Finding.** Commit `015e653` removed the `types_xml` validation, but the field
([config.py:83](../scada_web/config.py#L83)) and the parser for a `types:`
section ([config.py:143-144](../scada_web/config.py#L143-L144)) remain, and
[config.yaml](../scada_web/config.yaml) no longer has that section. The module
docstring ([config.py:6-7](../scada_web/config.py#L6-L7)) still describes the
XML type library as the source of types.

**Recommendation.** Remove the field, the parse, and the docstring paragraph.
Fold into the [CR-019](#cr-019) sweep.

---

## Clarity and cost

### CR-021
**Sample payload is serialized once per interested client.**

- **Severity:** LOW · **Area:** [`scada_web/server.py`](../scada_web/server.py)
- **Status:** **RESOLVED** by `2dbaecf`, per the rev 2 correction: the
  interested-client list is computed first (SR-004 demux stays inside the
  loop), then the payload is built once and reused, with an early return when
  no client is interested rather than an unconditional hoist.

**Finding.** [server.py:246-253](../scada_web/server.py#L246-L253) builds the
payload *inside* the per-client loop, so `_sample_to_view_dict()` and
`json.dumps()` run N times for N interested clients, producing N identical
strings.

**Recommendation.** Hoist both above the loop; build once, send many. Worth
doing while the code is being touched for [CR-011](#cr-011).

**Correction (rev 2).** Only the payload construction hoists — the
`_interest.is_interested(client_id, uid)` check at
[server.py:247](../scada_web/server.py#L247) must stay inside the loop, since it is
the SR-004 demux. Building the payload unconditionally also means it is now built
for samples no client wants, so guard the hoist on there being at least one
interested client, or accept one wasted serialization per uninteresting sample.
Given the value stream is periodic and mostly *is* wanted, the simple hoist is
right; the guard is worth a comment either way.

---

### CR-022
**The UI rebuilds all 500 rows on every pushed sample.**

- **Severity:** MEDIUM · **Area:** [`UI/index.html`](../UI/index.html)

**Finding.** `render()` is called per WebSocket message
([index.html:428](../UI/index.html#L428)) and reassigns
`rowsEl.innerHTML` for the full tag set
([index.html:303](../UI/index.html#L303)). At a 250 ms separation across several
watched tags this is continuous full-table layout, and it destroys focus and
text selection on every frame.

**Recommendation.** Coalesce renders behind `requestAnimationFrame` (one paint
per frame regardless of arrival rate), or patch only the changed row's cells.
The first is a few lines and fixes the common case.

**Correction (rev 2).** The two options are not interchangeable, and the finding
lists two distinct problems that they do not both solve. `requestAnimationFrame`
caps repaint *rate*:

```js
let renderPending = false;
function scheduleRender() {
  if (renderPending) return;
  renderPending = true;
  requestAnimationFrame(() => { renderPending = false; render(); });
}
```

It does **not** fix the focus and text-selection loss, because
`rowsEl.innerHTML = html` ([index.html:303](../UI/index.html#L303)) still discards
and rebuilds every node — just less often. Only per-cell patching fixes that.

So: take the rAF coalesce for the layout cost (five lines, fixes the common case as
stated), and treat focus/selection preservation as a separate question that depends
on whether operators actually interact with that table during live updates. Worth
asking before spending the effort — if they do not, rAF is the whole fix.

---

### CR-023
**`unionScalar` re-derives a wire contract the server no longer emits.**

- **Severity:** LOW · **Area:** [`UI/index.html`](../UI/index.html)

**Finding.** [index.html:208-215](../UI/index.html#L208-L215) probes five union
member names to unwrap a `Value_t`. Since the migration,
[views.py](../scada_web/views.py) scalarizes both `Value_t` and every member of
`Limits_t` before serialization, so the browser only ever receives plain
numbers. The function still works — the `typeof u !== "object"` guard passes
scalars through — but the member probe is now unreachable.

**Recommendation.** Reduce to the scalar path and delete `VALUE_MEMBERS`. This
also removes the last place where the union layout is encoded in two languages.

**Correction (rev 2).** Sequence this **after** [CR-005](#cr-005) — if CR-005 were
resolved as option 1 the emitted keys change, and this function's callers move in
the same edit. (Rev 2's correction to CR-005 recommends option 2, which leaves the
keys alone, but settle that first regardless.)

Keep the `typeof u !== "object"` guard at
[index.html:210](../UI/index.html#L210) — it is precisely what makes the reduction
safe, and deleting it alongside `VALUE_MEMBERS` would remove the check rather than
the dead branch. Add a comment naming
[`views.py:_value_t_to_scalar`](../scada_web/views.py#L17) as the server-side
guarantee, so the next reader does not restore the probe defensively.

---

### CR-024
**Runtime dataclasses lost their type annotations to `Any`.**

- **Severity:** LOW · **Area:** [`scada_web/gateway.py`](../scada_web/gateway.py)

**Finding.** `TopicRuntime.topic`/`reader` and `WriterRuntime.topic`/`writer`
are annotated `Any` ([gateway.py:43-56](../scada_web/gateway.py#L43-L56)); they
were `dds.DynamicData.Topic` / `dds.DynamicData.DataReader` before the
migration. Losing annotations in the change whose purpose is static typing is
worth correcting.

**Recommendation.** Annotate as `dds.Topic` / `dds.DataReader` (or the
parameterized generics, if the Connext Python stubs support them at the pinned
version).

**Correction (rev 2).** Do not spend time establishing whether the generics work —
the plain non-generic annotations are already the entire win over `Any`, and
`WriterRuntime.writer` needs `dds.DataWriter` alongside the two named. If the
parameterized forms turn out to be supported, they are a follow-up, not a
precondition.

---

### CR-025
**The `KIND_STRING` decode path is unverified and unexercised.**

- **Severity:** LOW · **Area:** [`scada_web/views.py`](../scada_web/views.py)
- **Status:** **RESOLVED** by `2dbaecf`. New `tests/test_views.py` constructs
  `PLC.Value_t(stringValue=list("hi"))` directly and confirms `rti.idl` yields
  one-character `str` (not integers) plus a NUL-padding-strip case -- no DDS
  pipeline or license needed, as the rev 2 correction predicted.

**Finding.** [views.py:29-31](../scada_web/views.py#L29-L31) does
`"".join(chars)` on `v.stringValue`. Whether `rti.idl` yields a sequence of
one-character `str` or of integers is not determinable from the generated stubs,
and the sim only ever publishes `float64`, so nothing exercises the branch. It
will either work or raise `TypeError` the first time a string-valued tag
appears.

**Recommendation.** A two-line unit test constructing a `PLC.Value_t` with
`KIND_STRING` and asserting the round trip. Cheap, and it converts an unknown
into a known.

**Correction (rev 2).** Promote this within the `LOW` batch — it is the highest
value-per-line item on the list. It needs no DDS pipeline and no license: construct
`PLC.Value_t` directly and call `_value_t_to_scalar`. That makes it one of only two
things in `scada_web` currently testable without the three-process fixture (the
other being `InterestManager`; see the [CR-017](#cr-017) correction).

The concrete risk is worth naming: if `rti.idl` yields `char[N]` as a sequence of
integers rather than one-character `str`, `"".join(chars)`
([views.py:31](../scada_web/views.py#L31)) raises `TypeError` — and the first
string-valued tag in the catalogue is what discovers it. Do this in the
[CR-019](#cr-019) sweep.

---

### CR-026
**`InterestManager` validates separation with a duplicated block.**

- **Severity:** LOW · **Area:** [`scada_web/interest.py`](../scada_web/interest.py)
- **Status:** **RESOLVED** by `2dbaecf`. `interest.py`'s two blocks collapsed
  into `_require_positive_separation()`, kept as the canonical statement of the
  rule; `config.py`, `server.py`, and `config.yaml` each still validate at
  their own layer per the rev 2 correction, but their comments now
  cross-reference `interest.py` instead of restating the ValueRequest
  contract.

**Finding.** [interest.py:51-55](../scada_web/interest.py#L51-L55) and
[interest.py:76-80](../scada_web/interest.py#L76-L80) are the same four-line
check under the same six-line comment, verbatim.

**Recommendation.** Extract `_require_positive_separation(ms)`. The comment is
good and should survive — it just needs one home.

**Correction (rev 2).** The rule is stated **four** times, not twice. Beyond the two
in `interest.py`, the same `PERIOD 0` semantics are explained again at
[config.py:74-77](../scada_web/config.py#L74-L77) (with its own `_validate` check at
[:195-196](../scada_web/config.py#L195-L196)), at
[server.py:218-225](../scada_web/server.py#L218-L225) (six lines, longest of the
four), and once more in [config.yaml:16-21](../scada_web/config.yaml).

The two in `interest.py` are straightforward duplication and should collapse to one
function. The other three are different layers — config load, protocol edge, domain
model — and each genuinely needs its own check, so the *validation* should stay
triplicated. The *explanation* should not: pick one canonical statement (the domain
model, in `interest.py`) and have the others cross-reference it in a single line
rather than restating the ValueRequest contract.

---

## Documentation

### CR-027
**`scada-web-architecture.md` still lists work that is now done.**

- **Severity:** LOW · **Area:** [`scada_web/docs/`](../scada_web/docs/)

**Finding.**
[scada-web-architecture.md:40](../scada_web/docs/scada-web-architecture.md#L40)
lists `mapping.py [DEPRECATED]` in the module tree, and
[:327](../scada_web/docs/scada-web-architecture.md#L327) carries *"Remove
`mapping.py`"* as pending work. Both were completed in `015e653`.

**Recommendation.** Drop the module-tree entry and move the pending-work item to
done. Add the regeneration command from [CR-006](#cr-006) while in the file.

---

### CR-028
**OQ-38 describes an XML dependency that no longer exists.**

- **Severity:** LOW · **Area:** [`docs/questions.md`](questions.md)
- **Status:** **PARTIAL** — `b78e934` deleted `dds/idl/PlcValue.xml`, resolving the
  second half (the unreferenced artifact, and the drift source the correction
  below argued was the substantive part). Verified: a full suite run is green with
  the file absent, confirming nothing first-party loaded it. **The OQ-38 amendment
  was not made** — [questions.md:1562](questions.md#L1562) still states that
  `scada_web/config.yaml` references the XML, and as of `b78e934` that file no
  longer exists either, so the entry is now doubly stale.

**Finding.** [questions.md:1562](questions.md#L1562) states that
`scada_web/config.yaml` references `dds/idl/PlcValue.xml`. It no longer does
(commits `c5ed510`, `015e653`). `dds/idl/PlcValue.xml` itself is now unreferenced
by any first-party component — the C++ side generates from the IDL directly and
the Python side uses `gen/`.

**Recommendation.** Amend OQ-38 with a superseding note. Separately, decide
whether `dds/idl/PlcValue.xml` should stay: it is now an artifact nothing loads,
and an unreferenced generated file is a future drift source. If it is retained
for external tooling (WIS, diagnostics), say so where it lives.

**Correction (rev 2).** The second half is the substantive half and should not read
as an aside. An unreferenced generated copy of the type library is exactly the
failure class [CR-006](#cr-006) is being fixed to prevent, and
[CR-R03](#cr-r03) is what it looks like once it has drifted — a stale second copy
missing the union-based `ValueRequest`, the `PERIOD` command, and the domain
constants. `dds/idl/PlcValue.xml` is now in the same position `scada_web/PlcValue.xml`
was in before `c5ed510`, minus the shadowing.

So: delete it, or add a header comment naming the consumer that justifies it.
"Decide whether it should stay" is not a resolution — leaving it undecided is how
CR-R03 happened.

---

## Test quality

### CR-029
**Two tests skip forever against a deleted endpoint.**

- **Severity:** MEDIUM · **Area:** [`tests/test_e2e.py`](../tests/test_e2e.py)
- **Status:** **RESOLVED** by `2dbaecf`. `TestE2ETopicType` deleted outright
  (both tests and its `_topic_url` helper), and its now-orphaned
  `urllib.parse` import removed with it. [CR-036](#cr-036) landed in the same
  commit, closing the mechanism this finding names as a live defect in its own
  right.

**Finding.** `TestE2ETopicType`
([test_e2e.py:234-267](../tests/test_e2e.py#L234-L267)) targets
`/api/v1/topics/{name}/type`, removed in `015e653`. The static-files mount at
`/` catches the unmatched route and returns 404, which both tests interpret as
`pytest.skip("Type endpoint not wired for topic-name lookup")`.

They were already permanently skipped before the migration — that skip is what
first revealed [CR-R02](#cr-r02). Now the endpoint is gone entirely and they can
never run.

**Recommendation.** Delete the class. A skip that cannot un-skip is worse than
no test: it reports as a green-ish suite while covering nothing.

**Correction (rev 2).** Agreed without reservation — and the skip already did its
one useful job, since it is what surfaced [CR-R02](#cr-r02).

But the finding treats the static mount as incidental scenery ("catches the
unmatched route and returns 404"). It is the reason this was ambiguous for as long
as it was, and it is a live defect in its own right, not only a test artifact — see
[CR-036](#cr-036). Fix that alongside deleting the class, or the next removed route
produces the same indistinguishable 404.

---

### CR-030
**`except (TimeoutError, Exception)` turns protocol errors into passes.**

- **Severity:** LOW · **Area:** [`tests/`](../tests/)
- **Status:** **RESOLVED** by `2dbaecf`, verbatim per the rev 2 correction: both
  sites (`test_e2e.py`'s `test_subscribe_receive_unsubscribe_cycle` and
  `test_scada_web.py`'s `test_unsubscribe_stops_samples`) now catch
  `TimeoutError` alone and `pytest.fail` on `websockets.ConnectionClosed`. Both
  files gained a module-level `import websockets` for the exception class.

**Finding.** [test_scada_web.py:184](../tests/test_scada_web.py#L184) and
[test_e2e.py:150](../tests/test_e2e.py#L150). The second clause subsumes the
first, and both wrap a `recv` loop whose purpose is to assert silence — so a
genuine connection or protocol failure reads as "silence, as expected" and the
test passes.

**Recommendation.** Catch `TimeoutError` alone.

**Correction (rev 2).** Catching `TimeoutError` alone is necessary but not
sufficient. Both sites wrap a `recv` loop asserting silence, and a
`websockets.ConnectionClosed` raised in that window is *also* not silence — it is
the connection failing, which is the condition the test should catch. Catch it
explicitly and **fail**:

```python
except TimeoutError:
    pass                      # silence, as intended
except websockets.ConnectionClosed as exc:
    pytest.fail(f"connection closed during assert-silence window: {exc}")
```

Otherwise narrowing to `TimeoutError` converts one false pass into an error whose
message does not say what happened.

---

### CR-031
**Assertions guarded into non-existence.**

- **Severity:** MEDIUM · **Area:** [`tests/test_e2e.py`](../tests/test_e2e.py)
- **Status:** **RESOLVED** by `2dbaecf`. Both cited sites fixed per the rev 2
  correction's generalized rule: `test_value_freshness`'s
  `pytest.skip("No value samples available yet")` became
  `assert samples, "no value samples available — pipeline not delivering"`,
  and `test_dynamic_period_change`'s `if fast_samples and slow_samples:` guard
  became the exact three-line unconditional assert sequence the finding
  recommended. The `pytest.skip` grep across `tests/` this correction asked for
  found only three survivors, all in `test_scada_select.py`/`test_sim.py`
  guarding on `rti.connextdds not available` — a legitimate missing-dependency
  skip, not absent data.

**Finding.**
[test_e2e.py:228-231](../tests/test_e2e.py#L228-L231) wraps its only assertion
in `if fast_samples and slow_samples:`, so the test passes when no samples
arrive at all — i.e. it passes hardest when the pipeline is most broken.
[test_e2e.py:88-89](../tests/test_e2e.py#L88-L89) calls `pytest.skip` when the
sample list is empty, reporting a pipeline failure as a skip.

**Recommendation.** Assert the precondition, then assert the property:

```python
assert fast_samples, "no samples at 200ms separation — pipeline not delivering"
assert slow_samples, "no samples at 2000ms separation"
assert len(fast_samples) >= len(slow_samples)
```

**Correction (rev 2).** The snippet is correct; generalize the rule while in the
file. **`pytest.skip` on empty data is always wrong in this suite** — a pipeline
that delivers no samples is the failure these tests exist to detect, so reporting
it as a skip inverts the test's purpose. That covers
[test_e2e.py:88-89](../tests/test_e2e.py#L88-L89) as cited and any sibling.

Grep `pytest.skip` across [`tests/`](../tests/) and require each survivor to carry a
comment saying what environmental precondition it is guarding — a missing binary or
absent license is a legitimate skip; absent data never is.
[CR-029](#cr-029)'s class is the extreme case of the same mistake.

---

### CR-032
**Session-scoped fixtures leak state between test modules.**

- **Severity:** MEDIUM · **Area:** [`tests/`](../tests/)

**Finding.** `sim_process`, `selector_process` and `scada_web_process` are all
`scope="session"` ([conftest.py:114-163](../tests/conftest.py#L114-L163)), so
selector state accumulates across modules.
[test_scada_select.py:103-121](../tests/test_scada_select.py#L103-L121)
documents the consequence directly: it cannot assert the pre-enabled uid range
strictly, because e2e tests in the same session have already sent `ADD` for
out-of-range uids, so it settles for a ">50% of traffic" heuristic. Its own note
says the real fix is a fresh selector per module.

**Recommendation.** Module-scoped process fixtures for the modules that mutate
selector state. Costs startup time; buys assertions that mean something. If the
cost is unacceptable, the alternative is an explicit reset — a `DELETE` sweep in
teardown — but per-module isolation is the honest version.

Note this interacts with [CR-001](#cr-001): more fixture teardowns means more
leaked processes until the signal handling is fixed. **Fix CR-001 first.**

**Correction (rev 2).** The CR-001 ordering is right and worth restating more
strongly: module scoping *before* the leak is fixed turns one leak per session into
one per module, so the suite gets measurably worse. It also interacts with
[CR-034](#cr-034) — more teardowns means more chances to hit the blocking
`stdout.read()`.

Scope the fixtures unevenly rather than uniformly. Only the **selector** accumulates
the state this finding is about, and `scada_web` holds the port:

- `sim_process` — keep `scope="session"`. It only publishes; it holds no
  cross-module state and is the slowest to reach steady state (the fixture already
  sleeps 2 s for the TRANSIENT_LOCAL MetaData burst,
  [conftest.py:121-122](../tests/conftest.py#L121-L122)).
- `selector_process`, `scada_web_process` — `scope="module"`.

That buys the isolation [test_scada_select.py:103-121](../tests/test_scada_select.py#L103-L121)
needs at the lowest startup cost. The `DELETE`-sweep alternative is worse than the
finding implies: it is test code that has to be kept correct as the selection model
changes, and it would have to be updated by whoever does
[CR-011](#cr-011) and [CR-016](#cr-016).

---

### CR-033
**Four different `sys.path` insertions across the suite.**

- **Severity:** LOW · **Area:** [`tests/`](../tests/)

**Finding.** [test_interest.py:11](../tests/test_interest.py#L11) inserts the
repo root; [test_sim.py:20](../tests/test_sim.py#L20) and
[:108](../tests/test_sim.py#L108) insert `sim/` twice;
[test_scada_select.py:20](../tests/test_scada_select.py#L20) inserts `sim/`
again. [`sim/plc_publisher.py:42-65`](../sim/plc_publisher.py#L42-L65) also
splits its imports around a `sys.path.insert` and the logging setup, while
[`plc_test_subscriber.py:23-28`](../sim/plc_test_subscriber.py#L23-L28) keeps
them together — the same trick in two layouts.

**Recommendation.** One `pythonpath = . sim` entry in
[pytest.ini](../pytest.ini) replaces all four. For the sim scripts, settle on
one import layout.

**Correction (rev 2).** `pythonpath` is a pytest ≥ 7 ini option — confirm the pin in
[requirements.txt](../requirements.txt) before relying on it (the current
[pytest.ini](../pytest.ini) uses only options available much earlier, so this is not
already established).

On the sim scripts: converging on
[`plc_test_subscriber.py`](../sim/plc_test_subscriber.py)'s layout is right, but the
[`plc_publisher.py`](../sim/plc_publisher.py) split is not arbitrary — the
`sys.path.insert` at [:42](../sim/plc_publisher.py#L42) *and* the logging
`basicConfig` at [:50-62](../sim/plc_publisher.py#L50-L62) both have to precede the
`field_simulation` / `plc_types` imports at [:64-65](../sim/plc_publisher.py#L64-L65).
Removing the path insert (which `pythonpath` makes redundant for tests but *not* for
running the sim directly) is what unblocks moving the imports up. Leave a comment on
the remaining ordering constraint; this overlaps the `basicConfig` extraction in
[CR-002](#cr-002).

---

## Added during rev 2 verification

### CR-034
**`proc.stdout.read()` on a live process hangs the fixture instead of reporting.**

- **Severity:** HIGH · **Area:** [`tests/conftest.py`](../tests/conftest.py)
- **Status:** **RESOLVED** by `ea25bed`. `_stop_process` now precedes the read,
  and the read goes through `_drain_startup_log`, which seeks a file rather than
  waiting on a pipe and so cannot block.

**Finding.** [conftest.py:158-161](../tests/conftest.py#L158-L161):

```python
if not _wait_for_http(SCADA_WEB_HOST, SCADA_WEB_PORT):
    output = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
    _stop_process(proc, "scada_web")
    raise RuntimeError(f"scada_web failed to become healthy:\n{output}")
```

This branch is reached precisely when the process **started but did not become
healthy** — so it is still running. `read()` with no argument blocks until EOF, and
EOF arrives only when the process exits. It is called *before* `_stop_process`, so
nothing will make it return.

The same idiom at [conftest.py:95](../tests/conftest.py#L95) is safe, and reads as
precedent for this one: there, `proc.poll() is not None` has already established
that the process is dead.

**Impact.** A scada_web that binds the port but never serves `/health` — a DDS
initialization failure, a missing license, a QoS profile error, or the port already
held by a process leaked per [CR-001](#cr-001) — hangs the test session
indefinitely instead of raising the `RuntimeError` written two lines below. The
diagnostic that was carefully assembled is never printed. CI kills it on job
timeout with no output, which is the least informative possible signal for the most
common startup failure.

Note the failure compounds with [CR-001](#cr-001): a leaked process holding port
8765 is exactly what makes the health check fail, and this turns that into a hang
rather than a message naming the port.

**Recommendation.** Stop the process first, then read — or better, use the timeout
already available:

```python
if not _wait_for_http(SCADA_WEB_HOST, SCADA_WEB_PORT):
    _stop_process(proc, "scada_web")          # ensures EOF on the pipe
    output = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
    raise RuntimeError(f"scada_web failed to become healthy:\n{output}")
```

`subprocess.communicate(timeout=...)` is the idiom that cannot get this wrong and
is worth preferring in both places. See also [CR-035](#cr-035), which removes the
pipe entirely and makes this moot.

---

### CR-035
**Captured stdout is never drained; a full pipe buffer stalls the component.**

- **Severity:** MEDIUM · **Area:** [`tests/conftest.py`](../tests/conftest.py)
- **Status:** **RESOLVED** by `ea25bed`. Startup output goes to a
  `tempfile.TemporaryFile` instead of a `PIPE`, so no writer can ever block on a
  full buffer. Note this fixes the stall by removing the pipe, not by draining it
  — there is still no live consumer of component stdout during a session, which is
  correct now that each component owns a rotating log under `logs/`
  ([CR-002](#cr-002)).

**Finding.** `_start_process` ([conftest.py:81-99](../tests/conftest.py#L81-L99))
starts every component with `stdout=subprocess.PIPE, stderr=subprocess.STDOUT`, and
the three process fixtures are `scope="session"`
([conftest.py:114-163](../tests/conftest.py#L114-L163)). Nothing reads that pipe for
the lifetime of the session — the only `read()` calls are on the two failure paths
([:95](../tests/conftest.py#L95), [:159](../tests/conftest.py#L159)).

A pipe buffer is 64 KiB on Linux. Once it fills, the writing process blocks in
`write()`. With [CR-001](#cr-001)'s `tee` in the pipeline, `tee` is the writer that
blocks, and it blocks holding the component's stdout — so the component stalls too.

**Impact.** Slow to trigger, because `tee -a` also writes to a file and the components
are not especially chatty at `INFO`. But it is a wall the suite walks toward
monotonically: a long pipeline run, a verbose selector (`-v`), or a
`DeprecationWarning` per request ([CR-018](#cr-018)) brings it closer. The symptom is
a component that goes silent mid-session with no error — indistinguishable from a
DDS stall, and it would be debugged as one.

**Recommendation.** The fixtures do not use this output except on the two startup
failure paths, and the log files exist for diagnostics — that is
[CR-002](#cr-002)'s entire subject. Use `stdout=subprocess.DEVNULL` and read the log
file on failure instead. If the captured output is wanted, drain it on a thread, or
redirect to a `tempfile` and read that; do not leave an undrained `PIPE` open across
a session-scoped fixture.

---

### CR-036
**The static mount swallows unmatched `/api/v1` routes into an opaque 404.**

- **Severity:** LOW · **Area:** [`scada_web/server.py`](../scada_web/server.py)
- **Status:** **RESOLVED** by `2dbaecf`. A catch-all
  `@app.get("/api/v1/{rest:path}")` declared after every specific route returns
  `{"error": "no such endpoint '/api/v1/{rest}'"}` at 404, distinct from
  `get_topic_samples`'s `{"error": "unknown topic 'x'"}`. Landed in the same
  commit as [CR-029](#cr-029), which this finding's mechanism had been hiding.

**Finding.** `StaticFiles` is mounted at `/`
([server.py:75-76](../scada_web/server.py#L75-L76)) with a comment noting it is
mounted last so it cannot shadow the API routes. That is true for routes that
*exist*. For any path that does not match a declared route — a typo, a removed
endpoint, a client on a newer protocol — the mount catches it and returns
`StaticFiles`' own 404, which is indistinguishable from `get_topic_samples`'
deliberate `{"error": "unknown topic 'x'"}` 404
([server.py:115-116](../scada_web/server.py#L115-L116)).

This is the mechanism behind [CR-029](#cr-029): two tests read "endpoint does not
exist" as "topic-name lookup not wired" and skipped for two commits across a
migration that deleted the route entirely ([CR-R02](#cr-r02)).

**Recommendation.** Give unmatched API paths a distinct response, so "no such
endpoint" and "no such topic" are never the same 404:

```python
@app.get("/api/v1/{rest:path}")            # declared after the real routes
async def unknown_api_route(rest: str):
    return JSONResponse({"error": f"no such endpoint '/api/v1/{rest}'"},
                        status_code=404)
```

Natural to fold into [CR-017](#cr-017), which moves the routes onto an `APIRouter`
and makes the ordering explicit rather than incidental. Until then the mount comment
should say what it actually guarantees — that declared routes win — rather than
implying the API surface is fully protected.

---

### CR-037
**Every tag in a rate band shares a due time, so bands publish in bursts.**

- **Severity:** LOW · **Area:** [`sim/plc_publisher.py`](../sim/plc_publisher.py)
- **Status:** OPEN — deliberately. The test that exposed it is fixed
  (`9f0cf64`); the sim behaviour is unchanged pending the decision below.

**Finding.** Found by the rev 3 acceptance run, not by reading.
[plc_publisher.py:166-168](../sim/plc_publisher.py#L166-L168) seeds the schedule
with one entry per tag at `start + period`:

```python
for tag in tags:
    period = publish_period_s(tag.uid)
    heapq.heappush(schedule, (start + period, tag.uid, period))
```

Every tag in a band therefore shares its first due time, and
[:189](../sim/plc_publisher.py#L189) reschedules at `due_time + period`, so the
phase alignment is permanent. The 200 tags of the uid 301-500 band publish as one
burst at t=10s, 20s, 30s… rather than trickling ~20/s across each period. Same for
the other three bands ([field_simulation.py:80-85](../sim/field_simulation.py#L80-L85)).

**Impact.** No product defect — the samples are published at the documented
average rate, and every downstream component is rate-agnostic. Two consequences
worth knowing:

1. **It made a test a coin flip.** `test_idvalue_covers_multiple_bands` observed a
   5s window and asserted the 10s band appeared in it. Because the band is
   invisible for 5 of every 10 seconds rather than merely sparse, the assertion
   depended on phase: it passed standalone (fixture sleeps happened to straddle the
   t=10s burst) and failed about half the time in the full suite, where
   `test_sim.py` runs last and the phase depends on how long the preceding modules
   took. This is the failure the rev 3 acceptance run hit.
2. **The load profile is burstier than the rate table implies.** The docstring
   describes a rate distribution; what the writer actually sees is 200 writes in one
   instant every 10s. Anything reasoning about queue depth or write-timeout
   behaviour from the stated rates is reasoning about a smoother stream than exists.

**Recommendation.** Decide, and record it — do not treat this as a defect by
default. Staggering the initial phase is two lines:

```python
for i, tag in enumerate(tags):
    period = publish_period_s(tag.uid)
    # Spread each band across its period rather than bursting at once.
    heapq.heappush(schedule, (start + period * ((i % 100) / 100), tag.uid, period))
```

But the sim exists as a *rate/load-test population*
([field_simulation.py:9](../sim/field_simulation.py#L9)), and a synchronized burst
is a legitimate worst case for exactly the write-timeout and
`replaced_dropped_sample_count` paths the selector instruments
([CR-009](#cr-009)). It may be the more useful profile. What is not defensible is
leaving it undocumented: whichever way this goes, state it where the schedule is
built, because the current code reads as if it intended a smooth stream.

Note the test no longer depends on the answer — `9f0cf64` derives its observation
window from `publish_period_s`, so it is correct under either profile.

---

## Resolution log

Work done against this review, newest last. Branch
`fix/log-writers-and-process-teardown`, on top of `015e653`.

| Commit | Findings | Effect |
|---|---|---|
| `e2dcd14` | [CR-002](#cr-002) RESOLVED, [CR-003](#cr-003) PARTIAL | Dropped the `tee` from `start-web.sh` / `start-sim.sh`; corrected `interest.py`'s SR-003 claim. No behaviour change for CR-003. |
| `ea25bed` | [CR-001](#cr-001), [CR-034](#cr-034), [CR-035](#cr-035) RESOLVED | Process substitution in `start-select.sh`; stop-before-read and `TemporaryFile` in `conftest.py`. |
| `baffe5b` | — | `start-web.sh` / `start-web.bat` install `requirements.txt`. Not from this review. |
| `b78e934` | [CR-028](#cr-028) PARTIAL | Deleted `dds/idl/PlcValue.xml`. OQ-38 itself not amended. |
| `9f0cf64` | [CR-037](#cr-037) symptom | Band observation window derived from `publish_period_s`. Applies [CR-031](#cr-031)'s pattern, but not at CR-031's sites. |
| `2dbaecf` | [CR-019](#cr-019), [CR-020](#cr-020), [CR-025](#cr-025) RESOLVED; [CR-011](#cr-011) (closes [CR-004](#cr-004)) RESOLVED; [CR-021](#cr-021), [CR-013](#cr-013), [CR-026](#cr-026) RESOLVED; [CR-029](#cr-029) (+[CR-036](#cr-036)), [CR-030](#cr-030), [CR-031](#cr-031) RESOLVED | Dead-code sweep across `config.py`/`gateway.py`/sim/tests; `InterestManager` refactored to `on_add`/`on_delete`/`on_period` callbacks (drops `_last_period_ms`); payload hoisted and exact-type dispatch in `server.py`; catch-all 404 route added; `TestE2ETopicType` deleted, assert-silencing `except` clauses narrowed, guarded assertions converted to hard asserts. |
| `1a9ea5d` | [CR-003](#cr-003) RESOLVED | Wired SR-003: `DdsGateway` attaches a `DataWriterListener` to every writer and exposes `on_publication_matched`; `server.py`'s new `_on_publication_matched` replays PERIOD + `reconcile()`'s ADD burst on the `ValueRequest` writer's 0→N match transition; `tests/test_reconcile.py` added. |

Deliberately **not** touched, despite being adjacent to the above: the
`basicConfig` duplication ([CR-002](#cr-002)) and the `.bat` script duplication
([CR-014](#cr-014)) — both still open, both in files these commits edited.

---

## Resolved during review

### CR-R01
**Docs described DD-052; code implemented the superseded DD-045.**

- **Status:** RESOLVED by `015e653` · **Was:** HIGH

`views.py` was an unused stub with commented-out mappers while `mapping.py` — the
module [DD-045](design-decisions.md#dd-045) marks superseded — carried the live
path, and the architecture doc diagrammed the unbuilt design. The migration to
Python generated types made the code match the accepted decisions. Residual
doc cleanup is [CR-027](#cr-027).

### CR-R02
**`/api/v1/topics/{name}/type` could never succeed.**

- **Status:** RESOLVED by `015e653` · **Was:** MEDIUM

The route took a *topic* name and resolved it against the XML *type* library, so
it returned 404 unconditionally. Removed with the DynamicData layer. The tests
that covered it are now zombies — [CR-029](#cr-029).

### CR-R03
**Stale `scada_web/PlcValue.xml` shadowed the canonical library.**

- **Status:** RESOLVED by `c5ed510` · **Was:** MEDIUM

A second copy of the type library, missing the union-based `ValueRequest`, the
`PERIOD` command, the domain constants, and the `@nested` annotations.

---

## Suggested sequence

Ordered by dependency and by risk of working around a defect instead of fixing
it.

**Revised in rev 2.** Three changes, each forced by a correction above:
[CR-002](#cr-002) moves ahead of [CR-001](#cr-001) (fixing it deletes the pipeline
that CR-001 is about); [CR-011](#cr-011) moves ahead of [CR-003](#cr-003) (CR-003
is incorrect without it); [CR-006](#cr-006) moves ahead of [CR-007](#cr-007)
(CR-007 removes a cross-check that CR-006 replaces). The rev 1 order is preserved
below as strikethrough where it differed.

1. ~~**[CR-002](#cr-002)** — one writer per log file.~~ **DONE** `e2dcd14`.
2. ~~**[CR-001](#cr-001)** + **[CR-034](#cr-034)** + **[CR-035](#cr-035)** — process
   leaks, the fixture hang, and the undrained pipe.~~ **DONE** `ea25bed`. The
   premise held: the suite is now runnable and everything below is verifiable
   against it. The acceptance run that followed found [CR-037](#cr-037).
3. ~~**[CR-019](#cr-019)**, [CR-020](#cr-020), + [CR-025](#cr-025)'s two-line test —
   dead-code sweep. Mechanical, and it shrinks the surface for every item below.
   Delete `websocket_path` / `rest_prefix` from the dataclass *and* the YAML.~~
   **DONE** `2dbaecf`.
4. ~~**[CR-029](#cr-029)** (+ [CR-036](#cr-036)), [CR-030](#cr-030),
   [CR-031](#cr-031) — tests that report green while asserting nothing, and the
   opaque 404 that let one of them hide.~~ **DONE** `2dbaecf`.
5. ~~**[CR-011](#cr-011)** (closes [CR-004](#cr-004)) + [CR-021](#cr-021),
   [CR-013](#cr-013), [CR-026](#cr-026) — one pass over `interest.py` /
   `server.py`. The keystone item: it deletes `_last_period_ms`, which is what makes
   the next step correct.~~ **DONE** `2dbaecf`. (Rev 1 had this at step 8.)
6. ~~**[CR-003](#cr-003)** — wire SR-003 or downgrade the claim. Now roughly
   a dozen lines, and actually restores the separation, because step 5 removed the
   global that suppressed the `PERIOD` replay.~~ **DONE** `1a9ea5d`. (Rev 1 had
   this at step 5.) Took the
   wire-it path, not the fallback: a `DataWriterListener` on the `ValueRequest`
   writer triggers `_send_period` + `reconcile()`'s ADD burst on the
   0→N match-count transition. New `tests/test_reconcile.py` covers the
   transition logic without needing a live selector restart.
7. **[CR-005](#cr-005)** then **[CR-023](#cr-023)** — decide what the view layer is
   for, then delete the UI's unreachable union probe.
8. **[CR-008](#cr-008)** (C++ accessors first) then **[CR-016](#cr-016)** — settle
   the vocabulary, then collapse the alias surface.
9. **[CR-006](#cr-006)** then **[CR-007](#cr-007)** — drift guard as a pytest test,
   *then* the sim convergence it makes safe. Record CR-007 as a new DD.
10. **[CR-014](#cr-014)**, [CR-015](#cr-015) — script consolidation; delete
    `conftest._find_and_set_license` rather than sharing it.
11. **[CR-032](#cr-032)** — test isolation (after step 2). Module-scoped selector
    and web, session-scoped sim.
12. **[CR-017](#cr-017)** + **[CR-018](#cr-018)** — app construction. Largest item;
    schedule deliberately. It is also what makes steps 5–8 testable in milliseconds
    rather than tens of seconds, so it is the one item whose deferral compounds.
13. Remaining `LOW` items as capacity allows — [CR-009](#cr-009),
    [CR-010](#cr-010), [CR-012](#cr-012), [CR-024](#cr-024), [CR-027](#cr-027),
    [CR-028](#cr-028), [CR-033](#cr-033).

---

## Verification performed

- `python3 -c "import scada_web.server"` — succeeds at `015e653`.
- `pytest tests/test_interest.py` — 14 passed.
- `pyflakes scada_web/ sim/ tests/` — clean except the unused imports itemized
  in [CR-019](#cr-019).
- `diff UI/serve-ui.ps1 scripts/serve-ui.ps1` — identical.
- Dead-symbol claims verified by `grep` across all first-party sources.

### rev 2 verification pass

Re-read the primary sources rather than re-running the rev 1 commands. Every rev 1
line-number claim checked below held; corrections above concern *recommendations*
and *severity*, not disputed evidence — except the two noted.

- Read in full: [`scada_web/server.py`](../scada_web/server.py),
  [`gateway.py`](../scada_web/gateway.py), [`interest.py`](../scada_web/interest.py),
  [`config.py`](../scada_web/config.py), [`views.py`](../scada_web/views.py),
  [`__main__.py`](../scada_web/__main__.py),
  [`tests/conftest.py`](../tests/conftest.py), [`config.yaml`](../scada_web/config.yaml),
  [`pytest.ini`](../pytest.ini). Read in part: the three start scripts,
  [`sim/plc_publisher.py`](../sim/plc_publisher.py),
  [`UI/index.html`](../UI/index.html), [`main.cxx`](../scada_select/src/main.cxx),
  [`MetaDataPlane.cxx`](../scada_select/src/MetaDataPlane.cxx),
  [`gen/PlcValue.py`](../scada_web/gen/PlcValue.py),
  [`dds/qos/profiles.xml`](../dds/qos/profiles.xml).
- **Two rev 1 claims corrected on evidence.** `TopicConfig.filter` is *not* "plumbed
  to the gateway" — `_create_readers` never reads it ([CR-019](#cr-019)). And the
  [CR-012](#cr-012) replacement snippet resolves non-types out of the `PLC`
  namespace, which is a regression rather than a fix.
- **New facts that changed recommendations.** `presentation::value_request` is
  `RELIABLE` + `VOLATILE`, which determines the correct SR-003 trigger
  ([CR-003](#cr-003)). The `PLC` module namespace binds constants, `str` aliases, and
  topic-name strings alongside types ([CR-012](#cr-012)). The shipped UI sends exactly
  one of the four accepted separation aliases ([CR-016](#cr-016)). The `PERIOD 0`
  rationale appears four times, not two ([CR-026](#cr-026)).
- **Three findings added** from reading `conftest.py` against `server.py`:
  [CR-034](#cr-034), [CR-035](#cr-035), [CR-036](#cr-036).

**Not performed in rev 2 either.** No tests were run and no pipeline was started —
`pytest`, `pyflakes` and `diff` results above are still rev 1's. The
`015e653` typed read path remains **unverified end-to-end against live DDS**.
[CR-034](#cr-034) and [CR-035](#cr-035) strengthen rather than weaken rev 1's
conclusion here: running the suite now risks not just leaking three processes but
hanging the session with no diagnostic. Steps 1–2 of the sequence, then the suite as
the real acceptance check for the migration.

### rev 3 acceptance run — supersedes the caveat above

Steps 1–2 landed, then the full pipeline suite was run. **The `015e653` typed read
path is now verified end-to-end against live DDS.** This closes rev 1's and rev 2's
open caveat.

- **`pytest tests/` — 47 passed, 2 skipped, exit 0**, in ~82 s. Four consecutive
  full-suite runs, all green. Run on `9f0cf64`; the last of the four also confirms
  `b78e934`'s deletion of `dds/idl/PlcValue.xml` (green with the file absent, so
  nothing first-party loaded it).
- **Zero leaked processes** after every teardown across all four runs, ports 8080
  and 8765 free — the [CR-001](#cr-001)/[CR-034](#cr-034)/[CR-035](#cr-035)
  acceptance criterion.
- **No duplicate log lines** in `logs/scada_web.log` — the
  [CR-002](#cr-002) criterion.
- **Two skips, both [CR-029](#cr-029)'s zombies**, exactly as predicted:
  `Type endpoint not wired for topic-name lookup` at
  [test_e2e.py:248](../tests/test_e2e.py#L248) and
  [:262](../tests/test_e2e.py#L262).
- **One failure, diagnosed and fixed:** `test_idvalue_covers_multiple_bands` on the
  first run. Not a regression from the migration or from steps 1–2 — it reads the sim
  directly on domain 15 through `build_plc_types()`, the hand-built path from
  [CR-007](#cr-007), and never touches migrated code. Root cause is
  [CR-037](#cr-037).

**Still not performed.** `pyflakes` and `diff` were not re-run; those results remain
rev 1's. The suite was run only on this machine's Connext 7.7.0 / Python 3.8, and
only with `-p no:randomly` (fixed order) — the ordering dependence
[CR-032](#cr-032) describes is therefore neither confirmed nor cleared by these
runs, and `test_scada_select.py`'s ">50% of traffic" heuristic still passed only
under that fixed order. Nothing here exercises a selector restart, so
[CR-003](#cr-003)'s SR-003 gap remains untested as well as unimplemented.

### rev 4 verification pass

Two commits landed the remainder of the [Suggested sequence](#suggested-sequence)
(steps 3–6), each re-verified against the live pipeline before moving to the next.

- **`pyflakes scada_web/ sim/ tests/`** (excluding `gen/`) — clean after `2dbaecf`'s
  dead-code sweep. This supersedes the rev 1 `pyflakes` result, which had flagged
  the [CR-019](#cr-019) items now deleted.
- **Fast unit subset** —
  `pytest tests/test_reconcile.py tests/test_interest.py tests/test_views.py -v` —
  28 passed, run without starting the pipeline (no DDS entities needed for these).
- **`pytest tests/` after `2dbaecf`** — 56 passed, exit 0, ~83–86 s. Confirms
  [CR-011](#cr-011)'s `InterestManager` refactor, [CR-013](#cr-013)'s exact-type
  dispatch, [CR-021](#cr-021)'s payload hoist, [CR-025](#cr-025)'s
  `KIND_STRING` decode test, [CR-029](#cr-029)/[CR-030](#cr-030)/[CR-031](#cr-031)'s
  test fixes, and [CR-036](#cr-036)'s catch-all route all pass together against a
  live selector — nothing here was verified only in isolation.
- **`pytest tests/` after `1a9ea5d`** — 61 passed, exit 0, ~93 s (`test_reconcile.py`
  adds 5 tests to the 56 above). **This closes [CR-003](#cr-003)'s previously-open
  gap:** the run exercises the `ValueRequest` writer's normal startup match, which
  is the same code path SR-003 reconciliation now hooks — it did not disrupt
  ordinary matching.
- **Zero leaked processes, ports 8080/8765 free** after both runs (`ps aux` +
  `ss -ltnp`), the same acceptance criterion rev 3 established.
- **Not performed in rev 4 either.** No selector-restart-mid-session test was added
  — [CR-003](#cr-003)'s fix is verified by unit test and by not regressing normal
  startup matching, not by an end-to-end restart scenario. `test_scada_select.py`'s
  fixed-run-order dependence ([CR-032](#cr-032)) is still neither confirmed nor
  cleared.

**Not performed.** The full pipeline suite was not run, so the typed read path
in `015e653` is **not** verified end-to-end against live DDS — only that it
imports and that the type definitions are structurally consistent with the IDL.
Running it now would leak three processes per session
([CR-001](#cr-001)); that finding should be fixed first, then the suite run as
the real acceptance check for the migration.
