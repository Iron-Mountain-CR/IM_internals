"""
Email
=====
Replaces the old `_Frequently_used.MAIL_Class_Prod.SendMail` family (breaking change: old ctor
took only `(mail_receiver, mail_subject)`; this one also requires `mail_sender`/`mail_password`
explicitly. Method `.send_mail(mail_text=)` -> `.send(body_text=)`).

Usage::

    from im_internals.email import SendMail
    mail = SendMail(mail_receiver="a@b.com", mail_subject="Job failed",
                     mail_sender=config["email_sender"], mail_password=config["email_password"])
    mail.send(body_text="...")
    mail.send_with_csv(text="...", filename="report.csv", folder=r"C:\reports")

Per this repo's root CLAUDE.md, `mail_sender`/`mail_password` should come from the `.cfg`'s
`[DEFAULT]` section keys at the call site, not from environment variables (see NOTE below).
"""
import os
import logging
import smtplib
import mimetypes
from typing import Tuple
from email import encoders
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

from . import logging as pl

# Standard logger kept solely for tenacity's before_sleep_log (requires stdlib Logger)
_tenacity_logger = logging.getLogger(__name__)


class SendMail:
    """
    A class to send emails with optional attachments and retry logic.

    NOTE: this docstring previously claimed credentials are loaded from MAIL_SENDER/MAIL_PASSWORD
    environment variables - that is not what the code below actually does. `mail_sender` and
    `mail_password` are plain required constructor arguments (see __init__); only `smtp_host`/
    `smtp_port` fall back to the SMTP_HOST/SMTP_PORT env vars when not passed explicitly. Corrected
    here since the previous text was actively misleading, not just incomplete.
    """

    # Retry decorator: up to 3 attempts, 5 seconds apart, on SMTP errors
    smtp_retry = retry(
        stop=stop_after_attempt(3),
        reraise=True,
        wait=wait_exponential(multiplier=1, min=3, max=10),
        retry=retry_if_exception_type(smtplib.SMTPException),
        before_sleep=before_sleep_log(_tenacity_logger, logging.WARNING)
    )

    def __init__(self, mail_receiver: str | Tuple[str], mail_subject: str, mail_sender: str, mail_password: str,
                 smtp_host: str = None, smtp_port: int = None, use_tls: bool = True):
        """
        Initialize SendMail with receiver and subject.

        :param mail_receiver: Recipient email address or list of addresses.
        :type mail_receiver: str | tuple
        :param mail_subject: Subject line for the email.
        :type mail_subject: str
        :param mail_sender: Email address of the email notification sender
        :type mail_sender: str
        :param mail_password: Password to the email sender
        :type mail_password: str
        :param smtp_host: SMTP server hostname (overrides SMTP_HOST env var).
        :type smtp_host: str or None
        :param smtp_port: SMTP server port (overrides SMTP_PORT env var).
        :type smtp_port: int or None
        :raises ValueError: If MAIL_SENDER or MAIL_PASSWORD[_B64] not set.
        :raises Exception: On other initialization errors.
        """
        assert isinstance(mail_receiver, str | Tuple), \
            "Mail receiver must either be a one email address string or tuple of multiple recipients as strings"
        assert isinstance(mail_subject, str), "Mail subject must be only string!!"
        assert isinstance(mail_sender, str) and "@" in mail_sender, "Mail sender must be an email address!"
        assert isinstance(mail_password, str), "Mail password must be provided as string!"
        assert smtp_host is None or isinstance(smtp_host, str), \
            "SMTP host can be string if you wanted to change it! Otherwise going back to gmail.smtp"
        assert smtp_port is None or isinstance(smtp_port, int), \
            "SMTP port can be only interger if you wanted to change it! Otherwise going back to 587"

        try:
            self.sender = mail_sender
            self.password = mail_password

            if not self.sender or not self.password:
                raise ValueError("Missing MAIL_SENDER or MAIL_PASSWORD!")

            # Configure SMTP server
            default_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
            default_port = int(os.getenv('SMTP_PORT', '587'))
            self.smtp_host = smtp_host or default_host
            self.smtp_port = smtp_port or default_port
            self.use_tls = use_tls

            self.receiver = mail_receiver
            self.subject = mail_subject
        except Exception as e:
            pl.error(f"Failed to initialize SendMail: {e}")
            raise

    def _prepare_message(self, body_text: str, attachment_path: str = None):
        """
        Prepare the MIME message with body and optional attachment.

        :param body_text: Plain-text body of the email.
        :type body_text: str
        :param attachment_path: Path to file to attach (optional).
        :type attachment_path: str | None
        :return: MIMEMultipart message ready to send.
        :raises FileNotFoundError: If attachment_path does not exist.
        """
        assert isinstance(body_text, str), "Body of the email can be only string!"
        assert (attachment_path is None or
                (isinstance(attachment_path, str) and os.path.exists(attachment_path))), \
            "Attachment_path must be a Path-like string or None if no file is attached"

        msg = MIMEMultipart()
        msg['From'] = self.sender
        msg['To'] = ", ".join(self.receiver) if isinstance(self.receiver, (list, tuple)) else self.receiver
        msg['Subject'] = self.subject

        msg.attach(MIMEText(body_text, 'plain'))

        if attachment_path:
            filename = os.path.basename(attachment_path)
            ctype, encoding = mimetypes.guess_type(attachment_path)
            if ctype is None or encoding:
                ctype = 'application/octet-stream'
            maintype, subtype = ctype.split('/', 1)
            with open(attachment_path, 'rb') as f:
                data = f.read()
            if maintype == 'text':
                part = MIMEText(data.decode('utf-8', errors='ignore'), _subtype=subtype)
            elif maintype == 'image':
                part = MIMEImage(data, _subtype=subtype)
            elif maintype == 'audio':
                part = MIMEAudio(data, _subtype=subtype)
            else:
                part = MIMEBase(maintype, subtype)
                part.set_payload(data)
                encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment', filename=filename)
            msg.attach(part)
            pl.progress(f"Attached file: {filename}")

        return msg

    @smtp_retry
    def send(self, body_text: str, attachment_path: str = None):
        """
        Send an email via SMTP server with optional attachment, with retries.

        :param body_text: Email body text.
        :type body_text: str
        :param attachment_path: Full path to the attachment file, if any.
        :type attachment_path: str | None
        :raises smtplib.SMTPException: On SMTP errors after retries.
        :raises Exception: On other errors during send.
        """
        assert isinstance(body_text, str), "Body of the email can be only string!"
        assert (attachment_path is None or
                (isinstance(attachment_path, str) and os.path.exists(attachment_path))), \
            "Attachment_path must be a Path-like string or None if no file is attached"

        try:
            message = self._prepare_message(body_text, attachment_path)
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls() if self.use_tls else None
                server.login(self.sender, self.password)
                server.sendmail(self.sender, self.receiver, message.as_string())
            pl.progress("Email sent successfully")
        except smtplib.SMTPException as smtp_err:
            pl.error(f"SMTP error during send: {smtp_err}")
            raise
        except Exception as e:
            pl.error(f"Unexpected error during email send: {e}")
            raise

    def send_text(self, text: str):
        """
        Send a plain-text email without attachments.

        :param text: Email body text.
        :raises Exception: On failure to send email.
        """
        assert isinstance(text, str), "Body of the email can be only string!"

        try:
            self.send(text)
        except Exception as e:
            pl.error(f"Failed to send text email: {e}")
            raise

    def send_with_csv(self, text: str, filename: str, folder: str):
        """
        Send an email with a file attachment.

        :param text: Email body text.
        :param filename: Name of the file to attach.
        :param folder: Directory where the file is located.
        :raises FileNotFoundError: If the attachment file is not found.
        :raises Exception: On failure to send email.
        """
        assert isinstance(text, str), "Body of the email can be only string!"
        assert (isinstance(filename, str) and isinstance(folder, str) and
                os.path.exists(os.path.join(folder, filename))), \
            "Attachment_path must be a Path-like string or None if no file is attached"

        try:
            path = os.path.join(folder, filename)
            self.send(text, path)
        except FileNotFoundError as fnf_err:
            pl.error(str(fnf_err))
            raise
        except Exception as e:
            pl.error(f"Failed to send email with attachment: {e}")
            raise
