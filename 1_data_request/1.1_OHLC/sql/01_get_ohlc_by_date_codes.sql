/*
Template query for one trade date + code list.
Replace:
  {TRADE_DT}   -> e.g. 20230103
  {CODE_LIST}  -> '000001.SZ','000002.SZ'
*/
SELECT
    p.TRADE_DT,
    p.S_INFO_WINDCODE,
    p.S_DQ_OPEN,
    p.S_DQ_HIGH,
    p.S_DQ_LOW,
    p.S_DQ_CLOSE,
    p.S_DQ_VOLUME,
    p.S_DQ_AMOUNT,
    p.S_DQ_ADJFACTOR,
    p.S_DQ_ADJOPEN,
    p.S_DQ_ADJHIGH,
    p.S_DQ_ADJLOW,
    p.S_DQ_ADJCLOSE,
    p.S_DQ_TRADESTATUS,
    p.S_DQ_TRADESTATUSCODE,
    p.S_DQ_LIMIT,
    p.S_DQ_STOPPING
FROM ASHAREEODPRICES p
WHERE p.TRADE_DT = '{TRADE_DT}'
  AND p.S_INFO_WINDCODE IN ({CODE_LIST});

