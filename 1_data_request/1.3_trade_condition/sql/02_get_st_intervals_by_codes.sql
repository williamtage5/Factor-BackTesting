/*
Template query for ST effective intervals.
Replace:
  {CODE_LIST} -> '000001.SZ','000002.SZ'
*/
SELECT
    s.S_INFO_WINDCODE,
    s.S_TYPE_ST,
    s.ENTRY_DT,
    s.REMOVE_DT
FROM ASHAREST s
WHERE s.S_INFO_WINDCODE IN ({CODE_LIST});

