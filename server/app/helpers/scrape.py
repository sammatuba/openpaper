import os

from firecrawl import FirecrawlApp

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

# Built on first use so a deployment without Firecrawl still starts; the web
# tool then fails only the scrape it was asked for.
_firecrawl_app: FirecrawlApp | None = None


def _get_firecrawl_app() -> FirecrawlApp:
    global _firecrawl_app
    if _firecrawl_app is None:
        api_key = os.getenv("FIRECRAWL_API_KEY") or FIRECRAWL_API_KEY
        if not api_key:
            raise ValueError("FIRECRAWL_API_KEY environment variable is not set.")
        _firecrawl_app = FirecrawlApp(api_key=api_key)
    return _firecrawl_app


def scrape_web_page(url: str) -> str:
    """
    Scrape the content of a web page using Firecrawl.

    Args:
        url (str): The URL of the web page to scrape.

    Returns:
        str: The scraped content of the web page.
    """
    try:
        # firecrawl-py 4.x: scrape() returns a Document (with .markdown) on
        # success and raises on failure. There is no .error attribute.
        document = _get_firecrawl_app().scrape(url, formats=["markdown"])
        if document.markdown:
            return document.markdown
        raise Exception(f"Failed to scrape {url}: no markdown content returned")
    except Exception as e:
        # Scrape failures are expected (anti-bot walls, dead links) and the
        # caller logs them at warning; don't also log at error here.
        raise Exception(f"Error scraping {url}: {str(e)}")
