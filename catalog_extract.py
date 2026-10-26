#!/usr/bin/env python3
"""Extract a small set of visible course facts from saved catalog HTML.

Offline demonstration, not a universal catalog crawler. Unknown templates,
ambiguous titles, missing credits and conflicting records require review.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urlparse


@dataclass
class Node:
    tag: str
    attrs: dict
    children: list

    def text(self):
        return ' '.join(''.join(x.text() if isinstance(x, Node) else x
                                for x in self.children).split())

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()


class Document(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
            'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node('document', {}, [])
        self.stack = [self.root]
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), [])
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if not any(n.tag in {'script', 'style'} for n in self.stack):
            self.stack[-1].children.append(data)


class ReviewRequired(ValueError):
    pass


def one(values, label):
    values = set(values)
    if len(values) != 1:
        raise ReviewRequired(f'{label}: expected one distinct value, found {len(values)}')
    return next(iter(values))


def credits(text):
    if not re.fullmatch(r'\d+(?:\.\d+)?', text):
        raise ReviewRequired('Credits must be an explicit nonnegative decimal')
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ReviewRequired('Invalid credits') from exc
    if value > 99:
        raise ReviewRequired('Credits exceed this demonstration’s supported range')
    return format(value.normalize(), 'f')


def extract_coursedog(doc):
    # Use rendered text, not an undocumented vendor API or serialized app state.
    headings = []
    pattern = r'([A-Z][A-Z& ]*\d+[A-Z]?)\s+-\s+(.+?)\s+\((\d+(?:\.\d+)?)(?:\s*[-–]\s*(\d+(?:\.\d+)?))?\s+cr\)'
    for n in doc.root.walk():
        if n.tag == 'h2':
            match = re.fullmatch(pattern, n.text())
            if match:
                headings.append(match.groups())
    code, title, shown_min, shown_max = one(headings, 'Course heading')
    code = re.sub(r'\s+', '', code)
    if code not in {re.sub(r'\s+', '', n.text()) for n in doc.root.walk() if n.tag == 'h1'}:
        raise ReviewRequired('Course heading lacks a matching primary course identifier')
    labels = {}
    for n in doc.root.walk():
        hs = [x.text() for x in n.children if isinstance(x, Node) and x.tag == 'h3']
        vs = [x.text() for x in n.children if isinstance(x, Node)
              and 'field-value' in x.attrs.get('class', '').split()]
        if len(hs) == 1 and vs and hs[0] in {'Minimum Credits', 'Maximum Credits'}:
            labels.setdefault(hs[0], []).extend(vs)
    lower = credits(one(labels.get('Minimum Credits', []), 'Minimum Credits'))
    upper = credits(one(labels.get('Maximum Credits', []), 'Maximum Credits'))
    if Decimal(lower) > Decimal(upper):
        raise ReviewRequired('Minimum credits exceed maximum')
    # A heading may abbreviate variable credits, so it must fall inside the range.
    if not Decimal(lower) <= Decimal(shown_min) <= Decimal(upper):
        raise ReviewRequired('Heading credits contradict the credit fields')
    if shown_max and Decimal(shown_max) != Decimal(upper):
        raise ReviewRequired('Heading maximum contradicts the credit field')
    return {'code': code, 'title': title,
            'credits_min': lower, 'credits_max': upper}


def extract(html: bytes, source_url: str):
    parsed = urlparse(source_url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ReviewRequired('Supply a credential-free HTTPS source URL')
    try:
        doc = Document(html.decode('utf-8-sig'))
    except (UnicodeError, RecursionError) as exc:
        raise ReviewRequired('Unreadable HTML') from exc
    if not any(n.tag == 'script' and n.attrs.get('id') == '__NUXT_DATA__'
               for n in doc.root.walk()):
        raise ReviewRequired('Unsupported template; no data guessed')
    facts = extract_coursedog(doc)
    return {**facts, 'source_url': source_url,
            'source_sha256': hashlib.sha256(html).hexdigest(),
            'adapter': 'coursedog-rendered-course-v1',
            'catalog_year': None}


def batch(manifest, base):
    extracted, review = [], []
    for entry in manifest:
        source = (base / entry['file']).resolve()
        if base.resolve() not in source.parents:
            raise ValueError('Input files must remain inside the manifest directory')
        try:
            record = extract(source.read_bytes(), entry['url'])
            record['checked_utc'] = entry.get('checked_utc')
            extracted.append(record)
        except (OSError, ReviewRequired) as exc:
            review.append({'file': entry['file'], 'source_url': entry['url'], 'reason': str(exc)})
    # Same course code across versions/institutions is not silently merged.
    groups = {}
    for record in extracted:
        key = (urlparse(record['source_url']).hostname, record['code'])
        groups.setdefault(key, []).append(record)
    clean = []
    for records in groups.values():
        if len(records) > 1:
            for record in records:
                review.append({'source_url': record['source_url'], 'code': record['code'],
                               'reason': 'Repeated course code requires version/deduplication review'})
        else:
            clean.extend(records)
    return {'records': clean, 'review': review,
            'source_count': len(manifest), 'clean_count': len(clean),
            'review_count': len(review), 'network_calls': 0,
            'limitations': ['One supported rendered course template; not a universal extractor.',
                            'Catalog year is unverified and left null.',
                            'No prerequisite interpretation or full-catalog completeness claim.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args()
    items = json.loads(args.manifest.read_text())
    print(json.dumps(batch(items, args.manifest.parent), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
