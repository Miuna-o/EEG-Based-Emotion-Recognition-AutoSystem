"""原生 PDF 预览沿用同一不可变工件和过期规则，普通下载仍为附件。"""
from test_workspace_api import client, assessment


def test_pdf_preview_is_inline_and_download_stays_attachment(client):
    _, result = assessment(client)
    report = client.post(f"/api/v1/assessments/{result['id']}/reports",
                         json={'format': 'pdf', 'expected_revision': 0}).json()
    url = f"/api/v1/reports/{report['id']}/download"
    download = client.get(url)
    preview = client.get(url + '?preview=true')
    assert download.headers['content-disposition'].startswith('attachment;')
    assert preview.headers['content-disposition'].startswith('inline;')
    assert preview.headers['content-type'] == 'application/pdf'
    assert preview.content == download.content
    assert preview.content.startswith(b'%PDF-')


def test_pdf_preview_cannot_bypass_stale_version(client):
    dataset, result = assessment(client)
    report = client.post(f"/api/v1/assessments/{result['id']}/reports",
                         json={'format': 'pdf', 'expected_revision': 0}).json()
    client.patch(f"/api/v1/datasets/{dataset['id']}/metadata",
                 json={'expected_version': dataset['version'], 'metadata': {'display_code': 'UPDATED-DEMO'}})
    response = client.get(f"/api/v1/reports/{report['id']}/download?preview=true")
    assert response.status_code == 409
    assert response.json()['code'] == 'version_conflict'
