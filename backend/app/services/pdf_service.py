"""PDF Export Service (Section 23 & Section 16).
Generates publication-quality downloadable PDF binaries using ReportLab.
Includes Journey details, Transport legs, Hotel accommodation, Day-by-day itinerary, and Itemized cost breakdown.
"""

import io
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus
from xml.sax.saxutils import escape as _xml_escape

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
    if isinstance(content, dict) and content.get("mode") == "short":
      return _generate_short_itinerary_pdf_bytes(title, content)
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
    display_title = title or content.get("title") or "AI Powered Travel Companion Itinerary"
    story.append(Paragraph(display_title, title_style))
    dest = content.get("destination", "")
    duration = content.get("duration_days", "")
    source = content.get("source", "")
    overview_meta = (
        f"AI Powered Travel Companion Itinerary • Destination: {dest} • Duration:"
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
            f"<i>Notice: {disclaimer} Generated by AI Powered Travel Companion.</i>",
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


# ---------------------------------------------------------------------------
# Short (travel-day) itinerary: the same plan on 1-2 pages, with map links.
# ---------------------------------------------------------------------------

def _esc(value: Any) -> str:
  return _xml_escape(str(value)) if value not in (None, "") else ""


def _map_url_for(item: Dict[str, Any]) -> Optional[str]:
  """Directions link from the plan if present, otherwise a plain Google Maps search for the place."""
  d = item.get("directions") or {}
  if isinstance(d, dict) and d.get("maps_url"):
    return str(d["maps_url"])
  name = item.get("name")
  if not name:
    return None
  query = f"{name} {item.get('address') or ''}".strip()
  return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(query)


def _map_link(url: Optional[str]) -> str:
  if not url:
    return ""
  return f' <link href="{_xml_escape(url, {chr(34): "&quot;"})}" color="#0B5FA5"><u>Map</u></link>'


def short_itinerary_rows(day: Dict[str, Any]) -> List[Dict[str, Any]]:
  """Flattens one day into [{'when', 'kind', 'name', 'detail', 'url'}] in visiting order.

  Pure data (no PDF objects) so the same shape can be unit-tested.
  """
  rows: List[Dict[str, Any]] = []

  def segment(when: str, seg: Optional[Dict[str, Any]]) -> None:
    if not isinstance(seg, dict):
      return
    places = [p for p in (seg.get("places") or []) if isinstance(p, dict) and p.get("name")]
    if places:
      for p in places:
        bits = [b for b in (p.get("duration"), p.get("admission")) if b]
        rows.append({"when": when, "kind": "visit", "name": p["name"], "detail": " | ".join(bits), "url": _map_url_for(p)})
    elif seg.get("title"):
      rows.append({"when": when, "kind": "plan", "name": seg["title"], "detail": seg.get("time_window") or "", "url": None})

  def meal(when: str, food: Optional[Dict[str, Any]]) -> None:
    if isinstance(food, dict) and food.get("name"):
      detail = " | ".join(b for b in (food.get("cuisine"), food.get("recommendation") and f"Try: {food['recommendation']}") if b)
      rows.append({"when": when, "kind": "meal", "name": food["name"], "detail": detail, "url": _map_url_for(food)})

  segment("Morning", day.get("morning"))
  meal("Lunch", day.get("food_stop_lunch"))
  segment("Afternoon", day.get("afternoon"))
  meal("Dinner", day.get("food_stop_dinner"))
  segment("Evening", day.get("evening"))
  return rows


def _short_transport_line(label: str, leg: Optional[Dict[str, Any]]) -> Optional[str]:
  if not isinstance(leg, dict):
    return None
  op = leg.get("operator") or leg.get("airline") or "Selected"
  num = f" {leg['number']}" if leg.get("number") else ""
  dep, arr = leg.get("departure_time", ""), leg.get("arrival_time", "")
  price = leg.get("price")
  price_txt = f" | Rs {int(price):,} per person (live quote)" if isinstance(price, (int, float)) and price else ""
  return f"<b>{label}:</b> {_esc(op)}{_esc(num)} | {_esc(dep)} to {_esc(arr)}{price_txt}"


def _generate_short_itinerary_pdf_bytes(title: str, content: Dict[str, Any]) -> bytes:
  buffer = io.BytesIO()
  doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.5 * inch, leftMargin=0.5 * inch,
                          topMargin=0.5 * inch, bottomMargin=0.5 * inch)
  styles = getSampleStyleSheet()
  primary = colors.HexColor("#0F766E")
  dark = colors.HexColor("#1F2937")
  muted = colors.HexColor("#4B5563")
  title_style = ParagraphStyle("ShortTitle", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=primary, spaceAfter=2)
  meta_style = ParagraphStyle("ShortMeta", parent=styles["Normal"], fontName="Helvetica", fontSize=12, leading=16, textColor=muted, spaceAfter=8)
  day_style = ParagraphStyle("ShortDay", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=colors.HexColor("#134E4A"), spaceBefore=12, spaceAfter=4)
  body = ParagraphStyle("ShortBody", parent=styles["Normal"], fontName="Helvetica", fontSize=12, leading=16, textColor=dark)
  small = ParagraphStyle("ShortSmall", parent=body, fontSize=10, leading=13, textColor=muted)

  story: List[Any] = []
  story.append(Paragraph(_esc(title or content.get("title") or "Quick Trip Plan"), title_style))
  route = " to ".join(x for x in (content.get("source"), content.get("destination")) if x)
  dates = " - ".join(x for x in (content.get("departure_date"), content.get("return_date")) if x)
  meta = " | ".join(x for x in (route, dates, f"{content.get('duration_days')} days" if content.get("duration_days") else "") if x)
  story.append(Paragraph("Quick Version | " + _esc(meta), meta_style))
  story.append(HRFlowable(width="100%", thickness=1.2, color=primary, spaceAfter=6))

  lines = [
      _short_transport_line("Outbound", content.get("outbound_transport") or content.get("selected_outbound_transport")),
      _short_transport_line("Return", content.get("return_transport") or content.get("selected_return_transport")),
  ]
  hotels = content.get("hotels") or [content.get("hotel") or content.get("selected_hotel")]
  for hotel in hotels:
    if isinstance(hotel, dict) and hotel.get("name"):
      addr = f" | {_esc(hotel['address'])}" if hotel.get("address") else ""
      where = f" in {_esc(hotel['area'])}" if hotel.get("area") else ""
      lines.append(f"<b>Stay{where}:</b> {_esc(hotel['name'])}{addr}{_map_link(_map_url_for(hotel))}")
  for ln in lines:
    if ln:
      story.append(Paragraph(ln, body))
      story.append(Spacer(1, 4))

  for d in content.get("days") or []:
    area = f" - {_esc(d['area'])}" if d.get("area") else ""
    head = f"Day {_esc(d.get('day_number', ''))}{area}: {_esc(d.get('theme', ''))}"
    if d.get("estimated_day_cost"):
      head += f"  <font size=11 color='#4B5563'>(est. {_esc(d['estimated_day_cost'])})</font>"
    rows = short_itinerary_rows(d)
    table_rows = [[Paragraph(f"<b>{_esc(r['when'])}</b>", body),
                   Paragraph(f"<b>{_esc(r['name'])}</b>{_map_link(r['url'])}" + (f"<br/><font size=11 color='#4B5563'>{_esc(r['detail'])}</font>" if r["detail"] else ""), body)]
                  for r in rows]
    block: List[Any] = [Paragraph(head, day_style)]
    if table_rows:
      t = Table(table_rows, colWidths=[1.05 * inch, 6.35 * inch])
      t.setStyle(TableStyle([
          ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
          ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
      ]))
      block.append(t)
    story.append(KeepTogether(block))

  total = content.get("estimated_budget_total")
  if total:
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"<b>Estimated total trip budget:</b> {_esc(total)}", body))
  story.append(Spacer(1, 6))
  story.append(Paragraph("Quick version of your full itinerary. Map links open Google Maps. Prices are quotes or estimates and can change; "
                         "check opening hours locally. Generated by AI Powered Travel Companion.", small))
  doc.build(story)
  buffer.seek(0)
  return buffer.getvalue()
