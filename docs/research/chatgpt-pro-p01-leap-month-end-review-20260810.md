NO_BLOCKER. The validator now shifts the supplied date through the signed offset, requires the resulting UTC time to be `23:59` on the final day of that UTC month, and preserves the original timestamp text. The regression cases cover both direct and offset-shifted non-month-end rejection while retaining the offset-shifted 1990 month-end case.  


*Generated 1 image(s). Saved to: C:\Users\yhmoo\.oracle\sessions\pro-d34e2f-9bcf91\artifacts\file_00000000f92c81f8bc242b239e387e0a.png*
