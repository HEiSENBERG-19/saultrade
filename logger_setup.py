import logging

def setup_logger(name, log_file, level=logging.INFO, formatter=None):
    handler = logging.FileHandler(log_file, encoding='utf-8')
    handler.setLevel(level)
    if formatter:
        handler.setFormatter(formatter)
    else:
        handler.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)
    return logger

common_formatter = logging.Formatter('%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Set up the main application logger
app_logger = setup_logger('app', 'logs/my_app.log', formatter=common_formatter)

# Set up the WebSocket logger
ws_logger = setup_logger('websocket', 'logs/ws_logs.log', formatter=common_formatter)

# Set up the PNL logger
pnl_logger = setup_logger('pnl', 'logs/pnl.log', formatter=common_formatter)

# Set up the position logger
pos_logger = setup_logger('pos', 'logs/positions.log', formatter=common_formatter)