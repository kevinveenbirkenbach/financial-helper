import os
import concurrent.futures
from pdfminer.high_level import extract_text
from .logger import Logger

class TransactionProcessor:
    """Coordinates reading files (PDF, CSV) from multiple paths and exporting transactions."""
    def __init__(self, input_paths, output_base, print_transactions=False, recursive=False, export_types=None,
                 from_date=None, to_date=None, create_dirs=False, quiet=False, logger=Logger(), print_cmd=False):
        self.input_paths = input_paths
        self.output_base = output_base
        self.all_transactions = []
        self.print_transactions = print_transactions
        self.recursive = recursive
        self.export_types = export_types or []
        self.from_date = from_date
        self.to_date = to_date
        self.create_dirs = create_dirs
        self.quiet = quiet
        self.print_cmd = print_cmd
        self.logger = logger

    def _filter_by_date(self):
        if self.from_date or self.to_date:
            filtered = []
            for transaction in self.all_transactions:
                if transaction.transaction_date:
                    if self.from_date and transaction.transaction_date < self.from_date:
                        continue
                    if self.to_date and transaction.transaction_date > self.to_date:
                        continue
                else:
                    self.logger.warning(f"Transaction {transaction} doesn't contain a date attribut.")
                filtered.append(transaction)
            self.all_transactions = filtered
        
    def process(self):
        pdf_csv_files = []
        for path in self.input_paths:
            if os.path.isdir(path):
                if self.recursive:
                    for root, _, files in os.walk(path):
                        for file_name in files:
                            if file_name.lower().endswith((".pdf", ".csv")):
                                pdf_csv_files.append(os.path.join(root, file_name))
                else:
                    pdf_csv_files.extend([
                        os.path.join(path, file_name)
                        for file_name in os.listdir(path)
                        if file_name.lower().endswith((".pdf", ".csv"))
                    ])
            elif os.path.isfile(path) and path.lower().endswith((".pdf", ".csv")):
                pdf_csv_files.append(path)
            else:
                self.logger.warning(f"Invalid input path: {path}")
        if not pdf_csv_files:
            self.logger.warning("No PDF/CSV files found in the given paths.")
            return
        self.logger.info(f"Found {len(pdf_csv_files)} files.")

        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = list(executor.map(self.extract_from_file, pdf_csv_files))
            for transactions in results:
                self.all_transactions.extend(transactions)

        self._filter_by_date();

        self.logger.debug(self.all_transactions)
        # Export logic: iterate over all specified export types
        for fmt in self.export_types:
            ext = f".{fmt}"
            output_file = self.output_base
            if not output_file.endswith(ext):
                output_file += ext
            if self.create_dirs:
                os.makedirs(os.path.dirname(output_file), exist_ok=True)

            if fmt == "csv":
                from .exporter import CSVExporter
                exporter = CSVExporter(self.all_transactions, output_file)
                exporter.export()
            elif fmt == "html":
                from .exporter import HTMLExporter
                exporter = HTMLExporter(self.all_transactions, output_file, from_date=self.from_date, to_date=self.to_date)
                exporter.export()
            elif fmt == "json":
                from .exporter import JSONExporter
                exporter = JSONExporter(self.all_transactions, output_file)
                exporter.export()
            elif fmt == "yaml":
                from .exporter import YamlExporter
                exporter = YamlExporter(self.all_transactions, output_file)
                exporter.export()
        if self.print_transactions:
            self.console_output()

    def extract_from_file(self,file_path):
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".csv":
            with open(file_path, encoding="utf-8") as f:
                lines = [f.readline() for _ in range(10)]
            content = " ".join(lines)
            if "Transaktionscode" in content or "PayPal" in content:
                from .extractor_csv_paypal import PayPalCSVExtractor
                extractor = PayPalCSVExtractor(file_path)
            elif "Buchungsdatum" in content:
                from .extractor_csv_dkb import DKBCSVExtractor
                extractor = DKBCSVExtractor(file_path, self.logger)
            else:
                return []
        elif ext == ".pdf":
            try:
                text = extract_text(file_path, maxpages=1)
                lower_text = text.lower()
            except Exception:
                text = ""
                self.logger.info(f"No text could be extracted from {file_path}.")
            if "PayPal" in text and ("Händlerkonto-ID" in text or "Transaktionsübersicht" in text):
                from .extractor_pdf_paypal import PayPalPDFExtractor
                extractor = PayPalPDFExtractor(file_path)
            elif "Consorsbank" in text or "KONTOAUSZUG" in text:
                from .extractor_pdf_consorsbank import PDFConsorsbankExtractor
                extractor = PDFConsorsbankExtractor(file_path, self.logger)
            elif "ing-diba" in lower_text or "ingddeffxxx" in lower_text:
                from .extractor_pdf_ing import IngPDFExtractor
                extractor = IngPDFExtractor(file_path, self.logger)
            elif "barclaycard" in lower_text or "barcdehaxx" in lower_text:
                from .extractor_pdf_barclay import BarclaysPDFExtractor
                extractor = BarclaysPDFExtractor(file_path, self.logger)
        if 'extractor' in locals():
            return extractor.extract_transactions()
        else:
            self.logger.info(f"No extractor found for {file_path}.")
            return []

    def console_output(self):
        if self.quiet:
            return
        print("\nAll Transactions:")
        for t in self.all_transactions:
            print(f"{t.date}\t{t.description}\t{t.value}\t{t.sender}\t{t.transaction_source_document}\t{t.bank}\t{t.id}")
