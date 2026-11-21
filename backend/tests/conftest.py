import os

# Tests run on the small, fixed seed knowledge base so results are predictable.
# The full website crawl is measured separately by the evals.
os.environ["CRAWLED_FILE"] = "/nonexistent/crawled_pages.json.gz"
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test.db")
