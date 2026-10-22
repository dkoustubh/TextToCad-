import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

PDF_PATH = "/Users/admin/Desktop/CAD/OmniCAD_Test_Commands_Cheatsheet.pdf"

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Header on every page
        self.drawString(40, 756, "OmniCAD Text-to-CAD Evaluation Guide & Test Prompts")
        self.setFont("Helvetica", 8)
        self.drawRightString(572, 756, "Autodesk Inventor 2025 Sync Suite")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(40, 750, 572, 750)
        
        # Footer on every page
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(40, 36, 572, 36)
        
        self.drawString(40, 24, "Confidential - For Internal QA & Evaluation | OmniCAD Core Engine")
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(572, 24, page_text)
        self.restoreState()


def build_pdf():
    doc = SimpleDocTemplate(
        PDF_PATH,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=46,
        bottomMargin=46
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0F172A")
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#475569")
    )
    
    h1_style = ParagraphStyle(
        'H1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#1E293B"),
        spaceBefore=6,
        spaceAfter=4
    )

    h2_style = ParagraphStyle(
        'H2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#1D4ED8"),
        spaceBefore=4,
        spaceAfter=2
    )

    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#334155")
    )

    code_style = ParagraphStyle(
        'CodePrompt',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#0F172A")
    )

    badge_style = ParagraphStyle(
        'Badge',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#1E40AF")
    )

    label_style = ParagraphStyle(
        'Label',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#475569")
    )

    guide_step_style = ParagraphStyle(
        'GuideStep',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=colors.HexColor("#1E293B")
    )

    story = []

    # ================= PAGE 1 =================
    story.append(Paragraph("OmniCAD Verification & Testing Suite", title_style))
    story.append(Spacer(1, 2))
    story.append(Paragraph("Structured Prompts & 2-Step Conversational CAD Commands for Autodesk Inventor Sync", subtitle_style))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563EB"), spaceBefore=1, spaceAfter=8))

    info_data = [
        [
            Paragraph("<b>Target Web Workbench:</b> <font color='#2563EB'>http://192.168.11.86:9999</font><br/>"
                      "<b>CAD Workstation (Sync Target):</b> <font color='#2563EB'>192.168.11.150</font> (Autodesk Inventor 2025)<br/>"
                      "<b>Local Save Directory:</b> <code>C:\\Users\\koustubh\\Documents\\OmniCAD\\</code>", body_style),
            Paragraph("<b>Evaluation Objectives:</b><br/>"
                      "• Sub-second (&lt;350ms) initial B-Rep generation<br/>"
                      "• Real-time multi-step parametric editing<br/>"
                      "• Live 3D assembly / Part auto-load into Inventor", body_style)
        ]
    ]
    info_table = Table(info_data, colWidths=[290, 242])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 6))

    # Category 1: Structural & Mounting Plates
    story.append(Paragraph("1. Structural & Mounting Plates (Sheet Metal / Machined)", h1_style))
    cat1_parts = [
        {
            "name": "Heavy-Duty Conveyor Bracket",
            "validation": "Validates 4-corner hole coordinate array, dual center slots, and edge corner fillets.",
            "step1": "Create a mounting plate 180mm long, 100mm wide, and 12mm thick with 4 M10 corner holes inset by 15mm from each edge",
            "step2": "Add two 40mm long adjustment slots along the center and apply 5mm fillets to all 4 vertical corners",
            "expected": "Rectangular solid plate with 4 counterbore/through holes, 2 stadium slots, smooth rounded corners in Inventor."
        },
        {
            "name": "Precision Sensor L-Bracket",
            "validation": "Validates multi-face geometry attachment, vertical vs horizontal sketch planes, through-wall cuts.",
            "step1": "Create an L-bracket with a base 120mm by 60mm and 10mm thick, and an upright wall 80mm high and 10mm thick",
            "step2": "Add two 8mm mounting holes on the base plate and a 25mm diameter center bore on the upright wall",
            "expected": "90-degree bracket with 2 base mounting holes and a circular cable/sensor cut on the vertical upright."
        }
    ]

    for part in cat1_parts:
        table_data = [
            [Paragraph("<b>STEP 1<br/>Creation</b>", badge_style), Paragraph(f"<code>{part['step1']}</code>", code_style)],
            [Paragraph("<b>STEP 2<br/>Edit</b>", badge_style), Paragraph(f"<code>{part['step2']}</code>", code_style)],
            [Paragraph("<b>Expected</b>", label_style), Paragraph(part['expected'], body_style)]
        ]
        t = Table(table_data, colWidths=[80, 452])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor("#EFF6FF")),
            ('BACKGROUND', (1, 0), (1, 0), colors.HexColor("#F8FAFC")),
            ('BACKGROUND', (0, 1), (0, 1), colors.HexColor("#FEF3C7")),
            ('BACKGROUND', (1, 1), (1, 1), colors.HexColor("#FFFBEB")),
            ('BACKGROUND', (0, 2), (0, 2), colors.HexColor("#F1F5F9")),
            ('BACKGROUND', (1, 2), (1, 2), colors.HexColor("#FFFFFF")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(Paragraph(f"<b>Part: {part['name']}</b> &nbsp;<font color='#64748B'>| <i>{part['validation']}</i></font>", h2_style))
        story.append(t)
        story.append(Spacer(1, 4))

    # Category 2: Rotating Machinery (on Page 1 as well if fits)
    story.append(Paragraph("2. Rotating Machinery & Power Transmission", h1_style))
    cat2_parts = [
        {
            "name": "Stepped Motor Drive Shaft with Keyway",
            "validation": "Validates multi-stage concentric cylindrical union, axial through-bores, and blind keyway slots.",
            "step1": "Create a stepped shaft with a large section 40mm diameter and 60mm long, and a smaller section 25mm diameter and 50mm long",
            "step2": "Add a 6mm wide, 4mm deep, and 30mm long keyway along the 25mm shaft section and a 10mm center through-bore",
            "expected": "Dual-diameter drive arbor with concentric through-hole and standard DIN 6885 keyseat."
        }
    ]
    for part in cat2_parts:
        table_data = [
            [Paragraph("<b>STEP 1<br/>Creation</b>", badge_style), Paragraph(f"<code>{part['step1']}</code>", code_style)],
            [Paragraph("<b>STEP 2<br/>Edit</b>", badge_style), Paragraph(f"<code>{part['step2']}</code>", code_style)],
            [Paragraph("<b>Expected</b>", label_style), Paragraph(part['expected'], body_style)]
        ]
        t = Table(table_data, colWidths=[80, 452])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor("#EFF6FF")),
            ('BACKGROUND', (1, 0), (1, 0), colors.HexColor("#F8FAFC")),
            ('BACKGROUND', (0, 1), (0, 1), colors.HexColor("#FEF3C7")),
            ('BACKGROUND', (1, 1), (1, 1), colors.HexColor("#FFFBEB")),
            ('BACKGROUND', (0, 2), (0, 2), colors.HexColor("#F1F5F9")),
            ('BACKGROUND', (1, 2), (1, 2), colors.HexColor("#FFFFFF")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(Paragraph(f"<b>Part: {part['name']}</b> &nbsp;<font color='#64748B'>| <i>{part['validation']}</i></font>", h2_style))
        story.append(t)
        story.append(Spacer(1, 4))

    # ================= PAGE 2 =================
    story.append(PageBreak())
    
    # Continuation of Category 2
    story.append(Paragraph("2. Rotating Machinery & Power Transmission (Cont.)", h1_style))
    cat2_cont = [
        {
            "name": "Flanged Bronze Bearing Bushing",
            "validation": "Validates concentric flanges, cylindrical body subtraction (ID bore), and circular pitch (PCD) bolt holes.",
            "step1": "Create a flanged bushing with an outer body diameter of 45mm, length 60mm, a flange diameter of 70mm, flange thickness 12mm, and a 30mm center bore",
            "step2": "Add 4 mounting holes of 6mm diameter evenly spaced on a 55mm bolt circle diameter on the flange",
            "expected": "Sleeve bearing with top retaining flange and 4 polar-array mounting holes."
        }
    ]
    for part in cat2_cont:
        table_data = [
            [Paragraph("<b>STEP 1<br/>Creation</b>", badge_style), Paragraph(f"<code>{part['step1']}</code>", code_style)],
            [Paragraph("<b>STEP 2<br/>Edit</b>", badge_style), Paragraph(f"<code>{part['step2']}</code>", code_style)],
            [Paragraph("<b>Expected</b>", label_style), Paragraph(part['expected'], body_style)]
        ]
        t = Table(table_data, colWidths=[80, 452])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor("#EFF6FF")),
            ('BACKGROUND', (1, 0), (1, 0), colors.HexColor("#F8FAFC")),
            ('BACKGROUND', (0, 1), (0, 1), colors.HexColor("#FEF3C7")),
            ('BACKGROUND', (1, 1), (1, 1), colors.HexColor("#FFFBEB")),
            ('BACKGROUND', (0, 2), (0, 2), colors.HexColor("#F1F5F9")),
            ('BACKGROUND', (1, 2), (1, 2), colors.HexColor("#FFFFFF")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(Paragraph(f"<b>Part: {part['name']}</b> &nbsp;<font color='#64748B'>| <i>{part['validation']}</i></font>", h2_style))
        story.append(t)
        story.append(Spacer(1, 4))

    # Category 3: Piping & Hydraulics
    story.append(Paragraph("3. Piping, Hydraulics & Fluid Systems", h1_style))
    cat3_parts = [
        {
            "name": "High-Pressure 8-Bolt Pipe Flange",
            "validation": "Validates ANSI/DIN circular bolt circle distribution, central fluid conduit, and planar face cuts.",
            "step1": "Create an ANSI-style pipe flange with outer diameter 150mm, thickness 18mm, and a 60mm center through-hole",
            "step2": "Add 8 bolt holes of 12mm diameter evenly spaced on a 115mm bolt circle diameter",
            "expected": "Standard 8-bolt flange disk ready for pipe welding or gasket mating."
        },
        {
            "name": "Hydraulic Distribution Manifold Block",
            "validation": "Validates blind counter-bores, linear hole arrays, top edge filleting, and multi-port fluid routing.",
            "step1": "Create a solid manifold block 120mm long, 90mm wide, and 50mm high with 6mm fillets on top edges",
            "step2": "Add three 18mm diameter ports spaced 30mm apart on the top face to a depth of 35mm, and 4 corner mounting holes of 8mm through the block",
            "expected": "Hydraulic valve subplate with 3 blind fluid cavity ports and 4 through mounting bolt locations."
        }
    ]
    for part in cat3_parts:
        table_data = [
            [Paragraph("<b>STEP 1<br/>Creation</b>", badge_style), Paragraph(f"<code>{part['step1']}</code>", code_style)],
            [Paragraph("<b>STEP 2<br/>Edit</b>", badge_style), Paragraph(f"<code>{part['step2']}</code>", code_style)],
            [Paragraph("<b>Expected</b>", label_style), Paragraph(part['expected'], body_style)]
        ]
        t = Table(table_data, colWidths=[80, 452])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor("#EFF6FF")),
            ('BACKGROUND', (1, 0), (1, 0), colors.HexColor("#F8FAFC")),
            ('BACKGROUND', (0, 1), (0, 1), colors.HexColor("#FEF3C7")),
            ('BACKGROUND', (1, 1), (1, 1), colors.HexColor("#FFFBEB")),
            ('BACKGROUND', (0, 2), (0, 2), colors.HexColor("#F1F5F9")),
            ('BACKGROUND', (1, 2), (1, 2), colors.HexColor("#FFFFFF")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(Paragraph(f"<b>Part: {part['name']}</b> &nbsp;<font color='#64748B'>| <i>{part['validation']}</i></font>", h2_style))
        story.append(t)
        story.append(Spacer(1, 4))

    # ================= PAGE 3 =================
    story.append(PageBreak())

    # Category 4: Couplings & Precision Motion
    story.append(Paragraph("4. Couplings & Motion Enclosures", h1_style))
    cat4_parts = [
        {
            "name": "Rigid Split-Hub Clamp Coupling",
            "validation": "Validates thin slit cutting, perpendicular cross-axis bore drilling, and clamping mechanics.",
            "step1": "Create a cylindrical coupling sleeve with 50mm outer diameter, 80mm length, and a 20mm center shaft bore",
            "step2": "Cut a 2mm wide lengthwise slit along one side of the cylinder and add two 6mm pinch bolt holes perpendicular to the bore",
            "expected": "Cylindrical shaft coupler with tensioning relief slot and transverse clamping screw holes."
        },
        {
            "name": "Aluminum Electronic Device Enclosure Base",
            "validation": "Validates pocket shelling, corner standoffs with tapped pilot holes, and exterior wall chamfers.",
            "step1": "Create an enclosure box 140mm long, 90mm wide, and 35mm high with a wall thickness pocket hollowed out to 30mm depth",
            "step2": "Add 4 internal corner standoff bosses 10mm diameter by 25mm high with 3mm center screw holes",
            "expected": "Machined/cast electronics chassis with interior PCB mounting standoffs."
        }
    ]
    for part in cat4_parts:
        table_data = [
            [Paragraph("<b>STEP 1<br/>Creation</b>", badge_style), Paragraph(f"<code>{part['step1']}</code>", code_style)],
            [Paragraph("<b>STEP 2<br/>Edit</b>", badge_style), Paragraph(f"<code>{part['step2']}</code>", code_style)],
            [Paragraph("<b>Expected</b>", label_style), Paragraph(part['expected'], body_style)]
        ]
        t = Table(table_data, colWidths=[80, 452])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor("#EFF6FF")),
            ('BACKGROUND', (1, 0), (1, 0), colors.HexColor("#F8FAFC")),
            ('BACKGROUND', (0, 1), (0, 1), colors.HexColor("#FEF3C7")),
            ('BACKGROUND', (1, 1), (1, 1), colors.HexColor("#FFFBEB")),
            ('BACKGROUND', (0, 2), (0, 2), colors.HexColor("#F1F5F9")),
            ('BACKGROUND', (1, 2), (1, 2), colors.HexColor("#FFFFFF")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(Paragraph(f"<b>Part: {part['name']}</b> &nbsp;<font color='#64748B'>| <i>{part['validation']}</i></font>", h2_style))
        story.append(t)
        story.append(Spacer(1, 4))

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceBefore=2, spaceAfter=8))

    # Live Testing Instructions
    story.append(Paragraph("5. Step-by-Step Live Testing Procedure", h1_style))
    
    guide_data = [
        [
            Paragraph("<b>Action 1: Launch Workbench</b>", badge_style),
            Paragraph("Open Google Chrome and navigate to: <b><font color='#2563EB'>http://192.168.11.86:9999</font></b>", guide_step_style)
        ],
        [
            Paragraph("<b>Action 2: Execute Step 1</b>", badge_style),
            Paragraph("Copy any <b>STEP 1</b> prompt from above, paste it into the prompt bar at the bottom of the screen, and press <code>Enter</code>.", guide_step_style)
        ],
        [
            Paragraph("<b>Action 3: Verify Browser</b>", badge_style),
            Paragraph("Within <b>~0.30 seconds</b>, the solid model will generate via the fast-path B-Rep engine and render in the interactive Three.js 3D viewport.", guide_step_style)
        ],
        [
            Paragraph("<b>Action 4: Check Inventor</b>", badge_style),
            Paragraph("Watch the Windows Workstation monitor (<code>192.168.11.150</code>). Within 2–3 seconds, <b>Autodesk Inventor 2025 automatically pops to the foreground</b> with the newly generated <code>.ipt</code> model open and saved in <code>C:\\Users\\koustubh\\Documents\\OmniCAD\\</code>.", guide_step_style)
        ],
        [
            Paragraph("<b>Action 5: Conversational Edit</b>", badge_style),
            Paragraph("In the <i>same project conversation</i> on the web UI, paste the corresponding <b>STEP 2</b> command and hit <code>Enter</code>. Observe that the existing solid updates seamlessly without topology loss.", guide_step_style)
        ]
    ]

    guide_table = Table(guide_data, colWidths=[120, 412])
    guide_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
    ]))
    story.append(guide_table)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Generated clean 3-page PDF at: {PDF_PATH}")

if __name__ == "__main__":
    build_pdf()
