# AUTHORIZED_LOCAL_REPAIR

## Repository authorization

The canonical schema requires `created_at` to satisfy JSON Schema Draft 2020-12 `format: date-time`, and W03 owns `python/epistemic_foundry/reassessment/**`. This is therefore a local runtime-conformance repair, not a new shared semantic decision.   

Draft 2020-12 defines `date-time` by RFC 3339. RFC 3339 permits lowercase `t` and `z`, uses four-digit years spanning `0000`–`9999`, requires real Gregorian calendar dates, constrains clock and numeric-offset fields, and permits an offset-shifted leap second at the UTC leap-second position. The official JSON Schema conformance cases specifically accept lowercase `t`/`z` and offset-form leap seconds while rejecting offsets such as `+10:60`. ([JSON Schema][1])

The current implementation is not contract-correct: its uppercase-only regex rejects lowercase forms, `datetime` cannot represent year `0000` or second `60`, and `datetime.fromisoformat()` accepts and normalizes invalid offset-minute fields—for example, `+10:60` becomes `+11:00`. Thus it is simultaneously too restrictive and too permissive. 

## Frozen accepted semantics

`_timestamp()` shall accept exactly:

* `YYYY-MM-DD[Tt]HH:MM:SS`
* an optional fractional part consisting of `.` followed by one or more ASCII digits;
* an explicit offset of `Z`, `z`, or `±HH:MM`;
* years `0000` through `9999`, interpreted using the proleptic Gregorian calendar;
* months `01`–`12` and a day valid for that year and month, including `0000-02-29`;
* hours `00`–`23`, minutes `00`–`59`, and ordinary seconds `00`–`59`;
* numeric-offset hours `00`–`23` and minutes `00`–`59`, including `-00:00` and offsets through `±23:59`;
* second `60` only when subtracting the declared local offset places it at UTC minute `23:59` on a month’s final day.

Leap-second acceptance is **structural only**. It does not assert that an actual leap second was announced for that historical or future month and requires no external leap-second table. JSON Schema format validation supplies syntactic/calendar conformance, not an external chronology service. ([JSON Schema][1])

The original string must be returned unchanged. There is no trimming, case conversion, offset conversion, instant normalization, or canonical spelling. Consequently, valid representations such as `T` versus `t`, `Z` versus `z`, and `Z` versus `+00:00` retain different bytes and therefore different hashes.

Every invalid value continues to raise `ReassessmentError` with code `TIMESTAMP_INVALID`.

## Smallest source-only repair

**Only:** `python/epistemic_foundry/reassessment/contracts.py`

```diff
@@
+import calendar
 import hashlib
 import json
 import re
 from collections.abc import Mapping, Sequence
 from dataclasses import dataclass
-from datetime import datetime
 from types import MappingProxyType
 from typing import Any, Final
 
 RFC3339_PATTERN: Final = re.compile(
-    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
-    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
+    r"^(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})"
+    r"[Tt](?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
+    r"(?:\.[0-9]+)?(?:[Zz]|(?P<offset_sign>[+-])"
+    r"(?P<offset_hour>[0-9]{2}):(?P<offset_minute>[0-9]{2}))$"
 )
@@
 def _timestamp(value: object, label: str) -> str:
-    if type(value) is not str or RFC3339_PATTERN.fullmatch(value) is None:
+    if type(value) is not str:
         _fail("TIMESTAMP_INVALID", f"{label} must be RFC 3339 with an explicit offset")
-    try:
-        datetime.fromisoformat(value.replace("Z", "+00:00"))
-    except ValueError as error:
-        raise ReassessmentError(
-            "TIMESTAMP_INVALID", f"{label} is not a real timestamp"
-        ) from error
+
+    match = RFC3339_PATTERN.fullmatch(value)
+    if match is None:
+        _fail("TIMESTAMP_INVALID", f"{label} must be RFC 3339 with an explicit offset")
+
+    year, month, day, hour, minute, second = (
+        int(match.group(name))
+        for name in ("year", "month", "day", "hour", "minute", "second")
+    )
+    offset_hour = int(match.group("offset_hour") or 0)
+    offset_minute = int(match.group("offset_minute") or 0)
+
+    if not 1 <= month <= 12:
+        _fail("TIMESTAMP_INVALID", f"{label} is not a real timestamp")
+
+    month_end = calendar.monthrange(year, month)[1]
+    if (
+        not 1 <= day <= month_end
+        or hour > 23
+        or minute > 59
+        or second > 60
+        or offset_hour > 23
+        or offset_minute > 59
+    ):
+        _fail("TIMESTAMP_INVALID", f"{label} is not a real timestamp")
+
+    if second == 60:
+        offset = offset_hour * 60 + offset_minute
+        if match.group("offset_sign") == "-":
+            offset = -offset
+
+        utc_day_delta, utc_minute = divmod(
+            hour * 60 + minute - offset,
+            24 * 60,
+        )
+        if utc_day_delta == 0:
+            leap_day_is_month_end = day == month_end
+        elif utc_day_delta == -1:
+            leap_day_is_month_end = day == 1
+        else:
+            leap_day_is_month_end = False
+
+        if utc_minute != 23 * 60 + 59 or not leap_day_is_month_end:
+            _fail("TIMESTAMP_INVALID", f"{label} is not a real timestamp")
+
     return value
```

No schema, workflow, manifest, report, test, dependency, call-site, hashing, or Passport change is authorized. The unrelated `span`/`decision` and seed-validation hunks remain untouched.

[1]: https://json-schema.org/draft/2020-12/json-schema-validation "https://json-schema.org/draft/2020-12/json-schema-validation"
