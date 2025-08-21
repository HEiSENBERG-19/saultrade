class PositionManager:
    def __init__(self, market_data_processor, influxdb_manager):
        self.positions = {}  # Stores open positions
        self.market_data_processor = market_data_processor
        self.influxdb_manager = influxdb_manager
        
        # --- NEW: PnL State Management ---
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.trade_margin = 0.0

    def set_trade_margin(self, margin):
        self.trade_margin = margin

    # --- REFACTORED: Now handles trade direction and averaging ---
    async def add_position(self, symbol, quantity, price, direction):
        signed_quantity = quantity if direction == 'B' else -quantity
        
        if symbol not in self.positions:
            self.positions[symbol] = {
                'quantity': signed_quantity,
                'entry_price': price,
                'current_price': price
            }
        else:
            # Logic to average price if adding to an existing position
            old_qty = self.positions[symbol]['quantity']
            old_value = old_qty * self.positions[symbol]['entry_price']
            new_value = signed_quantity * price
            
            total_qty = old_qty + signed_quantity
            if total_qty == 0:
                # This trade closes the position, handle as a close event
                await self.close_position(symbol, price, abs(signed_quantity))
                return
            
            self.positions[symbol]['entry_price'] = (old_value + new_value) / total_qty
            self.positions[symbol]['quantity'] = total_qty

        # Write data and recalculate PnL
        self._write_position_data(symbol, self.positions[symbol]['quantity'], price, "add")
        await self.update_and_write_all_pnl()

    # --- NEW: Crucial method to handle closing positions ---
    async def close_position(self, symbol, exit_price, quantity_to_close):
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]
        entry_price = pos['entry_price']
        original_quantity = pos['quantity']

        # Determine signed quantity being closed (opposite of original trade)
        signed_qty_to_close = min(abs(original_quantity), quantity_to_close)
        if original_quantity > 0: # Long position
             signed_qty_to_close *= -1

        trade_pnl = (exit_price - entry_price) * abs(signed_qty_to_close)
        self.realized_pnl += trade_pnl
        
        # Reduce position size or remove completely
        pos['quantity'] += signed_qty_to_close # This will be original_qty - quantity_to_close
        
        self._write_position_data(symbol, pos['quantity'], exit_price, "close", trade_pnl)

        if pos['quantity'] == 0:
            del self.positions[symbol]

        await self.update_and_write_all_pnl()

    # --- REFACTORED: Now only updates price and recalculates unrealized PnL ---
    async def update_position_price(self, symbol, new_price):
        if symbol in self.positions:
            self.positions[symbol]['current_price'] = new_price
            await self.update_and_write_all_pnl()
            
    # --- NEW: Centralized PnL calculation and writing ---
    async def update_and_write_all_pnl(self):
        # 1. Calculate current unrealized PnL
        current_unrealized_pnl = 0.0
        for symbol, pos in self.positions.items():
            position_pnl = (pos['current_price'] - pos['entry_price']) * pos['quantity']
            current_unrealized_pnl += position_pnl
            # Write individual position PnL
            self._write_position_data(symbol, pos['quantity'], pos['current_price'], "update", position_pnl)

        self.unrealized_pnl = current_unrealized_pnl

        # 2. Write aggregated PnL data
        await self._write_pnl_data()

    def _write_position_data(self, symbol, quantity, price, action, pnl=None):
        fields = {"quantity": quantity, "price": price}
        if pnl is not None:
            fields["pnl"] = pnl
        
        self.influxdb_manager.write_data(
            measurement="positions",
            fields=fields,
            tags={"symbol": symbol, "action": action}
        )

    async def _write_pnl_data(self):
        total_pnl = self.realized_pnl + self.unrealized_pnl
        roi = (total_pnl / self.trade_margin) * 100 if self.trade_margin != 0 else 0
        
        # Calculate total values based on current state
        total_entry_value = sum(p['entry_price'] * abs(p['quantity']) for p in self.positions.values())
        total_current_value = sum(p['current_price'] * abs(p['quantity']) for p in self.positions.values())

        self.influxdb_manager.write_data(
            measurement="pnl",
            fields={
                "total_pnl": total_pnl,
                "realized_pnl": self.realized_pnl,
                "unrealized_pnl": self.unrealized_pnl,
                "roi": roi,
                "trade_margin": self.trade_margin,
                "total_entry_value": total_entry_value,
                "total_current_value": total_current_value
            }
        )
        
    async def get_all_positions(self):
        return self.positions