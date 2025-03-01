import re
from datetime import datetime
from pdfminer.high_level import extract_text
from .transaction import Transaction
from .logger import Logger


class PDFConsorsbankExtractor:
    def __init__(self, pdf_path, debug=False):
        self.pdf_path = pdf_path
        self.transactions = []
        self.previous_balance = None
        self.debug = debug
        self.logger = Logger(debug=debug)

    @staticmethod
    def parse_amount(s):
        s = s.strip()
        sign = 1
        if s.endswith('+'):
            sign = 1
        elif s.endswith('-'):
            sign = -1
        s = s[:-1].strip()
        s = s.replace('.', '').replace(',', '.')
        try:
            return sign * float(s)
        except Exception as e:
            print(f"[ERROR] Could not parse amount '{s}': {e}")
            return None

    @staticmethod
    def format_amount(val):
        if val is None:
            return ""
        s = f"{abs(val):.2f}".replace('.', ',')
        return s + ("+" if val >= 0 else "-")

    @staticmethod
    def convert_to_iso(datum_str, global_year):
        datum_str = datum_str.strip()
        m = re.fullmatch(r'(\d{2})\.(\d{2})\.(\d{2,4})', datum_str)
        if m:
            day, month, year = m.groups()
            if len(year) == 2:
                year = "20" + year
            return f"{year}-{month}-{day}"
        m2 = re.fullmatch(r'(\d{2})\.(\d{2})\.', datum_str)
        if m2 and global_year:
            day, month = m2.groups()
            return f"{global_year}-{month}-{day}"
        return datum_str

    def extract_transactions(self):
        text = extract_text(self.pdf_path)
        global_year = None
        year_match = re.search(r'\b\d{2}\.\d{2}\.(\d{2,4})\b', text)
        if year_match:
            year_str = year_match.group(1)
            global_year = "20" + year_str if len(year_str) == 2 else year_str
        block_pattern = re.compile(
            r'^(?P<type>LASTSCHRIFT|EURO-UEBERW\.|GUTSCHRIFT)\s*\n'
            r'(?P<block>.*?)(?=^(?:LASTSCHRIFT|EURO-UEBERW\.|GUTSCHRIFT)\s*\n|\Z)',
            re.DOTALL | re.MULTILINE
        )
        detail_pattern = re.compile(
            r'(?P<datum>\d{2}\.\d{2}\.)\s+(?P<pnnr>\d{3,4})\s*\n\s*'
            r'(?P<wert>\d{2}\.\d{2}\.)\s*\n\s*'
            r'(?P<amount>[\d.,]+[+-])',
            re.MULTILINE
        )
        balance_pattern = re.compile(
            r'\*\*\*\s*Kontostand zum [^\d]*\s*(?P<balance>[\d.,]+[+-])'
        )
        for m_block in block_pattern.finditer(text):
            trans_type = m_block.group('type').strip()
            block = m_block.group('block')
            if trans_type in {"LASTSCHRIFT", "EURO-UEBERW."}:
                detail_match = detail_pattern.search(block)
                if not detail_match:
                    continue
                datum_raw = detail_match.group('datum').strip()
                wert_raw = detail_match.group('wert').strip()
                amount_extracted = detail_match.group('amount').strip()
            else:
                lines = [line.strip() for line in block.splitlines() if line.strip()]
                datum_raw, wert_raw = "", ""
                for idx, line in enumerate(lines):
                    m_date = re.match(r'^(\d{2}\.\d{2}\.?\d{0,4})', line)
                    if m_date:
                        datum_raw = m_date.group(1)
                        if idx + 1 < len(lines):
                            m_date2 = re.match(r'^(\d{2}\.\d{2}\.?\d{0,4})', lines[idx+1])
                            if m_date2:
                                wert_raw = m_date2.group(1)
                        break
                amount_extracted = ""
            datum_iso = self.convert_to_iso(datum_raw, global_year) if datum_raw else ""
            current_balance = None
            balance_match = balance_pattern.search(block)
            if balance_match:
                current_balance = self.parse_amount(balance_match.group('balance'))
            if trans_type == "GUTSCHRIFT" and (amount_extracted == "" or self.parse_amount(amount_extracted) is None):
                if self.previous_balance is not None and current_balance is not None:
                    diff = current_balance - self.previous_balance
                    amount_extracted = self.format_amount(diff)
                else:
                    amount_extracted = ""
            if trans_type in {"LASTSCHRIFT", "EURO-UEBERW."} and detail_pattern.search(block):
                description = block[:detail_pattern.search(block).start()].strip().replace('\n', ' ')
            else:
                description = block.strip().replace('\n', ' ')
            
            amount_val = self.parse_amount(amount_extracted)
            full_description = f"{trans_type}: {description}"
            transaction = Transaction(datum_iso, full_description, amount_val, "", self.pdf_path, bank="Consorsbank", currency="", invoice="", to="")
            self.transactions.append(transaction)
            if self.debug:
                self.logger.debug(f"Transaction {transaction} appended.")
            if current_balance is not None:
                self.previous_balance = current_balance
        return self.transactions
