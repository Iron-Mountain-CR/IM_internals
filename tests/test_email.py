import smtplib
import pytest
from email.mime.text import MIMEText
from im_internals.email import SendMail


# Dummy SMTP class to capture calls
class DummySMTP:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.started_tls = False
        self.logged_in = False
        self.sent = []
        self.closed = False

    def starttls(self):
        self.started_tls = True

    def login(self, sender, password):
        if password == "bad":
            raise smtplib.SMTPAuthenticationError(535, b"Auth failed")
        self.logged_in = True

    def sendmail(self, sender, receiver, msg_str):
        self.sent.append((sender, receiver, msg_str))

    def quit(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.quit()


@pytest.fixture(autouse=True)
def patch_smtp_and_env(monkeypatch):
    # Redirect environment defaults
    monkeypatch.delenv('SMTP_HOST', raising=False)
    monkeypatch.delenv('SMTP_PORT', raising=False)

    # Capture created DummySMTP instances
    instances = []

    def fake_smtp(host, port):
        inst = DummySMTP(host, port)
        instances.append(inst)
        return inst

    monkeypatch.setenv('SMTP_HOST', 'smtp.test.com')
    monkeypatch.setenv('SMTP_PORT', '2525')
    monkeypatch.setattr(smtplib, 'SMTP', fake_smtp)

    # Expose instances list
    return instances


def test_init_defaults(monkeypatch):
    # Without overriding env, defaults should fallback
    # Remove any SMTP_HOST/PORT
    monkeypatch.delenv('SMTP_HOST', raising=False)
    monkeypatch.delenv('SMTP_PORT', raising=False)
    sm = SendMail('to@example.com', 'Subject', 'from@example.com', 'pwd')

    assert sm.smtp_host == 'smtp.gmail.com'
    assert sm.smtp_port == 587
    assert sm.receiver == 'to@example.com'
    assert sm.subject == 'Subject'


def test_prepare_message_without_attachment():
    sm = SendMail('to@example.com', 'Subj', 'from@example.com', 'pwd')
    body = 'Hello World'
    msg = sm._prepare_message(body)
    assert msg['From'] == 'from@example.com'
    assert msg['To'] == 'to@example.com'
    assert msg['Subject'] == 'Subj'

    # Ensure payload includes plain text part
    parts = msg.get_payload()
    assert any(isinstance(p, MIMEText) and p.get_payload() == body for p in parts)


def test_prepare_message_with_attachment(tmp_path):
    # Create a dummy text file
    file_path = tmp_path / 'test.txt'
    file_path.write_text('data')
    sm = SendMail('to@example.com', 'Subj', 'from@example.com', 'pwd')
    msg = sm._prepare_message('Body', str(file_path))
    parts = msg.get_payload()

    # Expect two parts: body and attachment
    assert len(parts) == 2
    attachment = parts[1]
    assert attachment.get_filename() == 'test.txt'


def test_send_success(patch_smtp_and_env):
    instances = patch_smtp_and_env
    sm = SendMail('to@example.com', 'S', 'from@example.com', 'pwd')
    sm.send('Greetings', None)

    # There should be one SMTP instance used
    assert len(instances) == 1
    smtp = instances[0]
    assert smtp.host == 'smtp.test.com'
    assert smtp.port == 2525
    assert smtp.started_tls is True
    assert smtp.logged_in is True
    assert smtp.sent[0][0] == 'from@example.com'
    assert smtp.sent[0][1] == 'to@example.com'


def test_send_auth_failure(patch_smtp_and_env):
    instances = patch_smtp_and_env

    # Use wrong password to trigger SMTPAuthenticationError
    sm = SendMail('to@example.com', 'S', 'from@example.com', 'bad')
    with pytest.raises(smtplib.SMTPAuthenticationError):
        sm.send('Hi')

    # Ensure login attempt was made
    assert instances[0].closed is True


def test_send_text_calls_send(monkeypatch):
    sent = []

    class SubSM(SendMail):
        def send(self, body_text, attachment_path=None):
            sent.append((body_text, attachment_path))

    s = SubSM('a@b.com', 'Subj', 'from@c.com', 'pwd')
    s.send_text('Plain text')
    assert sent == [('Plain text', None)]


def test_send_with_csv_success(tmp_path, monkeypatch):
    sent = []
    # Create CSV file
    csv = tmp_path / 'data.csv'
    csv.write_text('col1,col2')

    class SubSM(SendMail):
        def send(self, text, attachment_path=None):
            sent.append((text, attachment_path))

    s = SubSM('r@e.com', 'S', 'from@x.com', 'pwd')
    s.send_with_csv('Body', 'data.csv', str(tmp_path))
    # Attachment path should be full path
    assert sent == [('Body', str(csv))]


def test_send_with_csv_missing_file():
    s = SendMail('a@b.com', 'S', 'from@c.com', 'pwd')
    with pytest.raises(AssertionError):
        s.send_with_csv('Text', 'nofile.csv', '/does/not/exist')
