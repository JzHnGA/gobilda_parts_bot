# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
import hashlib
import io
import os
import re
import zipfile
from itemadapter import ItemAdapter

CAD_EXTENSIONS = ('.step', '.stp')

def get_valid_filename(name):
    s = str(name).strip().replace(' ', '_')
    s = re.sub(r'(?u)[^-\w.]', '', s)
    return s

def read_cad_files(zip):
    """Return [(filename, bytes)] for every CAD file in a zip, including zips nested inside it."""
    cad_files = []
    for member in zip.infolist():
        if member.is_dir() or member.filename.startswith('__MACOSX/'):
            continue
        filename = os.path.basename(member.filename)
        if filename.lower().endswith(CAD_EXTENSIONS):
            cad_files.append((filename, zip.read(member)))
        elif filename.lower().endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(zip.read(member))) as inner:
                cad_files += read_cad_files(inner)
    return cad_files

class GobildaPartsBotPipeline:
    def open_spider(self, spider):
        # Read from the crawl's settings so `-s FILES_STORE=...` overrides work too
        self.store = spider.settings.get('FILES_STORE')
        self.sku_names = spider.settings.getbool('SKU_FILE_NAMES')
        self.written = set() # paths written during this crawl, so parts never overwrite each other
        self.processed_urls = set() # downloads already extracted (product variants share one zip)

    def unique_path(self, base, ext, sku):
        path = os.path.join(self.store, base + ext)
        if path in self.written and sku:
            path = os.path.join(self.store, f'{base}_{sku}{ext}')
        n = 2
        while path in self.written:
            path = os.path.join(self.store, f'{base}_{n}{ext}')
            n += 1
        self.written.add(path)
        return path

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        stats = spider.crawler.stats
        # Item loaders give us a list with one value, so we have to access the first
        # element of the list to get the actual string data
        sku = get_valid_filename(adapter['sku'][0]) if adapter.get('sku') else ''
        name = sku if self.sku_names and sku else get_valid_filename(adapter['name'][0])

        cad_files = []
        new_downloads = False
        for downloaded in adapter.get('files') or []:
            if downloaded['url'] in self.processed_urls:
                continue
            self.processed_urls.add(downloaded['url'])
            new_downloads = True
            zip_path = os.path.join(self.store, downloaded['path'])
            if os.path.exists(zip_path):
                if zipfile.is_zipfile(zip_path):
                    with zipfile.ZipFile(zip_path, 'r') as zip:
                        cad_files += read_cad_files(zip)
                elif zip_path.lower().endswith(CAD_EXTENSIONS):
                    with open(zip_path, 'rb') as f:
                        cad_files.append((os.path.basename(zip_path), f.read()))
                os.remove(zip_path)

        if not new_downloads:
            # Another variant of this product already extracted the same download
            stats.inc_value('parts/shared_download')
            return item
        if not cad_files:
            stats.inc_value('parts/no_cad_in_download')
            spider.logger.warning('Download contained no CAD file (likely software/docs): %s (%s)', name, adapter.get('url'))
            return item

        for filename, data in cad_files:
            stem, _ = os.path.splitext(filename)
            # A single file is named after the part; multi-file zips keep each member's name too
            base = name if len(cad_files) == 1 else f'{name}__{get_valid_filename(stem)}'
            with open(self.unique_path(base, '.STEP', sku), 'wb') as f:
                f.write(data)
        stats.inc_value('parts/cad_files', len(cad_files))
        return item

    def close_spider(self, spider):
        # FilesPipeline downloads into FILES_STORE/full; remove it once it's empty
        try:
            os.rmdir(os.path.join(self.store, 'full'))
        except OSError:
            pass
        self.remove_duplicates(spider)

    def remove_duplicates(self, spider):
        """Delete byte-identical CAD files (e.g. pack contents that repeat individual parts)."""
        by_hash = {}
        for path in self.written:
            with open(path, 'rb') as f:
                by_hash.setdefault(hashlib.sha256(f.read()).hexdigest(), []).append(path)
        removed = []
        for paths in by_hash.values():
            if len(paths) < 2:
                continue
            # Keep an individual part's own file over a member of a multi-file zip, then the shortest name
            paths.sort(key=lambda p: ('__' in os.path.basename(p), len(p), p))
            for duplicate in paths[1:]:
                os.remove(duplicate)
                removed.append(f'{os.path.basename(duplicate)} (same as {os.path.basename(paths[0])})')
        spider.crawler.stats.set_value('parts/duplicates_removed', len(removed))
        if removed:
            spider.logger.info('Removed %d duplicate CAD files:\n  %s', len(removed), '\n  '.join(sorted(removed)))
