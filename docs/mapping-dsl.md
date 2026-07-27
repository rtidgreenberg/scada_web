# scada_web Mapping DSL — Draft Specification

**Status:** Draft v0.1 — companion to [technical-requirements.md](technical-requirements.md) §6
**Date:** 2026-07-27

This document specifies the declarative language used to define data model
transformations and field member mappings. It is a draft: the expression
grammar in §4 is pending the outcome of OQ-6 (bespoke grammar vs. a restricted
CEL profile).

---

## 1. Design principles

1. **Declarative first.** The common cases — rename, reshape, unit convert,
   project — require no code. Native plugins (TRD FR-XF-052) exist for the rest.
2. **Fail at compile time.** A mapping is compiled and type-checked when the
   configuration loads. Anything that could fail per-sample for structural
   reasons must instead fail at startup.
3. **Total evaluation.** No loops, no recursion, no I/O, bounded allocation.
   The evaluator runs inline on the data path (TRD FR-XF-011).
4. **Explicit about direction.** Every mapping declares whether it works
   outbound (DDS → web), inbound (web → DDS), or both, and the compiler
   verifies the claim rather than trusting it.
5. **Keys are sacred.** Instance identity survives every transformation, or the
   mapping is rejected (TRD §6.5).

---

## 2. Structure

```xml
<transformation_library name="LibName">
  <view_schema name="..."> ... </view_schema>    <!-- optional explicit view type -->
  <mapping name="..." direction="..."> ... </mapping>
</transformation_library>
```

A mapping is referenced as `LibName::MappingName` from a `<data_reader>` or
`<data_writer>`:

```xml
<data_reader name="TankView" topic_ref="TankTelemetry">
  <transformation mapping_ref="ScadaViews::TankToUi"/>
</data_reader>
```

### 2.1 `<mapping>` attributes

| Attribute | Values | Default | Meaning |
|---|---|---|---|
| `name` | identifier | required | Unique within the library. |
| `direction` | `outbound` \| `inbound` \| `bidirectional` | `outbound` | Declared direction. The compiler verifies it. |

### 2.2 `<mapping>` children

| Element | Cardinality | Purpose |
|---|---|---|
| `<input>` | 1 | Wire side. Cardinality is retained in the schema, but more than one is a compile error in v1 — join is out of scope (TRD FR-XF-022, [DD-024](design-decisions.md#dd-024)). |
| `<output>` | 1 | View side: either `view_schema=` referencing a declared schema, or inferred from the rules. |
| `<lookup>` | 0..n | Reference-data binding — read-only keyed context (§3.8). Not a join. |
| `<unmapped_policy>` | 0..1 | What to do with members no rule touches. |
| `<on_error>` | 0..1 | Runtime evaluation failure policy. |
| `<assign>` | 0..n | Direct member mapping. |
| `<compute>` | 0..n | Expression-derived member. |
| `<aggregate>` | 0..n | Reduction over a collection member. |
| `<constant>` | 0..n | Literal injection. |
| `<filter>` | 0..1 | Predicate; non-matching samples are not delivered. |
| `<key_mapping>` | 1 | Required. View-key to wire-key correspondence. |

---

## 3. Rule elements

### 3.1 `<assign>`

Copies a member, optionally converting.

```xml
<assign to="{view-path}" from="{wire-path}"
        convert="{conversion}"        <!-- optional -->
        enum_as="name|ordinal"        <!-- optional -->
        on_narrowing="error|saturate|wrap"   <!-- default error -->
        on_overflow="error|truncate"         <!-- bounded collections, default error -->
        direction="outbound|inbound|bidirectional"> <!-- default: mapping's -->
  <value_map from="..." to="..."/>    <!-- 0..n, explicit value table -->
</assign>
```

`to` is always the **view** path and `from` always the **wire** path,
regardless of direction. This is deliberately unlike the Routing Service
Assignment Transformation, where `<name>`/`<value>` mean output/input and
therefore flip meaning with the route. Fixing the roles to view/wire removes an
entire class of configuration error. The translation tool (TRD FR-XF-053)
handles the rewrite.

Widening conversions are implicit. Narrowing requires `on_narrowing`, defaulting
to `error`.

### 3.2 `<compute>`

```xml
<compute to="{view-path}" type="{view-type}"
         direction="outbound|inbound">
  <!-- expression, §4 -->
</compute>
```

`type` is required — it anchors type checking and view schema generation rather
than inferring a type the user did not intend. A `<compute>` is not
automatically invertible; an inbound counterpart must be written explicitly.

### 3.3 `<aggregate>`

```xml
<aggregate to="{view-path}" from="{wire-collection-path}"
           op="sum|min|max|avg|count|first|last"
           direction="outbound"/>
```

Outbound only. Its presence forces the member — and, if the mapping is declared
`bidirectional` without an inbound counterpart for it, the whole mapping — to be
reclassified, which is a compile error under a `bidirectional` declaration.

### 3.4 `<constant>`

```xml
<constant to="{view-path}" type="{view-type}" value="{literal}"/>
```

### 3.5 `<filter>`

```xml
<filter pushdown="auto|always|never">   <!-- default auto -->
  <!-- boolean expression over wire paths -->
</filter>
```

Under `auto`, the compiler attempts to express the predicate as DDS SQL and push
it into a content-filtered topic, so filtering happens before the sample reaches
this process. Under `always`, failure to push down is a compile error. The
chosen strategy is reported in the compiled plan (TRD FR-XF-041).

### 3.6 `<key_mapping>`

```xml
<key_mapping>
  <key view="{view-path}" wire="{wire-path}"/>   <!-- 1..n -->
</key_mapping>
```

Mandatory. Every wire key member must be covered for an inbound or
bidirectional mapping. Key mappings must be pure `<assign>`-equivalent — no
expressions, no aggregation — so that instance identity is bijective.

### 3.7 `<unmapped_policy>` and `<on_error>`

```xml
<unmapped_policy outbound="omit|default|error"
                 inbound="omit|default|error"/>   <!-- defaults: omit / error -->
<on_error>drop_sample|substitute_default|fail_request</on_error>  <!-- default drop_sample -->
```

Inbound defaults to `error` because a partially specified write is more
dangerous than a partially specified read.

### 3.8 `<lookup>` — reference data

Binds a slowly-changing keyed topic as read-only context, so a view can pull in
descriptive fields that do not travel with the value sample.

```xml
<lookup name="{alias}" topic_ref="{topic}" key="{wire-path}"
        on_missing="omit|default|error"/>   <!-- default omit -->
```

Looked-up members are then addressed through the alias:

```xml
<lookup name="meta" topic_ref="MetaData" key="uid"/>
<assign to="tag"   from="meta.longName"/>
<assign to="hi_hi" from="meta.limits.redHigh"/>
```

**This is deliberately not a join** ([FR-XF-022](technical-requirements.md), which
stays out of v1). The restrictions are what keep it cheap, and they are enforced
at compile time:

- **Single key, exact match.** No join expressions.
- **No time semantics.** The value is the latest known one; there is no window,
  no staleness policy, and no correlation ordering.
- **Read-only.** A `<lookup>` member may not be a mapping target, and it never
  participates in an inbound mapping. It therefore has no effect on invertibility
  (§7).
- **Bounded state.** One entry per key, sized by the source topic's instance
  count. No eviction policy, because there is nothing to evict.

The source should be `TRANSIENT_LOCAL` so a late-joining service populates the map
regardless of start order. If it is not, `on_missing` governs early samples that
arrive before their key is known — and `omit` is the default precisely because a
value arriving before its description is normal at startup, not an error.

See [DD-024](design-decisions.md#dd-024) for why this exists rather than a join.

---

## 4. Member paths

```
path      := segment ( '.' segment )*
segment   := identifier index?
index     := '[' ( integer | '*' ) ']'
```

- `header.stamp.sec` — nested struct member
- `points[2].x` — array or sequence element
- `sensors[*].value` — all elements; legal only as the `from` of an
  `<aggregate>`, or in a `<compute>` argument that reduces it
- Union members are addressed by branch name; the compiler inserts a
  discriminator check and applies `on_error` if the branch is not active
- Optional members resolve to absent, which propagates per `on_error`

---

## 5. Expression language (provisional)

Pending OQ-6. The requirements the chosen language must satisfy:

- Total: terminates on all inputs, no loops or recursion.
- Statically typed against XTypes, checked at compile time.
- No I/O, no ambient state, no clock access except an explicit `now()` that the
  host injects.
- Bounded memory per evaluation.

Provisional operator set: `+ - * / %`, `== != < <= > >=`, `&& || !`,
`? :`, string concatenation, and member path references.

Provisional function library:

| Group | Functions |
|---|---|
| Numeric | `abs`, `min`, `max`, `round`, `floor`, `ceil`, `clamp`, `pow`, `sqrt` |
| String | `concat`, `substr`, `len`, `upper`, `lower`, `trim`, `starts_with`, `contains` |
| Time | `now`, `to_rfc3339`, `from_rfc3339`, `sec`, `nanosec` |
| Convert | `to_int32`, `to_int64`, `to_double`, `to_string`, `parse_int`, `parse_double` |
| Collection | `size`, `at` (reductions belong in `<aggregate>`) |

XML requires `&lt;`, `&gt;`, `&amp;` escaping, or a `CDATA` section for
expressions containing them.

---

## 6. Unit conversions

`convert="<from>-><to>"` on `<assign>`. Conversions are invertible, so a
converted `<assign>` stays bidirectional.

| Domain | Units |
|---|---|
| Temperature | `degC`, `degF`, `K` |
| Angle | `rad`, `deg` |
| Pressure | `Pa`, `kPa`, `bar`, `psi` |
| Length | `m`, `cm`, `mm`, `km`, `ft`, `in` |
| Time | `s`, `ms`, `us`, `ns` |
| Mass | `kg`, `g`, `lb` |

Custom affine conversions:

```xml
<assign to="flow_gpm" from="flow_raw">
  <linear scale="0.0631" offset="0.0"/>
</assign>
```

---

## 7. Invertibility

The compiler classifies each mapping (TRD FR-XF-025):

| Construct | Invertible | Note |
|---|---|---|
| `<assign>` without conversion | yes | |
| `<assign>` with unit conversion or `<linear>` | yes | affine, exactly invertible |
| `<assign>` with `<value_map>` | yes, if the table is injective | non-injective table → outbound only |
| `<constant>` | outbound only | no information to recover |
| `<compute>` | no | write an explicit inbound counterpart |
| `<aggregate>` | no | outbound only by definition |
| `<filter>` | n/a | does not affect classification |
| `<lookup>` | n/a | read-only context; never a mapping target (§3.8) |

A mapping declared `bidirectional` whose computed class is narrower is a
**compile error**, listing the offending members. This is intentional: silently
degrading to read-only is how a SCADA operator discovers at 3 a.m. that their
setpoint writes never reached the plant.

---

## 8. Worked example

Wire type:

```idl
struct Timestamp { int32 sec; uint32 nanosec; };
struct Device    { string<64> tag_name; int32 unit_id; };
struct Level     { double percent; double meters; };
struct Sensor    { string<32> name; double value; };
enum ControlMode { MODE_AUTO, MODE_MANUAL, MODE_LOCKOUT };

struct TankReading {
  @key Device device;
  Timestamp   header_stamp;
  Level       level;
  double      temp_c;
  ControlMode control_mode;
  sequence<Sensor, 16> sensors;
};
```

Desired view:

```json
{ "tag": "TK-101", "level_pct": 72.4, "temp_f": 88.2,
  "status": "OK", "mode": "auto", "sensor_max": 91.3, "updated_sec": 1785000000 }
```

Mapping:

```xml
<transformation_library name="ScadaViews">
  <mapping name="TankToUi" direction="outbound">
    <input topic_ref="TankTelemetry" registered_type_name="TankReading"/>
    <output view_schema="TankUiView"/>

    <unmapped_policy outbound="omit" inbound="error"/>
    <on_error>drop_sample</on_error>

    <assign to="tag"         from="device.tag_name"/>
    <assign to="level_pct"   from="level.percent"/>
    <assign to="updated_sec" from="header_stamp.sec"/>
    <assign to="temp_f"      from="temp_c" convert="degC->degF"/>

    <assign to="mode" from="control_mode" enum_as="name">
      <value_map from="MODE_AUTO"    to="auto"/>
      <value_map from="MODE_MANUAL"  to="manual"/>
      <value_map from="MODE_LOCKOUT" to="lockout"/>
    </assign>

    <compute to="status" type="string"><![CDATA[
      level.percent > 95 ? "HIGH" : (level.percent < 5 ? "LOW" : "OK")
    ]]></compute>

    <aggregate to="sensor_max" from="sensors[*].value" op="max"
               direction="outbound"/>

    <key_mapping>
      <key view="tag" wire="device.tag_name"/>
    </key_mapping>
  </mapping>
</transformation_library>
```

`direction="outbound"` is correct here: `status` and `sensor_max` are not
invertible. A companion `UiToTank` inbound mapping would carry only the
writable members (setpoints), with its own `<key_mapping>`.

---

## 9. Compilation

1. **Parse and schema-validate** the XML.
2. **Resolve types** — wire types from the types library or discovery; view
   schema from `<view_schema>` or inferred from the rules.
3. **Resolve paths** to member offsets and type descriptors. Unresolvable path →
   error naming the path and the closest valid member.
4. **Type-check** every assignment, conversion, and expression.
5. **Check keys** — every wire key covered for inbound/bidirectional; key rules
   are pure.
6. **Classify invertibility** and compare against the declared `direction`.
7. **Plan filter pushdown** and record the decision.
8. **Emit the plan** — a flat instruction sequence over precomputed offsets, so
   there is no name lookup on the data path (TRD RISK-1).
9. **Generate the JSON Schema** for the view (TRD FR-XF-040).

Errors are reported with file, line, XPath, and the offending member path. All
errors from steps 3–6 are collected and reported together, not one per run.

---

## 10. Tooling

```
scada-web-mapc validate   <config.xml>              # steps 1–7, report all errors
scada-web-mapc describe   <config.xml> --mapping M  # plan, class, provenance
scada-web-mapc apply      <config.xml> --mapping M --direction outbound --input s.json
scada-web-mapc roundtrip  <config.xml> --mapping M --samples dir/
scada-web-mapc schema     <config.xml> --mapping M  # JSON Schema for the view
scada-web-mapc import-rs  <routing_service.xml>     # translate Assignment Transformations
```

`validate` and `roundtrip` are intended to run in CI over the deployed
configuration.

---

## 11. Open items

- **OQ-6** (TRD): expression language selection — bespoke grammar vs. restricted
  CEL profile. Blocks §4 and §5 finalization.
- Join syntax for multi-`<input>` mappings (TRD FR-XF-022) is unspecified
  pending the v1/v2 decision in OQ-4.
- Split/fan-out syntax (TRD FR-XF-023) is unspecified for the same reason.
- Whether `<view_schema>` should be authorable directly in XML, or always
  inferred from rules with an optional generated-schema check.
- Versioning of view schemas, and how a client detects an incompatible change.
