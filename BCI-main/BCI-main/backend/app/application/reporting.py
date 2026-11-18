"""中文辅助报告：报告快照中的事实、缺失字段和复核状态完整可见。"""
import io
from pathlib import Path
import threading
from xml.sax.saxutils import escape

from backend.app.domain.models import AppError

FONT_LOCK = threading.Lock()
BAND_NAMES = {'delta': 'δ / delta', 'theta': 'θ / theta', 'alpha': 'α / alpha', 'beta': 'β / beta', 'gamma': 'γ / gamma'}


def render_pdf(snapshot):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    except ImportError as exc:
        raise AppError('dependency_unavailable', '缺少 PDF 组件，请运行安装脚本安装 reportlab', 503) from exc
    with FONT_LOCK:
        if 'XinlanChinese' not in pdfmetrics.getRegisteredFontNames():
            font_path = Path('C:/Windows/Fonts/simsun.ttc')
            if not font_path.exists():
                raise AppError('font_unavailable', '没有找到可嵌入的中文字体 simsun.ttc，当前环境不能导出 PDF', 503)
            pdfmetrics.registerFont(TTFont('XinlanChinese', str(font_path), subfontIndex=0))
    stream = io.BytesIO()
    document = SimpleDocTemplate(stream, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=54, bottomMargin=52,
                                 title='心澜心理健康辅助评估报告', author='心澜本地工作台')
    body = ParagraphStyle('body', fontName='XinlanChinese', fontSize=10, leading=16, textColor=colors.HexColor('#172B3A'), wordWrap='CJK', spaceAfter=6)
    title = ParagraphStyle('title', parent=body, fontSize=22, leading=30, spaceAfter=12)
    heading = ParagraphStyle('heading', parent=body, fontSize=13, leading=21, textColor=colors.HexColor('#0F766E'), spaceBefore=12, spaceAfter=7)
    muted = ParagraphStyle('muted', parent=body, fontSize=9, leading=14, textColor=colors.HexColor('#526674'))
    def paragraph(value, style=body):
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), style)
    story = [paragraph('心澜 · 辅助评估报告', title), paragraph('脑电支持的心理健康辅助筛查与状态评估', muted)]
    if snapshot['watermark']:
        story.append(paragraph(snapshot['watermark'], heading))
    state = '已完成人工复核' if snapshot['status'] == 'reviewed' else '草稿 · 尚未完成人工复核'
    story += [paragraph(state, heading), paragraph(snapshot['boundary'])]
    dataset, result = snapshot['dataset'], snapshot['assessment']
    meta = dataset['metadata']
    story += [paragraph('一、输入与来源', heading)]
    rows = [
        ('数据编码', meta['display_code']), ('数据集 / 版本', f"{dataset['id']} / v{dataset['version']}"),
        ('会话', dataset['session_id']), ('数据来源', '模拟演示' if dataset['data_mode'] == 'demo' else '真实模式'),
        ('格式 / 维度', f"{dataset['source_format']} / {dataset['shape']}"), ('轴定义', ', '.join(meta['axes'])),
        ('采样率 / 单位', f"{meta['sampling_rate'] if meta['sampling_rate'] is not None else '未提供'} Hz / {meta['unit']}"),
        ('通道 / 频带', ', '.join(meta['channels']) + ' / ' + ', '.join(meta['bands'])),
        ('输入 SHA256', result['input_hash']), ('来源说明', meta['source_description'] or '未填写'),
    ]
    table = Table([[paragraph(label), paragraph(value)] for label, value in rows], colWidths=[92, 419], hAlign='LEFT')
    table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F5F8F8')),
                               ('LINEBELOW', (0, 0), (-1, -1), 0.4, colors.HexColor('#DCE5E7')), ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    story += [table, paragraph('二、情绪输出与证据', heading)]
    for output in result['emotions']:
        confidence = '未提供' if output['confidence'] is None else f"{output['confidence']:.2%}"
        story.append(paragraph(f"时间窗 / 样本 {output['sample_id']}：{output['label']}；分类置信度 {confidence}"))
    reliability = '可靠性信息缺失，需要复核' if result['reliability'] is None else str(result['reliability'])
    story += [paragraph('可靠性：' + reliability), paragraph('复核要求：' + result['review_reason']), paragraph('质量说明：' + result['quality']['note'])]
    for evidence in result['band_evidence']:
        values = f"贡献：{evidence['contribution'] if evidence['contribution'] is not None else '缺失'}；后验：{evidence['posterior'] if evidence['posterior'] is not None else '缺失'}；一致性：{evidence['consistency'] if evidence['consistency'] is not None else '缺失'}"
        story.append(KeepTogether([paragraph(BAND_NAMES[evidence['band']] + ' — ' + values), paragraph(evidence['missing_reason'] or '提供方已提供', muted)]))
    story.append(paragraph('三、人工复核历史', heading))
    if not snapshot['reviews']:
        story.append(paragraph('尚无人工复核记录。本报告为草稿。'))
    for review in snapshot['reviews']:
        story += [paragraph(f"修订 {review['revision']} · {review['reviewer']} · {review['created_at']}"),
                  paragraph('复核状态：' + ('已复核' if review['status'] == 'reviewed' else '需要跟进')), paragraph(review['opinion'])]
    story += [paragraph('四、可追溯信息与限制', heading)]
    for label, key in [('结果 ID', 'id'), ('任务 ID', 'job_id'), ('配置版本', 'config_version'), ('提供方版本', 'provider_version'), ('适配器版本', 'adapter_version'), ('生成时间', 'generated_at')]:
        story.append(paragraph(label + '：' + result[key], muted))
    story += [paragraph('报告生成时间：' + snapshot['generated_at'], muted), paragraph('报告 ID：' + snapshot['report_id'], muted),
              paragraph('人工复核记录不会改变模型原始可靠性。缺失字段未补零，置信度不代表可靠性或患病概率。没有当前电极坐标时不提供定位脑地形。', muted)]
    def page_decoration(canvas, doc):
        canvas.saveState()
        canvas.setFont('XinlanChinese', 9)
        canvas.setFillColor(colors.HexColor('#526674'))
        canvas.drawString(42, 817, '心澜 | 本地辅助评估')
        canvas.drawRightString(553, 30, f'第 {doc.page} 页 · {state}')
        if snapshot['data_mode'] == 'demo':
            canvas.setFillColor(colors.HexColor('#B45309'))
            canvas.drawString(42, 30, '模拟演示，非实际筛查结果')
        canvas.restoreState()
    document.build(story, onFirstPage=page_decoration, onLaterPages=page_decoration)
    return stream.getvalue()
