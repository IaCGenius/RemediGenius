"""Optional real-browser smoke: run against a local console with synthetic data only."""
from pathlib import Path
import os
from playwright.sync_api import sync_playwright, expect


def main():
    out = Path("playwright-output")
    out.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=os.environ.get("RGCE_TEST_BROWSER", "msedge" if os.name == "nt" else "chromium"))
        page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:8765")
        page.get_by_role("button", name="Try the sample workspace").click()
        expect(page.locator("#message")).to_contain_text("Synthetic demo only")
        page.get_by_role("button", name="Investigate", exact=True).first.click()
        expect(page.locator("#detail-body")).to_contain_text("SGNET-002")
        page.get_by_role("button", name="Close details").click()
        page.get_by_role("button", name="Prepare proposal", exact=True).first.click()
        expect(page.locator("#detail-body")).to_contain_text('"ai_used": false')
        page.get_by_role("button", name="Close details").click()
        page.get_by_role("button", name="Compare evidence", exact=True).click()
        expect(page.locator("#detail-body")).to_contain_text("RULE_NO_LONGER_MATCHES")
        page.get_by_role("button", name="Close details").click()
        page.get_by_role("button", name="Knowledge", exact=True).click()
        page.locator("#knowledge-documents > summary").click()
        page.locator("#document-intake input[type=file]").set_input_files(str(Path(__file__).parent / "fixtures/knowledge/sample.docx"))
        expect(page.locator("#document-library")).to_contain_text("sample.docx", timeout=60000)
        page.locator("#document-paste").fill("SAMPLE: source context for a security review.")
        page.locator("#document-title").fill("Sample source note")
        page.get_by_role("button", name="Add pasted source", exact=True).click()
        expect(page.locator("#document-library")).to_contain_text("Sample source note.md")
        page.locator("#document-search").fill("source context")
        page.get_by_role("button", name="Search sources", exact=True).click()
        expect(page.locator("#document-library")).to_contain_text("Sample source note.md")
        expect(page.locator("#document-library")).not_to_contain_text("sample.docx")
        page.locator("#knowledge-assessment-notes > summary").click()
        page.locator("#note-source").select_option(index=1)
        page.screenshot(path=str(out / "knowledge.png"), full_page=True)
        page.locator("#reviewer").fill("Sample reviewer")
        page.locator("#knowledge-text").fill("SAMPLE: the platform team owns this resource. <script>throw new Error('must remain text')</script>")
        page.get_by_role("button", name="Save a draft", exact=True).click()
        expect(page.locator("#message")).to_contain_text("Draft saved")
        page.get_by_role("button", name="Review & approve exact version").first.click()
        page.get_by_role("button", name="Approve reviewed version").click()
        expect(page.locator("#message")).to_contain_text("Approved immutable")
        expect(page.locator("#approved")).to_contain_text("HUMAN APPROVED CONTEXT")
        page.get_by_role("button", name="Connections", exact=True).click()
        page.get_by_text("Optional: connect through MCP", exact=True).click()
        page.get_by_role("button", name="Hermes YAML", exact=True).click()
        expect(page.locator("#connection")).to_contain_text("mcp_servers:")
        page.screenshot(path=str(out / "integrations.png"), full_page=True)
        page.get_by_role("button", name="Workspace", exact=True).click()
        page.screenshot(path=str(out / "workspace.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(out / "mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Horizontal overflow"
        assert not errors, errors
        browser.close()
    print("Browser workflow passed: sample, evidence, proposal, reassessment, document upload, pasted source, search, cited approval, MCP config, mobile and source-text injection.")


if __name__ == "__main__":
    main()
