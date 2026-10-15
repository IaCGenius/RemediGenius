"""Run against the isolated synthetic preview at localhost:8766."""
import os
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


BASE=os.environ.get('RGCE_PREVIEW_URL','http://127.0.0.1:8766')

with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge')
    page=browser.new_page(viewport={'width':1440,'height':1050})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(BASE)
    page.get_by_role('button',name='Connect an existing source',exact=True).click()
    page.locator('#source-role').fill('arn:aws:iam::111122223333:role/RemediGeniusCommunityReadOnly')
    page.get_by_role('button',name='Review read plan',exact=True).click()
    expect(page.locator('#source-plan')).to_contain_text('AWS access has not been tested')
    expect(page.locator('#source-plan pre').first).to_contain_text('--output')
    expect(page.locator('#source-plan')).to_contain_text('on your workstation')
    expect(page.locator('#source-plan pre').first).not_to_contain_text('/usr/local/bin/python')
    page.locator('#source-kind').select_option('s3-object')
    page.locator('#source-location').fill('s3://example-bucket/log.json')
    page.get_by_role('button',name='Review read plan',exact=True).click()
    expect(page.locator('#source-plan pre').first).to_contain_text('s3://example-bucket/log.json')
    with page.expect_download() as download:
        page.get_by_role('button',name='Download CloudFormation',exact=True).click()
    assert download.value.suggested_filename=='selected-source-role.json'
    session=page.request.get(BASE+'/api/session').json()
    response=page.request.post(BASE+'/api/import',headers={'x-rgce-token':session['token']},data={
        'adapter':'cloudwatch-logs','scope':{'account':'111122223333','provider':'aws','location':'/synthetic/example'},
        'observed_at':datetime.now(timezone.utc).isoformat(),'facts':{'records':[{'message':'Synthetic event'}]},'coverage':'complete'})
    assert response.ok,response.text()
    assert response.json()['assessment'] is None
    page.get_by_role('button',name='Refresh collected evidence',exact=True).click()
    expect(page.locator('#recent-source-evidence')).to_contain_text('/synthetic/example')
    page.get_by_role('button',name='Review evidence',exact=True).first.click()
    expect(page.locator('#detail-summary')).to_contain_text('Synthetic event')
    expect(page.locator('#detail-intro')).to_contain_text('No deterministic security verdict')
    page.get_by_role('button',name='Close details',exact=True).click()
    page.get_by_role('button',name='Connections',exact=True).click()
    Path('playwright-output').mkdir(exist_ok=True)
    page.screenshot(path='playwright-output/onboarding.png',full_page=True)
    assert not errors,errors
    browser.close()
    print('Onboarding browser flow passed: plan, template download, context import and workspace review.')
