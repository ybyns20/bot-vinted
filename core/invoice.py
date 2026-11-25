"""Génération de facture PDF + envoi par mail."""
import html
import time
from email.message import EmailMessage
from email.utils import formataddr
from io import BytesIO

import aiosmtplib
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

import config
from catalog import PLANS


def _eur(v: float) -> str:
    return f"{v:.2f} €".replace(".", ",")


def build_invoice_pdf(inv) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    left, right = 20 * mm, w - 20 * mm

    plan_label = PLANS.get(inv["plan"], {}).get("label", inv["plan"])
    date = time.strftime("%d/%m/%Y", time.localtime(inv["created_at"]))
    ttc = float(inv["amount"])
    ht = ttc / (1 + config.VAT_RATE / 100) if config.VAT_RATE else ttc
    tva = ttc - ht

    # En-tête
    c.setFont("Helvetica-Bold", 22)
    c.drawString(left, h - 30 * mm, "FACTURE")
    c.setFont("Helvetica", 10)
    c.drawRightString(right, h - 25 * mm, f"N° {inv['number']}")
    c.drawRightString(right, h - 30 * mm, f"Date : {date}")

    # Vendeur
    y = h - 50 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "Vendeur")
    c.setFont("Helvetica", 10)
    lines = [config.SELLER_NAME, config.SELLER_ADDRESS]
    if config.SELLER_SIRET:
        lines.append(f"SIRET : {config.SELLER_SIRET}")
    if config.SELLER_EMAIL:
        lines.append(config.SELLER_EMAIL)
    for i, line in enumerate(lines):
        c.drawString(left, y - (i + 1) * 5 * mm, line)

    # Client
    cx = w / 2 + 10 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(cx, y, "Client")
    c.setFont("Helvetica", 10)
    lines = [inv["name"]]
    if inv["company"]:
        lines.append(inv["company"])
    lines += [inv["address"], inv["city"], inv["email"]]
    for i, line in enumerate(lines):
        c.drawString(cx, y - (i + 1) * 5 * mm, line[:60])

    # Tableau
    y = h - 100 * mm
    c.setFillColorRGB(0.035, 0.69, 0.73)
    c.rect(left, y - 2 * mm, right - left, 8 * mm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left + 3 * mm, y, "Description")
    c.drawRightString(right - 50 * mm, y, "Qté")
    c.drawRightString(right - 3 * mm, y, "Montant HT")
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 10)
    y -= 10 * mm
    c.drawString(left + 3 * mm, y, f"Abonnement Vinted Monitor — offre {plan_label} ({inv['days']} jours)")
    c.drawRightString(right - 50 * mm, y, "1")
    c.drawRightString(right - 3 * mm, y, _eur(ht))
    c.line(left, y - 4 * mm, right, y - 4 * mm)

    # Totaux
    y -= 14 * mm
    for label, val, bold in (
        ("Total HT", ht, False),
        (f"TVA ({config.VAT_RATE:g} %)", tva, False),
        ("Total TTC", ttc, True),
    ):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        c.drawRightString(right - 40 * mm, y, label)
        c.drawRightString(right - 3 * mm, y, _eur(val))
        y -= 6 * mm

    # Mentions
    c.setFont("Helvetica-Oblique", 9)
    y -= 6 * mm
    if not config.VAT_RATE and config.VAT_MENTION:
        c.drawString(left, y, config.VAT_MENTION)
        y -= 5 * mm
    c.drawString(left, y, "Facture acquittée — paiement reçu.")

    c.setFont("Helvetica", 8)
    c.drawCentredString(w / 2, 15 * mm, f"{config.SELLER_NAME} — {config.SELLER_ADDRESS}")
    c.showPage()
    c.save()
    return buf.getvalue()


async def send_invoice_email(inv, pdf: bytes, from_name: str):
    plan_label = PLANS.get(inv["plan"], {}).get("label", inv["plan"])
    msg = EmailMessage()
    msg["From"] = formataddr((from_name, config.MAIL_FROM_ADDRESS))
    msg["To"] = formataddr((inv["name"], inv["email"]))
    msg["Subject"] = f"Votre facture {inv['number']} — {from_name}"

    text = (
        f"Bonjour {inv['name']},\n\n"
        f"Merci pour votre achat de l'offre {plan_label} ({inv['days']} jours).\n"
        f"Vous trouverez votre facture {inv['number']} en pièce jointe.\n\n"
        f"Montant : {_eur(float(inv['amount']))}\n\n"
        f"— {from_name}"
    )
    msg.set_content(text)
    name = html.escape(inv["name"])
    msg.add_alternative(
        f"""<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto">
<h2 style="color:#09B1BA">Merci pour votre achat 🎉</h2>
<p>Bonjour <b>{name}</b>,</p>
<p>Votre abonnement <b>{html.escape(plan_label)}</b> ({inv['days']} jours) est bien enregistré.</p>
<p>Facture : <b>{inv['number']}</b><br>Montant : <b>{_eur(float(inv['amount']))}</b></p>
<p>La facture est jointe à ce mail en PDF.</p>
<p style="color:#888">— {html.escape(from_name)}</p></div>""",
        subtype="html",
    )
    msg.add_attachment(pdf, maintype="application", subtype="pdf", filename=f"{inv['number']}.pdf")

    await aiosmtplib.send(
        msg,
        hostname=config.SMTP_HOST,
        port=config.SMTP_PORT,
        username=config.SMTP_USER or None,
        password=config.SMTP_PASS or None,
        use_tls=config.SMTP_SSL,
        start_tls=not config.SMTP_SSL,
    )
