"""PDF rendering for the Executive Dashboard export (accounts.views.dashboard_export_pdf).

Uses fpdf2 with core fonts only (no bundled font files, nothing beyond pure Python) —
this app deploys to Vercel's serverless Python runtime, where a system-library-dependent
renderer like WeasyPrint isn't reliably available.
"""
from django.utils import timezone
from fpdf import FPDF
from fpdf.enums import XPos, YPos

NAVY = (13, 27, 62)
GOLD = (201, 162, 75)
INK = (26, 35, 50)
INK_SOFT = (90, 102, 120)
INK_FAINT = (138, 148, 166)
LINE = (225, 230, 238)
HEADER_BG = (241, 244, 249)
BLUE = (37, 99, 235)
GREEN = (34, 197, 94)
RED = (239, 68, 68)
WHITE = (255, 255, 255)

CONTENT_W = 180  # A4 width (210mm) minus 15mm margins on each side


# fpdf2's core (non-embedded) fonts hard-reject anything outside strict Latin-1 — even
# common "smart" punctuation like en/em dashes and curly quotes raise
# FPDFUnicodeEncodingException. Normalize those to plain ASCII first so text still reads
# correctly instead of just losing the character.
_PUNCT_MAP = {
    '–': '-', '—': '-', '‘': "'", '’': "'",
    '“': '"', '”': '"', '…': '...', '•': '*', ' ': ' ',
}


def _safe(value):
    """Normalize smart punctuation, then strip anything else a core PDF font can't
    render (emoji, etc.) rather than let stray characters from free-text data crash
    the export."""
    text = str(value if value is not None else '')
    for src, dest in _PUNCT_MAP.items():
        text = text.replace(src, dest)
    return text.encode('latin-1', 'ignore').decode('latin-1')


def _hex_to_rgb(hex_color):
    hex_color = (hex_color or '#6b7280').lstrip('#')
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


class DashboardPDF(FPDF):
    def __init__(self, range_label, agent_label):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.range_label = range_label
        self.agent_label = agent_label
        self.set_margins(15, 15, 15)
        self.set_auto_page_break(auto=True, margin=22)
        self.alias_nb_pages()

    def header(self):
        self.set_fill_color(*NAVY)
        self.rect(0, 0, self.w, 26, style='F')
        self.set_xy(15, 7)
        self.set_font('Helvetica', 'B', 18)
        self.set_text_color(*GOLD)
        self.cell(0, 8, 'PIE REAL ESTATE', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(15)
        self.set_font('Helvetica', '', 10)
        self.set_text_color(*WHITE)
        subtitle = f'Executive Dashboard Report  |  {_safe(self.range_label)}'
        if self.agent_label:
            subtitle += f'  |  Agent: {_safe(self.agent_label)}'
        self.cell(0, 6, subtitle, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_y(32)
        self.set_text_color(*INK)

    def footer(self):
        self.set_y(-16)
        self.set_draw_color(*LINE)
        self.set_line_width(0.2)
        self.line(15, self.get_y(), self.w - 15, self.get_y())
        self.set_y(-12)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(*INK_FAINT)
        self.cell(0, 6, 'PIE Real Estate  |  +92 311 1222141  |  info@pierealestate.com', new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_x(-45)
        self.cell(30, 6, f'Page {self.page_no()} of {{nb}}', align='R')

    def section_title(self, title, needed_height=40):
        if self.will_page_break(needed_height):
            self.add_page()
        else:
            self.ln(5)
        self.set_font('Helvetica', 'B', 12.5)
        self.set_text_color(*NAVY)
        self.cell(0, 7, _safe(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        y = self.get_y() + 0.5
        self.set_draw_color(*GOLD)
        self.set_line_width(0.7)
        self.line(15, y, 42, y)
        self.set_line_width(0.2)
        self.ln(5)
        self.set_text_color(*INK)

    def table_header(self, columns):
        """columns: list of (label, width, align)"""
        self.set_fill_color(*HEADER_BG)
        self.set_text_color(*INK)
        self.set_font('Helvetica', 'B', 9)
        self.set_draw_color(*HEADER_BG)
        for label, width, align in columns:
            self.cell(width, 8, _safe(label), border=0, align=align, fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.ln(8)
        self.set_font('Helvetica', '', 9.5)

    def table_row(self, cells):
        """cells: list of (text, width, align). Draws a solid-white row with a bottom rule."""
        y = self.get_y()
        for text, width, align in cells:
            self.cell(width, 8, _safe(text), border=0, align=align, new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_draw_color(*LINE)
        self.set_line_width(0.15)
        self.line(15, y + 8, 15 + CONTENT_W, y + 8)
        self.ln(8)

    def kpi_card(self, x, y, w, h, label, value, delta=None):
        self.set_draw_color(*LINE)
        self.set_fill_color(*WHITE)
        self.rect(x, y, w, h, style='DF', round_corners=True, corner_radius=2.2)
        self.set_xy(x + 3.5, y + 3.5)
        self.set_font('Helvetica', '', 7.6)
        self.set_text_color(*INK_SOFT)
        self.multi_cell(w - 7, 3.4, _safe(label.upper()), align='L', new_x=XPos.LEFT, new_y=YPos.NEXT)
        self.set_x(x + 3.5)
        self.set_font('Helvetica', 'B', 14.5)
        self.set_text_color(*NAVY)
        self.cell(w - 7, 8, _safe(value), align='L', new_x=XPos.LEFT, new_y=YPos.NEXT)
        if delta:
            self.set_x(x + 3.5)
            self.set_font('Helvetica', 'B', 7.6)
            color = GREEN if delta['dir'] == 'up' else RED if delta['dir'] == 'down' else INK_FAINT
            self.set_text_color(*color)
            text = delta['text']
            if text.endswith('%'):
                sign = '+' if delta['dir'] == 'up' else '-'
                text = f'{sign}{text} vs prior period'
            self.cell(w - 7, 4, _safe(text), align='L')
        self.set_text_color(*INK)

    def stat_card(self, x, y, w, h, label, value):
        self.set_draw_color(*LINE)
        self.set_fill_color(*HEADER_BG)
        self.rect(x, y, w, h, style='DF', round_corners=True, corner_radius=2.2)
        self.set_xy(x + 3.5, y + 4)
        self.set_font('Helvetica', 'B', 15)
        self.set_text_color(*NAVY)
        self.cell(w - 7, 7, _safe(value), align='L', new_x=XPos.LEFT, new_y=YPos.NEXT)
        self.set_x(x + 3.5)
        self.set_font('Helvetica', '', 7.6)
        self.set_text_color(*INK_SOFT)
        self.multi_cell(w - 7, 3.4, _safe(label), align='L')
        self.set_text_color(*INK)


def _kpi_section(pdf, kpis):
    pdf.section_title('Key Performance Indicators', needed_height=42)
    cards = [
        ('New Leads', str(kpis['new_leads']), kpis['new_leads_delta']),
        ('Revenue (Closed Deals)', kpis['revenue_display'], kpis['revenue_delta']),
        ('Active Deals', str(kpis['active_deals']), None),
        ('Upcoming Follow-ups (7d)', str(kpis['upcoming_follow_ups']), None),
        ('Deals Closed', str(kpis['deals_closed']), kpis['deals_closed_delta']),
    ]
    gap = 3
    w = (CONTENT_W - gap * (len(cards) - 1)) / len(cards)
    y = pdf.get_y()
    x = 15
    for label, value, delta in cards:
        pdf.kpi_card(x, y, w, 26, label, value, delta)
        x += w + gap
    pdf.set_y(y + 26)


def _funnel_section(pdf, funnel):
    pdf.section_title('Leads Conversion Funnel', needed_height=10 + len(funnel) * 9)
    label_w, count_w = 42, 24
    bar_w = CONTENT_W - label_w - count_w
    max_pct = max((row['pct'] for row in funnel), default=0) or 1
    for row in funnel:
        y = pdf.get_y()
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(*INK)
        pdf.set_xy(15, y)
        pdf.cell(label_w, 7, _safe(row['label']), new_x=XPos.RIGHT, new_y=YPos.TOP)
        fill_w = max(bar_w * row['pct'] / max_pct, 1.5) if row['pct'] else 1.5
        pdf.set_fill_color(*HEADER_BG)
        pdf.rect(15 + label_w, y + 1, bar_w, 5, style='F')
        pdf.set_fill_color(*BLUE)
        pdf.rect(15 + label_w, y + 1, fill_w, 5, style='F')
        pdf.set_xy(15 + label_w + bar_w, y)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.cell(count_w, 7, _safe(f"{row['count']} ({row['pct']}%)"), align='R')
        pdf.set_y(y + 9)


def _pipeline_section(pdf, pipeline):
    rows = [
        ('Negotiation', pipeline['negotiation']),
        ('Documentation', pipeline['documentation']),
        ('Payment Tracking', pipeline['payment_tracking']),
        ('Deal Closed', pipeline['deal_closed']),
    ]
    pdf.section_title('Pipeline Snapshot', needed_height=10 + len(rows) * 8)
    cols = [('Stage', 140, 'L'), ('Leads', 40, 'R')]
    pdf.table_header(cols)
    for label, count in rows:
        pdf.table_row([(label, 140, 'L'), (str(count), 40, 'R')])


def _lead_quality_section(pdf, lead_quality):
    pdf.section_title('Lead Quality - Active Pipeline', needed_height=10 + len(lead_quality) * 8)
    cols = [('Segment', 90, 'L'), ('Leads', 45, 'R'), ('Share', 45, 'R')]
    pdf.table_header(cols)
    for row in lead_quality:
        y = pdf.get_y()
        r, g, b = _hex_to_rgb(row['color'])
        pdf.set_fill_color(r, g, b)
        pdf.rect(15, y + 2.5, 3, 3, style='F')
        pdf.set_xy(21, y)
        pdf.set_font('Helvetica', '', 9.5)
        pdf.cell(84, 8, _safe(row['label']), new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(45, 8, str(row['count']), align='R', new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(45, 8, f"{row['pct']}%", align='R', new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.15)
        pdf.line(15, y + 8, 15 + CONTENT_W, y + 8)
        pdf.ln(8)


def _submissions_section(pdf, submissions):
    pdf.section_title('Property Submissions', needed_height=32)
    cards = [
        ('Pending Review', str(submissions['pending'])),
        ('Awaiting Evaluation Approval', str(submissions['awaiting_approval'])),
        ('Listed This Period', str(submissions['listed_in_period'])),
    ]
    gap = 4
    w = (CONTENT_W - gap * (len(cards) - 1)) / len(cards)
    y = pdf.get_y()
    x = 15
    for label, value in cards:
        pdf.stat_card(x, y, w, 20, label, value)
        x += w + gap
    pdf.set_y(y + 20)


def _revenue_by_city_section(pdf, donut_rows, total_display):
    if not donut_rows:
        return
    pdf.section_title('Revenue by City - Sold Properties', needed_height=10 + len(donut_rows) * 8 + 8)
    cols = [('City', 90, 'L'), ('Revenue', 55, 'R'), ('Share', 35, 'R')]
    pdf.table_header(cols)
    for row in donut_rows:
        y = pdf.get_y()
        r, g, b = _hex_to_rgb(row['color'])
        pdf.set_fill_color(r, g, b)
        pdf.rect(15, y + 2.5, 3, 3, style='F')
        pdf.set_xy(21, y)
        pdf.set_font('Helvetica', '', 9.5)
        pdf.cell(84, 8, _safe(row['label']), new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(55, 8, _safe(row['amount_display']), align='R', new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(35, 8, f"{row['pct']}%", align='R', new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.15)
        pdf.line(15, y + 8, 15 + CONTENT_W, y + 8)
        pdf.ln(8)
    pdf.set_font('Helvetica', 'B', 9.5)
    pdf.set_text_color(*NAVY)
    pdf.cell(145, 8, 'Total', new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(35, 8, _safe(total_display), align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*INK)


def _monthly_trend_section(pdf, chart, this_year):
    labels = chart['labels']
    this_year_data = chart['thisYear']
    last_year_data = chart['lastYear']
    if not labels:
        return
    pdf.section_title('Monthly Revenue Trend (PKR Millions)', needed_height=52)

    chart_h = 32
    x0, y0 = 15, pdf.get_y()
    max_val = max([*this_year_data, *last_year_data, 0.01])

    pdf.set_draw_color(*LINE)
    pdf.set_line_width(0.15)
    pdf.line(x0, y0, x0 + CONTENT_W, y0)
    pdf.line(x0, y0 + chart_h, x0 + CONTENT_W, y0 + chart_h)

    group_w = CONTENT_W / len(labels)
    bar_w = group_w * 0.32
    for i, label in enumerate(labels):
        gx = x0 + i * group_w + group_w / 2
        ty_h = chart_h * (this_year_data[i] / max_val) if max_val else 0
        ly_h = chart_h * (last_year_data[i] / max_val) if max_val else 0
        pdf.set_fill_color(*BLUE)
        pdf.rect(gx - bar_w - 0.5, y0 + chart_h - ty_h, bar_w, ty_h, style='F')
        pdf.set_fill_color(*GOLD)
        pdf.rect(gx + 0.5, y0 + chart_h - ly_h, bar_w, ly_h, style='F')
        pdf.set_font('Helvetica', '', 6.8)
        pdf.set_text_color(*INK_FAINT)
        pdf.set_xy(x0 + i * group_w, y0 + chart_h + 1.5)
        pdf.cell(group_w, 4, _safe(label), align='C')

    pdf.set_y(y0 + chart_h + 7)
    pdf.set_font('Helvetica', '', 8.5)
    pdf.set_fill_color(*BLUE)
    pdf.rect(15, pdf.get_y() + 1, 3, 3, style='F')
    pdf.set_xy(20, pdf.get_y())
    pdf.set_text_color(*INK_SOFT)
    pdf.cell(30, 5, _safe(str(this_year)), new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_fill_color(*GOLD)
    pdf.rect(55, pdf.get_y() + 1, 3, 3, style='F')
    pdf.set_xy(60, pdf.get_y())
    pdf.cell(30, 5, _safe(str(this_year - 1)))
    pdf.ln(9)
    pdf.set_text_color(*INK)


def _recent_activity_section(pdf, activities):
    if not activities:
        return
    pdf.section_title('Recent Activity', needed_height=10 + min(len(activities), 8) * 9)
    cols = [('When', 32, 'L'), ('Activity', 148, 'L')]
    pdf.table_header(cols)
    pdf.set_font('Helvetica', '', 8.8)
    for item in activities[:8]:
        when = timezone.localtime(item['when']).strftime('%b %d, %I:%M %p')
        y = pdf.get_y()
        text = _safe(item['text'])
        pdf.set_xy(15, y)
        pdf.cell(32, 7, _safe(when), new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_xy(47, y)
        line_h = pdf.multi_cell(148, 4.6, text, align='L', dry_run=True, output='LINES')
        row_h = max(7, len(line_h) * 4.6 + 2)
        pdf.multi_cell(148, 4.6, text, align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        bottom_y = max(pdf.get_y(), y + row_h)
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.15)
        pdf.line(15, bottom_y, 15 + CONTENT_W, bottom_y)
        pdf.set_y(bottom_y + 2)


def build_dashboard_pdf(data):
    """Render the dashboard's current data (same dict the on-screen view and the old CSV
    export used) into a branded, multi-section PDF report. Returns raw PDF bytes."""
    agent_label = data['filter_agent'].get_full_name() if data.get('filter_agent') else None
    pdf = DashboardPDF(range_label=data['range_label'], agent_label=agent_label)
    pdf.add_page()

    _kpi_section(pdf, data['kpis'])
    _funnel_section(pdf, data['funnel'])
    _pipeline_section(pdf, data['pipeline'])
    _lead_quality_section(pdf, data['lead_quality'])
    _submissions_section(pdf, data['submissions_snapshot'])
    _revenue_by_city_section(pdf, data['donut_rows'], data['total_sold_revenue_display'])
    _monthly_trend_section(pdf, data['chart_data']['revenue'], data['this_year'])
    _recent_activity_section(pdf, data['recent_activities'])

    return bytes(pdf.output())
