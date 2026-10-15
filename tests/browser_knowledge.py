"""End-to-end browser test against a local synthetic CE workspace."""
from pathlib import Path
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect


def main():
    suffix=uuid4().hex[:8]
    account='9'+str(int(suffix,16)).zfill(11)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge')
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto('http://127.0.0.1:8765')
        page.get_by_role('button',name='Try the sample workspace').click()
        expect(page.locator('#message')).to_contain_text('Synthetic')
        token=page.request.get('http://127.0.0.1:8765/api/session').json()['token']
        state=page.request.get('http://127.0.0.1:8765/api/state').json()
        assessment=next(a for a in state['assessments'] if a['body']['findings'] and a['body']['demo'])
        evidence=page.request.get('http://127.0.0.1:8765/api/records/'+assessment['body']['evidence_id']).json()['body']
        evidence['scope']['account']=account
        for group in evidence['facts']['security_groups']:group['owner_id']=account
        imported=page.request.post('http://127.0.0.1:8765/api/import',data=evidence,headers={'X-RGCE-Token':token})
        assert imported.ok
        page.reload()
        page.get_by_role('button',name='Knowledge',exact=True).click()
        page.locator('#knowledge-advanced').evaluate('(el) => el.open = true')
        def save(name, statement, application='', baseline=None):
            page.get_by_role('button',name='Start a new concept',exact=True).click()
            page.locator('#concept-id').fill(name)
            page.locator('#concept-title').fill(name)
            page.locator('#concept-requirement').fill('networking-'+suffix)
            page.locator('#concept-author').fill('Synthetic reviewer')
            page.locator('#concept-due').fill('2099-01-01T00:00:00Z')
            page.locator('#concept-account').fill(account)
            page.locator('#concept-application').fill(application)
            page.locator('#concept-statement').fill(statement)
            if baseline:page.locator('#concept-baseline').select_option(baseline)
            page.get_by_role('button',name='Save concept draft',exact=True).click()
            expect(page.locator('#message')).to_contain_text('Concept draft saved')
            card=page.locator('#concept-list article').filter(has=page.get_by_role('heading',name='Draft: '+name,exact=True))
            card.get_by_role('button',name='Review concept for publication').click()
            page.locator('#concept-approve-reviewer').fill('Synthetic reviewer')
            page.get_by_role('button',name='Publish reviewed concept',exact=True).click()
            expect(page.locator('#message')).to_contain_text('Published reusable')
        base_name='browser-baseline-'+suffix; variant_name='browser-portal-'+suffix
        save(base_name,'Private networking is the baseline.')
        data=page.request.get('http://127.0.0.1:8765/api/concepts').json()
        base=next(e['record']['id'] for e in data['concepts'] if e['record']['body']['concept_id']==base_name)
        save(variant_name,'Public HTTPS is permitted on portal ingress; backends remain private.','portal',base)
        page.get_by_role('button',name='Workspace',exact=True).click()
        page.get_by_role('button',name='Investigate',exact=True).first.click()
        expect(page.locator('#detail-summary')).to_contain_text('needs clarification')
        page.get_by_text('Confirm which application this belongs to',exact=True).click()
        page.locator('#detail-summary').get_by_label('application',exact=True).fill('portal')
        page.get_by_role('button',name='Save application context').click()
        expect(page.locator('#detail-summary')).to_contain_text('Public HTTPS is permitted')
        page.get_by_role('button',name='Close details').click()
        page.get_by_role('button',name='Prepare proposal',exact=True).first.click()
        expect(page.locator('#detail-summary')).to_contain_text('saved with this proposal')
        before=page.locator('#detail-body').text_content()
        Path('playwright-output').mkdir(exist_ok=True)
        page.screenshot(path='playwright-output/knowledge-applied.png',full_page=True)
        page.get_by_role('button',name='Close details').click()
        page.get_by_role('button',name='Knowledge',exact=True).click()
        page.locator('#knowledge-advanced').evaluate('(el) => el.open = true')
        card=page.locator('#concept-list article').filter(has=page.get_by_role('heading',name=base_name,exact=True))
        card.get_by_role('button',name='Revise this concept').click()
        page.locator('#concept-statement').fill('Updated baseline requires private networking and owner review.')
        page.get_by_role('button',name='Save concept draft',exact=True).click()
        expect(page.locator('#message')).to_contain_text('Concept draft saved')
        draft=page.locator('#concept-list article').filter(has=page.get_by_role('heading',name='Draft: '+base_name,exact=True))
        draft.get_by_role('button',name='Review concept for publication').click()
        page.locator('#concept-approve-reviewer').fill('Synthetic reviewer')
        page.get_by_role('button',name='Publish reviewed concept',exact=True).click()
        expect(page.locator('#message')).to_contain_text('Published reusable')
        variant=page.locator('#concept-list article').filter(has=page.get_by_role('heading',name=variant_name,exact=True))
        expect(variant).to_contain_text('Dependency requires review')
        # Saved receipt is a historical snapshot even after the baseline changed.
        import json
        receipt=json.loads(before)['knowledge_receipt_id']
        historical=page.request.get('http://127.0.0.1:8765/api/records/'+receipt).json()
        assert historical['body']['status']=='READY'
        page.screenshot(path='playwright-output/knowledge-refresh.png',full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_timeout(250)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), page.evaluate("({width:document.documentElement.scrollWidth,els:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>390 && e.getBoundingClientRect().width>0).map(e=>[e.tagName,e.id,e.className,e.getBoundingClientRect().width,e.textContent.slice(0,40)]).slice(0,20)})")
        assert not errors,errors
        browser.close()
    print('Knowledge browser passed: publish baseline/variation, missing context, mapping, applied guidance, receipt, revised baseline and dependent review.')


if __name__=='__main__':main()


