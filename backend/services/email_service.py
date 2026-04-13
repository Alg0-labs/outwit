import logging
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

import httpx
from config import settings

logger = logging.getLogger(__name__)

# ── HTML template ─────────────────────────────────────────────────────────────

def _otp_html(username: str, otp: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Your Agent Arena verification code</title>
</head>
<body style="margin:0;padding:0;background:#0A0E1A;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0A0E1A;padding:40px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="480" cellpadding="0" cellspacing="0"
               style="max-width:480px;width:100%;background:#111827;border-radius:16px;border:1px solid #1e293b;overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="background:#0f172a;padding:24px 32px;border-bottom:1px solid #1e293b;">
              <p style="margin:0;font-size:22px;font-weight:900;color:#ffffff;letter-spacing:-0.5px;">
                &#9876;&#65039; Agent Arena
              </p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 32px 28px;">
              <h1 style="margin:0 0 8px;font-size:20px;font-weight:800;color:#ffffff;">
                Verify your account
              </h1>
              <p style="margin:0 0 28px;font-size:15px;color:#94a3b8;line-height:1.6;">
                Hey <strong style="color:#e2e8f0;">{username}</strong>, enter the code below
                to complete your signup. It expires in <strong style="color:#e2e8f0;">10&nbsp;minutes</strong>.
              </p>

              <!-- OTP box -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center"
                      style="background:#1e2d4a;border:1px solid rgba(59,130,246,0.25);
                             border-radius:12px;padding:28px 24px;">
                    <p style="margin:0 0 10px;font-size:11px;font-weight:600;
                               letter-spacing:2px;text-transform:uppercase;color:#64748b;">
                      Your verification code
                    </p>
                    <p style="margin:0;font-size:44px;font-weight:900;
                               letter-spacing:12px;color:#3b82f6;
                               font-family:'Courier New',Courier,monospace;">
                      {otp}
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:0 32px 32px;">
              <p style="margin:0;font-size:12px;color:#475569;line-height:1.7;">
                If you didn't create an Agent Arena account, you can safely ignore this email.<br>
                This code is valid for one use only.
              </p>
            </td>
          </tr>

          <!-- Legal strip -->
          <tr>
            <td style="background:#0f172a;padding:16px 32px;border-top:1px solid #1e293b;">
              <p style="margin:0;font-size:11px;color:#334155;text-align:center;">
                Agent Arena · INTEL tokens have no real-world monetary value.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _otp_plain(username: str, otp: str) -> str:
    return (
        f"Agent Arena — Verify your account\n\n"
        f"Hey {username},\n\n"
        f"Your verification code is: {otp}\n\n"
        f"It expires in 10 minutes.\n\n"
        f"If you didn't create an account, ignore this email.\n\n"
        f"— Agent Arena"
    )


# ── Public API ────────────────────────────────────────────────────────────────

async def send_otp_email(to_email: str, username: str, otp: str) -> None:
    subject = "Your Agent Arena verification code"
    html = _otp_html(username, otp)
    plain = _otp_plain(username, otp)

    # Try Resend first; fall through to Gmail SMTP if it fails (e.g. unverified domain)
    if settings.resend_api_key and settings.resend_api_key not in ("", "your_resend_key_here"):
        sent = await _send_via_resend(to_email, subject, html)
        if sent:
            return

    if settings.smtp_user and settings.smtp_pass:
        await _send_via_smtp(to_email, subject, html, plain)
        return

    # Dev fallback — print to terminal
    logger.info("=" * 60)
    logger.info(f"[DEV] OTP for {username} <{to_email}>")
    logger.info(f"[DEV] Code: {otp}")
    logger.info("[DEV] Set RESEND_API_KEY or SMTP_USER+SMTP_PASS in .env to send real emails")
    logger.info("=" * 60)


# ── Resend ────────────────────────────────────────────────────────────────────

async def _send_via_resend(to: str, subject: str, html: str) -> bool:
    """Returns True if Resend accepted the email, False otherwise (e.g. unverified domain)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": f"Agent Arena <{settings.email_from}>",
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
            )
            if resp.status_code not in (200, 201):
                logger.warning(
                    f"Resend rejected email ({resp.status_code}): {resp.text} — "
                    "falling back to Gmail SMTP"
                )
                return False
            logger.info(f"OTP email sent via Resend to {to}")
            return True
    except Exception as e:
        logger.warning(f"Resend send failed: {e} — falling back to Gmail SMTP")
        return False


# ── Gmail SMTP (aiosmtplib) ───────────────────────────────────────────────────

async def _send_via_smtp(to: str, subject: str, html: str, plain: str) -> None:
    """
    Sends via Gmail SMTP with STARTTLS.
    Using both plain-text and HTML parts keeps spam filters happy.
    DKIM/SPF are handled by Gmail's outbound servers automatically.
    """
    import ssl
    import aiosmtplib

    from_addr = settings.smtp_user
    display_from = f"Agent Arena <{from_addr}>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = display_from
    msg["To"] = to
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain="agentarena.app")
    msg["X-Mailer"] = "Agent-Arena/1.0"
    msg["X-Entity-Ref-ID"] = str(uuid.uuid4())

    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    # Build SSL context — try certifi first (handles macOS missing CA chain),
    # fall back to system context, then to no-verify as last resort.
    ssl_ctx: Optional[ssl.SSLContext] = None
    try:
        import certifi
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ssl_ctx = ssl.create_default_context()

    send_kwargs = dict(
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=from_addr,
        password=settings.smtp_pass,
        start_tls=True,
        tls_context=ssl_ctx,
    )

    try:
        await aiosmtplib.send(msg, **send_kwargs)
        logger.info(f"OTP email sent via Gmail SMTP to {to}")
        return
    except Exception as first_err:
        logger.warning(f"Gmail SMTP with cert validation failed ({first_err}), retrying without cert check")

    # Retry without certificate validation (macOS dev environment)
    no_verify_ctx = ssl.create_default_context()
    no_verify_ctx.check_hostname = False
    no_verify_ctx.verify_mode = ssl.CERT_NONE
    send_kwargs["tls_context"] = no_verify_ctx

    try:
        await aiosmtplib.send(msg, **send_kwargs)
        logger.info(f"OTP email sent via Gmail SMTP (no-verify) to {to}")
    except Exception as e:
        logger.error(f"Gmail SMTP send failed: {e}")
