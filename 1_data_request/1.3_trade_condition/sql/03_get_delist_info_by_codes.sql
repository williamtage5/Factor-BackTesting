/*
Template query for delist-related fields.
Replace:
  {CODE_LIST} -> '000001.SZ','000002.SZ'
*/
SELECT
    d.S_INFO_WINDCODE,
    d.S_INFO_DELISTDATE,
    d.IS_DELISTED
FROM ASHAREDESCRIPTION d
WHERE d.S_INFO_WINDCODE IN ({CODE_LIST});

