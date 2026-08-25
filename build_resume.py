from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.style import WD_STYLE_TYPE
from pathlib import Path

OUT = Path('E:/时序/任晓旭_AI方向简历_含时序项目.docx')

NAVY = '123B5D'
BLUE = '1E6A8A'
INK = '1F2933'
MUTED = '52606D'
LIGHT = 'EAF2F5'
RULE = 'C8D8DE'

def set_cell_shading(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn('w:shd'))
    if shd is None:
        shd = OxmlElement('w:shd')
        tcPr.append(shd)
    shd.set(qn('w:fill'), fill)

def set_cell_margins(cell, top=80, start=120, bottom=80, end=120):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcMar = tcPr.first_child_found_in('w:tcMar')
    if tcMar is None:
        tcMar = OxmlElement('w:tcMar')
        tcPr.append(tcMar)
    for m, v in [('top', top), ('start', start), ('bottom', bottom), ('end', end)]:
        node = tcMar.find(qn('w:' + m))
        if node is None:
            node = OxmlElement('w:' + m)
            tcMar.append(node)
        node.set(qn('w:w'), str(v))
        node.set(qn('w:type'), 'dxa')

def set_cell_border(cell, **kwargs):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = tcPr.first_child_found_in('w:tcBorders')
    if tcBorders is None:
        tcBorders = OxmlElement('w:tcBorders')
        tcPr.append(tcBorders)
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        if edge in kwargs:
            tag = 'w:{}'.format(edge)
            element = tcBorders.find(qn(tag))
            if element is None:
                element = OxmlElement(tag)
                tcBorders.append(element)
            for key in ['val', 'sz', 'space', 'color']:
                if key in kwargs[edge]:
                    element.set(qn('w:{}'.format(key)), str(kwargs[edge][key]))

def set_run_font(run, name='Aptos', size=10.5, color=INK, bold=False, italic=False):
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn('w:ascii'), name)
    run._element.get_or_add_rPr().rFonts.set(qn('w:hAnsi'), name)
    run._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    run.bold = bold
    run.italic = italic

def style_para(p, before=0, after=4, line=1.08, keep=False):
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line
    if keep:
        pf.keep_with_next = True

def add_text(doc, text='', size=10.5, color=INK, bold=False, italic=False, align=None, before=0, after=4, line=1.08):
    p = doc.add_paragraph()
    style_para(p, before, after, line)
    if align is not None:
        p.alignment = align
    if text:
        r = p.add_run(text)
        set_run_font(r, size=size, color=color, bold=bold, italic=italic)
    return p

def add_section(doc, title):
    p = doc.add_paragraph()
    style_para(p, before=8, after=3, line=1.0, keep=True)
    r = p.add_run(title.upper())
    set_run_font(r, size=11, color=NAVY, bold=True)
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single'); bottom.set(qn('w:sz'), '8'); bottom.set(qn('w:space'), '2'); bottom.set(qn('w:color'), RULE)
    pBdr.append(bottom); pPr.append(pBdr)
    return p

def add_bullet(doc, text, after=2):
    p = doc.add_paragraph(style='List Bullet')
    style_para(p, after=after, line=1.08)
    p.paragraph_format.left_indent = Inches(0.24)
    p.paragraph_format.first_line_indent = Inches(-0.14)
    r = p.add_run(text)
    set_run_font(r, size=10, color=INK)
    return p

def add_project(doc, name, meta, bullets):
    p = doc.add_paragraph()
    style_para(p, before=4, after=1, line=1.0, keep=True)
    r = p.add_run(name)
    set_run_font(r, size=10.8, color=NAVY, bold=True)
    r = p.add_run('  |  ' + meta)
    set_run_font(r, size=9.3, color=MUTED)
    for b in bullets:
        add_bullet(doc, b)

doc = Document()
sec = doc.sections[0]
sec.page_width = Inches(8.27); sec.page_height = Inches(11.69)
sec.top_margin = Inches(0.45); sec.bottom_margin = Inches(0.42); sec.left_margin = Inches(0.58); sec.right_margin = Inches(0.58)
sec.header_distance = Inches(0.2); sec.footer_distance = Inches(0.2)

styles = doc.styles
normal = styles['Normal']
normal.font.name = 'Aptos'; normal._element.rPr.rFonts.set(qn('w:ascii'), 'Aptos'); normal._element.rPr.rFonts.set(qn('w:hAnsi'), 'Aptos'); normal._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei'); normal.font.size = Pt(10.5); normal.font.color.rgb = RGBColor.from_string(INK)
for sty_name in ['List Bullet']:
    s = styles[sty_name]; s.font.name='Aptos'; s._element.rPr.rFonts.set(qn('w:ascii'),'Aptos'); s._element.rPr.rFonts.set(qn('w:hAnsi'),'Aptos'); s._element.rPr.rFonts.set(qn('w:eastAsia'),'Microsoft YaHei'); s.font.size=Pt(10); s.font.color.rgb=RGBColor.from_string(INK)

# Header
header = sec.header
hp = header.paragraphs[0]
style_para(hp, after=0, line=1.0)
hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
hr = hp.add_run('AI APPLICATION / SOLUTIONS ENGINEER')
set_run_font(hr, size=8.5, color=BLUE, bold=True)

# Name and contact
p = doc.add_paragraph(); style_para(p, after=0, line=1.0)
r = p.add_run('任晓旭'); set_run_font(r, size=22, color=NAVY, bold=True)
r = p.add_run('   AI 应用开发 / AI 解决方案工程师'); set_run_font(r, size=12.5, color=BLUE, bold=True)
p = doc.add_paragraph(); style_para(p, after=7, line=1.0)
r = p.add_run('男  |  河北张家口  |  177-3323-5360  |  17733235360@163.com  |  Base：北京'); set_run_font(r, size=9.5, color=MUTED)

add_section(doc, '职业概述')
p = add_text(doc, after=4, line=1.15)
r = p.add_run('具备 Java 后端与 Python AI 应用开发经验，能够独立完成从需求分析、数据建模、API 开发到前后端联调和上线交付。已从零交付足球数据 AI Agent：接入 DeepSeek，构建 16 个智能工具、SSE 流式输出、语义缓存和防幻觉机制，并针对工具调用缺陷自建路由系统。目标岗位：AI 应用开发、AI 解决方案工程师、AI 技术售前。')
set_run_font(r, size=10.2, color=INK)

add_section(doc, '核心能力')
skills = [
    ('AI 应用工程', 'Python / FastAPI、LangChain、DeepSeek、Agent 架构、RAG、Tool Calling、Prompt Engineering、SSE'),
    ('检索与可靠性', 'ChromaDB 语义检索、内存 LRU + 向量缓存、防幻觉决策树 / 预取 / 自检、多数据源编排'),
    ('后端与数据', 'Java、Spring Boot、Spring Cloud、MyBatis-Plus、MySQL、Redis、分布式锁、布隆过滤器'),
    ('交付与协作', '需求拆解、数据库设计、API 设计、前后端联调、问题定位、用户反馈迭代、Git / Linux / Nginx 基础'),
]
for label, value in skills:
    p = doc.add_paragraph(); style_para(p, after=2, line=1.05)
    r = p.add_run(label + '：'); set_run_font(r, size=10, color=NAVY, bold=True)
    r = p.add_run(value); set_run_font(r, size=10, color=INK)

add_section(doc, '项目经验')
add_project(doc, '足球 AI 助手 | 全栈 AI Agent 产品（个人项目）', '2026.06 - 至今', [
    '从零设计并开发可复用的 AI Agent 方案框架，支持中英文自然语言交互，覆盖实时比分、积分榜、球员数据、比赛预测、球队模拟等 16 个智能工具。',
    '接入 DeepSeek 与 SSE 流式输出；数据库覆盖 197 名球员、48 支世界杯国家队、17 家欧洲俱乐部，端到端响应时间控制在 5 秒以内。',
    '针对大模型工具调用不稳定问题，自建智能工具路由系统，将查询耗时从 5-7 秒降至约 0.2 秒，查询速度提升约 80%。',
    '设计三层防幻觉机制（决策树、工具路由预取、自检清单）与两级语义缓存（内存 LRU、ChromaDB），重复查询命中率 30%+，降低模型 API 调用成本。',
    '采用模块化架构，可将足球数据源替换为客服知识库、销售数据或产品手册，具备迁移至企业 AI 场景的可复用性。',
])
add_project(doc, '时序（Shixu）| 多模块陪伴型 AI Agent（个人项目）', '2026.08 - 至今', [
    '从零搭建 FastAPI + Vue3 + SQLite 全栈陪伴型 Agent，采用 WebSocket 实现流式对话，支持会话历史落库、断线重连、连接状态管理与健康检查。',
    '设计长期记忆闭环：用户画像、行为特征、关系锚点、待跟进事项与主动提醒分层存储，并提供 REST API 管理记忆、会话和陪伴设置。',
    '实现规则优先 + 大模型兜底的场景路由，支持日常陪伴、情感指导、吐槽陪伴、工作顾问等多种人格面具；结合情绪识别、回复模式、语气约束和行动安全规则，提升回复稳定性。',
    '接入受控联网研究与 Markdown 文档工具：对公开来源进行筛选、引用和失败降级，文件创建采用目标白名单、原子写入、重复命名与 SHA-256 校验，避免模型直接操作任意本地路径。',
    '扩展实时语音基础协议与本地 Faster-Whisper ASR，统一 turn_id、序列号、取消和错误事件；沉淀可继续扩展 TTS、向量检索和多端形态的 Agent 工程骨架。',
])
add_project(doc, '球队模拟与分析系统 | AI 多数据源编排', '2026.07', [
    '用户选择两支球队后，系统在约 4 秒内并行完成 MySQL 阵容查询、联网历史交锋、赔率预测与数据对比，并由 AI 自动生成结构化比赛叙事。',
    '沉淀“多数据源整合 + AI 生成”的方案模式，可映射至企业报表自动生成、竞品分析等场景。',
])

add_section(doc, '工作经历')
add_project(doc, '北京三端互娱科技有限公司 | 游戏策划（全栈开发）', '2025.11 - 至今', [
    '主导 MMORPG 传奇游戏版本策划与开发，负责玩法设计、数值平衡、消费点优化及盒子上线全流程推进。',
    '通过优化地图对象管理与技能模板表，定位并解决百人同屏卡顿问题；持续根据用户反馈完成 BUG 修复和版本迭代。',
])
add_project(doc, '北京仙灏网络有限公司 | 游戏开发工程师', '2025.04 - 2025.10', [
    '参与 MMORPG 游戏服务端开发与版本迭代，承担功能实现、问题排查和联调支持。',
])
add_project(doc, '北京星龙数智科技有限公司 | Java 开发工程师（实习+转正）', '2024.08 - 2025.03', [
    '使用 Spring Boot、Spring Cloud、MyBatis-Plus、MySQL、Redis 开发数据可视化管理大屏，独立负责人员管理、客户管理、资源录入等模块。',
    '通过自定义注解与 Redis 缓存策略使数据库压力降低 30%+；使用分布式锁与布隆过滤器解决缓存穿透问题。',
])

add_section(doc, '补充信息')
p = add_text(doc, after=2, line=1.08)
r = p.add_run('AI 工具实践：'); set_run_font(r, size=10, color=NAVY, bold=True)
r = p.add_run('重度使用 Codex、Claude Code、Hermes 等 Agent 工具辅助需求拆解、代码实现、测试验证与问题定位。'); set_run_font(r, size=10, color=INK)
p = add_text(doc, after=0, line=1.08)
r = p.add_run('求职方向：'); set_run_font(r, size=10, color=NAVY, bold=True)
r = p.add_run('AI 应用开发 / AI 解决方案工程师 / AI 技术售前（北京）。'); set_run_font(r, size=10, color=INK)

# Footer page number field
fp = sec.footer.paragraphs[0]; fp.alignment = WD_ALIGN_PARAGRAPH.CENTER; style_para(fp, after=0, line=1.0)
r = fp.add_run('任晓旭  |  '); set_run_font(r, size=8, color=MUTED)
fld = OxmlElement('w:fldSimple'); fld.set(qn('w:instr'), 'PAGE'); fp._p.append(fld)

doc.core_properties.title = '任晓旭 - AI方向简历'
doc.core_properties.subject = 'AI应用开发 / AI解决方案工程师'
doc.core_properties.author = '任晓旭'
doc.save(OUT)
print(OUT)
