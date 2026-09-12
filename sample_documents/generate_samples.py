"""Generator script for 4 realistic demo documents:
1. sample_documents/financial_report.pdf
2. sample_documents/hr_report.docx
3. sample_documents/sales_operations_report.pdf
4. sample_documents/academic_report.docx
"""
import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import docx
from docx.shared import Pt, Inches, RGBColor

os.makedirs("sample_documents", exist_ok=True)

# -------------------------------------------------------------
# 1. Financial Report (PDF)
# -------------------------------------------------------------
def generate_financial_pdf():
    pdf_path = "sample_documents/financial_report.pdf"
    doc = SimpleDocTemplate(pdf_path, pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1E293B'),
        spaceAfter=12
    )
    h2_style = ParagraphStyle(
        'DocH2',
        parent=styles['Heading2'],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#0F766E'),
        spaceBefore=14,
        spaceAfter=8
    )
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#334155'),
        spaceAfter=10
    )
    
    story = []
    story.append(Paragraph("Q3 FY24 Corporate Financial Performance Report", title_style))
    story.append(Paragraph("Reporting Period: Quarter Ended December 31, 2023 | Entity: Apex Global Enterprises", body_style))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("Executive Financial Summary", h2_style))
    story.append(Paragraph(
        "Revenue increased by 14% year-over-year to INR 842 crore, primarily driven by a 21% increase in domestic sales. "
        "EBITDA margin improved from 18.2% to 20.1%. Net profit after tax reached INR 128 crore, reflecting an operating growth of 16.5%. "
        "The company maintained robust cash conversion with working capital days reduced from 54 to 48 days.",
        body_style
    ))
    story.append(Spacer(1, 8))
    
    story.append(Paragraph("Business Segment Revenue & Operating Margin Breakdown", h2_style))
    table_data = [
        ["Business Segment", "Q3 FY23 Revenue (INR Cr)", "Q3 FY24 Revenue (INR Cr)", "YoY Growth (%)", "EBITDA Margin (%)"],
        ["Domestic Consumer", "450", "545", "+21.1%", "22.4%"],
        ["Enterprise Solutions", "180", "195", "+8.3%", "18.1%"],
        ["International Exports", "108", "102", "-5.6%", "15.2%"]
    ]
    t = Table(table_data, colWidths=[130, 100, 100, 85, 85])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))
    
    story.append(Paragraph("Capital Expenditure & Liquidity Outlook", h2_style))
    story.append(Paragraph(
        "Capital expenditure for the quarter stood at INR 64 crore, focusing on supply chain automation and warehouse expansion. "
        "Gross debt decreased by 12% to INR 210 crore, strengthening the debt-to-equity ratio to 0.35.",
        body_style
    ))
    
    doc.build(story)
    print(f"Generated {pdf_path}")

# -------------------------------------------------------------
# 2. HR Report (DOCX)
# -------------------------------------------------------------
def generate_hr_docx():
    docx_path = "sample_documents/hr_report.docx"
    doc = docx.Document()
    
    title = doc.add_heading("Annual Talent & Workforce Review 2024", level=0)
    title.runs[0].font.color.rgb = RGBColor(30, 41, 59)
    
    meta_p = doc.add_paragraph("Organization: Meridian Health Technologies | Scope: Global Operations")
    meta_p.runs[0].font.size = Pt(9)
    meta_p.runs[0].font.color.rgb = RGBColor(100, 116, 139)
    
    doc.add_heading("Workforce Highlights & Retention Trends", level=1)
    doc.add_paragraph(
        "Employee headcount increased from 1,196 to 1,284. Attrition declined from 13.4% to 11.2%. "
        "Engineering accounted for 42% of the workforce, followed by Sales at 26%, Operations at 20%, and Corporate Support at 12%. "
        "The average time-to-hire dropped from 44 days to 32 days across all technical roles."
    )
    
    doc.add_heading("Department Distribution & Retention Metrics", level=2)
    table = doc.add_table(rows=1, cols=5)
    table.style = 'Light Shading Accent 1'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "Department"
    hdr_cells[1].text = "2023 Headcount"
    hdr_cells[2].text = "2024 Headcount"
    hdr_cells[3].text = "Workforce Share (%)"
    hdr_cells[4].text = "Retention Rate (%)"
    
    rows_data = [
        ["Engineering", "502", "540", "42.0%", "91.2%"],
        ["Sales & Marketing", "311", "334", "26.0%", "88.0%"],
        ["Operations", "239", "256", "20.0%", "87.5%"],
        ["Corporate Support", "144", "154", "12.0%", "93.0%"]
    ]
    for r in rows_data:
        row_cells = table.add_row().cells
        for i, val in enumerate(r):
            row_cells[i].text = val
            
    doc.add_heading("Diversity & Inclusion Benchmarks", level=1)
    doc.add_paragraph(
        "Female representation in senior leadership positions expanded from 24.5% to 29.0%. "
        "The overall employee net promoter score (eNPS) improved significantly from +38 to +52."
    )
    
    doc.save(docx_path)
    print(f"Generated {docx_path}")

# -------------------------------------------------------------
# 3. Sales & Operations Report (PDF)
# -------------------------------------------------------------
def generate_sales_pdf():
    pdf_path = "sample_documents/sales_operations_report.pdf"
    doc = SimpleDocTemplate(pdf_path, pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0F172A'),
        spaceAfter=12
    )
    h2_style = ParagraphStyle(
        'DocH2',
        parent=styles['Heading2'],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#2563EB'),
        spaceBefore=14,
        spaceAfter=8
    )
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#334155'),
        spaceAfter=10
    )
    
    story = []
    story.append(Paragraph("Regional Logistics & Operations Performance Report", title_style))
    story.append(Paragraph("Period: Q3 FY24 | Business Unit: SwiftExpress Freight & Distribution", body_style))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("Operational Volume & Service Levels", h2_style))
    story.append(Paragraph(
        "Total logistics volume reached 164,600 deliveries in Q3, up 9.5% QoQ. "
        "Average SLA compliance reached 94.9% across all fulfillment zones. "
        "The return rate dropped from 3.6% to 2.8%, driven by improved address verification and barcoding accuracy.",
        body_style
    ))
    story.append(Spacer(1, 8))
    
    story.append(Paragraph("Zone Logistics Matrix: Volumes, SLAs and Returns", h2_style))
    table_data = [
        ["Logistics Zone", "Deliveries Completed", "SLA Compliance (%)", "Return Rate (%)", "Avg Transit Days"],
        ["North", "45,200", "96.2%", "2.1%", "2.4"],
        ["South", "38,100", "94.8%", "3.4%", "2.9"],
        ["West", "51,900", "97.1%", "1.8%", "2.1"],
        ["East", "29,400", "91.5%", "4.2%", "3.5"]
    ]
    t = Table(table_data, colWidths=[110, 110, 100, 90, 90])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EFF6FF')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#BFDBFE')),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))
    
    story.append(Paragraph("Fleet Efficiency & Route Optimization", h2_style))
    story.append(Paragraph(
        "Electric vehicle fleet adoption reached 22% of last-mile routes, cutting fuel expenses by INR 4.2 crore. "
        "First-attempt delivery success rate increased from 89.1% to 92.4%.",
        body_style
    ))
    
    doc.build(story)
    print(f"Generated {pdf_path}")

# -------------------------------------------------------------
# 4. Academic Accreditation Report (DOCX)
# -------------------------------------------------------------
def generate_academic_docx():
    docx_path = "sample_documents/academic_report.docx"
    doc = docx.Document()
    
    title = doc.add_heading("Institutional Accreditation & Academic Performance Review", level=0)
    title.runs[0].font.color.rgb = RGBColor(15, 23, 42)
    
    meta_p = doc.add_paragraph("Institution: National Institute of Engineering & Technology | Academic Year: 2023-2024")
    meta_p.runs[0].font.size = Pt(9)
    meta_p.runs[0].font.color.rgb = RGBColor(100, 116, 139)
    
    doc.add_heading("Enrollment, Placements & Research Grants", level=1)
    doc.add_paragraph(
        "Total undergraduate enrollment expanded to 3,420 students across 6 engineering departments. "
        "Overall placement rate reached 88.4% compared to 82.1% in the prior academic year. "
        "Total sponsored research funding secured reached INR 18.5 crore, up 26% year-over-year. "
        "The overall faculty-to-student ratio improved from 1:18 to 1:15."
    )
    
    doc.add_heading("Department Placement & Average Package Matrix", level=2)
    table = doc.add_table(rows=1, cols=4)
    table.style = 'Light Shading Accent 2'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "Academic Department"
    hdr_cells[1].text = "Enrolled Final Year"
    hdr_cells[2].text = "Placement Rate (%)"
    hdr_cells[3].text = "Average CTC (INR LPA)"
    
    rows_data = [
        ["Computer Science", "120", "96.0%", "18.2"],
        ["Electronics & Comm.", "110", "91.0%", "14.5"],
        ["Mechanical Engg.", "115", "82.0%", "9.8"],
        ["Civil Engineering", "85", "74.0%", "8.2"]
    ]
    for r in rows_data:
        row_cells = table.add_row().cells
        for i, val in enumerate(r):
            row_cells[i].text = val
            
    doc.add_heading("Accreditation Grades & Research Publications", level=1)
    doc.add_paragraph(
        "Scopus indexed faculty research publications increased from 142 to 215 papers. "
        "Student retention from 1st to 2nd year was maintained at 94.2%."
    )
    
    doc.save(docx_path)
    print(f"Generated {docx_path}")

if __name__ == "__main__":
    generate_financial_pdf()
    generate_hr_docx()
    generate_sales_pdf()
    generate_academic_docx()
    print("All 4 sample documents generated successfully!")
