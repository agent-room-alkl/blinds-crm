"""Test-only helpers for exercising the pricing knowledge publish workflow."""
import base64
from unittest.mock import patch


def publish_fixture_knowledge(staff, workbook_bytes, filename="fixture.xlsx", confirm_deluxe_fixture=False):
    """Upload a synthetic workbook, review its parsed rules, and publish them.

    Analysis is stubbed because these tests cover workbook parsing and publishing,
    not the external AI provider. The production template-import endpoint stays
    retired and is never used to seed these fixtures.
    """
    uploaded = staff.post('/api/operations/pricing-knowledge/sources', json={
        'filename': filename,
        'content_base64': base64.b64encode(workbook_bytes).decode('ascii'),
    })
    assert uploaded.status_code == 200, uploaded.text
    source_id = uploaded.json()['id']

    with patch('pricing_knowledge.analyze_source', return_value={
        'summary': 'Synthetic fixture analysis; no external service used.',
        'facts': [],
    }):
        analyzed = staff.post(f'/api/operations/pricing-knowledge/sources/{source_id}/analyze')
    assert analyzed.status_code == 200, analyzed.text
    draft = analyzed.json()
    if confirm_deluxe_fixture:
        # A synthetic fixture may explicitly approve its invented placeholder
        # solely to retain price-engine calculation coverage in these tests.
        deluxe = next(rule for rule in draft['manifest']['products']
                      if rule.get('source_code') == 'VERA_Ashwood_provisional')
        deluxe.update(rate_per_m2='1.00', status='configured', provisional=False, warnings=[])

    reviewed = staff.put(
        f"/api/operations/pricing-knowledge/drafts/{draft['id']}",
        json={'manifest': draft['manifest'], 'facts': draft['facts']},
    )
    assert reviewed.status_code == 200, reviewed.text
    published = staff.post(f"/api/operations/pricing-knowledge/drafts/{draft['id']}/publish")
    assert published.status_code == 200, published.text
    result = published.json()
    assert result['active'] is True
    return result
