import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

def _send_via_sendgrid(sender, recipient, subject, body_text, attachment_bytes, attachment_name):
    api_key = os.getenv("SENDGRID_API_KEY")
    if not api_key:
        return False, "SENDGRID_API_KEY not set"
    try:
        import requests, base64
    except Exception as e:
        return False, f"requests/base64 not available: {e}"

    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {"Authorization": f"Bearer {api_key}"}
    data = {
      "personalizations": [{"to": [{"email": recipient}], "subject": subject}],
      "from": {"email": sender},
      "content": [{"type":"text/plain","value": body_text}],
      "attachments": [{
          "content": base64.b64encode(attachment_bytes).decode("utf-8"),
          "type": "text/csv",
          "filename": attachment_name,
          "disposition": "attachment"
      }]
    }
    resp = requests.post(url, json=data, headers=headers)
    if resp.status_code in (200, 202):
        return True, "Sent"
    return False, f"SendGrid error {resp.status_code}: {resp.text}"

def _send_via_smtp(sender, recipient, subject, body_text, attachment_bytes, attachment_name):
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", sender)
    password = os.getenv("SMTP_PASS")
    if not password:
        return False, "SMTP_PASS not set"

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain"))

    part = MIMEBase("application", "octet-stream")
    part.set_payload(attachment_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={attachment_name}")
    msg.attach(part)

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(sender, recipient, msg.as_string())
    return True, "Sent"

def send_email_with_attachment(sender, recipient, subject, body_text, attachment_bytes, attachment_name):
    if os.getenv("SENDGRID_API_KEY"):
        return _send_via_sendgrid(sender, recipient, subject, body_text, attachment_bytes, attachment_name)
    return _send_via_smtp(sender, recipient, subject, body_text, attachment_name)
