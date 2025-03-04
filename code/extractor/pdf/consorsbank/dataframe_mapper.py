import pandas as pd
import re
from typing import List, Optional
from code.model.transaction import Transaction
from code.logger import Logger


class ConsorsbankDataframeMapper:
    """
    Maps rows from a Consorsbank PDF DataFrame to a list of Transaction objects.
    
    A new transaction starts whenever the 'Text/Verwendungszweck' contains
    one of these triggers:
        - *** Kontostand zum
        - LASTSCHRIFT
        - GEBUEHREN
        - EURO-UEBERW.
        - GUTSCHRIFT
        - DAUERAUFTRAG
    
    We first collect rows in 'blocks' until the next trigger is found.
    Then each block is mapped to a single Transaction object.
    """
    TRIGGERS = ["*** Kontostand zum", "LASTSCHRIFT", "GEBUEHREN", "EURO-UEBERW.", "GUTSCHRIFT", "DAUERAUFTRAG"]

    def __init__(self, logger: Logger, source: str):
        self.logger = logger
        self.source = source
        self.id = 0
        
    def getId(self):
        self.id += 1
        return self.id

    def map_transactions(self, df: pd.DataFrame) -> List[Transaction]:
        """
        Main entry point: 
        1) Split the DataFrame rows into blocks, each block ends when a new trigger is found.
        2) Map each block to a Transaction.
        """
        blocks = self._split_into_blocks(df)
        transactions = []

        for idx, block in enumerate(blocks):
            transaction = self._map_block_to_transaction(block)
            if transaction:
                transactions.append(transaction)
            else:
                # Optionally log if the block couldn't be mapped
                self.logger.debug(f"Block {idx} could not be mapped: {[r.to_dict() for r in block]}")

        return transactions

    def _split_into_blocks(self, df: pd.DataFrame) -> List[List[pd.Series]]:
        """
        Splits the DataFrame into a list of blocks (each block is a list of rows).
        A new block is started whenever we encounter a trigger in 'Text/Verwendungszweck'.
        """
        blocks: List[List[pd.Series]] = []
        current_block: List[pd.Series] = []

        for i, row in df.iterrows():
            text_val = str(row.get("Text/Verwendungszweck", "")).strip()

            # If we find a trigger, we finish the current block (if any) and start a new one
            if any(trigger in text_val for trigger in self.TRIGGERS):
                # Falls der current_block schon gefüllt ist, speichern wir ihn
                if current_block:
                    blocks.append(current_block)
                # Neuer Block mit der aktuellen Zeile als Start
                current_block = [row]
            else:
                # Einfach zur aktuellen Block-Liste hinzufügen
                current_block.append(row)

        # Am Ende den letzten Block noch anhängen
        if current_block:
            blocks.append(current_block)

        return blocks

    def _map_block_to_transaction(self, block: List[pd.Series]) -> Optional[Transaction]:
        first_row = block[0]
        text_val = str(first_row.get("Text/Verwendungszweck", "")).strip()
        if "*** Kontostand zum" not in text_val:
            transaction = Transaction(self.logger, self.source)
            transaction.id = str(first_row.get("PNNr", "")).strip()

            #transaction.setValutaDate(first_row.get("Wert",""))
            #transaction.setTransactionDate(first_row.get("Datum", ""))
            transaction.setValutaDate("1993-09-07")
            transaction.setTransactionDate("1993-09-07")
            transaction.currency = "EUR"
            transaction.owner.name = "Max"
            transaction.owner.id = "testid"
            transaction.owner.institute = "Consorsbank"
        
            transaction.type = text_val  # e.g. "LASTSCHRIFT", "GEBUEHREN", etc.

            partner_name_row = block[1] if len(block) > 1 else None
            partner_institute_row = block[2] if len(block) > 2 else None
            description_row = block[3] if len(block) > 3 else None
            data_row = block[4] if len(block) > 4 else None

            transaction.partner.name = str(partner_name_row.get("Text/Verwendungszweck", "")).strip() or "Moritz"
            transaction.partner.institute = str(partner_institute_row.get("Text/Verwendungszweck", "")).strip() or "Blööb"

            if description_row is not None:
                transaction.description = str(description_row.get("Text/Verwendungszweck", "")).strip()

            transaction.value = self._parse_value(
                str(first_row.get("Soll", "")).strip(),
                str(first_row.get("Haben", "")).strip()
            ) or 0
            return transaction

    def _parse_date(self, date_str: str) -> str:
        """
        Converts a date like '31.10.22' to '2022-10-31'.
        If parsing fails, returns the original string or logs a debug message.
        """
        match = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})', date_str)
        if match:
            day, month, year = match.groups()
            if len(year) == 2:
                year = "20" + year
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        else:
            self.logger.debug(f"Could not parse date from '{date_str}'")
            return date_str

    def _parse_value(self, soll_str: str, haben_str: str) -> Optional[float]:
        if soll_str:
            val_str = soll_str.replace('.', '').replace(',', '.').replace('-', '')
            try:
                return -float(val_str)
            except ValueError:
                self.logger.debug(f"Could not parse soll value from '{soll_str}'")
        elif haben_str:
            val_str = haben_str.replace('.', '').replace(',', '.').replace('+', '')
            try:
                return float(val_str)
            except ValueError:
                self.logger.debug(f"Could not parse haben value from '{haben_str}'")
        return None
