#!/usr/bin/env python3
"""Archive current public source versions; never infer a first-result clock."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SOURCES = {
    'AP_CONTROL_EXPLAINER': 'https://apnews.com/article/when-ap-calls-congress-control-9dae62cdd7d776a20a26eab6fbd9b12c',
    'AP_CONTROL_REPORT': 'https://apnews.com/article/trump-midterms-stakes-lame-duck-ab37ed4820d674453e7dc311e2e6636f',
    'AP_SPANISH_UPDATES': 'https://apnews.com/article/trump-elecciones-republicanos-democratas-congreso-0fef291d3de7dd59a1eb2caa6d93fbb5',
    'KY_ENR': 'https://vrsws.sos.ky.gov/liveresults/?id=2026',
    'IN_ENR': 'https://enr.indianavoters.in.gov/site/index.html',
}


def stamp():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = []
        self.times = []
        self.ld = []
        self.in_ld = False
        self.buffer = ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('content'):
            key = attrs.get('property', attrs.get('name', ''))
            if any(x in key.lower() for x in ('time', 'date', 'title', 'modified')):
                self.meta.append(dict(key=key, content=attrs['content']))
        if tag == 'time' and attrs.get('datetime'):
            self.times.append(attrs['datetime'])
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.in_ld = True
            self.buffer = ''

    def handle_data(self, data):
        if self.in_ld:
            self.buffer += data

    def handle_endtag(self, tag):
        if tag == 'script' and self.in_ld:
            try:
                value = json.loads(self.buffer)
                self.scan(value)
            except (ValueError, TypeError):
                pass
            self.in_ld = False

    def scan(self, node):
        if isinstance(node, list):
            for v in node:
                self.scan(v)
        elif isinstance(node, dict):
            fields = {k: node[k] for k in ('@type', '@id', 'url', 'datePublished', 'dateModified', 'startDate', 'endDate') if k in node}
            if any(k in fields for k in ('datePublished', 'dateModified', 'startDate', 'endDate')):
                self.ld.append(fields)
            for v in node.values():
                if isinstance(v, (list, dict)):
                    self.scan(v)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    root = parser.parse_args().output
    root.mkdir(parents=True, exist_ok=False)
    records = []
    for name, url in SOURCES.items():
        record = dict(source_id=name, request_url=url, request_started_at_utc=stamp(),
                      first_availability_status='NOT_ESTABLISHED', accepted_result_anchor=False)
        raw = None
        try:
            request = Request(url, headers={'User-Agent':'crypto-price-feed-election-research/1.1',
                              'Accept':'text/html', 'Accept-Encoding':'identity'})
            with urlopen(request, timeout=25) as response:
                record['http_status'] = response.status
                record['final_url'] = response.url
                record['headers'] = {k:v for k,v in response.headers.items()
                    if k.lower() in ('date','last-modified','etag','content-type','cache-control','age','content-encoding')}
                raw = response.read(4_000_001)
            record['retrieved_at_utc'] = stamp()
            if len(raw) > 4_000_000:
                raise ValueError('response size limit; capture incomplete')
            if record['http_status'] != 200:
                raise ValueError('non-200 response')
            record['capture_status'] = 'ORIGINAL_CURRENT_RESPONSE_NOT_FIRST_PUBLICATION'
            parsed = Metadata()
            parsed.feed(raw.decode('utf-8', errors='replace'))
            record.update(meta=parsed.meta, time_elements=parsed.times, json_ld_clocks=parsed.ld)
        except Exception as error:
            if isinstance(error, HTTPError):
                record['http_status'] = error.code
                raw = error.read(4_000_001)
            record.update(capture_status='FAILED', error=str(error), retrieved_at_utc=stamp())
        if raw is not None:
            path = root / (name + '.response.gz')
            path.write_bytes(gzip.compress(raw, mtime=0))
            record.update(path=path.name, raw_sha256=hashlib.sha256(raw).hexdigest(),
                          gzip_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), raw_bytes=len(raw))
        records.append(record)
    result = dict(completed_at_utc=stamp(), records=records,
        rule='Current document dates, update timestamps and call occurrence statements do not by themselves establish original first public availability. No ledger clocks changed.')
    (root / 'capture_manifest.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
