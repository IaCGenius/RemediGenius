from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from uuid import uuid4


def main():
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge');page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:8765')
        page.get_by_role('button',name='Knowledge',exact=True).click()
        expect(page.locator('#guidance-statement')).to_be_visible()
        expect(page.locator('#concept-id')).not_to_be_visible()
        expect(page.locator('#document-topic')).not_to_be_visible()
        statement='Our sample backend servers stay private. '+uuid4().hex[:6]
        page.locator('#guidance-statement').fill(statement)
        page.get_by_role('button',name='Review this guidance',exact=True).click()
        expect(page.locator('#detail-summary')).to_contain_text(statement)
        expect(page.locator('#detail-summary')).to_contain_text('This local workspace')
        expect(page.locator('#detail-body')).not_to_be_visible()
        page.get_by_role('button',name='Use this guidance',exact=True).click()
        expect(page.locator('#message')).to_contain_text('Guidance saved')
        expect(page.locator('#guidance-library')).to_contain_text(statement)
        card=page.locator('#guidance-library article').filter(has_text=statement).first
        card.get_by_role('button',name='Edit',exact=True).click()
        page.locator('#guidance-statement').fill(statement+' Databases also stay private.')
        page.get_by_role('button',name='Review this guidance',exact=True).click()
        page.get_by_role('button',name='Use this guidance',exact=True).click()
        expect(page.locator('#guidance-library')).to_contain_text('Databases also stay private.')
        page.locator('#knowledge-files > summary').click()
        page.get_by_role('button',name='Prepare review folder',exact=True).click()
        expect(page.locator('#guidance-file-location')).to_contain_text('README.md')
        expect(page.locator('#guidance-file-location')).to_contain_text('discouraged')
        card.get_by_role('button',name='Review with my AI',exact=True).click()
        expect(page.locator('#guidance-ai-prompt')).to_be_visible()
        assert 'Do not invent approval' in page.locator('#guidance-ai-prompt').input_value()
        page.get_by_role('button',name='Close details').click()
        page.locator('#knowledge-ai > summary').click()
        page.locator('#guidance-ai-reply').fill('{"title":"AI suggestion","statement":"Check owner before changes.","scope":{"application":"sample"}}')
        page.get_by_role('button',name='Review AI suggestion',exact=True).click()
        expect(page.locator('#guidance-statement')).to_have_value('Check owner before changes.')
        expect(page.locator('#guidance-application')).to_have_value('sample')
        page.get_by_role('button',name='Review this guidance',exact=True).click()
        expect(page.locator('#detail-summary')).to_contain_text('AI-assisted draft')
        page.get_by_role('button',name='Close details').click()
        # No automatic approval of the AI-generated draft.
        expect(page.locator('#guidance-library')).to_contain_text('Waiting for your review')
        page.locator('#knowledge-ai > summary').click()
        page.locator('#knowledge-files > summary').click()
        Path('playwright-output').mkdir(exist_ok=True)
        page.screenshot(path='playwright-output/simple-knowledge.png',full_page=True)
        page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(200)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors,errors
        browser.close()
    print('Simple knowledge browser passed: plain note, review, use, edit, hidden advanced fields, Markdown files, AI review handoff and unapproved suggestion, mobile.')


if __name__=='__main__':main()
