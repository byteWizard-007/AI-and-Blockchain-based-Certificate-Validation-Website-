import qrcode
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime

def generate_pdf_table(title, headers, rows, file_path):
    doc = SimpleDocTemplate(file_path, pagesize=letter)
    elements = []
    
    styles = getSampleStyleSheet()
    elements.append(Paragraph(title, styles['Title']))
    elements.append(Spacer(1, 20))
    
    str_rows = [[str(cell)[:40] for cell in row] for row in rows]
    data = [headers] + str_rows
    
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#fefefe')),
        ('TEXTCOLOR', (0,1), (-1,-1), colors.black),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey)
    ]))
    
    elements.append(t)
    doc.build(elements)

def generate_qr_code(data_url, file_path):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data_url)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    img.save(file_path)

def generate_pdf_report(cert_data, file_path):
    c = canvas.Canvas(file_path, pagesize=letter)
    width, height = letter
    
    # Background Box Header
    c.setFillColorRGB(0.1, 0.1, 0.3)
    c.rect(0, height - 80, width, 80, fill=1)
    
    # Title
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(50, height - 50, "Certificate Validation Report")
    
    # Content body
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 120, "Student Details")
    c.line(50, height - 125, width - 50, height - 125)
    
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 150, f"Student Name: {cert_data['student_name']}")
    c.drawString(50, height - 170, f"Register Number: {cert_data['register_number']}")
    c.drawString(50, height - 190, f"Course: {cert_data['course']}")
    c.drawString(50, height - 210, f"Year of Passing: {cert_data['year']}")
    
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 260, "Security & Authenticity")
    c.line(50, height - 265, width - 50, height - 265)
    
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 290, f"Blockchain Hash:")
    c.setFont("Courier", 10)
    c.drawString(50, height - 305, f"{cert_data['blockchain_hash']}")
    
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 335, f"Document SHA-256 Hash:")
    c.setFont("Courier", 10)
    c.drawString(50, height - 350, f"{cert_data['certificate_hash']}")
    
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 400, "AI Verification Summary")
    c.line(50, height - 405, width - 50, height - 405)
    
    # Color Coded Result
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 430, f"Authenticity Score: {cert_data['authenticity_score']}%")
    
    status = cert_data['ai_status']
    if status == 'Genuine':
        c.setFillColorRGB(0, 0.6, 0)
    elif status == 'Suspicious':
        c.setFillColorRGB(0.8, 0.6, 0)
    else:
        c.setFillColorRGB(0.8, 0, 0)
        
    c.drawString(50, height - 450, f"Classification: {status}")
    
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(50, 50, f"Report Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Secured by custom Blockchain Platform")
    
    c.save()
