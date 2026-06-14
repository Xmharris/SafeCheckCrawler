import urllib.robotparser
import urllib.parse
import urllib.request
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

# Global Configuration Layer
CONFIG = {
    # It's crucial to identify your bot and provide contact information 
    # so server admins can reach you if there's an issue.
    'USER_AGENT': 'EthicalDataBot/1.0 (+mailto:research@example.org)',
    
    # A polite fallback delay if the server doesn't specify one in robots.txt
    'DEFAULT_CRAWL_DELAY': 3.0, 
    
    # Sample target URLs
    'TARGET_URLS': [
        'https://example.com',
    ]
}
class EthicalComplianceManager:
    """
    Dynamically checks robots.txt permissions and enforces crawl delays.
    Caches the parser instances to prevent redundant requests to the host.
    """
    def __init__(self, user_agent: str):
        self.user_agent = user_agent
        self._parsers: Dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last_request_time: Dict[str, float] = {}

    def _get_domain_root(self, url: str) -> str:
        """Extracts the base domain from a full URL."""
        parsed = urllib.parse.urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _get_parser(self, url: str) -> urllib.robotparser.RobotFileParser:
        """Fetches and caches the robots.txt parser for a domain."""
        domain = self._get_domain_root(url)
        if domain not in self._parsers:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = urllib.parse.urljoin(domain, '/robots.txt')
            rp.set_url(robots_url)
            try:
                # Fetch robots.txt with our declared User-Agent
                req = urllib.request.Request(robots_url, headers={'User-Agent': self.user_agent})
                with urllib.request.urlopen(req, timeout=10) as response:
                    rp.parse(response.read().decode('utf-8').splitlines())
            except Exception as e:
                print(f"[!] Warning: Could not parse robots.txt for {domain}. Assuming restrictive defaults. ({e})")
            
            self._parsers[domain] = rp
            self._last_request_time[domain] = 0.0
            
        return self._parsers[domain]

    def can_fetch(self, url: str) -> bool:
        """Validates if the endpoint is allowed for scraping by the host."""
        rp = self._get_parser(url)
        return rp.can_fetch(self.user_agent, url)

    def get_crawl_delay(self, url: str, fallback_delay: float) -> float:
        """Retrieves the host-specified crawl delay, or applies the safe fallback."""
        rp = self._get_parser(url)
        delay = rp.crawl_delay(self.user_agent)
        
        # If no specific delay for our agent, check the wildcard agent
        if delay is None:
            delay = rp.crawl_delay('*')
            
        return delay if delay is not None else fallback_delay

    def apply_rate_limit(self, url: str, fallback_delay: float):
        """Blocks execution to ensure we do not hammer the host server."""
        domain = self._get_domain_root(url)
        delay = self.get_crawl_delay(url, fallback_delay)
        
        # Ensure the domain is tracked
        self._get_parser(url)
        
        elapsed = time.time() - self._last_request_time.get(domain, 0.0)
        if elapsed < delay:
            sleep_time = delay - elapsed
            print(f"[*] Polite backoff: Sleeping for {sleep_time:.2f}s to respect {domain} rate limits.")
            time.sleep(sleep_time)
            
    def mark_request_complete(self, url: str):
        """Registers the timestamp of the last successful HTTP request."""
        domain = self._get_domain_root(url)
        self._last_request_time[domain] = time.time()

class BaseScraper(ABC):
    """
    Abstract base class establishing the contract for all domain-specific scrapers.
    """
    def __init__(self, compliance_manager: EthicalComplianceManager):
        self.compliance = compliance_manager

    def fetch_content(self, url: str) -> Optional[str]:
        """
        The core engine for retrieving data. Guarantees robots.txt checks and rate limiting.
        """
        if not self.compliance.can_fetch(url):
            print(f"[X] Blocked by robots.txt: Permission denied for {url}")
            return None
            
        # Sleep if we are making requests too quickly
        self.compliance.apply_rate_limit(url, CONFIG['DEFAULT_CRAWL_DELAY'])
        
        print(f"[>] Fetching: {url}")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': self.compliance.user_agent})
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8')
                
            # Record the time immediately after request finishes
            self.compliance.mark_request_complete(url)
            return html
            
        except Exception as e:
            print(f"[!] Failed to fetch {url}. Error: {e}")
            self.compliance.mark_request_complete(url)
            return None

    @abstractmethod
    def parse(self, html: str) -> Any:
        """Extract entities from raw HTML."""
        pass

    def scrape(self, url: str) -> Any:
        """Template method connecting the compliant fetch with domain-specific parsing."""
        html = self.fetch_content(url)
        if html:
            # The DB preparation step is implicitly handled here
            # by returning a standardized dictionary or object.
            return self.parse(html)
        return None


class ScraperFactory:
    """
    Instantiates the correct scraper subclass based on the target URL's domain.
    """
    _registry = {}

    @classmethod
    def register(cls, domain: str):
        """Decorator to link a URL domain to a specific scraper class."""
        def inner_wrapper(wrapped_class):
            cls._registry[domain] = wrapped_class
            return wrapped_class
        return inner_wrapper

    @classmethod
    def get_scraper(cls, url: str, compliance_manager: EthicalComplianceManager) -> BaseScraper:
        domain = urllib.parse.urlparse(url).netloc
        scraper_cls = cls._registry.get(domain)
        if not scraper_cls:
            raise NotImplementedError(f"No scraper implemented for domain: {domain}")
        return scraper_cls(compliance_manager)

@ScraperFactory.register('example.com')
class ExampleScraper(BaseScraper):
    """
    Concrete implementation tailored for a specific domain.
    """
    def parse(self, html: str) -> Dict[str, Any]:
        # Implement custom HTML parsing logic here (e.g. using BeautifulSoup)
        title_start = html.find('<title>') + 7
        title_end = html.find('</title>')
        title = html[title_start:title_end] if title_start > 6 else "Unknown Title"
        
        prepared_data = {
            'source_domain': 'example.com',
            'page_title': title.strip(),
            'scraped_bytes': len(html),
            'timestamp': time.time()
        }
        return prepared_data

if __name__ == "__main__":
    # Setup the Compliance Manager
    manager = EthicalComplianceManager(CONFIG['USER_AGENT'])
    
    print("========== RUNNING SCRAPER PIPELINE ==========")
    for target_url in CONFIG['TARGET_URLS']:
        try:
            # Factory instantiates the exact scraper needed
            active_scraper = ScraperFactory.get_scraper(target_url, manager)
            
            # Perform the scrape (handles politeness, fetch, and parse automatically)
            data_record = active_scraper.scrape(target_url)
            
            if data_record:
                print(f"\n[+] Scrape successful for {target_url}. Prepared record:")
                import json
                print(json.dumps(data_record, indent=4))
            
        except Exception as e:
            print(f"[!] Pipeline Error for {target_url}: {e}")
