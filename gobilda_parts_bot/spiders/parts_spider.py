from scrapy.spiders import SitemapSpider
from scrapy.loader import ItemLoader
from gobilda_parts_bot.items import Product
from tqdm import tqdm
import re
import sys

# Kits, bundles and merch have CAD files that are assemblies repeating individual parts,
# so we skip them. Products filed under these top-level categories are skipped...
EXCLUDED_TOP_CATEGORIES = ('KITS', 'MERCH')
# ...as are products named like this (some kit/bundle pages have no breadcrumbs).
# Smaller "kits" such as standoff or tensioner kits are real parts and are kept.
EXCLUDED_NAMES = re.compile(r'bundle|\b(ftc|starter|chassis) kit\b', re.IGNORECASE)


class PartsSpider(SitemapSpider):
	name = "parts"
	# The product sitemap lists every product on the site, so we don't miss parts
	# that are only reachable through unusual category links
	sitemap_urls = ['https://www.gobilda.com/xmlsitemap.php']
	sitemap_follow = [r'type=products']
	sitemap_rules = [('', 'parse_product_page')]

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.pbar = tqdm(total=0, unit='page', file=sys.stdout)
		self.excluded = []

	def sitemap_filter(self, entries):
		for entry in entries:
			# Product pages (not nested sitemaps) count towards the progress bar total
			if 'xmlsitemap.php' not in entry['loc']:
				self.pbar.total += 1
				self.pbar.refresh()
			yield entry

	def parse_product_page(self, response):
		self.pbar.update(1)
		# Some products have more than one CAD download, so grab every one
		step_files = list(dict.fromkeys(response.css('a.ext-zip::attr(href)').getall()))
		if not step_files:
			return

		name = (response.css('h1.productView-title::text').get() or '').strip()
		sku = (response.css('span.productView-sku-input::text').get() or '').strip()
		crumbs = [c.strip() for c in response.css('.breadcrumbs a ::text').getall() if c.strip()]

		if ((crumbs and crumbs[0].upper() in EXCLUDED_TOP_CATEGORIES)
				or any(EXCLUDED_NAMES.search(text) for text in crumbs + [name])):
			self.excluded.append(f'{name} | {" > ".join(crumbs)} | {response.url}')
			self.crawler.stats.inc_value('parts/excluded')
			return

		loader = ItemLoader(Product(), response=response)
		loader.add_value('sku', sku or None)
		loader.add_value('file_urls', [response.urljoin(f) for f in step_files])
		# Fall back to the URL slug if a page has no title
		loader.add_value('name', name or response.url.rstrip('/').rsplit('/', 1)[-1])
		loader.add_value('url', response.url)
		return loader.load_item()

	def closed(self, reason):
		self.pbar.close()
		if self.excluded:
			self.logger.info('Skipped %d kit/bundle/merch products:\n  %s',
				len(self.excluded), '\n  '.join(sorted(self.excluded)))
