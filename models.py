class Direction:
    LONG = "B"
    SHORT = "S"

class OrderStatus:
    OPEN_PENDING = "PENDING " #The order has been submitted but is awaiting further processing.
    CANCELLED = "CANCELED"   #The order has been canceled by the trader before being executed.
    OPEN = "OPEN"  #The order is active and waiting to be matched with a counterparty.
    REJECTED = "REJECTED"   #The order has been declined due to certain criteria not being met.
    COMPLETE = "COMPLETE"  #The order has been successfully executed and completed.
    TRIGGER_PENDING = "TRIGGER_PENDING"   #A specific condition must be met before the order can become active.
    INVALID_STATUS_TYPE = "INVALID_STATUS_TYPE"  #The provided order status is not recognized or valid.

class OrderType:
    LIMIT = "LMT"
    MARKET = "MKT"
    SL_LIMIT = "SL-LMT"
    SL_MARKET = " SL-MKT"

class ProductType:
    CNC = "C" 
    NRML = "M"
    MIS = "I"
    BRACKET_ORDER = 'B'
    COVER_ORDER = 'H'

class Segment:
    NSE = "NSE"   #NSE Equity
    NFO = "NFO"   #NSE FNO
    CDS = "CDS"   #Currency
    MCX = "MCX"   #Commodity
    BSE = "BSE"   #BSE Equity
    BFO = "BFO"   #BSE FNO