/*
Template query for HS300 close by date range.
Replace:
  {TRADE_DT_FROM} -> e.g. 20230103
  {TRADE_DT_TO}   -> e.g. 20231229
*/
SELECT
    p.TRADE_DT,
    p.S_INFO_WINDCODE,
    p.S_DQ_CLOSE
FROM AINDEXEODPRICES p
WHERE p.S_INFO_WINDCODE = '000300.SH'
  AND p.TRADE_DT >= '{TRADE_DT_FROM}'
  AND p.TRADE_DT <= '{TRADE_DT_TO}';

