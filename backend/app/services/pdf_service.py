"""PDF Export Service (Section 23 & Section 16).
Generates publication-quality downloadable PDF binaries using ReportLab.
Includes Journey details, Transport legs, Hotel accommodation, Day-by-day itinerary, and Itemized cost breakdown.
"""

import io
import logging
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)


class PDFService:

  def generate_itinerary_pdf_bytes(
      self, title: str, content: Dict[str, Any]
  ) -> bytes:
    """Renders the comprehensive trip itinerary to a PDF byte buffer.

    Area Guide payloads (character_summary, no days) get the area report instead.
    """
    if isinstance(content, dict) and content.get("character_summary") and not content.get("days"):
      return _generate_area_pdf_bytes(title, content)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    primary_color = colors.HexColor("#0F766E")
    secondary_color = colors.HexColor("#134E4A")
    accent_color = colors.HexColor("#D97706")
    dark_text = colors.HexColor("#1F2937")
    muted_text = colors.HexColor("#4B5563")

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=primary_color,
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=muted_text,
        spaceAfter=12,
    )
    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=secondary_color,
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "BodyDark",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=dark_text,
    )
    bold_style = ParagraphStyle(
        "BodyBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=dark_text,
    )
    tag_style = ParagraphStyle(
        "TagStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=accent_color,
    )

    story: List[Any] = []

    # Title & Header
    display_title = title or content.get("title") or "Smart Local Guide Itinerary"
    story.append(Paragraph(display_title, title_style))
    dest = content.get("destination", "")
    duration = content.get("duration_days", "")
    source = content.get("source", "")
    overview_meta = (
        f"Smart Local Guide Itinerary • Destination: {dest} • Duration:"
        f" {duration} Days"
    )
    if source:
      overview_meta = f"Origin: {source} → " + overview_meta
    story.append(Paragraph(overview_meta, subtitle_style))
    story.append(
        HRFlowable(
            width="100%",
            thickness=1.5,
            color=primary_color,
            spaceAfter=12,
            spaceBefore=0,
        )
    )

    # Trip Overview if present
    overview = content.get("trip_overview")
    if overview:
      story.append(
          Paragraph(
              f"<b>Trip Overview:</b> {overview}",
              body_style,
          )
      )
      story.append(Spacer(1, 10))

    # Transport / Journey Details
    outbound = content.get("outbound_transport") or content.get(
        "selected_outbound_transport"
    )
    inbound = content.get("return_transport") or content.get(
        "selected_return_transport"
    )

    if outbound or inbound:
      story.append(Paragraph("Transport Journey", section_heading))
      transport_data = [
          [
              Paragraph("<b>Leg</b>", bold_style),
              Paragraph("<b>Mode / Operator</b>", bold_style),
              Paragraph("<b>Route / Times</b>", bold_style),
              Paragraph("<b>Duration / Stops</b>", bold_style),
              Paragraph("<b>Price (Provider Live Quote)</b>", bold_style),
          ]
      ]

      if outbound:
        mode = outbound.get("mode", "Transport").capitalize()
        op = (
            outbound.get("operator")
            or outbound.get("airline")
            or outbound.get("train_name")
            or "Selected"
        )
        dep = outbound.get("departure_time", "N/A")
        arr = outbound.get("arrival_time", "N/A")
        orig = outbound.get("origin", source)
        dest_loc = outbound.get("destination", dest)
        dur = outbound.get("duration", f"{outbound.get('duration_minutes', '')}m")
        stops = outbound.get("stops", 0)
        stops_str = "Direct" if stops == 0 else f"{stops} stop(s)"
        price = (
            f"{outbound.get('currency', '₹')} {outbound.get('price', 'N/A'):,}"
            if isinstance(outbound.get("price"), (int, float))
            else str(outbound.get("price", "N/A"))
        )

        transport_data.append([
            Paragraph("Outbound", bold_style),
            Paragraph(f"{mode}<br/>{op}", body_style),
            Paragraph(f"{orig} → {dest_loc}<br/>{dep} – {arr}", body_style),
            Paragraph(f"{dur}<br/>{stops_str}", body_style),
            Paragraph(f"<b>{price}</b><br/>(Live Quote)", body_style),
        ])

      if inbound:
        mode = inbound.get("mode", "Transport").capitalize()
        op = (
            inbound.get("operator")
            or inbound.get("airline")
            or inbound.get("train_name")
            or "Selected"
        )
        dep = inbound.get("departure_time", "N/A")
        arr = inbound.get("arrival_time", "N/A")
        orig = inbound.get("origin", dest)
        dest_loc = inbound.get("destination", source)
        dur = inbound.get("duration", f"{inbound.get('duration_minutes', '')}m")
        stops = inbound.get("stops", 0)
        stops_str = "Direct" if stops == 0 else f"{stops} stop(s)"
        price = (
            f"{inbound.get('currency', '₹')} {inbound.get('price', 'N/A'):,}"
            if isinstance(inbound.get("price"), (int, float))
            else str(inbound.get("price", "N/A"))
        )

        transport_data.append([
            Paragraph("Return", bold_style),
            Paragraph(f"{mode}<br/>{op}", body_style),
            Paragraph(f"{orig} → {dest_loc}<br/>{dep} – {arr}", body_style),
            Paragraph(f"{dur}<br/>{stops_str}", body_style),
            Paragraph(f"<b>{price}</b><br/>(Live Quote)", body_style),
        ])

      t_table = Table(
          transport_data, colWidths=[1.1 * inch, 1.4 * inch, 2.0 * inch, 1.2 * inch, 1.6 * inch]
      )
      t_table.setStyle(
          TableStyle([
              ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0FDFA")),
              ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
              ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("TOPPADDING", (0, 0), (-1, -1), 4),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
          ])
      )
      story.append(t_table)
      story.append(Spacer(1, 10))

    # Hotel / Accommodation Details
    hotel = content.get("hotel") or content.get("selected_hotel")
    story.append(Paragraph("Accommodation", section_heading))
    if hotel:
      h_name = hotel.get("name", "Selected Hotel")
      h_price = hotel.get("nightly_price") or hotel.get("price", "N/A")
      h_total = hotel.get("total_price", "N/A")
      h_curr = hotel.get("currency", "₹")
      h_rate_text = (
          f"{h_curr} {h_price:,}/night (Total stay: {h_curr} {h_total:,})"
          if isinstance(h_price, (int, float))
          else str(h_price)
      )
      h_rating = hotel.get("rating", "N/A")
      h_address = hotel.get("address", "")
      hotel_desc = (
          f"<b>{h_name}</b> (★ {h_rating})<br/>Address:"
          f" {h_address}<br/><b>Rate:</b> {h_rate_text} <i>(Provider Live"
          " Quote)</i>"
      )
      story.append(Paragraph(hotel_desc, body_style))
    else:
      story.append(
          Paragraph(
              "Accommodation: <b>Not selected</b> (continue with local itinerary"
              " schedule).",
              body_style,
          )
      )
    story.append(Spacer(1, 10))

    # Day-by-Day Itinerary
    days = content.get("days", [])
    if days:
      story.append(Paragraph("Day-by-Day Schedule", section_heading))
      for d in days:
        day_num = d.get("day_number", 1)
        theme = d.get("theme", "")
        cost = d.get("estimated_day_cost", "")

        day_title = f"Day {day_num}: {theme}"
        if cost:
          day_title += f" • Est. Cost: {cost}"

        day_elements = [
            Spacer(1, 4),
            Paragraph(day_title, bold_style),
            HRFlowable(
                width="100%",
                thickness=0.5,
                color=colors.HexColor("#94A3B8"),
                spaceAfter=4,
                spaceBefore=2,
            ),
        ]

        # Segments: morning, lunch, afternoon, dinner, evening
        segments = [
            ("Morning", d.get("morning")),
            ("Lunch Food Stop", d.get("food_stop_lunch")),
            ("Afternoon", d.get("afternoon")),
            ("Dinner Food Stop", d.get("food_stop_dinner")),
            ("Evening", d.get("evening")),
        ]

        for seg_name, seg in segments:
          if not seg:
            continue
          if isinstance(seg, dict):
            if "cuisine" in seg:  # Food stop
              r_name = seg.get("name", "Local Spot")
              cuisine = seg.get("cuisine", "")
              rec = seg.get("recommendation", "")
              food_line = (
                  f"<b>🍴 {seg_name}: {r_name}</b> ({cuisine}) — <i>Must try:"
                  f" {rec}</i>"
              )
              day_elements.append(Paragraph(food_line, body_style))
            else:  # Itinerary segment
              s_title = seg.get("title", seg_name)
              s_time = seg.get("time_window", "")
              s_desc = seg.get("description", "")
              t_note = seg.get("transport_note", "")

              seg_line = f"<b>🕒 {seg_name} ({s_time}): {s_title}</b>"
              if s_desc:
                seg_line += f"<br/>{s_desc}"
              if t_note:
                seg_line += f"<br/><i>Transit Note: {t_note}</i>"
              day_elements.append(Paragraph(seg_line, body_style))

              # Places
              places = seg.get("places", [])
              if places:
                p_text = " • ".join(
                    [p.get("name", "") for p in places if p.get("name")]
                )
                if p_text:
                  day_elements.append(
                      Paragraph(f"• <b>Sights:</b> {p_text}", body_style)
                  )
          day_elements.append(Spacer(1, 3))

        story.append(KeepTogether(day_elements))
        story.append(Spacer(1, 6))

    # Cost Breakdown & Disclaimer
    story.append(Paragraph("Cost Breakdown Summary", section_heading))
    cost_rows = [
        [
            Paragraph("<b>Category</b>", bold_style),
            Paragraph("<b>Type</b>", bold_style),
            Paragraph("<b>Cost Estimate / Live Quote</b>", bold_style),
        ]
    ]

    if outbound and outbound.get("price"):
      cost_rows.append([
          Paragraph("Outbound Transport", body_style),
          Paragraph("Provider Live Quote", tag_style),
          Paragraph(
              f"{outbound.get('currency', '₹')} {outbound.get('price'):,}",
              body_style,
          ),
      ])
    if inbound and inbound.get("price"):
      cost_rows.append([
          Paragraph("Return Transport", body_style),
          Paragraph("Provider Live Quote", tag_style),
          Paragraph(
              f"{inbound.get('currency', '₹')} {inbound.get('price'):,}",
              body_style,
          ),
      ])
    if hotel and hotel.get("total_price"):
      cost_rows.append([
          Paragraph("Accommodation", body_style),
          Paragraph("Provider Live Quote", tag_style),
          Paragraph(
              f"{hotel.get('currency', '₹')} {hotel.get('total_price'):,}",
              body_style,
          ),
      ])
    else:
      cost_rows.append([
          Paragraph("Accommodation", body_style),
          Paragraph("Not Selected", body_style),
          Paragraph("₹0 (Not selected)", body_style),
      ])

    tot = content.get("estimated_budget_total", "As estimated in daily plan")
    cost_rows.append([
        Paragraph("<b>Total Trip Budget Estimate</b>", bold_style),
        Paragraph("AI & Provider Consolidated", body_style),
        Paragraph(f"<b>{tot}</b>", bold_style),
    ])

    cost_table = Table(
        cost_rows, colWidths=[2.5 * inch, 2.2 * inch, 2.6 * inch]
    )
    cost_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8FAFC")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    story.append(cost_table)
    story.append(Spacer(1, 10))

    disclaimer = content.get(
        "disclaimer",
        "Provider prices are live quotes, not booking guarantees. Check opening"
        " hours locally.",
    )
    story.append(
        Paragraph(
            f"<i>Notice: {disclaimer} Generated by Smart Local Guide.</i>",
            subtitle_style,
        )
    )

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def _generate_area_pdf_bytes(title: str, content: Dict[str, Any]) -> bytes:
  """Renders an Area Guide report (character, quick facts, sections, pros/cons)."""
  from xml.sax.saxutils import escape

  buffer = io.BytesIO()
  doc = SimpleDocTemplate(
      buffer, pagesize=letter, rightMargin=0.6 * inch, leftMargin=0.6 * inch,
      topMargin=0.6 * inch, bottomMargin=0.6 * inch,
  )
  styles = getSampleStyleSheet()
  primary = colors.HexColor("#0F766E")
  h1 = ParagraphStyle("AreaH1", parent=styles["Title"], textColor=primary, fontSize=20)
  h2 = ParagraphStyle("AreaH2", parent=styles["Heading2"], textColor=primary, fontSize=13, spaceBefore=10)
  body = ParagraphStyle("AreaBody", parent=styles["BodyText"], fontSize=9.5, leading=13)

  def p_(text, style=body):
    return Paragraph(escape(str(text or "")), style)

  story: List[Any] = [p_(title or content.get("area_name") or "Area Guide", h1)]
  if content.get("region"):
    story.append(p_(content["region"]))
  story.append(HRFlowable(width="100%", thickness=1.2, color=primary, spaceAfter=8))
  if content.get("character_summary"):
    story.append(p_(content["character_summary"]))

  qf = content.get("quick_facts") or {}
  if qf:
    story.append(p_("Quick Facts", h2))
    rows = [[p_(k.replace("_", " ").title()), p_(v)] for k, v in qf.items()]
    t = Table(rows, colWidths=[1.8 * inch, 5.2 * inch])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0"))]))
    story.append(t)

  sections = content.get("sections") or {}
  items = sections.values() if isinstance(sections, dict) else sections
  for sec in items:
    if not isinstance(sec, dict):
      continue
    story.append(p_(sec.get("title", "Section"), h2))
    story.append(p_(sec.get("summary", "")))
    if sec.get("highlights"):
      story.append(p_("Highlights: " + ", ".join(map(str, sec["highlights"]))))

  for label, key in (("Advantages", "advantages"), ("Limitations", "limitations"),
                     ("Who This Area May Suit", "suitability")):
    vals = content.get(key) or []
    if vals:
      story.append(p_(label, h2))
      for v in vals:
        story.append(p_("• " + str(v)))

  if content.get("source"):
    story.append(Spacer(1, 8))
    story.append(p_("Source: " + str(content["source"])))
  doc.build(story)
  return buffer.getvalue()


pdf_service = PDFService()
