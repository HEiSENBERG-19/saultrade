import logging, pyotp, pandas as pd, zipfile, requests, asyncio
from io import BytesIO
from NorenRestApiPy.NorenApi import NorenApi
from logger_setup import app_logger

logger = logging.getLogger(__name__)

def login(config):
    class ShoonyaApiPy(NorenApi):
        def __init__(self):
            NorenApi.__init__(self, host='https://api.shoonya.com/NorenWClientTP/', websocket='wss://api.shoonya.com/NorenWSTP/')

    api = ShoonyaApiPy()        
    factor2 = pyotp.TOTP(config.get_config('secret')).now()
    
    try:
        ret = api.login(
            userid=config.get_config('user'),
            password=config.get_config('pwd'),
            twoFA=factor2,
            vendor_code=config.get_config('vc'),
            api_secret=config.get_config('app_key'),
            imei=config.get_config('imei')
        )
        
        if ret and 'request_time' in ret:
            app_logger.info(f"Login Successful: {ret['request_time']}")
            return api
        else:
            app_logger.error(f"Login failed with response: {ret}")
            return None
    except Exception as e:
        app_logger.error(f"Error during login: {e}", exc_info=True)
        return None

def get_quotes(api, exchange, token):
    try:
        return api.get_quotes(exchange=exchange, token=token)
    except Exception as e:
        app_logger.error(f"Error getting quotes: {e}")
        return None

def fetch_symbols(url: str, file_name: str) -> pd.DataFrame:
    try:
        response = requests.get(url)
        response.raise_for_status() 
        content = response.content

        with zipfile.ZipFile(BytesIO(content)) as z:
            symbols = pd.read_csv(z.open(file_name), delimiter=',')
        
        return symbols
    except Exception as e:
        app_logger.error(f"Error while fetching symbols from {url}: {e}", exc_info=True)
        return None
    
async def get_atm_strike(tsymbol: str, get_quotes_func) -> float:
    symbol_map = {
        'NIFTY': ('Nifty 50', 50, 'NSE', 'INDEX'),
        'BANKNIFTY': ('Nifty Bank', 100, 'NSE', 'INDEX'),
        'FINNIFTY': ('Nifty Fin Services', 50, 'NSE', 'INDEX'),
        'MIDCPNIFTY': ('NIFTY MID SELECT', 50, 'NSE', 'INDEX'),
        'CRUDEOILM': ('CRUDEOILM', 100, 'MCX', 'FUTCOM'), 
        'CRUDEOIL': ('CRUDEOIL', 100, 'MCX', 'FUTCOM'),
        'GOLD': ('GOLD', 100, 'MCX', 'FUTCOM'),
        'GOLDM': ('GOLDM', 100, 'MCX', 'FUTCOM'),
        'COPPER': ('COPPER', 100, 'MCX', 'FUTCOM'),
        'SILVERM': ('SILVERM', 100, 'MCX', 'FUTCOM'),
        'SILVER': ('SILVER', 100, 'MCX', 'FUTCOM'),
        'NATURALGAS': ('NATURALGAS', 100, 'MCX', 'FUTCOM'),
        'ZINC': ('ZINC', 100, 'MCX', 'FUTCOM'),
    }
    
    try:
        if tsymbol not in symbol_map:
            raise ValueError(f"Invalid tsymbol: {tsymbol}")
        
        symbol, base, exchange, instrument = symbol_map[tsymbol]
        
        fno_scrips = fetch_symbols(f'https://api.shoonya.com/{exchange}_symbols.txt.zip', f'{exchange}_symbols.txt')
        if fno_scrips is None:
            raise ValueError(f"Failed to fetch symbols for {exchange}")
        
        fut_token = str(fno_scrips[(fno_scrips['Instrument'] == instrument) & (fno_scrips['Symbol'] == symbol)].iloc[0]['Token'])
        quotes = get_quotes_func(exchange, fut_token)
        
        if not quotes or 'lp' not in quotes:
            raise ValueError("Invalid response from quotes API")

        fut = float(quotes['lp'])
        atm_strike = round(fut / base) * base
        app_logger.info(f'{symbol} ATM: {atm_strike}')
        return atm_strike
    except Exception as e:
        app_logger.error(f"Error while fetching ATM strike: {e}", exc_info=True)
        return None

async def get_option_symbols(tsymbol: str, strikes: dict) -> dict:
    try:
        exchange = 'NFO' if tsymbol in ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY'] else 'MCX'
        file_url = f'https://api.shoonya.com/{exchange}_symbols.txt.zip'
        file_name = f'{exchange}_symbols.txt'
        
        fno_scrips = fetch_symbols(file_url, file_name)
        if fno_scrips is None:
            raise ValueError(f"Failed to fetch option symbols for {exchange}")
        
        fno_scrips['Expiry'] = pd.to_datetime(fno_scrips['Expiry'], format='%d-%b-%Y')
        fno_scrips['StrikePrice'] = fno_scrips['StrikePrice'].astype(float)
        fno_scrips.sort_values('Expiry', inplace=True)
        fno_scrips.reset_index(drop=True, inplace=True)

        options = {}
        for opt_key, strike_info in strikes.items():
            strike, option_type = strike_info
            row = fno_scrips[(fno_scrips['Symbol'] == tsymbol) &
                             (fno_scrips['OptionType'] == option_type) &
                             (fno_scrips['StrikePrice'] == strike)]
            if row.empty:
                raise ValueError(f"No option found for {opt_key} with strike {strike} and type {option_type}")
            options[opt_key] = {
                'Exchange': row.iloc[0]['Exchange'],
                'Token': int(row.iloc[0]['Token']),
                'LotSize': int(row.iloc[0]['LotSize']),
                'Symbol': row.iloc[0]['Symbol'],
                'TradingSymbol': row.iloc[0]['TradingSymbol'],
                'Expiry': row.iloc[0]['Expiry'],
                'Instrument': row.iloc[0]['Instrument'],
                'OptionType': row.iloc[0]['OptionType'],
                'StrikePrice': float(row.iloc[0]['StrikePrice'])
            }
        
        app_logger.info(f"Symbols Obtained")
        return options
    except Exception as e:
        app_logger.error(f"Error while fetching option symbols: {e}", exc_info=True)
        return None
    
def adjust_quantity_for_lot_size(quantity: int, lot_size: int) -> int:
    final_quantity = quantity * lot_size
    app_logger.info(f"Final quantity to be used: {final_quantity}")
    return final_quantity

async def get_account_limits(api):
    try:
        limits = await asyncio.to_thread(api.get_limits)
        if limits and limits.get('stat') == 'Ok':
            return limits
        else:
            logger.error(f"Failed to fetch account limits: {limits}")
            return None
    except Exception as e:
        logger.error(f"Error fetching account limits: {e}", exc_info=True)
        return None