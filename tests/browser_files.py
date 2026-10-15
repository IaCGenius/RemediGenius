"""Skills-first export UX, tested against a local preview with synthetic data only."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get('RGCE_PREVIEW_URL','http://127.0.0.1:8765')
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge')
    page=browser.new_page(viewport={'width':1440,'height':1050})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(BASE)
    expect(page.locator('#storage-status')).to_contain_text('local data directory')
    page.get_by_role('button',name='Try the sample workspace').click()
    expect(page.locator('#message')).to_contain_text('Synthetic demo only')
    page.get_by_role('button',name='Connections',exact=True).click()
    expect(page.locator('#file-workspace')).to_contain_text('No MCP required')
    expect(page.locator('#connection')).not_to_be_visible()
    expect(page.locator('#file-workspace-record option').first).to_have_attribute('value',__import__('re').compile('[a-f0-9]{64}'))
    page.get_by_role('button',name='Export readable workspace',exact=True).click()
    expect(page.locator('#file-workspace-result')).to_contain_text('No cloud or model calls')
    with page.expect_download() as investigation:
        page.get_by_role('link',name='Download investigation ZIP',exact=True).click()
    assert investigation.value.suggested_filename=='remedigenius-investigation.zip'
    with page.expect_download() as download:
        page.get_by_role('link',name='Read / download the investigation skill',exact=True).click()
    assert download.value.suggested_filename=='SKILL.md'
    page.get_by_text('Optional: connect through MCP',exact=True).click()
    runtime=page.request.get(BASE+'/api/state').json()['runtime']
    if runtime.get('local_stdio_supported',True):
        page.get_by_role('button',name='Hermes YAML',exact=True).click()
        expect(page.locator('#connection')).to_contain_text('mcp_servers:')
    else:
        expect(page.get_by_role('button',name='Hermes YAML',exact=True)).to_be_disabled()
        expect(page.locator('#connection')).to_contain_text('download selected investigation files')
    page.get_by_text('Optional: connect through MCP',exact=True).click()
    Path('playwright-output').mkdir(exist_ok=True)
    page.screenshot(path='playwright-output/files-first.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+2')
    assert not errors,errors
    browser.close()
    print('Skills-first browser passed: selected export, skill download, optional MCP and mobile layout.')
