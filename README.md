## goBILDA Parts Bot

A [ Scrapy ](https://scrapy.org/) spider written in python that scrapes almost the entirety of the goBILDA website for each and every `.STEP` file, for use in any CAD software supporting `.STEP`. 

## How to Run

1. Create a [ virtualenv ](https://docs.python.org/3/tutorial/venv.html) and install [ scrapy ](https://scrapy.org/) and [ tqdm ](https://tqdm.github.io/) (assuming you already have python 3 installed)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
> On Windows, activate with `.venv\Scripts\activate` instead.

2. Make sure you have a valid `FILES_STORE` defined in `settings.py`. By default, files go into a folder at the root of this repository called `models.nosync` (Scrapy creates it if it doesn't exist):
```
├───gobilda_parts_bot
│   ├───spiders
│   │   └───__pycache__
│   └───__pycache__
└───models.nosync  <-- CAD files end up here
```
> The `.nosync` ending stops iCloud Drive from uploading the ~8 GB of models if the repo lives in a synced folder like `Documents`. Feel free to change `FILES_STORE` to whatever suits your needs

3. set `SKU_FILE_NAMES` (also defined in `settings.py`). By default, file names are the full product name as displayed on the goBILDA website. These names are long, which can cause problems with uploading to Fusion. To get filenames that consist only of the part's SKU, set `SKU_FILE_NAMES` to `True`.

4. Run the `parts` spider:
```bash
scrapy crawl parts
```
5. Wait for the `FILES_STORE` to populate, and you are good to go! A full crawl visits ~2,400 product pages and is throttled to be polite to the site, so expect it to take a while. At the end, the log lists every kit/bundle/merch product that was skipped, and the stats show `parts/cad_files` (files written), `parts/duplicates_removed`, and `parts/no_cad_in_download` (downloads that only contained software or docs).

## How it works
The spider reads goBILDA's product sitemap (`https://www.gobilda.com/xmlsitemap.php`), which lists every product on the site, so no part is missed because it sits in an unusual category. Each product page is passed to `parse_product_page()`, which:
- skips pages with no `.STEP` download (`a.ext-zip`)
- skips kits, bundles and merch: products whose top-level breadcrumb is `KITS` or `MERCH`, or whose name or breadcrumbs mention a bundle, FTC kit, starter kit or chassis kit. Their CAD files are assemblies that repeat individual parts. Small "kits" like standoff or tensioner kits are real parts and are kept.
- otherwise records the part's name, SKU and every CAD download link

Scrapy's `FilesPipeline` downloads the zips, then `GobildaPartsBotPipeline` extracts **every** `.STEP`/`.stp` file from each zip (including zips nested inside it), ignores software/docs, and deletes the zip. A single-file zip becomes `<name>.STEP`; a multi-file zip becomes `<name>__<file>.STEP` for each file. If two parts would get the same filename, the SKU (or a number) is appended so nothing is overwritten. At the end of the crawl, byte-identical files (e.g. hardware packs that repeat individual parts) are removed, keeping the individual part's file. One thing to note: the file's names don't look exactly like the names displayed on the website, as I had to get rid of colons, spaces, and other forbidden characters to get a clean filename. 

> Note: When I uploaded the complete parts folder to Fusion 360 (my CAD software of choice), it said 10 out of the 80 models failed to upload. I'm not sure which ones are the culprits, or if it is just Fusion being fusion,but create an issue or pull request if you've found the problem and/or solution. 