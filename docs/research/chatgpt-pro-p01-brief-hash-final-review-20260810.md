## BLOCKER — leap-second date validation remains incomplete

`_timestamp()` now correctly validates ordinary calendar fields and requires `:60` to map through the numeric offset to UTC minute `23:59`. However, it checks only the UTC **time of day**, not the corresponding UTC **date**. Consequently, a value such as:

```text
2026-08-01T23:59:60Z
```

is still accepted even though August 1 is not a month end. The current condition is limited to the modulo-minute comparison.  RFC 3339 permits second `60` only at the end of a month in which a leap second occurs, with non-UTC representations shifted by their offset. ([RFC Editor][1])

The regression cases reject `23:58:60Z` and preserve the valid offset-shifted 1990 example, but they do not cover a non-month-end `23:59:60` value. 

**Smallest P01-owned correction:** when `second == 60`, convert the supplied local date and offset to the corresponding UTC date, including day/month/year rollover, and require both:

```text
UTC time == 23:59
UTC date == final day of its UTC month
```

Preserve the original timestamp string. Add one refusal case for `2026-08-01T23:59:60Z` and one offset-shifted equivalent that resolves to a non-month-end UTC date. The detached-snapshot blocker is closed by the current single canonicalization-and-parse boundary. 

[1]: https://www.rfc-editor.org/rfc/inline-errata/rfc3339.html?utm_source=chatgpt.com "rfc3339"


*Generated 1 image(s). Saved to: C:\Users\yhmoo\.oracle\sessions\pro-d34e2f-2a5ad7\artifacts\file_00000000f92c81f8bc242b239e387e0a.png*
