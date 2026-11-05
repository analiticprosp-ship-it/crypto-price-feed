import importlib.util
from pathlib import Path
import tempfile
import unittest

PATH = Path(__file__).resolve().parents[1] / "scripts/collect_free_news.py"
spec = importlib.util.spec_from_file_location("free_news", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class CollectorTest(unittest.TestCase):
    def test_rss(self):
        rows = module.parse_feed(b'<rss><channel><item><title>Update</title><link>https://example.org/a</link><pubDate>Thu, 05 Nov 2026 09:00:00 GMT</pubDate></item></channel></rss>')
        self.assertEqual(rows[0]["original_url"], "https://example.org/a")
    def test_atom(self):
        rows = module.parse_feed(b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Update</title><link href="https://example.org/b"/><id>abc</id></entry></feed>')
        self.assertEqual(rows[0]["source_item_id"], "abc")
    def test_empty(self):
        self.assertEqual(module.parse_feed(b'<rss><channel/></rss>'), [])
if __name__ == "__main__":
    unittest.main()
