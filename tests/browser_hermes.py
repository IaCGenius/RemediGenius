"""Explicit cloud browser acceptance; prepares disclosure but starts no model call."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    url = os.environ['RGCE_CLOUD_PREVIEW_URL']
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge')
        page = browser.new_page(viewport={'width': 1440, 'height': 1050})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(url)
        expect(page.locator('#storage-status')).to_contain_text('S3')
        expect(page.locator('#hermes-agent')).to_be_visible()
        expect(page.locator('#hermes-agent')).to_contain_text('Ready')
        picker = page.locator('#hermes-assessment')
        expect(picker.locator('option').first).to_have_attribute('value', __import__('re').compile('[a-f0-9]{64}'))
        picker.select_option(index=0)
        page.get_by_role('button', name='Review investigation scope', exact=True).click()
        expect(page.get_by_role('button', name='Consent and start Hermes', exact=True)).to_be_visible()
        expect(page.locator('#hermes-agent')).to_contain_text('snapshot files')
        page.get_by_role('button', name='Read exact snapshot', exact=True).click()
        expect(page.locator('#detail-title')).to_contain_text('Model disclosure snapshot')
        page.get_by_role('button', name='Close details', exact=True).click()
        page.locator('#hermes-question').fill('Changed question requires a new disclosure review')
        expect(page.get_by_role('button', name='Consent and start Hermes', exact=True)).to_have_count(0)
        page.get_by_role('button', name='Ask a follow-up', exact=True).first.click()
        expect(page.locator('#hermes-question')).to_have_value('')
        page.locator('#hermes-question').fill('Review the existing answer; do not invent missing context.')
        page.get_by_role('button', name='Review investigation scope', exact=True).click()
        page.get_by_role('button', name='Read exact snapshot', exact=True).click()
        expect(page.locator('#detail')).to_contain_text('prior-analysis.md')
        page.get_by_role('button', name='Close details', exact=True).click()
        Path('playwright-output').mkdir(exist_ok=True)
        page.screenshot(path='playwright-output/hermes-cloud.png', full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+2')
        assert not errors, errors
        browser.close()
    print('Cloud Hermes browser passed: S3, runtime status, selected input, exact disclosure review, changed-question invalidation, real follow-up disclosure and mobile layout. No model call started by this test.')


if __name__ == '__main__':
    main()
