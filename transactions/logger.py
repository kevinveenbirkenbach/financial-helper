# transactions/logger.py

class Logger:
    RESET = "\033[0m"
    RED = "\033[91m"      # For [ERROR]
    YELLOW = "\033[93m"   # For [WARNING]
    BLUE = "\033[94m"     # For [INFO]
    WHITE = "\033[97m"    # For [DEBUG] text

    def __init__(self, debug=False, quiet=False):
        self.debug_enabled = debug
        self.quiet = quiet

    def info(self, message):
        if self.quiet:
            return
        print(f"{self.BLUE}[INFO]{self.RESET} {message}")

    def warning(self, message):
        if self.quiet:
            return
        print(f"{self.YELLOW}[WARNING]{self.RESET} {message}")

    def error(self, message):
        if self.quiet:
            return
        print(f"{self.RED}[ERROR]{self.RESET} {message}")

    def debug(self, message):
        if self.quiet or not self.debug_enabled:
            return
        print(f"{self.WHITE}[DEBUG]{self.RESET} {message}")
